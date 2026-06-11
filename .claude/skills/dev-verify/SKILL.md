---
name: dev-verify
description: "Run development verification commands for one slice before the formal verify-slice gate. Use for fast local checks while keeping final real UI/backend verification owned by verify-slice."
argument-hint: "<TASK_ID>"
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



# dev-verify

Use task-pack stack commands and verification refs. Good defaults:

```bash
./scripts/check-task-dag.sh
./scripts/check-task-descriptions.sh
./scripts/check-orchestrator-gaps.sh
```

For app slices, use stack-specific commands from compiled `stack.commands`.


##  resolved-spec/DAG-handoff rule

When a task is active, use `title`, `description`, `dependency_rationale` and `resolved_specs[]`. Do not stop at IDs: each resolved spec carries `description`, `details`, `raw` and `source_ref`; use those fields to preserve the full blueprint YAML contract in implementation, verification, handoff and report evidence.

Mutating lifecycle work must leave durable `HANDOFF` and `EVIDENCE` paths in the final `CLAUDE_TRAILER`; closer must also leave `REPORT`.
