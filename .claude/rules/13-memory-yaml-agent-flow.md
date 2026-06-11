# Memory YAML agent contract 

This rule defines the orchestrator memory discipline for the blueprint-first runtime.

## Canonical memory read order

Every agent/subagent reads in this order when context is missing or after `/clear`:

1. `CLAUDE.md` -> `.claude/CLAUDE.md` for static project instructions.
2. `orchestrator-state/memory/PROGRESS.yaml` for active task, counts, spawn budget and recent events.
3. `orchestrator-state/memory/project-context.yaml` for project/stack/logic summary compiled from `inputs/BLUEPRINT.md`.
4. `orchestrator-state/tasks/registry.json` and `orchestrator-state/tasks/task-dag.json` for canonical runtime state.
5. `orchestrator-state/tasks/slices/<TASK_ID>.yaml` for compact per-slice state.
6. `orchestrator-state/tasks/task-packs/<TASK_ID>.json|md` for human scope and trailer examples.
7. `orchestrator-state/tasks/handoffs/<TASK_ID>.yaml|md` for cross-agent handoff.
8. `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` for role-specific durable lessons.

## Write authority

Agents may write only:

- their own `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` for stable cross-slice lessons;
- task evidence under `orchestrator-state/tasks/evidence/<TASK_ID>/`;
- task handoff entries under `orchestrator-state/tasks/handoffs/<TASK_ID>.md` or via the hook/skill path;
- closer reports under `orchestrator-state/tasks/reports/<TASK_ID>.md`.

Agents must not hand-edit:

- `orchestrator-state/tasks/registry.json`;
- `orchestrator-state/tasks/runtime-state.json`;
- `orchestrator-state/tasks/task-dag.json`;
- `orchestrator-state/tasks/task-packs/*`;
- `orchestrator-state/memory/PROGRESS.yaml`;
- `.claude/orchestrator-contract.json` or `orchestrator/rules/state-machine.yaml`.

Those shared files are mutated by compiler/bootstrap/hooks/scripts under locks.

## Handoff mirrors

Every accepted/rejected trailer is mirrored to:

- `orchestrator-state/tasks/handoffs/<TASK_ID>.yaml`;
- `orchestrator-state/tasks/handoff-index.yaml`;
- `orchestrator-state/tasks/lifecycle-events.yaml`;
- `orchestrator-state/agent-memory/<agent>/MEMORY.yaml`;
- `orchestrator-state/memory/PROGRESS.yaml`.

The Markdown handoff is for human continuity. The YAML handoff is for deterministic recovery.

## Verify UI/non-UI rule

`journey_refs` alone are not a UI signal. The compiled `verification_surface` decides:

- `browser_ui` or `mobile_ui` requires visual MCP and `screen-journey-reviewer`;
- `journey_backend_contract` uses API/worker/DB/log/domain verification and leaves journey verification to `/verify-journey` or a later UI slice;
- backend/deployment/automated contracts do not force Flutter/mobile/browser MCP.

`./scripts/check-verify-surface.sh` must stay green.
