# 08 - Blueprint descriptions and resolved specs

The blueprint machine layer must carry human meaning, not only IDs.

## Required description fields

Every machine-readable item needs a production-grade `description`:

```text
project
stack
auxiliary.arc42[]
building_blocks[]
logic.domain[]
logic.application[]
logic.journey[]
logic.permission[]
logic.state[]
logic.error[]
logic.integration[]
logic.ui[]
auxiliary.data[]
auxiliary.config[]
auxiliary.verification[]
auxiliary.adr[]
auxiliary.risks[]
auxiliary.glossary[]
auxiliary.external_refs[]
registry.slices[]
```

A slice also needs `dependency_rationale`, per-dependency `depends_on_rationale` and compiled `dependency_edges`. The compiler rejects missing or weak descriptions. Descriptions must preserve the human intent from arc42 and must not contain filler, monkey text, fake-product proof, or incomplete runtime markers.

## Compiled propagation

The compile/bootstrap pipeline must propagate descriptions through:

```text
inputs/BLUEPRINT.md yaml block
 -> orchestrator-input.json item.description
 -> registry.json task.description and task.resolved_specs[].description
 -> task-dag.json node.description
 -> task-packs/<TASK_ID>.json
 -> task-packs/<TASK_ID>.md
 -> SubagentStart context
```

`resolved_specs` is the anti-drift payload. It turns `implements: [UC-002, INT-adapter]` into human-readable contracts that a subagent can execute without guessing what the IDs mean. Each entry must preserve `description`, selected prompt-friendly fields, `details` for structured YAML fields, `raw` for the complete YAML item and `source_ref` for navigation back to inputs/BLUEPRINT.md.

## Agent behavior

Subagents must read `title`, `description`, `dependency_rationale`, `depends_on_rationale`, `dependency_edges`, `resolved_dependencies[].description` and `resolved_specs[].description` before editing or verifying. IDs, aliases and locations define traceability, but descriptions define the human scope.
