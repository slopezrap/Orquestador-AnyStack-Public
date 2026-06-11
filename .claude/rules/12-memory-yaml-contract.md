# Memory YAML contract

Claude Code official subagent memory and orchestrator runtime memory are complementary:

- Claude Code official memory is enabled by `memory: project` in every `.claude/agents/*.md` file. Claude Code manages that memory according to its documented subagent memory behavior.
- Orchestrator runtime memory is stored under `orchestrator-state/` and is the only memory read by hooks, scripts and recovery tools.

## Runtime memory files

- `orchestrator-state/memory/PROGRESS.yaml` — compact project progress and `/clear` recovery summary.
- `orchestrator-state/memory/project-context.yaml` — blueprint/project/stack/logic summary generated from compiled input and registry.

- `orchestrator-state/memory/source-manifest.yaml` — blueprint/input/compiler manifest replacing the compiled source manifest generated from inputs/BLUEPRINT.md.
- `orchestrator-state/memory/project-brief.yaml|md` — concise project/product brief compiled from inputs/BLUEPRINT.md project/arc42/logic blocks.
- `orchestrator-state/memory/architecture-contract.yaml|md` — architecture/building-block/integration/UI/state contract compiled from arc42 and logic blocks.
- `orchestrator-state/memory/stack-profile.yaml` — compiled stack/orchestrator/runtime profile compiled from the stack block as active runtime memory.
- `orchestrator-state/memory/decisions.yaml` — durable architecture/orchestration decisions.
- `orchestrator-state/memory/risk-register.yaml` — durable cross-slice risks.
- `orchestrator-state/tasks/task-index.yaml` — YAML task index generated from `registry.json`.
- `orchestrator-state/tasks/runtime-state.yaml` — YAML mirror of runtime counters and active task state.
- `orchestrator-state/tasks/slices/<TASK_ID>.yaml` — YAML projection of each compiled slice.
- `orchestrator-state/tasks/handoffs/<TASK_ID>.yaml` — structured companion to the Markdown handoff ledger.
- `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` — canonical structured memory per agent/subagent.
- `orchestrator-state/agent-memory/<agent>/MEMORY.md` — human-readable mirror/index only.

`registry.json`, `runtime-state.json`, `task-dag.json`, task-packs and handoffs remain authoritative. YAML memory is context and recovery support; it is not permission to mutate lifecycle.

## Agent write policy

Agents may update only their own `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` and only with stable cross-slice lessons, codepaths, recurring risks and compact task summaries. Do not store secrets, raw transcripts, large logs, temporary scratch, unverified claims, full task-packs or provider payloads.

Mutating agents must write durable task facts to the handoff/evidence/report before emitting `CLAUDE_TRAILER`. SubagentStop mirrors accepted and rejected trailer summaries into `MEMORY.yaml`, `PROGRESS.yaml`, task handoff YAML and lifecycle ledgers. Info-only agents may write findings to their own memory, but cannot write `NEXT_STATUS` or change lifecycle state.

## Recovery order after `/clear`

Read in this order:

1. `orchestrator-state/memory/PROGRESS.yaml`
2. `orchestrator-state/memory/project-context.yaml`
3. `orchestrator-state/tasks/registry.json`
4. `orchestrator-state/tasks/task-dag.json`
5. `orchestrator-state/tasks/runtime-state.json`
6. active `orchestrator-state/tasks/task-packs/<TASK_ID>.json|md`
7. active `orchestrator-state/tasks/handoffs/<TASK_ID>.yaml|md`
8. role-specific `orchestrator-state/agent-memory/<agent>/MEMORY.yaml`

Do not reconstruct state from chat history when disk artifacts exist.

## Case sensitivity

Use the exact filename `MEMORY.yaml`, not `memory.yaml`, and `PROGRESS.yaml`, not `progress.yaml`. This package treats macOS as case-sensitive for paths, MCP server names, tool names, agent names and hook matchers.

## Verification surface memory

Every compiled slice exposes `verification_surface` in registry, task-dag, task-pack JSON and task YAML. `journey_refs` alone are not UI evidence. Browser/mobile MCP is required only when `verification_surface.requires_visual_mcp=true`; backend journey dependencies use API/worker/DB/log evidence and may leave a pending journey gate for `/verify-journey`.

## Backend journey verification routing

`journey_refs` and `closes_journeys` are journey-gate metadata, not proof that the slice has a UI route. The compiled task field `verification_surface` decides the verification route:

- `browser_ui` and `mobile_ui` require visual/mobile evidence and usually `screen-journey-reviewer`.
- `journey_backend_contract` means the slice participates in or closes a journey through backend/API/worker/state behavior but has no compiled UI route. Verify it with real/provided data, API calls, DB state, worker logs and domain assertions; do not force MCP browser/mobile.
- Journey gates are completed later through `/verify-journey` or a UI slice with explicit UI specs.

Agents must read `orchestrator-state/tasks/slices/<TASK_ID>.yaml` or the task-pack JSON before choosing browser/mobile/runtime verification. The checkers reject tasks that treat journey-only backend slices as UI verification surfaces.
