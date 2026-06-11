# 05 - Runtime write contract

Generated core state is controlled by scripts and hooks under locks.

## Do not edit by hand

```text
orchestrator-state/compiled/orchestrator-input.json
orchestrator-state/compiled/orchestrator-input.lock.json
orchestrator-state/compiled/source-map.json
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/runtime-state.json
orchestrator-state/tasks/task-dag.json
orchestrator-state/tasks/ledger.jsonl
orchestrator-state/memory/execution-graph.json
```

Use scripts instead:

```bash
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/next-slice.sh <TASK_ID>
./scripts/transition-task.sh <TASK_ID> --actor <actor> --to <status>
```

## Blueprint writes

`inputs/BLUEPRINT.md` is editable only outside an active slice or inside an explicit blueprint-maintenance task. Recompile and bootstrap afterward.

## Claude adapter writes

`.claude/agents`, `.claude/settings.json`, `.claude/rules`, `.claude/schemas`, `.claude/skills` and hooks are orchestrator configuration. Do not change them during app slice execution unless the active task is orchestrator maintenance.

## Trailer vocabulary

The authoritative trailer contract is `.claude/orchestrator-contract.json -> trailer_schema.roles`. The state-machine file decides legal transitions.

## POSIX lock contract

Runtime mutation uses adjacent `.lock` files with Python `fcntl.flock`, which is available on Ubuntu/Linux and macOS/Darwin. These are advisory Unix locks: all orchestrator writers must use the provided Python entrypoints instead of shell redirection or manual edits.

Critical lock surfaces:

```text
orchestrator-state/tasks/registry.json.lock
orchestrator-state/tasks/runtime-state.json.lock
orchestrator-state/tasks/handoffs/<TASK_ID>.md.lock
```

The DAG also emits `task.locks` and `task.parallel` so agents can see the write/conflict surfaces before editing.


## Agent write map authority

`.claude/orchestrator-contract.json -> agent_write_contract` is the machine-readable role write map. Agent prompts may explain the role, but write permission questions resolve through that JSON contract plus the active `write_set`.

- Mutating roles write product/evidence only inside the active `TASK_ID` scope.
- Info-only roles write findings, handoff notes or their own memory only.
- Only main-orchestrator or the operator promotes or waives follow-ups. Workers may report candidates. Proposal requires repair triage; small/in-scope fixes stay in the current slice. Promotion creates a patch request for `inputs/BLUEPRINT.md`; compile/bootstrap regenerates registry and DAG. Do not mutate generated registry/DAG files directly for follow-ups.
- Core state writes are script/hook operations under locks.

## Scope mismatch and durable lifecycle event

Generated runtime files are changed only by compiler, bootstrap, claim, hook and lifecycle scripts under lock. If a role sees `TASK_ID`, task pack, registry status or handoff path drift, it must stop and report the mismatch; do not patch `registry.json`, `runtime-state.json`, `task-dag.json` or task-packs by hand.

The close path records durable lifecycle evidence so the DAG can be rehydrated after PR flow or session reset. Closer may stage reports, lifecycle events and Git workflow artifacts only after `verify-slice` has accepted real evidence.

## Linked worktree root-split contract

In branch-per-task workflows, the linked worktree is not allowed to become a second scheduler brain. The canonical scheduler root is the repository root returned by `scripts/ensure-task-worktree.sh --print-root`.

Allowed in a task worktree:

```text
product files inside the active write_set
tracked compatibility blueprint memory JSON mirrors already committed in older projects:
  orchestrator-state/memory/blueprint-blocks.json
  orchestrator-state/memory/blueprint-lossless.json
  orchestrator-state/memory/blueprint-manifest.json
  orchestrator-state/memory/blueprint-sections.json
  orchestrator-state/memory/execution-graph.json
late commit mirrors copied by git-add-slice during closer
```

Forbidden during an active slice:

```text
orchestrator-state/compiled/**
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/runtime-state.json
orchestrator-state/tasks/task-dag.json
manual symlinks for individual generated state files
manual edits to task-packs
```

Subagents must use the exact handoff/evidence paths printed by `SubagentStart`. If those paths are absolute canonical paths, keep them absolute. If split-brain is detected, stop and run `scripts/repair-worktree-state.sh --apply <WORKTREE>` from the canonical root before resuming.
