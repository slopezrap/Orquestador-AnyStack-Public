---
name: official-docs-check
description: "Check volatile or provider-specific facts against official documentation before implementation, verification, dependency introduction or blueprint reconciliation. Use when APIs, SDKs, Claude Code features, MCPs or platform behavior may have changed."
argument-hint: "<topic or provider feature>"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Bash, Glob, Grep, WebFetch, WebSearch
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



# official-docs-check

Use `official-docs-researcher` for APIs, SDKs, Claude Code hooks/subagents/skills, GitHub Actions, providers and brokers.

Record:

- official source;
- access date;
- exact finding;
- effect on blueprint/task.

If docs contradict the blueprint, reconcile the blueprint and recompile.


##  resolved-spec/DAG-handoff rule

When a task is active, use `title`, `description`, `dependency_rationale` and `resolved_specs[]`. Do not stop at IDs: each resolved spec carries `description`, `details`, `raw` and `source_ref`; use those fields to preserve the full blueprint YAML contract in implementation, verification, handoff and report evidence.
