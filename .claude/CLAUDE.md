# orchestrator-AnyStack Claude Code memory

Blueprint-first explicit-DAG orchestrator. Human input lives in `inputs/`; runtime authority comes from `inputs/BLUEPRINT.md`, compiled artifacts, the task DAG, hooks, trailers, YAML memory and pr-flow closure.

## Authority chain

```text
inputs/BLUEPRINT.md yaml orchestrator blocks
  -> orchestrator-state/compiled/orchestrator-input.json
  -> orchestrator-state/tasks/registry.json
  -> orchestrator-state/tasks/task-dag.json
  -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
  -> handoff/evidence/report/ledger artifacts
```

Rules:

- Root split is normal: per-task worktrees may have empty local `orchestrator-state/`; scheduler truth lives at the canonical root resolved by `scripts/ensure-task-worktree.sh --print-root` or `scripts/resolve-orchestrator-root.sh`.
- The compiler reads fenced `yaml orchestrator` blocks as machine semantics. Prose is required human context and is preserved through lossless source references.
- Generated artifacts are not hand-edited: compiled input, lock/source map, registry, DAG, task packs and runtime state.
- If scope changes, edit `inputs/BLUEPRINT.md`, then run compile, bootstrap and checks.
- Descriptions are scope: every arc42 item, building block, logic item, data/config/verification/ADR/risk/glossary/external ref and registry slice must carry a detailed production-grade `description`.

Core checks:

```bash
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-task-dag.sh
./scripts/check-parallel-locks.sh
./scripts/check-task-descriptions.sh
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-gold-blueprint.sh examples/gold/BLUEPRINT.md
./scripts/check-orchestrator-gaps.sh
./scripts/check-claude-adapter.sh
./scripts/check-skills-runtime.sh
```


## Per-slice chain — max 70 spawns, parallelism first

```text
/next-slice <TASK_ID>
  └─ planner [blocking, context + NEEDS_OFFICIAL_DOCS]
      └─ developer ∥ official-docs-researcher? [same assistant message when docs are needed]
          └─ validator ∥ tester [mandatory parallel pair]
              ├─ pass  -> slice-maintain -> verify-slice automático -> verified_pending_close
              └─ fail  -> debugger -> validator ∥ tester (max 4 cycles, then blocked)
```

`planner` writes/enriches the task handoff; `developer` and optional `official-docs-researcher` run with that pack; `validator` and `tester` read that same pack in parallel; `debugger` loops only for in-scope defects; `closer` runs manually only after `verified_pending_close`.

Follow-up triage is mandatory before `/register-followup`: if a finding fits the active `write_set`, touches only a few files and needs no new blueprint IDs/dependencies/real-data/human decision, solve it inside the active slice via developer/debugger/retest.

## State machine

The lifecycle contract lives in `orchestrator/rules/state-machine.yaml` and `.claude/orchestrator-contract.json`.

```text
todo -> ready -> claimed -> in_progress -> validator_tester_pending -> ready_for_close -> verified_pending_close -> done
validator_tester_pending -> needs_debug
needs_debug -> validator_tester_pending
* -> blocked when the role contract permits it
```

Mutating roles:

```text
developer/debugger -> validator_tester_pending
tester             -> ready_for_close | needs_debug | blocked
slice-verifier     -> verified_pending_close | needs_debug | blocked
deployer           -> ready_for_close | blocked
closer             -> done | blocked
```

Info-only roles never mutate `task.status`:

```text
main-orchestrator planner task-planner blueprint-reviewer document-analyzer
project-architect official-docs-researcher validator screen-journey-reviewer
```

`closer` is the only role that may set `done`.

## Claude Code adapter contract

- Project subagents live in `.claude/agents/*.md` and use YAML frontmatter.
- The frontmatter `name` is the operational identity used by hooks and `CLAUDE_TRAILER.AGENT`.
- If an agent declares `tools`, that list is restrictive.
- `main-orchestrator` must include `Agent` and `Skill`; it delegates and uses skills.
- Mutating slice agents intentionally do not include `Agent`; they implement one slice and do not spawn uncontrolled subtrees.
- `official-docs-researcher` must include `WebFetch` and `WebSearch`, and should use official documentation first.
- Skills live in `.claude/skills/<skill-name>/SKILL.md`; all project skills keep `disable-model-invocation: false` so the Skill tool can invoke them from main and subagents; scripts and hooks still enforce lifecycle safety.


### Agent model allocation

Agent frontmatter must use explicit role-optimized aliases; do not use `model: inherit` for project agents.

```text
fable[1m]: developer
opus[1m]: main-orchestrator
opus: planner, blueprint-reviewer, project-architect, validator, debugger, slice-verifier
sonnet: tester, deployer, closer, task-planner, document-analyzer, official-docs-researcher, screen-journey-reviewer
```

`check-claude-adapter` and `check-unix-agent-runtime` enforce this matrix so model drift is caught before execution.

- Project memory starts at root `CLAUDE.md`, which imports this file.

## DAG parallelism and POSIX locks

The compiled DAG carries explicit parallel metadata:

```text
task-dag.parallelism.max_parallel_slices
task-dag.parallel_groups[]
task.locks.write_set
task.locks.conflict_groups
task.locks.lock_files
task.parallel.safe_group
```

`/next-wave` returns only a non-conflicting parallel subset. `claim_task` rechecks dependencies and active `write_set`/`conflict_group` blockers under the registry lock before reserving a task. Locks are advisory POSIX `fcntl.flock` files and are intended for Linux, macOS and WSL2 Unix workspaces. Do not run parallel slices manually unless `check-parallel-locks` is green.

## SubagentStart/SubagentStop

`SubagentStart` injects operational context:

```text
TASK_ID title description dependency_rationale depends_on_rationale dependency_edges
resolved_dependencies resolved_specs write_set conflict_group verification_refs trailer contract
```

`SubagentStop` parses `CLAUDE_TRAILER`, validates role keys, enforces `state-machine.yaml` and mutates `registry.json` only for legal lifecycle transitions.

Trailer invariants:

```text
CLAUDE_TRAILER:
AGENT: <agent-name>
TASK_ID: <active-task-id>
OUTCOME: <role outcome>
NEXT_STATUS: <only for lifecycle-mutating roles>
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/...
```

Info-only roles must not emit `NEXT_STATUS`.

## Orchestrator-state YAML memory

Runtime memory is outside `.claude/` and is generated/updated under lock:

```text
orchestrator-state/memory/PROGRESS.yaml
orchestrator-state/memory/project-context.yaml
orchestrator-state/memory/source-manifest.yaml
orchestrator-state/memory/project-brief.yaml|md
orchestrator-state/memory/architecture-contract.yaml|md
orchestrator-state/memory/stack-profile.yaml
orchestrator-state/tasks/task-index.yaml
orchestrator-state/tasks/slices/<TASK_ID>.yaml
orchestrator-state/tasks/handoffs/<TASK_ID>.yaml|md
orchestrator-state/agent-memory/<agent>/MEMORY.yaml|md
```

Agents read these files after `/clear`; hooks write counters, trailer summaries, handoff YAML, PROGRESS and lifecycle ledgers. Agents may update only their own `MEMORY.yaml` with compact stable lessons. Agent memory is compacted automatically before `/next-wave` and by the `PreCompact` hook when Claude Code compacts the conversation.

Verification uses `task.verification_surface`: `journey_refs` alone do not force browser/mobile MCP. `/next-slice` must run `slice-maintain` and then invoke the full `verify-slice` skill automatically once `tester` reaches `ready_for_close`; the user should not have to type `/verify-slice` in the normal path. Do not delete or weaken `verify-slice`; it remains the real evidence gate.

## Handoff and evidence

- Handoff path: `orchestrator-state/tasks/handoffs/<TASK_ID>.md`.
- Evidence path: `orchestrator-state/tasks/evidence/<TASK_ID>/...`.
- Accepted trailers are marked and are not replayed as fresh lifecycle mutations.
- Missing/mismatched `AGENT`, `TASK_ID`, `HANDOFF` or required evidence blocks mutation.

## Blueprint completeness

Gold blueprint blocks:

```text
project stack auxiliary.arc42 building_blocks
logic.domain logic.application logic.journey logic.permission logic.state logic.error logic.integration logic.ui
auxiliary.data auxiliary.config auxiliary.verification auxiliary.adr auxiliary.risks auxiliary.glossary auxiliary.external_refs
registry.slices
```

Every registry slice must include:

```text
id title description dependency_rationale depends_on depends_on_rationale dependency_edges implements builds verifies arc42_refs risk verify_mode
```

## CI contract

Required checks:

```text
Lint
Claude Code adapter
Bootstrap
Unit tests 3.13
```

Local equivalent:

```bash
./scripts/run-all-tests.sh lint
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./scripts/python-safe.sh -m pytest -q --cache-clear
```

## pr-flow close contract

Under `pr-flow`, `closer` cannot mark `done` unless its trailer includes:

```text
REPORT_READY: yes
BASELINE_SYNC_READY: yes
GIT_READY: yes
PUSH_READY: yes
GIT_WORKFLOW_READY: yes
RUNTIME_CLEANED: yes
DOCKER_RUNTIME_CLEANED: yes|not_applicable:<reason>
RANCHER_RUNTIME_CLEANED: yes|not_applicable:<reason>
DEV_PORTS_RELEASED: yes|not_applicable:<reason>
WORKTREES_CLEANED: yes
PR_READY: yes
MERGED: yes
CANONICAL_MAIN_SYNCED: yes
```

## Docker/Rancher per-slice runtime

At the start of a slice, use the generated `TASK_ID` runtime context. If the compiled stack exposes Docker Compose files, start the isolated Rancher/Docker runtime with:

```bash
./scripts/dev-restart.sh --task <TASK_ID> --soft
```

The scripts prepend `~/.rd/bin`, `/opt/homebrew/bin` and `/usr/local/bin` for macOS/Linux. Host ports come from `.claude/bin/allocate_slice_ports.py` and are reserved under `orchestrator-state/dev-ports/<compose_project>.env`, because `docker compose -p` isolates object names but not host ports. At close, `closer` must run `./scripts/cleanup-slice-runtime.sh --task <TASK_ID> --apply --strict` before emitting `RUNTIME_CLEANED: yes`.

## Runtime write restrictions

Do not hand-edit generated runtime artifacts during slice execution:

```text
orchestrator-state/compiled/*
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/task-dag.json
orchestrator-state/tasks/task-packs/*
```

Use the runtime entrypoints and hooks to mutate lifecycle and generated artifacts.

## Rule index

- `00-blueprint-runtime-authority.md`
- `01-non-negotiables.md`
- `02-phase-execution.md`
- `03-dev-loop.md`
- `04-traceability.md`
- `05-runtime-write-contract.md`
- `06-subagents-and-trailers.md`
- `07-skills-runtime.md`
- `08-blueprint-descriptions-and-resolved-specs.md`
- `10-macos-case-sensitive-and-mcp.md`
- `11-pr-flow-rancher-runtime.md`
- `12-memory-yaml-contract.md`
- `13-memory-yaml-agent-flow.md`
- `13-lossless-blueprint-flow.md`
- `13-verify-slice-evidence-matrix.md`

## Memory YAML and verify-surface guard

- Runtime memory is structured YAML under `orchestrator-state/`.
- Agents read `PROGRESS.yaml`, `project-context.yaml`, per-task slice YAML, task pack, handoff YAML and their own `MEMORY.yaml` before relying on chat context.
- Shared memory/task YAML is mutated by compiler/bootstrap/hooks/scripts under locks; agents only write their own memory plus task handoff/evidence/report.
- `journey_refs` alone do not imply UI. Use `verification_surface` to choose browser/mobile MCP vs backend API/worker/domain verification.


## Documentation surface

Active docs are intentionally small:

```text
docs/ORCHESTRATOR.md
docs/templates/**
docs/prompts/**
```

`docs/templates/` stays because it defines the blueprint shape expected by compile/bootstrap and by the gold/smoke checkers. `docs/prompts/` contains operator prompts for turning a product idea or incomplete blueprint into a bootstrap-ready `inputs/BLUEPRINT.md`. Do not create parallel product-contract files; the runtime input remains `inputs/BLUEPRINT.md`.

## Skills runtime

Project slash entrypoints are native Claude Code skills under `.claude/skills/<name>/SKILL.md`. Use `/next-wave`, `/next-slice <TASK_ID>`, `/verify-slice <TASK_ID>`, `/closer <TASK_ID>` and `/compact-agent-memory` as skills; they preserve the DAG, hook, trailer, evidence and cleanup behavior through scripts and generated runtime state. Run `./scripts/check-skills-runtime.sh` after changing skills, hooks, agents or scripts. Memory cleanup is automatic through `scripts/next-wave.sh` and the `PreCompact` hook; use `/compact-agent-memory` only for manual maintenance. Treat skill, agent, MCP tool and path names as case-sensitive on macOS/Unix. See `.claude/rules/07-skills-runtime.md` and `.claude/rules/10-macos-case-sensitive-and-mcp.md`.

## Structured YAML memory

- Every subagent declares `memory: project` for Claude Code official subagent memory, but orchestrator runtime truth remains under `orchestrator-state/`.
- Agent/subagent structured memory is `orchestrator-state/agent-memory/<agent>/MEMORY.yaml`; the `MEMORY.md` file is only a human index.
- Project structured memory is `orchestrator-state/memory/PROGRESS.yaml`, `project-context.yaml`, `decisions.yaml` and `risk-register.yaml`.
- Task/slice structured memory is `orchestrator-state/tasks/task-index.yaml`, `runtime-state.yaml`, `slices/<TASK_ID>.yaml` and `handoffs/<TASK_ID>.yaml`.
- SubagentStart reads/injects memory context; SubagentStop mirrors trailers to `MEMORY.yaml`, `PROGRESS.yaml` and handoff YAML.
- Use exact case on macOS/Linux: `MEMORY.yaml` and `PROGRESS.yaml`. See `.claude/rules/12-memory-yaml-contract.md`.

## Lossless blueprint invariant

The orchestrator preserves the complete `inputs/BLUEPRINT.md` by reference. The compiler writes `orchestrator-state/compiled/BLUEPRINT.snapshot.md`, `blueprint-sections.json|yaml`, `blueprint-blocks.json|yaml`, `blueprint-lossless.json|yaml` and `blueprint-manifest.json|yaml`. Bootstrap propagates `source_sections` and `blueprint_lossless_refs` into registry tasks, DAG nodes, task-packs, per-slice YAML and SubagentStart context. Agents must use those pointers before assuming the blueprint lacks detail.

Agent memory remains under `orchestrator-state/agent-memory/<agent>/MEMORY.yaml`. Global runtime memory remains under `orchestrator-state/memory/*.yaml`. Do not write generated registry/task-dag/runtime-state by hand; use skills, hooks and trailers.

Rule index addition: `.claude/rules/13-lossless-blueprint-flow.md` defines the lossless blueprint preservation contract and the required memory/task fields.

- `.claude/rules/13-verify-slice-evidence-matrix.md` — exact `/verify-slice` routing for UI and non-UI backend/DB/worker/dependency/core slices.

## Final sanity before packaging

```bash
./scripts/reset-state.sh
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-handoff-contract.sh
./scripts/check-parallel-locks.sh
./scripts/check-claude-adapter.sh
./scripts/check-orchestrator-gaps.sh
./scripts/check-skills-runtime.sh
./scripts/compact-agent-memory.py --all --apply --threshold-lines 250
./scripts/simulate-blueprint-to-claude-flow.sh
```


## Git commit hygiene

Do not add `Co-Authored-By: Claude ...` or Anthropic noreply trailers to commits. The runtime blocks Bash `git commit` commands containing those trailers; amend any local accidental commit before push.

## Hook-safe worktree cleanup

Closer must not delete any task worktree before `SubagentStop` records the final trailer. Use `scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active`; `active_deferred=1` is a successful hook-safe cleanup state. With `--schedule-active`, matching task worktrees are deferred even when cleanup is launched from the canonical root, and deferred cleanup is retried by Stop/next-wave only after `done` is recorded.
