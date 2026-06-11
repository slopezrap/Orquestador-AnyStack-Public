---
name: "promote-followup"
description: "Promociona un follow-up aceptado a una solicitud de cambio del blueprint canónico sin mutar a mano el registry ni el DAG. Usa esta skill cuando el main-orchestrator o el operador humano decide que una propuesta fuera de scope debe convertirse en nueva slice/slices en inputs/BLUEPRINT.md y después recompilar/bootstrappear el runtime."
argument-hint: "<FOLLOWUP_ID>"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# promote-followup

Entrada slash de Claude Code para `/promote-followup <FOLLOWUP_ID>`.

```bash
./scripts/promote-followup.sh <FOLLOWUP_ID>
```

## Qué hace

- Lee `orchestrator-state/tasks/follow-ups/<FOLLOWUP_ID>.yaml`.
- Cambia el estado a `promoted_to_blueprint`.
- Crea `orchestrator-state/tasks/source-doc-patches/<FOLLOWUP_ID>.md` con la solicitud de parche.
- No toca `registry.json`, `task-dag.json`, `runtime-state.json` ni task-packs.

## Qué debe hacer después el operador/modelo

1. Abrir la patch request generada.
2. Añadir el trabajo a `inputs/BLUEPRINT.md` como slice/slices normales con refs, `depends_on`, `write_set`, `conflict_groups`, acceptance y evidence contract.
3. Ejecutar:

```bash
./scripts/compile-blueprint.sh
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-task-dag.sh
```

Esta política mantiene el runtime DAG final: el blueprint es la única fuente humana y bootstrap genera el registry/DAG.

## Source-chain context

When deciding whether work is in scope, read task `title`, `description`, `dependency_rationale`, `depends_on_rationale`, `dependency_edges`, `resolved_dependencies` and `resolved_specs` from the task-pack. IDs alone are navigation, not scope.
