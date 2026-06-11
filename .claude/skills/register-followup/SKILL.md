---
name: "register-followup"
description: "Registra un follow-up solo cuando el trabajo no cabe razonablemente en la slice activa. Antes de proponerlo exige triage: si el arreglo cabe en el write_set actual, toca pocos ficheros y no requiere nuevos IDs/dependencias/datos/decisión humana, se arregla en la misma slice vía developer/debugger/retest."
argument-hint: "propose --origin-task <TASK_ID> --scope-classification <classification> --repair-decision <followup_required|human_decision_required> --why-not-debugger <reason> --title <title> --severity <blocker|critical|high|medium|low>"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# register-followup

Entrada slash de Claude Code para `/register-followup`. Delega al runtime y escribe únicamente YAML de propuesta en `orchestrator-state/tasks/follow-ups/`.

## Uso canónico

```bash
./scripts/register-followup-task.sh propose \
  --origin-task <TASK_ID> \
  --scope-classification <out_of_scope|missing_coverage|missing_real_data|external_dependency|future_enhancement|scope_expansion|blocked_by_human_decision> \
  --repair-decision <followup_required|human_decision_required> \
  --why-not-debugger "<por qué no cabe en debugger/retest del TASK_ID actual>" \
  --title "<título>" \
  --severity <blocker|critical|high|medium|low> \
  --description "<detalle>" \
  --files-estimate <n|unknown> \
  --fits-current-write-set <yes|no|unknown> \
  --outside-current-write-set <yes|no|unknown> \
  --requires-blueprint-change <yes|no|unknown> \
  --requires-new-dependency <yes|no|unknown> \
  --requires-human-decision <yes|no|unknown> \
  --missing-real-data <yes|no|unknown> \
  --write-set "<ruta/recurso>" \
  --verify "<evidencia mínima real>"
```

Atajo compatible, solo para operador humano:

```bash
./scripts/register-followup-task.sh <TASK_ID> "<title>"
```

El atajo marca `scope_classification: missing_coverage` y requiere revisión posterior.

## Política

- `in_scope_defect` está rechazado: usa debugger/retest en la misma slice.
- `--repair-decision fix_in_current_slice|debugger_retest|mechanical_retry` está rechazado como FU: corrige/reintenta en la misma slice.
- Un FU requiere `--repair-decision followup_required|human_decision_required` y al menos un disparador duro: fuera del `write_set`, cambio de blueprint/nuevos IDs, nueva dependencia, datos reales ausentes o decisión humana.
- Si parece un arreglo pequeño (`--files-estimate <= 3`) que cabe en el `write_set` actual y no requiere blueprint/dependencia/datos/decisión humana, el runtime lo rechaza y manda a debugger/retest.
- Todo follow-up debe explicar `why_not_debugger`.
- Severidad `blocker|critical|high` bloquea `/next-wave` y `claim_task` hasta `/promote-followup` o waiver.
- El closer puede incluir propuestas formales en su PR, pero no las promueve automáticamente.
- La promoción no edita `registry.json` ni `task-dag.json`; crea una patch request para `inputs/BLUEPRINT.md`.

## Waiver

```bash
./scripts/register-followup-task.sh waive <FOLLOWUP_ID> --reason "<decisión humana>"
```

## Blueprint authority chain

```text
inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> orchestrator-state/tasks/task-dag.json -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```

## Source-chain context

When deciding whether work is in scope, read task `title`, `description`, `dependency_rationale`, `depends_on_rationale`, `dependency_edges`, `resolved_dependencies` and `resolved_specs` from the task-pack. IDs alone are navigation, not scope.
