---
name: "check-gold-blueprint"
description: "Valida inputs/BLUEPRINT.md gold con arc42, lógicas completas, descripciones, DAG, resolved_specs, trailers y handoff."
argument-hint: "[inputs/BLUEPRINT.md]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# check-gold-blueprint

```bash
./scripts/check-gold-blueprint.sh $ARGUMENTS
```

When `$ARGUMENTS` is empty, validate `inputs/BLUEPRINT.md`. Also validate the canonical fixture with:

```bash
./scripts/check-gold-blueprint.sh examples/gold/BLUEPRINT.md
```

## Blueprint authority chain

```text
inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> orchestrator-state/tasks/task-dag.json -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```
