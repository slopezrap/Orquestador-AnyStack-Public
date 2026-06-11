# Rule 13 — Lossless blueprint flow

The blueprint is the human source of truth. The compiler must preserve it as a full snapshot and as indexed sections/blocks. Every runtime artifact must carry either the full data or a pointer to it:

```text
inputs/BLUEPRINT.md
 -> BLUEPRINT.snapshot.md
 -> blueprint-sections.json|yaml
 -> blueprint-blocks.json|yaml
 -> orchestrator-input.json
 -> registry/task-dag/task-packs/slices YAML
 -> SubagentStart additionalContext
 -> handoff/evidence/report/trailer
```

Required task fields:

- `description`
- `dependency_rationale`
- `resolved_specs[].description`
- `resolved_specs[].raw`
- `resolved_specs[].source_sections`
- `source_sections`
- `blueprint_lossless_refs`
- `verification_surface`
- `evidence_contract`

Agents and subagents must not treat an ID as sufficient scope. They must use `source_sections` and `BLUEPRINT.snapshot.md` when they need surrounding arc42 prose, tables, or rationale.

Agents may write only:

- their own `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` for stable reusable lessons;
- task handoff/evidence/report files;
- final `CLAUDE_TRAILER`.

Hooks and runtime scripts own shared YAML updates under `orchestrator-state/memory` and `orchestrator-state/tasks`.
