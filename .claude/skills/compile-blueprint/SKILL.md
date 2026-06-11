---
name: "compile-blueprint"
description: "Compila inputs/BLUEPRINT.md a orchestrator-input.json y valida bloques yaml orchestrator. Funciona también cuando orchestrator-state aún está vacío."
argument-hint: "[inputs/BLUEPRINT.md]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# compile-blueprint

Este skill es una excepción de arranque: debe funcionar aunque `orchestrator-state/compiled`, `registry.json`, `task-dag.json` y `task-packs/` estén vacíos. No inspecciones un `TASK_ID`, no pidas task-pack y no concluyas que el runtime está roto por estar todavía sin bootstrap.

## Root split obligatorio

Si estás dentro de una worktree de slice, la verdad compartida del scheduler vive en la raíz canónica, no en la worktree. Resuelve raíz antes de compilar:

```bash
BOOTSTRAP_ROOT="${CLAUDE_ORCHESTRATOR_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
ROOT="$(bash "$BOOTSTRAP_ROOT/scripts/ensure-task-worktree.sh" --print-root 2>/dev/null || bash "$BOOTSTRAP_ROOT/scripts/resolve-orchestrator-root.sh" "$BOOTSTRAP_ROOT" 2>/dev/null || printf '%s\n' "$BOOTSTRAP_ROOT")"
cd "$ROOT"
```

## Ejecución

Run the deterministic compiler. Default input is `inputs/BLUEPRINT.md`.

```bash
./scripts/compile-blueprint.sh $ARGUMENTS
```

When `$ARGUMENTS` is empty, run:

```bash
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
```

Then inspect `orchestrator-state/compiled/compile-report.md`. Do not edit generated JSON manually.

## Resultado esperado

```text
orchestrator-state/compiled/orchestrator-input.json
orchestrator-state/compiled/source-map.json
orchestrator-state/compiled/compile-report.md
```

## Blueprint authority chain

```text
inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> orchestrator-state/tasks/task-dag.json -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```

Use task descriptions, dependency rationales, resolved_specs, source_sections and blueprint_lossless_refs as human scope. IDs alone are navigation, not implementation scope.
