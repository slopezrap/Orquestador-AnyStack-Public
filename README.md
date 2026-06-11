# orchestrator-AnyStack

Runtime blueprint-first por DAG explícito para Claude Code. El operador prepara una entrada humana en `inputs/BLUEPRINT.md`; opcionalmente añade un ZIP/prototipo visual en `inputs/design/`; el compilador genera `orchestrator-input.json`; el bootstrap genera registry, DAG, task-packs y memoria; Claude Code ejecuta slices con project skills, subagentes, hooks, trailers, locks, verificación real y cierre por PR.

```text
inputs/BLUEPRINT.md + inputs/design/*.zip opcional
  -> ./scripts/compile-blueprint.sh
  -> orchestrator-state/compiled/orchestrator-input.json
  -> ./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
# bootstrap rehydrates lifecycle-events automatically if prior slices are already closed
  -> orchestrator-state/tasks/registry.json
  -> orchestrator-state/tasks/task-dag.json
  -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
  -> /next-wave
  -> /next-slice <TASK_ID>
  -> SubagentStart + subagentes
  -> CLAUDE_TRAILER
  -> SubagentStop
  -> verify-slice automático dentro de next-slice
  -> /closer <TASK_ID>
  -> done
```

## Uso rápido

Usa shell o skills; no hace falta ejecutar ambos caminos. Tras crear o cambiar `inputs/BLUEPRINT.md`:

```bash
./scripts/reset-state.sh
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-blueprint-lossless-flow.sh
./scripts/check-blueprint-machine-contract.sh
./scripts/check-task-dag.sh
./scripts/check-memory-yaml.sh
./scripts/check-claude-adapter.sh
./scripts/check-skills-runtime.sh
./scripts/check-verify-surface.sh
./scripts/next-wave.sh --limit 1
```

En Claude Code, la equivalencia es:

```text
/compile-blueprint
/bootstrap-registry
/next-wave
/next-slice <TASK_ID>   # incluye verify-slice automático si tester deja ready_for_close
/closer <TASK_ID>       # manual: el usuario valida antes de cerrar
/verify-journey <JOURNEY_ID>
/phase-gate <PHASE_ID>
/register-followup propose --origin-task <TASK_ID> --scope-classification <classification> --why-not-debugger <reason> --title <title> --severity <severity>
/promote-followup <FOLLOWUP_ID>
/revise-slice <TASK_ID>
/slice-maintain <TASK_ID>
/compact-agent-memory --all --apply --threshold-lines 250
```

## Invariantes

Root split: si estás dentro de `<app>-worktrees/<TASK_ID>`, el scheduler canónico sigue viviendo en la raíz principal. Los scripts de compile/bootstrap/wave resuelven esa raíz automáticamente; para comprobarla manualmente usa `bash scripts/ensure-task-worktree.sh --print-root`.

- La entrada humana ejecutable es `inputs/BLUEPRINT.md`.
- El ZIP de diseño ayuda a completar UX, pero no sustituye al blueprint y no se compila. El template `docs/templates/blueprint-gold/BLUEPRINT.template.md` define la forma esperada del `inputs/BLUEPRINT.md`.
- Los agentes no mutan lifecycle directamente: producen evidencia, handoff, report o memoria; `SubagentStop` valida trailers y aplica transiciones legales.
- No se editan a mano `orchestrator-input.json`, `registry.json`, `task-dag.json`, `runtime-state.json` ni task-packs.
- Cada task conserva `description`, `dependency_rationale`, `dependency_edges`, `resolved_specs`, `source_sections` y `blueprint_lossless_refs`.
- `journey_refs` no implica UI; `verification_surface` decide si la evidencia requiere browser/mobile MCP o backend/API/DB/worker/dependency/core.
- `closer` es el único rol que puede llevar una slice a `done`; en `pr-flow` exige PR mergeada, main canónico sincronizado y cleanup runtime.
- No ejecutes la suite de self-tests del orquestador durante una slice activa; usa tests de producto/task-pack. Los self-tests del runtime pueden resetear `orchestrator-state` y están bloqueados salvo override explícito de mantenedor.

## Documentación

- `docs/CHEATSHEET.md`: operación diaria, qué sustituir, dónde poner el blueprint y qué skills usar.
- `docs/ORCHESTRATOR.md`: manual canónico del runtime DAG.
- `docs/CALL_MATRIX.md`: matriz de cableado para borrar/mover con seguridad.
- `docs/prompts/`: prompts para generar y auditar `inputs/BLUEPRINT.md` desde blueprint + diseño.
- `docs/templates/`: plantillas neutrales de `inputs/BLUEPRINT.md` usadas por prompts, checks y tests.



## Flujo manual mínimo

En operación diaria el usuario debería lanzar solo:

```text
/next-wave
/next-slice <TASK_ID>
/closer <TASK_ID>
```

`/verify-slice` sigue existiendo como skill completa y puede ejecutarse manualmente para reparar/reintentar verificaciones, pero el camino normal la invoca automáticamente desde `/next-slice` cuando `tester` deja la slice en `ready_for_close`. `slice-maintain` y `compact-agent-memory` se ejecutan como housekeeping; no sustituyen trailers ni verificaciones.

## Plataformas y entrega

Soporte objetivo: Linux, macOS y Windows mediante WSL2. Usa Claude Code >= 2.1.170 dentro del entorno Unix del proyecto; en Windows usa WSL2 y lanza `claude` desde la distribución Linux, no desde PowerShell/CMD para este runtime. Clona en filesystem Unix/WSL, conserva LF y bits de ejecución. Si el checkout perdió permisos, ejecuta `bash ./scripts/fix-permissions.sh` antes de los checks. El paquete incluye `.gitattributes` para forzar LF en texto y marcar binarios. Para slices UI configura un browser MCP real antes de cerrar verificaciones visuales (`claude mcp list` debe mostrar un servidor aceptado como `chrome-devtools`, `claude-in-chrome`, `agent360-browser-mcp` o `browser-mcp`); slices sin UI usan modalidad backend con evidencia real. En entornos gestionados revisa que políticas globales de Claude Code no sobrescriban `.claude/settings.json`, especialmente `permissions.defaultMode` y `CLAUDE_SPAWN_BUDGET`.


## Agent model allocation

Project agents keep explicit role-optimized Claude Code aliases instead of `model: inherit`.

```text
fable[1m]: developer
opus[1m]: main-orchestrator
opus: planner, blueprint-reviewer, project-architect, validator, debugger, slice-verifier
sonnet: tester, deployer, closer, task-planner, document-analyzer, official-docs-researcher, screen-journey-reviewer
```

Run `./scripts/check-claude-adapter.sh` or `./scripts/check-unix-agent-runtime.sh` to catch drift.

## Linked worktrees and scheduler state

For branch-per-task workflows, a task worktree is only a code workspace. The canonical scheduler state stays in the main repository root that owns the shared `.git` directory. Hooks and scripts resolve that root automatically; subagents must not create local generated scheduler state or orchestrator-state symlinks inside the worktree. Runtime commands set both CLAUDE_WORKTREE_ROOT and CLAUDE_WORKSPACE_ROOT to the active checkout. Tracked compatibility blueprint memory JSON mirrors under `orchestrator-state/memory/` are not scheduler state; `repair-worktree-state.sh --check` reports them as `local_commit_artifacts_only` and `ensure-task-worktree.sh` must not block on them.

Use:

```bash
bash scripts/ensure-task-worktree.sh --print-root
bash scripts/repair-worktree-state.sh --check "<worktree>"
```

If a worktree already contains divergent core state, archive it with:

```bash
bash scripts/repair-worktree-state.sh --apply "<worktree>"
```

Never create per-file symlinks for `registry.json`, `runtime-state.json` or `task-dag.json`. Runtime writes are atomic and may replace those symlinks with real files.

### Git hygiene and hook-safe cleanup

Do not include `Co-Authored-By: Claude ...` or Anthropic noreply trailers in commits. If the last local commit has one, amend the message before push. During `/closer`, do not remove the active task worktree directly; run `scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active  # task worktrees are deferred even when cleanup runs from canonical root; Stop/next-wave removes after done`. `active_deferred=1` is the safe path because `SubagentStop` still needs the checkout/session alive to record `done`; Stop/next-wave retries deferred cleanup from the canonical root.

## Bootstrap lifecycle safety

`bootstrap-registry` is still a generator, but it now protects existing progress: after writing registry/DAG/task-packs it reapplies durable per-task close signals from `orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json`. If progress exists without a durable rehydration source, it fails instead of silently resetting statuses.

## Política anti-FU innecesario

Antes de abrir un follow-up, el runtime exige triage de reparabilidad. Si el hallazgo cabe en el `write_set` actual, toca pocos ficheros y no requiere nuevos IDs, dependencia externa, datos reales ausentes ni decisión humana, se arregla dentro de la slice activa mediante developer/debugger/retest. Los FUs quedan para scope real fuera de slice o cambios que deben entrar por `inputs/BLUEPRINT.md`.

