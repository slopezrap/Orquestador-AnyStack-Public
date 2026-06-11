---
name: phase-execution
description: "Guide normal execution over explicit DAG slices without imposing fixed phases. Use to interpret next-wave/next-slice ordering, dependencies, conflict groups and lifecycle gates."
argument-hint: "[TASK_ID|phase label]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Bash, Glob, Grep
---

## Source model

Active authority chain:

```text
inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> task-dag.json -> task-packs
```

Do not require or recreate the single-source blueprint input. There is no second Markdown slash layer in this skills runtime profile.

## Global rules

- Do not hand-edit generated compiled/runtime artifacts.
- Use task `title`, `description`, `dependency_rationale`, `depends_on_rationale`, `dependency_edges`, `resolved_dependencies[].description` and `resolved_specs[].description` as human scope; IDs alone are never enough.
- Respect `write_set` and `conflict_groups`.
- No fake product data, stubs or unfinished runtime paths as proof.
- Trailer values must match `.claude/orchestrator-contract.json` and `orchestrator/rules/state-machine.yaml`.



# phase-execution

Use phases only as grouping. Slice readiness is decided by the explicit DAG:

```bash
./scripts/next-wave.sh
./scripts/next-slice.sh <TASK_ID>
```

Do not infer hidden dependencies from phase order.


##  resolved-spec/DAG-handoff rule

When a task is active, use `title`, `description`, `dependency_rationale` and `resolved_specs[]`. Do not stop at IDs: each resolved spec carries `description`, `details`, `raw` and `source_ref`; use those fields to preserve the full blueprint YAML contract in implementation, verification, handoff and report evidence.
