# Cheatsheet — orchestrator-AnyStack

## 1. Qué tienes que pasar a ChatGPT

Para preparar una aplicación nueva, pasa al modelo estos materiales:

| Material | Obligatorio | Qué es | Cómo lo usa el modelo |
|---|---:|---|---|
| Blueprint base, PRD o notas | sí | Tu intención funcional: producto, reglas, datos, roles, permisos, integraciones, lógica, restricciones y verificación. | Lo convierte o repara como `inputs/BLUEPRINT.md`. |
| ZIP de diseño/prototipo | no, recomendado si hay UI | ZIP exportado con HTML/CSS/JS, capturas, prototipo estático o diseño aproximado. | Extrae pantallas, rutas, layout, componentes, copy, navegación y estados UI. No lo copia como app. |
| Template de blueprint | sí | Normalmente `docs/templates/blueprint-gold/BLUEPRINT.template.md`. | Define la forma que debe respetar el modelo al generar `inputs/BLUEPRINT.md`. |
| Prompt 01 | sí | `docs/prompts/01-generate-blueprint-from-inputs.md` | Pide al modelo generar el blueprint completo. |
| Prompt 02 | sí antes de bootstrap | `docs/prompts/02-audit-blueprint-before-bootstrap.md` | Pide al modelo auditar y corregir el blueprint generado. |

El modelo no debe quedar limitado a un número fijo de phases, tareas o slices. Debe crear todas las slices necesarias y solo las necesarias, con dependencias explícitas, `write_set`, `conflict_group`, verificación real y descripciones suficientes.

## 2. Qué archivos sustituir en el ZIP del orquestador

Sustituye únicamente entradas humanas:

```text
inputs/BLUEPRINT.md              # obligatorio
inputs/design/<tu-diseno>.zip    # opcional/recomendado para UI
```

No sustituyas ni edites a mano:

```text
orchestrator-state/compiled/orchestrator-input.json
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/task-dag.json
orchestrator-state/tasks/task-packs/**
orchestrator-state/tasks/runtime-state.json
.claude/**
orchestrator/**
scripts/**
```

## 3. Dónde añadir el blueprint para que lo coja bootstrap

Pon el blueprint final aquí:

```text
inputs/BLUEPRINT.md
```

El flujo real es:

```text
inputs/BLUEPRINT.md
  -> ./scripts/compile-blueprint.sh
  -> orchestrator-state/compiled/orchestrator-input.json
  -> ./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
  -> orchestrator-state/tasks/registry.json
  -> orchestrator-state/tasks/task-dag.json
  -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```

`bootstrap-registry` no lee Markdown. Lee el JSON generado por `compile-blueprint`.

## 4. Flujo recomendado para generar el blueprint

1. Abre `docs/prompts/01-generate-blueprint-from-inputs.md`.
2. Pégalo en ChatGPT/Claude junto con tu blueprint base, adjunta el ZIP de diseño si existe y pega o referencia `docs/templates/blueprint-gold/BLUEPRINT.template.md`.
3. Guarda la respuesta completa como `inputs/BLUEPRINT.md`.
4. Abre `docs/prompts/02-audit-blueprint-before-bootstrap.md`.
5. Pégalo junto con el `inputs/BLUEPRINT.md` generado, el mismo ZIP de diseño y el template usado.
6. Sustituye `inputs/BLUEPRINT.md` por la versión corregida.
7. Ejecuta compile/bootstrap/checks.

## 5. Preparar runtime desde cero

Haz siempre esta cadena después de crear o cambiar `inputs/BLUEPRINT.md`. Puedes usar shell **o** slash skills; no hace falta ejecutar las dos variantes.

Opción shell determinista:

```bash
./scripts/reset-state.sh
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/next-wave.sh --limit 1
```

Opción Claude Code / skills:

```text
/compile-blueprint
/bootstrap-registry
/next-wave
```

Equivalencia exacta:

```text
/compile-blueprint    == ./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
/bootstrap-registry  == ./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
/next-wave           == ./scripts/next-wave.sh
```

`bootstrap-registry` no lee Markdown. Si `orchestrator-state/compiled/orchestrator-input.json` no existe, primero falta `/compile-blueprint`.

### Si ya hay slices cerradas y cambias el blueprint

`bootstrap-registry` regenera `registry.json`, `task-dag.json`, `runtime-state.json` y `task-packs` desde el compiled input. El runtime ahora rehidrata automáticamente los estados durables desde `orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json` después de bootstrap. Si detecta progreso local sin evento durable que lo restaure, bloquea en vez de resetear silenciosamente.

Flujo seguro para añadir/promover slices después de haber cerrado trabajo:

```bash
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/sync-lifecycle-events.sh --apply   # idempotente; bootstrap ya lo hace, útil como verificación explícita
./scripts/next-wave.sh --limit 1
```

No uses `--no-sync-lifecycle` ni `ORCHESTRATOR_ALLOW_BOOTSTRAP_LIFECYCLE_RESET=1` salvo mantenimiento intencional del runtime.

### Root split en worktrees

Si estás dentro de una worktree de slice, por ejemplo:

```text
<app>-worktrees/SLICE-F0-001
```

no diagnostiques el `orchestrator-state/` local de esa worktree como autoridad. La verdad compartida del scheduler vive en la raíz canónica. Para comprobarla:

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root)"
cd "$ROOT"
ls -la orchestrator-state/compiled/orchestrator-input.json orchestrator-state/tasks/registry.json orchestrator-state/tasks/task-dag.json
```

Los scripts `compile-blueprint`, `bootstrap-registry`, `reset-state`, `next-wave`, `next-slice` y `verify-slice` resuelven esa raíz canónica automáticamente cuando se lanzan desde una linked worktree.

## 6. Checks mínimos después del bootstrap

```bash
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-blueprint-lossless-flow.sh
./scripts/check-blueprint-machine-contract.sh
./scripts/check-task-dag.sh
./scripts/check-parallel-locks.sh
./scripts/check-memory-yaml.sh
./scripts/check-claude-adapter.sh
./scripts/check-skills-runtime.sh
./scripts/check-verify-surface.sh
./scripts/check-orchestrator-gaps.sh
```

## 7. Slash skills en Claude Code

```text
/compile-blueprint
/bootstrap-registry
/next-wave
/next-slice <TASK_ID>   # ejecuta developer/validator/tester y verify-slice automático si queda ready_for_close
/closer <TASK_ID>       # manual, después de verified_pending_close
/verify-journey <JOURNEY_ID>
/phase-gate <PHASE_ID>
/register-followup propose --origin-task <TASK_ID> --scope-classification <classification> --why-not-debugger <reason> --title <title> --severity <severity>
/promote-followup <FOLLOWUP_ID>
/revise-slice <TASK_ID>
/slice-maintain <TASK_ID>
/compact-agent-memory --all --apply --threshold-lines 250
```

## 8. Ejecución diaria del DAG

Después de compile/bootstrap, lista la siguiente wave desde la raíz canónica:

```bash
./scripts/next-wave.sh --limit 1
```

o con skill:

```text
/next-wave
```

Después, en Claude Code:

```text
/next-slice <TASK_ID>   # ejecuta planner -> developer ∥ researcher? -> validator ∥ tester -> debugger? -> verify-slice automático
/closer <TASK_ID>       # manual, después de verified_pending_close
```

Si `/next-wave` dice `Ready tasks: 0` pero sabes que el root canónico tiene registry/task-packs, revisa que no estés mirando la worktree local:

```bash
bash scripts/ensure-task-worktree.sh --print-root
```


## 8.1 Follow-ups correctos

Usa follow-ups solo para trabajo que no cabe razonablemente en la slice activa. Antes de abrir uno, diferencia:

- Si cabe en el `write_set` actual, toca pocos ficheros y no requiere nuevos IDs/dependencias/datos reales/decisión humana: **arréglalo en la slice** con developer/debugger/retest.
- Si requiere blueprint nuevo, superficie fuera del `write_set`, dependencia externa, datos reales ausentes o decisión humana: FU formal.

```bash
./scripts/register-followup-task.sh propose \
  --origin-task <TASK_ID> \
  --scope-classification <out_of_scope|missing_coverage|missing_real_data|external_dependency|future_enhancement|scope_expansion|blocked_by_human_decision> \
  --repair-decision <followup_required|human_decision_required> \
  --why-not-debugger "<razón concreta>" \
  --files-estimate <n|unknown> \
  --fits-current-write-set <yes|no|unknown> \
  --outside-current-write-set <yes|no|unknown> \
  --requires-blueprint-change <yes|no|unknown> \
  --requires-new-dependency <yes|no|unknown> \
  --requires-human-decision <yes|no|unknown> \
  --missing-real-data <yes|no|unknown> \
  --title "<título>" \
  --severity <blocker|critical|high|medium|low> \
  --verify "<evidencia mínima real>"
```

`in_scope_defect`, `fix_in_current_slice`, `debugger_retest` y problemas mecánicos de runtime están prohibidos como follow-up: vuelve a debugger/retest o corrige/reintenta dentro del mismo `TASK_ID`. Los follow-ups `blocker|critical|high` en estado `proposed` bloquean nuevas waves/claims hasta `/promote-followup <FOLLOWUP_ID>` o waiver humano:

```bash
./scripts/register-followup-task.sh waive <FOLLOWUP_ID> --reason "<decisión humana>"
```

`/promote-followup` no edita `registry.json` ni `task-dag.json`; crea una patch request para añadir la nueva slice/slices a `inputs/BLUEPRINT.md` y después recompilar/bootstrappear.

## 9. Tests durante una slice activa

Durante `/next-slice <TASK_ID>`, el tester debe ejecutar **tests de producto o de task-pack**, no la suite de self-tests del orquestador. No ejecutes desde una slice:

```bash
python -m pytest -q                 # si cae sobre los self-tests del orquestador
python3.13 scripts/run-tests-one-by-one.py tests/test_*.py
./scripts/run-all-tests.sh          # modo completo / sin argumentos
./scripts/run-golden-e2e.sh
./scripts/simulate-blueprint-to-claude-flow.sh
./scripts/reset-state.sh
```

Esos comandos son de mantenimiento del runtime: varios tests llaman a `reset-state.sh`, `compile-blueprint.sh` y `bootstrap-registry.sh`, por lo que pueden borrar handoffs/evidence/registry de una slice activa. El runtime los bloquea si detecta `CLAUDE_ACTIVE_TASK_ID`, `CLAUDE_TASK_ID` o una worktree `SLICE-*`, salvo override explícito de mantenedor. `./scripts/run-all-tests.sh lint` es estático/read-only y no resetea ni compila ni bootstrappea, pero sigue siendo un check de mantenimiento del orquestador, no un gate de producto de la slice.

Usa en su lugar los comandos declarados por el task-pack o el stack de la app, por ejemplo:

```bash
uv run pytest backend/tests/<area> -q
flutter test test/<area>
./scripts/check-verify-routing.sh <TASK_ID>
./scripts/check-runtime-logs.sh --task <TASK_ID> --mode hard-reset
```

`check-runtime-logs.sh --task <TASK_ID>` filtra `hook-errors.log` por la slice activa para que errores históricos de otra task no aborten mantenimiento/verificación. Sin `--task`, conserva el modo de mantenedor y revisa las últimas entradas globales.

Overrides sólo para mantenimiento del orquestador, fuera de una slice de producto:

```bash
ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE=1 python -m pytest -q tests/test_*.py
ORCHESTRATOR_ALLOW_DESTRUCTIVE_STATE_RESET=1 ./scripts/reset-state.sh
```

## 10. Tests con timeout por fichero

Linux/WSL2:

```bash
for t in tests/test_*.py; do
  echo "== $t"
  /usr/bin/timeout -k 10s 180s python3.13 -m pytest -q "$t"
done
```

macOS portable, sin depender de GNU `timeout`:

```bash
python3.13 scripts/run-tests-one-by-one.py --timeout 180 tests/test_*.py
```

No uses `pkill` global. Para limpiar, usa scripts acotados del orquestador.



## 11. Primeros gotchas Linux/macOS/WSL2

- El repo debe conservar LF. `.gitattributes` fuerza LF para `.sh`, `.py`, `.yaml`, `.json` y `.md`.
- Los entrypoints `scripts/*.sh`, `.claude/bin/*.sh|*.py`, `.claude/git-workflows/*.sh` y `.claude/enforcers/*.sh` deben tener bit ejecutable.
- En Windows usa WSL2 y clona dentro del filesystem Linux, no en `/mnt/c`, para evitar CRLF, metadatos NTFS y peor rendimiento de locks. Ejecuta `claude` dentro de WSL2.
- Usa Claude Code >= 2.1.170 con soporte de project skills, subagents, hooks y `Agent`; verifica con `claude --version` y `claude doctor` si el entorno parece antiguo.
- Los agentes no deben usar `model: inherit`: `fable[1m]` queda para developer, `opus[1m]` para main-orchestrator, `opus` para planning/architecture/validation/debug/verify y `sonnet` para testing, deploy, closer, research y revisión documental/visual; los checks lo validan.
- Si hay managed settings corporativos en Windows/WSL2, revisa que no sobrescriban `.claude/settings.json`, especialmente `permissions.defaultMode=bypassPermissions` y `CLAUDE_SPAWN_BUDGET=70`.
- Para slices UI registra un browser MCP real antes de verificar: `claude mcp list` debe mostrar `chrome-devtools`, `claude-in-chrome`, `agent360-browser-mcp` o `browser-mcp`; si falta, añádelo con `claude mcp add ...` siguiendo la instalación de tu MCP. Para Flutter mobile usa Dart/Flutter MCP. Slices no-UI no necesitan MCP visual y deben declarar `MCP_BROWSER: not_applicable:no_ui_surface`.
- `schema_version` es un identificador de forma de JSON/YAML; no representa una release vieja del orquestador.


Nota de permisos: si un checkout o ZIP pierde el bit ejecutable, ejecuta `bash ./scripts/fix-permissions.sh` antes de operar.

### Root-split sin split-brain

En `pr-flow`/`git-flow`, la worktree de la slice es solo workspace de código. El scheduler canónico vive siempre en la raíz devuelta por:

```bash
bash scripts/ensure-task-worktree.sh --print-root
```

Durante una slice activa, los subagentes deben escribir handoff/evidence en las rutas canónicas que imprime `SubagentStart`. Si esas rutas son absolutas, se conservan absolutas. No crees symlinks por fichero para `registry.json`, `runtime-state.json`, `task-dag.json` ni `task-packs`: `os.replace` puede clobberar el symlink y crear split-brain. Si `repair-worktree-state.sh --check` devuelve `Topology: local_commit_artifacts_only`, no hay split-brain: solo hay mirrors JSON de compatibilidad de blueprint en `orchestrator-state/memory/`.

Si una worktree existente ya tiene estado local divergente:

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root)"
bash "$ROOT/scripts/repair-worktree-state.sh" --apply "$PWD"
```

Eso archiva el `orchestrator-state/` local como `orchestrator-state.split-brain.<timestamp>` o `orchestrator-state.symlink.<timestamp>` y deja la worktree sin cerebro local. Revisa el archivo si necesitas recuperar prosa/evidencia, pero no restaures `registry.json`, `runtime-state.json`, `task-dag.json` ni `compiled/**`.

### Git hygiene and hook-safe cleanup

Do not include `Co-Authored-By: Claude ...` or Anthropic noreply trailers in commits. If the last local commit has one, amend the message before push. During `/closer`, do not remove the active task worktree directly; run `scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active  # task worktrees are deferred even when cleanup runs from canonical root; Stop/next-wave removes after done`. `active_deferred=1` is the safe path because `SubagentStop` still needs the checkout/session alive to record `done`; Stop/next-wave retries deferred cleanup from the canonical root.
