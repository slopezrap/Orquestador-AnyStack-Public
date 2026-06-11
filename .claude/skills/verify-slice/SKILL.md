---
name: "verify-slice"
description: "Verificación humana-real post-slice. Hard reset/logs/MCP visual o mobile con datos reales/proporcionados. Deja la slice en verified_pending_close; el cierre lo invoca el usuario con /closer."
argument-hint: "<TASK_ID>|--task <TASK_ID>  (o terminal con CLAUDE_ACTIVE_TASK_ID exportado)"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# verify-slice

This is the active Claude Code project skill for `/verify-slice`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /verify-slice <TASK_ID>

## Propósito

Verifica una slice que ya está `ready_for_close`. No implementa producto y no hace commit. Si pasa, `slice-verifier` mueve a `verified_pending_close`; el usuario ejecuta después `/closer <TASK_ID>`. Puede ser invocada manualmente, pero el flujo normal la ejecuta automáticamente desde `/next-slice` cuando `tester` deja la task en `ready_for_close`.

## Invariante DAG

```text
MODO DAG ACTIVO: production = explicit_dag.
Unidad verificable = TASK_ID canónico del registry.
No existe modo DAG-disabled improvisado.
Todo subagente recibe TASK_ID + CLAUDE_TASK_PACK + resolved_specs + evidence_contract.
```

## Root/worktree gate

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root 2>/dev/null || pwd -P)"
bash "$ROOT/scripts/ensure-task-worktree.sh" --check-current <TASK_ID>
./scripts/verify-slice.sh <TASK_ID>
```

En `pr-flow`, verifica desde la worktree del `TASK_ID`. No verifiques una rama distinta de la que implementó developer.

## Flujo mecánico

```text
tester pass
 -> verify-slice-state router
 -> init verify handoff skeleton
 -> runtime hard reset/log helper
 -> check-verify-routing (UI visual vs non-UI journey dependency)
 -> slice-verifier
 -> screen-journey-reviewer solo si `verification_surface.requires_screen_journey_reviewer=true` o `verify_routing.screen_journey_reviewer_required=true`
 -> verified_pending_close
 -> /closer <TASK_ID> manual
```

`/verify-slice` nunca invoca `closer`.

## Contexto obligatorio

Lee:

1. `task-packs/<TASK_ID>.json|md`
2. `handoffs/<TASK_ID>.md`
3. `registry.json`, `task-dag.json`, `runtime-state.json`
4. `resolved_specs[].description/details/raw`
5. `acceptance`, `evidence_contract`, `verification_refs`, `arc42_refs`
6. `write_set`, `conflict_group`, `locks`, `parallel.safe_group`

## Router de estado y routing de verificación

Ejecuta antes de spawnear y después de cada ciclo verifier/debugger:

```bash
./scripts/verify-slice-state.sh <TASK_ID> --json
./scripts/check-verify-routing.sh <TASK_ID>
```

Interpretación:

- `invoke_slice_verifier`: lanza `slice-verifier`.
- `invoke_closer`: ya está verificada; no spawnees closer, muestra `/closer <TASK_ID>`.
- `invoke_debugger` o `invoke_debugger_or_register_followup`: debugger/retest si defecto in-scope.
- `wait_validator_tester`: todavía no verifiques.
- `blocked`: corrige blocker mecánico o pide acción humana.

`verification_surface` (task-pack/registry) y `verify_routing` (router runtime) separan las señales: `journey_refs` por sí solo NO exige MCP browser/mobile ni `screen-journey-reviewer`. Una slice backend/worker/integration/data que participa en un journey se verifica por API, logs, DB, worker output o contrato runtime con `MCP_BROWSER: not_applicable:no_ui_surface`. Solo se exige verificación visual cuando hay `logic.ui`, `SCR-*`, `route`, write-set frontend/mobile/web/UI, o un `VISUAL_CONTRACT_CHECK` explícito.

## Verificación humana-real obligatoria

`slice-verifier` debe ejecutar una reproducción real/proporcionada, no solo tests unitarios:

- hard reset del runtime cuando el stack lo declare;
- migraciones/carga de datos reales o proporcionados por el task-pack;
- ejecución del flujo de usuario o API real;
- logs front/back/DB/worker/queue/compose/k8s cuando aplique;
- evidencia persistente bajo `orchestrator-state/tasks/evidence/<TASK_ID>/`;
- tabla visible para el usuario: URL, qué probar, descripción, esperado, observado, pasa/no pasa;
- `NO_STUB_DATA_USED: yes`, `HUMAN_REPRODUCTION: yes`, `RUNTIME_LOGS_CHECKED: yes` cuando aplique.

## MCP visual/mobile, non-UI journeys y macOS case-sensitive

Primero lee `verification_surface` en el task-pack/registry y confirma con `verify_routing`. Si `visual_required=false`, no inventes navegador ni Flutter: usa evidencia API/backend/worker/DB/logs y registra `MCP_BROWSER: not_applicable:no_ui_surface`.

Para web/browser, cuando `visual_required=true` y `visual_mode=web`, MCPs aceptados y escritos exactamente en minúsculas:

```text
chrome-devtools
claude-in-chrome
agent360-browser-mcp
browser-mcp
```

Orden de elección: `chrome-devtools` aislado primero; luego `claude-in-chrome`; luego `agent360-browser-mcp`/`browser-mcp`. Si están listados pero no funcionan, bloquea con diagnóstico; no sustituyas por `curl` como cierre humano.

Para Flutter/mobile, solo cuando `visual_required=true` y `visual_mode=mobile`:

```text
dart
flutter
flutter-driver
```

con `VISUAL_CHECK_METHOD: simulator|emulator|device`. No cierres una slice mobile con verificación solo web.

Los MCP tools y matchers de hooks son case-sensitive y siguen `mcp__<server>__<tool>`. No escribas variantes como `ChromeDevTools`, `Browser_MCP`, `mcp__<server>__<tool>` con mayúsculas o prefijos MCP en mayúsculas.

## Runtime reset/log helper


Antes de verificar, si el stack usa Docker Compose, levanta o resetea el runtime aislado de la slice con Rancher/Docker:

```bash
./scripts/docker-hard-reset.sh --task <TASK_ID>
```

Si no hay compose file, el script debe declarar `DOCKER_HARD_RESET: skipped_no_compose_file`. Si hay compose pero Docker/Rancher no está disponible, bloquea como `runtime_unavailable` y no cierres con sólo tests.

Antes de `slice-verifier`:

```bash
./scripts/init-verify-slice-handoff.sh <TASK_ID>
./scripts/check-runtime-logs.sh --task <TASK_ID> --mode hard-reset
```

`check-runtime-logs.sh --task <TASK_ID>` filters hook errors to the active task. The wrapper records a warning instead of aborting solely on log-history noise; direct maintainer runs without `--task` still inspect the global log tail.

Este paso no es opcional. `scripts/verify-slice.sh` lo ejecuta sin `|| true`; si no se puede crear el skeleton `## verify-slice` en el handoff canónico, la verificación debe bloquearse como fallo mecánico antes de spawnear `slice-verifier`. Además, `SubagentStart` inicializa ese skeleton automáticamente cuando el agente es `slice-verifier`, para proteger invocaciones manuales o reparaciones que salten el wrapper.

Si Docker Compose aplica, el project name debe derivarse del `TASK_ID`/`COMPOSE_PROJECT_NAME` de runtime context y los puertos deben venir de `allocate_slice_ports.py`; `docker compose -p` no evita por sí solo colisiones de puertos host.



##  non-UI evidence matrix

If `verification_surface.requires_visual_mcp=false`, the slice still requires real verification. Read `verification_surface.evidence_matrix` and execute every row with `required=true`:

| Touched surface | Required real verification |
|---|---|
| Endpoint/service | hard reset when applicable -> live server -> real `httpx`/`curl`/CLI call -> response contract -> DB persistence if writes -> clean logs |
| DB/DDL/data | apply schema changes up to head -> inspect actual schema/tables/indexes/constraints -> idempotence -> rollback/down when reversible -> real rows/missing semantics |
| Pipeline/worker/queue | run the real worker/pipeline/consumer with real/provided input -> observe durable output -> worker/Docker/Rancher logs -> retry/backoff/idempotence when declared |
| Dependency runtime | run real install/sync such as `uv sync` -> import proof from real venv/runtime -> version and `__file__`/path proof -> lockfile check -> adjacent regression |
| Integration adapter | provider probe/contract call or explicit not-applicable reason -> auth/pagination/rate-limit/degradation/provider-health evidence -> redacted raw/evidence ref |
| Core/domain/application logic | real calculation/use-case with real/provided fixtures -> DR/UC invariant checks -> boundary/error cases -> anti-stub grep/check |
| Permission/state/error | legal and illegal transitions/gates -> expected block/error/degraded state -> audit/handoff/log proof |

Minimum proof for every non-UI slice:

```text
HARD_RESET_OR_NOT_APPLICABLE: yes
REAL_OR_PROVIDED_DATA_USED: yes
RUNTIME_COMMAND_OUTPUT_CAPTURED: yes
RUNTIME_LOGS_CHECKED: yes|not_applicable:<reason>
NO_STUB_DATA_USED: yes
MCP_BROWSER: not_applicable:no_ui_surface
```

Do not invoke browser/mobile MCP for `journey_backend_contract` unless a later UI slice or `/verify-journey` explicitly owns a UI route.

Minimum proof for every non-UI slice:

```text
HARD_RESET_OR_NOT_APPLICABLE: yes|not_applicable:<reason>
MCP_BROWSER: not_applicable:no_ui_surface
VISUAL_CHECK_METHOD: backend
REAL_OR_PROVIDED_DATA_USED: yes
REAL_DATA_SOURCE: <real data/migration/wheel/command source>
NO_STUB_DATA: yes
NO_STUB_DATA_USED: yes
FLOWS_TESTED: <real commands or flows executed>
DATA_SETUP: <reset/migrations/data/dependency setup>
DATA_CONTRACT_ROWS: <row-count|not_applicable:<reason>>
PERSISTED_DATA_OBSERVED: yes|not_applicable:<reason>
RUNTIME_COMMAND_OUTPUT_CAPTURED: yes
RUNTIME_LOGS_CHECKED: yes
ERROR_LOGS_STATUS: clean
RUNTIME_LOG_ERRORS: 0
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/slice-verifier.json
```

For `verified_pending_close`, the hook validates the `## verify-slice` handoff plus durable evidence. A backend/no-UI slice is blocked if it omits `MCP_BROWSER: not_applicable:no_ui_surface`, `VISUAL_CHECK_METHOD: backend`, real/provided data source, executed flows, data setup, persisted rows or explicit `not_applicable:<reason>`, clean logs and zero runtime log errors.



## Tabla obligatoria de resultado para el usuario

Antes del trailer final de `slice-verifier`, muestra una tabla compacta y honesta:

| Área verificada | Método/evidencia | Esperado | Observado | Estado | Follow-up |
|---|---|---|---|---|---|
| UI/backend/DB/logs/worker/dependency/core según la slice | comando real, paso MCP, query DB, log path o evidence file | contrato del task-pack | hecho observado | pass/fail/blocked | none o FU candidate |

Después de la tabla:

- Si todo está dentro de scope y falla, devuelve `issues_found -> needs_debug`.
- Si parece fuera de scope real, propón FU sólo después de triage de reparabilidad: `scope_classification`, `repair_decision`, `why_not_debugger`, `files_estimate`, `fits_current_write_set`, triggers duros, título, severidad y verify mínimo. Si cabe en pocos ficheros dentro del write_set actual, manda a debugger/retest.
- Si faltan datos/entorno reales, bloquea con razón concreta.
- No reduzcas verify-slice a tests unitarios o texto declarativo.

## Trailer de slice-verifier

```text
CLAUDE_TRAILER:
AGENT: slice-verifier
TASK_ID: <TASK_ID>
OUTCOME: verified
NEXT_STATUS: verified_pending_close
VERIFY_OUTCOME: verified
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/slice-verifier.json
MCP_BROWSER: chrome-devtools|claude-in-chrome|agent360-browser-mcp|browser-mcp|not_applicable:flutter_mobile|not_applicable:no_ui_surface
REAL_USER_VERIFIED: yes
NO_STUB_DATA_USED: yes
RUNTIME_LOGS_CHECKED: yes
```

Issues:

```text
CLAUDE_TRAILER:
AGENT: slice-verifier
TASK_ID: <TASK_ID>
OUTCOME: issues_found
NEXT_STATUS: needs_debug
VERIFY_OUTCOME: issues_found
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/slice-verifier.json
```

Blocked:

```text
CLAUDE_TRAILER:
AGENT: slice-verifier
TASK_ID: <TASK_ID>
OUTCOME: blocked
NEXT_STATUS: blocked
VERIFY_OUTCOME: blocked
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/slice-verifier.json
BLOCKER_REASON: browser_mcp_unavailable|flutter_mobile_mcp_unavailable|runtime_unavailable|missing_real_data
```

## UI/journey review

Invoca `screen-journey-reviewer` info-only solo cuando `verification_surface.requires_screen_journey_reviewer=true` o `verify_routing.screen_journey_reviewer_required=true`: UI/route/visual surface real o cierre de journey que deba revisar el recorrido. No fuerces Flutter/mobile/web para slices `journey_backend_contract` o `not_applicable:no_ui_surface`; No fuerces Flutter/mobile/web por mera presencia de `journey_refs`; no lo invoques por mera presencia de `journey_refs`; una dependencia backend/non-UI de un journey no tiene pantalla que abrir. Si recomienda cambios in-scope o pequeños dentro del write_set, manda a debugger/retest; si detecta fuera de scope real, registra FU con triage completo (`repair_decision`, `why_not_debugger`, `files_estimate`, triggers duros).

## Preparar cierre manual

Cuando el handoff contiene tester pass + verify-slice verified:

```bash
./scripts/check-handoff-contract.sh <TASK_ID> --require-ready-for-close --require-verify-slice --require-production-observability
```

Si pasa, resume evidencia y pide al usuario:

```text
/closer <TASK_ID>
```

No spawnees `closer` desde aquí.


## Blueprint-first source chain

- Active source chain: `inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> task-pack -> resolved_specs`.


## Skills runtime runtime

This `SKILL.md` is the canonical Claude Code entrypoint for `/verify-slice`. The project intentionally has one slash surface: project skills.
