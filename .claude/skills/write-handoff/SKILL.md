---
name: write-handoff
description: "Write or check scoped handoff evidence for the current slice without editing registry, DAG or runtime state directly. Use when an agent must preserve findings, evidence paths or follow-up candidates for SubagentStop and later agents."
argument-hint: "<TASK_ID>"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Bash, Glob, Grep, Edit, MultiEdit, Write
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



# write-handoff

Handoffs live under:

```text
orchestrator-state/tasks/handoffs/<TASK_ID>.md
```

A verifier handoff must name evidence, verification refs, data source and remaining issues.


##  resolved-spec/DAG-handoff rule

When a task is active, use `title`, `description`, `dependency_rationale` and `resolved_specs[]`. Do not stop at IDs: each resolved spec carries `description`, `details`, `raw` and `source_ref`; use those fields to preserve the full blueprint YAML contract in implementation, verification, handoff and report evidence.

Mutating lifecycle work must leave durable `HANDOFF` and `EVIDENCE` paths in the final `CLAUDE_TRAILER`; closer must also leave `REPORT`.
