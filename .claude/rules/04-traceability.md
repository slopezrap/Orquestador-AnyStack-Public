# 04 - Traceability

Every slice must be traceable across the complete chain:

```text
inputs/BLUEPRINT.md source block
 -> orchestrator-input.json item IDs
 -> registry.json task
 -> task-dag.json node
 -> task-pack
 -> handoff/evidence/report/ledger
```

## Required task fields

A valid task includes:

- `id` / `task_id`
- `title`, `description`, `dependency_rationale`, `depends_on_rationale` and `dependency_edges`
- `phase_id`, `step_id`, `order`, `type`, `status`
- `depends_on`, `dependents`
- `implements`, `builds`, `verification_refs`
- `journey_refs`, `closes_journeys` where relevant
- `building_block_refs`
- `write_set`, `read_set`, `conflict_group`, `conflict_groups`
- `acceptance`, `evidence_contract`
- `contract_refs`, `resolved_specs`, `source_refs`, `generated_from`; each `resolved_specs[]` entry carries `description`, `details`, `raw` and `source_ref` so Claude does not lose YAML information

## Description contract

`description` is not decoration. It is the human explanation of the task scope and must preserve product intent, production constraints, boundaries, expected evidence and no-go areas. `resolved_specs[].description` carries the same obligation for each implemented ID. It must not contain filler or non-production wording.

## Verification trace

`/verify-slice` must state:

- which verification refs were exercised;
- which data was real/provided;
- which logs/runtime observations were checked;
- whether journeys/screens/events were covered;
- where evidence is stored.

## Report trace

Closer reports summarize what was implemented, verified, committed, merged and cleaned. Reports do not become a new source of truth.
