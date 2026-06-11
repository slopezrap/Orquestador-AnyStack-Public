# 03 - Developer loop

The developer works from the task pack, not memory.

## Required reads

- `orchestrator-state/tasks/task-packs/<TASK_ID>.md`
- `orchestrator-state/tasks/task-packs/<TASK_ID>.json`
- `orchestrator-state/compiled/orchestrator-input.json` only when expansion is needed
- `orchestrator-state/compiled/source-map.json` when source tracing is needed
- `inputs/BLUEPRINT.md` source refs only for human context

## Write rules

- Do not mutate generated orchestrator state.
- Do not edit `inputs/BLUEPRINT.md` during an active app slice.
- Do not edit `.claude/` adapter files unless the active task is orchestrator maintenance.
- Stay inside `write_set`; ask the main orchestrator before touching paths outside it.

## Trailer rules

Developer success:

```text
CLAUDE_TRAILER:
AGENT: developer
TASK_ID: <TASK_ID>
OUTCOME: success
NEXT_STATUS: validator_tester_pending
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/developer.json
```

Developer blocked:

```text
CLAUDE_TRAILER:
AGENT: developer
TASK_ID: <TASK_ID>
OUTCOME: blocked
NEXT_STATUS: blocked
BLOCKER_REASON: <reason>
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/developer.json
```

## Handoff hygiene and shared-surface regression guard

Developer, tester, debugger, verifier and closer append concise handoff sections with plain `KEY: value` or `- KEY: value` facts. Do not write field names as headings. The hook can recover from non-current formats, but current agents must emit clean key lines and a separate final `CLAUDE_TRAILER`.

When a slice touches shared runtime, settings, security, provider, UI shell or dependency surfaces, tests must include at least one regression check for adjacent slices or explain why the adjacent risk is not applicable. Shared-surface risk is task evidence, not a reason to silently widen `write_set`.

