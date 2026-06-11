---
name: "next-slice"
description: "Arranca una slice DAG explícita desde su task-pack compilado: claim atómico, plan aprobado, developer + official-docs-researcher opcional, validator + tester en paralelo, debugger si hace falta, mantenimiento automático y verificación verify-slice automática. No cierra; deja la slice en verified_pending_close, needs_debug o blocked."
argument-hint: "<TASK_ID>  (o terminal con CLAUDE_ACTIVE_TASK_ID ya exportado)"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# next-slice

This is the active Claude Code project skill for `/next-slice`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /next-slice <TASK_ID>

## Realidad skills runtime

Ejecuta la coreografía blueprint-first desde el input único:

```text
inputs/BLUEPRINT.md -> orchestrator-input.json -> registry.json -> task-dag.json -> task-packs
```

El `TASK_ID` debe venir de `$ARGUMENTS` o de `CLAUDE_ACTIVE_TASK_ID`. Si falta, para y usa:

```bash
./scripts/next-wave.sh --limit 1
```

## Invariante DAG visible en el plan

Incluye siempre en el plan:

```text
MODO DAG ACTIVO: production = explicit_dag.
Unidad ejecutable = TASK_ID canónico del registry.
No existe modo DAG-disabled improvisado.
No inventes slices efímeras.
Cada subagente recibe TASK_ID + CLAUDE_TASK_PACK + resolved_specs + write_set/conflict_group/locks.
```

## Gate de checkout y root split

Antes de claim/spawn:

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root 2>/dev/null || pwd -P)"
bash "$ROOT/scripts/ensure-task-worktree.sh" --check-current <TASK_ID>
bash "$ROOT/scripts/inspect-task-state.sh" --task <TASK_ID>
bash "$ROOT/scripts/check-worktree-deps-visible.sh" <TASK_ID> --json
```

En `pr-flow`, debes estar en la worktree/rama del `TASK_ID`; en `push-to-main`, en root/main. Si no, para y usa el bloque exacto de `/next-wave`.

## Contexto mínimo antes del plan

Lee, sin mutar:

1. `orchestrator-state/tasks/task-packs/<TASK_ID>.json`
2. `orchestrator-state/tasks/task-packs/<TASK_ID>.md`
3. `orchestrator-state/tasks/registry.json`
4. `orchestrator-state/tasks/task-dag.json`
5. `orchestrator-state/tasks/runtime-state.json`
6. `.claude/CLAUDE.md`
7. `.claude/rules/01-non-negotiables.md`
8. `.claude/rules/03-dev-loop.md`
9. `.claude/orchestrator-contract.json`
10. `orchestrator/rules/state-machine.yaml`

Usa como scope humano:

```text
title
description
dependency_rationale
depends_on_rationale
dependency_edges
resolved_dependencies[].description
resolved_specs[].description/details/raw/source_ref
acceptance
evidence_contract
verification_refs
```

Los IDs solos no bastan.

## Paso 1 — claim atómico

Tras aprobación del plan por el usuario, ejecuta:

```bash
./scripts/next-slice.sh <TASK_ID>
```

Este entrypoint llama a `claim_task` y revalida bajo lock:

- task sigue `ready`;
- deps siguen `done`;
- no hay blockers activos por `write_set`/`conflict_group`;
- no hay journey gate aplicable;
- se inicializa handoff.

Si bloquea por conflicto o dependencia, no lo fuerces: vuelve a `/next-wave`.

## Paso 2 — propuesta previa obligatoria / approval gate

Antes de tocar código, presenta:

```md
# Plan para la siguiente slice

## Estado actual
- TASK_ID:
- Status:
- Phase:
- DAG mode:
- Worktree/root:

## Siguiente slice propuesta
- Title:
- Description:
- Dependency rationale:
- Depends on / rationale:
- resolved_specs principales:
- acceptance/evidence:

## Invariante DAG de esta ejecución
...

## Ficheros/áreas previstas
- Write set:
- Conflict groups:
- Locks:

## Riesgos
- entorno
- scope
- datos reales/proporcionados
- MCP/visual si aplica

## ¿Procedo?
```

Regla de oro: no edites, no lances workers y no mutes estado antes de esa aprobación, salvo lecturas y checks read-only.


## Paso 2.5 — Runtime Docker/Rancher de la slice

Antes de spawnear `developer`, prepara el entorno local si el stack compilado declara Docker Compose:

```bash
./scripts/dev-restart.sh --task <TASK_ID> --soft
```

Reglas blueprint-first activas:

- Rancher Desktop es el runtime local esperado en macOS/Linux; los scripts cargan `scripts/unix-runtime-env.sh` y añaden `~/.rd/bin`, `/opt/homebrew/bin` y `/usr/local/bin` al `PATH`.
- `COMPOSE_PROJECT_NAME` y `CLAUDE_COMPOSE_PROJECT_NAME` se derivan del `TASK_ID`, no del directorio, para que dos worktrees no compartan stack.
- Los puertos host se asignan con `.claude/bin/allocate_slice_ports.py`; `docker compose -p` aísla nombres/redes/volúmenes, pero no evita colisiones de puertos host.
- Si no hay compose file, el script devuelve `DEV_RESTART: skipped_no_compose_file` y puedes continuar sólo si la slice no necesita runtime.
- Si hay compose file y Docker/Rancher no está disponible, bloquea mecánicamente con `BLOCKER_REASON: runtime_unavailable`; no lo conviertas en follow-up de producto.

## Paso 3 — subagentes: pipeline paralelo obligatorio

La cadena canónica de `/next-slice` es:

```text
planner -> developer ∥ official-docs-researcher? -> validator ∥ tester -> debugger? -> validator ∥ tester -> slice-maintain -> verify-slice automático
```

1. `planner` es bloqueante. Debe dejar el contexto operativo listo antes de cualquier mutación: `CONTEXT_READY: yes`, `IMPACT_READY: yes`, `ACTIVE_TASK`, `TASK_PACK`, `WRITE_SET`, `CONFLICT_GROUPS` y `NEEDS_OFFICIAL_DOCS`.
2. Después de `planner`, lanza `developer` y, sólo si aplica, `official-docs-researcher` en el mismo mensaje con 1-2 llamadas `Agent`.
   - Invoca `official-docs-researcher` si el planner marca `NEEDS_OFFICIAL_DOCS: yes`, si la slice toca API/librería/framework externo, seguridad/auth, IA/RAG/MCP, streaming, DB driver, CLI, deploy/runtime provider, o si hay incertidumbre de versión/comportamiento.
   - No lo invoques para CRUD interno, copy, cambios locales o tareas sin dependencia externa volátil.
   - El researcher es info-only: aporta enlaces/notas oficiales al handoff y nunca emite `NEXT_STATUS`.
3. Tras `developer`, lanza `validator` y `tester` juntos en un único mensaje con 2 llamadas `Agent`. Este paralelismo es obligatorio salvo bloqueo técnico explícito.
   - `validator` es info-only: revisa scope, arquitectura, seguridad, contratos y puede pedir cambios, pero no escribe lifecycle ni emite `NEXT_STATUS`.
   - `tester` es el rol lifecycle del par: ejecuta pruebas reales/proporcionadas y emite `ready_for_close`, `needs_debug` o `blocked`.
   - Los hooks y `.claude/orchestrator-contract.json` permiten que el orden de llegada de ambos stops no corrompa estado: validator informa; tester transiciona.
4. Si `tester` falla o `validator` pide cambios in-scope, lanza `debugger`; después vuelve siempre a `validator ∥ tester`.
   - Máximo 4 ciclos `debugger -> validator ∥ tester`.
   - Tras 4 ciclos sin converger, bloquea con evidencia y `BLOCKER_REASON`; no abras follow-up para defectos in-scope.
5. Cuando `tester` deja `ready_for_close`, `/next-slice` ejecuta `slice-maintain` e invoca automáticamente el skill completo `/verify-slice`. El operador no debe tener que escribir `/verify-slice` en el camino normal.
6. No aumentes el spawn budget para tapar una slice demasiado grande; si no cabe, el blueprint debe partir `registry.slices[]`.

## Trailers válidos

Developer success:

```text
CLAUDE_TRAILER:
AGENT: developer
TASK_ID: <TASK_ID>
OUTCOME: success
NEXT_STATUS: validator_tester_pending
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/developer.json
```

Tester pass:

```text
CLAUDE_TRAILER:
AGENT: tester
TASK_ID: <TASK_ID>
OUTCOME: pass
NEXT_STATUS: ready_for_close
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/tester.json
```

Tester issues:

```text
CLAUDE_TRAILER:
AGENT: tester
TASK_ID: <TASK_ID>
OUTCOME: fail
NEXT_STATUS: needs_debug
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/tester.json
```

Blocked:

```text
CLAUDE_TRAILER:
AGENT: developer
TASK_ID: <TASK_ID>
OUTCOME: blocked
NEXT_STATUS: blocked
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/developer.json
BLOCKER_REASON: <mechanical_or_product_data_blocker>
```

The hook validates `AGENT`, `TASK_ID`, duplicates, allowed `OUTCOME`, allowed `NEXT_STATUS`, required handoff/evidence and the state machine. Do not edit `registry.json` manually.

## Paso 4 — mantenimiento y verify-slice automático

Cuando `tester` deja la task en `ready_for_close`, ejecuta mantenimiento seguro sin pedir otro comando al usuario:

```bash
./scripts/slice-maintain.sh <TASK_ID>
```

Si `tester` deja la task en `ready_for_close`, **no pidas al usuario `/verify-slice`**. Carga y ejecuta inmediatamente la skill `verify-slice` para el mismo `TASK_ID`; no copies ni reduzcas su contrato. `verify-slice` conserva toda su responsabilidad: init obligatorio del skeleton `## verify-slice`, hard reset, datos reales/proporcionados, MCP visual/mobile cuando la slice tiene UI, modalidad backend cuando no tiene UI, logs, persistencia, evidencia, tabla de resultado y propuesta de follow-up cuando aplique. No spawnees `slice-verifier` directamente salvo reparación manual; si lo haces, confirma antes que `scripts/init-verify-slice-handoff.sh <TASK_ID>` pasó en la raíz canónica.

```text
ready_for_close -> ejecutar verify-slice automáticamente -> verified_pending_close | needs_debug | blocked
```

Si `verify-slice` devuelve `needs_debug`, ejecuta el bucle mínimo `debugger -> validator ∥ tester`; sólo cuando `tester` vuelva a dejar `ready_for_close`, repite `slice-maintain -> verify-slice` hasta que quede `verified_pending_close` o `blocked`, respetando spawn budget y sin ampliar scope. Si el hallazgo parece fuera de scope, primero haz triage de reparabilidad: si cabe en el `write_set` actual, toca pocos ficheros y no requiere nuevos IDs/dependencias/datos/decisión humana, arréglalo en la misma slice mediante debugger/retest. Sólo registra follow-up con `register-followup` cuando el triage pruebe que no cabe en esta slice.

`/next-slice` nunca invoca `closer`. El único comando manual posterior que debe ejecutar el usuario es:

```bash
/closer <TASK_ID>
```

## Follow-ups

- Defecto in-scope o pequeño fix dentro del `write_set`: developer/debugger/retest, no follow-up.
- Trabajo fuera de scope real: `/register-followup` con `--repair-decision followup_required|human_decision_required`, `--files-estimate`, `--fits-current-write-set` y triggers duros.
- Problema mecánico del orquestador: corrige/reintenta/bloquea, no follow-up de producto.

## macOS / case-sensitive

Mantén exactos los nombres de agentes (`slice-verifier`, no `slice_verifier` salvo normalización de trailer), skills, paths y MCP servers. En macOS con filesystem case-sensitive, `Scripts/Next-Wave.sh`, `Chrome-DevTools` o `MCP__browser` son errores, no aliases.


## Skills runtime runtime

This `SKILL.md` is the canonical Claude Code entrypoint for `/next-slice`. The project intentionally has one slash surface: project skills.

## Root-split / linked worktree guard

When a slice runs in a linked worktree, the worktree is only the code workspace. The scheduler truth remains in the canonical root returned by `scripts/ensure-task-worktree.sh --print-root`. Tracked compatibility blueprint memory JSON mirrors under `orchestrator-state/memory/` are classified as `local_commit_artifacts_only`, not split-brain. Do not inspect or mutate a local worktree `orchestrator-state/` as authority.

Before resuming a suspicious worktree, run:

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root)"
bash "$ROOT/scripts/repair-worktree-state.sh" --check "$PWD"
```

If it reports split-brain, archive the local state and resume from canonical:

```bash
bash "$ROOT/scripts/repair-worktree-state.sh" --apply "$PWD"
```

Never create per-file symlinks for `registry.json`, `runtime-state.json`, `task-dag.json` or task-packs. Use the canonical handoff/evidence paths injected by `SubagentStart`; if they are absolute, keep them absolute.
