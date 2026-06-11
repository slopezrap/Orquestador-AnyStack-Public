# 06 - Subagents and trailers

Claude Code project subagents live in `.claude/agents/`. The frontmatter `name` is the role name seen by hooks.

## Role split

Mutating lifecycle roles:

```text
developer
debugger
tester
slice-verifier
deployer
closer
```

Info-only roles:

```text
planner
main-orchestrator
official-docs-researcher
blueprint-reviewer
task-planner
document-analyzer
project-architect
validator
screen-journey-reviewer
```

Info-only roles must not emit `NEXT_STATUS`. They may write prose findings or a non-binding `RECOMMENDATION`, but `SubagentStop` treats lifecycle mutation as exclusive to mutating roles.

## Trailer format

Use exactly one final trailer block:

```text
CLAUDE_TRAILER:
AGENT: <agent-name>
TASK_ID: <TASK_ID>
OUTCOME: <allowed outcome>
[mutating roles only] NEXT_STATUS: <allowed status>
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>
```

Required keys and allowed values are in `.claude/orchestrator-contract.json`. The state machine is in `orchestrator/rules/state-machine.yaml`.

## Common failures

- Missing `CLAUDE_TRAILER` means the hook may block the subagent from stopping.
- `tester` cannot emit `done`; it emits `ready_for_close`.
- `slice-verifier` cannot commit; it emits `verified_pending_close`.
- `validator` cannot move a task; it is metadata only.
- `closer` cannot close under `pr-flow` without merge/main-sync evidence.


## Durable artifact rule

Mutating roles must not rely on chat-only state. Before emitting a lifecycle-changing trailer they must append to `orchestrator-state/tasks/handoffs/<TASK_ID>.md` and write or reference evidence under `orchestrator-state/tasks/evidence/<TASK_ID>/`. `closer` must additionally write `orchestrator-state/tasks/reports/<TASK_ID>.md`. The hook rejects trailers whose artifact paths are missing or outside the expected task directories.


## Claude Code frontmatter tool reality

When a project subagent declares `tools`, that list is restrictive. `main-orchestrator` must include `Agent` and `Skill` because it delegates to subagents and invokes skills. Mutating implementation agents intentionally do not include `Agent` so they cannot spawn uncontrolled subtrees. `official-docs-researcher` must include `WebFetch` and `WebSearch` and should use official documentation first.

## Handoff locking

Handoff ledgers are append-only but still require locking: multi-line `CLAUDE_TRAILER` sections are appended through runtime helpers under `orchestrator-state/tasks/handoffs/<TASK_ID>.md.lock`. Do not append handoff sections with shell redirection from an agent; use the runtime handoff helper or let `SubagentStop` append the accepted section.

A trailer must be scoped by both `AGENT` and `TASK_ID`. The hook rejects duplicate keys, role mismatches, task mismatches and replay of already accepted handoff trailers.

The hook-accepted markdown block must preserve every valid trailer key declared by `.claude/orchestrator-contract.json`; it is not allowed to drop newly required keys such as `CONTEXT_READY`, `NEEDS_OFFICIAL_DOCS`, `REAL_DATA_OR_USER_PROVIDED` or future global trailer fields. The structured handoff YAML is the compatibility source if an older markdown block omitted a key that was present in the accepted trailer.

## Runtime role contract

The active prompts in `.claude/agents/` are blueprint-first agent contracts. Their authority comes from `.claude/orchestrator-contract.json`, `orchestrator/rules/state-machine.yaml`, task-packs, memory YAML and the trailer schema.

Important preserved semantics:

- `main-orchestrator` owns delegation and recovery after `/clear`.
- `planner`/`task-planner` prepare context and analyze DAG/write/conflict/parallel surfaces, but do not implement or mutate lifecycle.
- `developer`, `debugger`, `tester`, `slice-verifier`, `deployer` and `closer` are the only lifecycle-mutating agents.
- `validator`, `screen-journey-reviewer`, `official-docs-researcher`, `document-analyzer`, `project-architect`, `blueprint-reviewer` and planners are info-only.
- Each agent reads/writes manual memory only under `orchestrator-state/agent-memory/<agent>/MEMORY.yaml`.
- Mutating roles append handoff/evidence first, then emit a final trailer. The `SubagentStop` hook validates the trailer, artifacts, state transition and pr-flow guardrails before mutating registry.

## Active role semantics and contract priority

Role authority lives in `.claude/orchestrator-contract.json` and transition legality lives in `orchestrator/rules/state-machine.yaml`. Agent prompts explain how to work; they do not expand the allowed trailer vocabulary. If a prompt example conflicts with the contract, the contract wins.

Only `main-orchestrator` may use the Claude Code `Agent(...)` tool allowlist to coordinate workers from the main thread. Worker subagents do not spawn subagents. Every mutating worker emits one final `CLAUDE_TRAILER`; `SubagentStop` validates it and performs any lifecycle mutation.

