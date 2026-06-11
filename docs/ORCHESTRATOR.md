# orchestrator-AnyStack runtime

## 1. Modelo mental

orchestrator-AnyStack es un runtime blueprint-first para Claude Code. La entrada humana canónica vive en `inputs/BLUEPRINT.md`; el ZIP de diseño vive en `inputs/design/` y sirve solo como apoyo visual para preparar o auditar el blueprint; el estado generado vive en `orchestrator-state/`; la ejecución se hace por DAG explícito y las transiciones de lifecycle se validan con hooks.

```text
inputs/BLUEPRINT.md + inputs/design/*.zip opcional
  -> ./scripts/compile-blueprint.sh
  -> orchestrator-state/compiled/orchestrator-input.json
  -> ./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
  -> orchestrator-state/tasks/registry.json
  -> orchestrator-state/tasks/task-dag.json
  -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
  -> /next-wave
  -> /next-slice <TASK_ID>
  -> SubagentStart
  -> subagentes
  -> CLAUDE_TRAILER
  -> SubagentStop
  -> debugger si hace falta; si queda ready_for_close, slice-maintain + verify-slice automático
  -> /closer <TASK_ID>
  -> done
```

El chat no decide el estado. Los agentes producen handoff, evidencia, report o memoria propia. `SubagentStop` valida el trailer contra `.claude/orchestrator-contract.json` y `orchestrator/rules/state-machine.yaml`; solo entonces escribe `registry.json` y `runtime-state.json` bajo lock.

## 2. Matriz de superficies activas

| Superficie | Ruta | Quién la usa | Puede mutar estado |
|---|---|---|---|
| Blueprint humano | `inputs/BLUEPRINT.md` | operador, compiler, blueprint-reviewer, prompts | no durante una slice activa |
| Diseño de apoyo | `inputs/design/*.zip` | modelo que genera/audita blueprint | no; no lo compila bootstrap |
| Compiled input | `orchestrator-state/compiled/orchestrator-input.json` | bootstrap, checks, task-pack builder | solo compiler |
| Registry | `orchestrator-state/tasks/registry.json` | next-wave, claim, hooks, checks | solo scripts/hooks bajo lock |
| DAG | `orchestrator-state/tasks/task-dag.json` | next-wave, claim, checks | solo bootstrap |
| Task-pack | `orchestrator-state/tasks/task-packs/<TASK_ID>.json|md` | agentes y hooks | solo bootstrap/claim |
| State machine | `orchestrator/rules/state-machine.yaml` | hooks, checks, tests | configuración estática |
| Contract | `.claude/orchestrator-contract.json` | agents, hooks, checks | configuración estática |
| Project skills | `.claude/skills/<name>/SKILL.md` | slash entrypoints | delegan a scripts |
| Subagentes | `.claude/agents/*.md` | Agent tool y hooks | solo mediante trailer |
| Hooks | `orchestrator/hooks/*.py`, `.claude/bin/hook_*.py` | Claude Code settings | sí, en scope definido |
| Scripts | `scripts/*.sh`, `.claude/bin/*.py` | skills, CI, operador, hooks | sí, si son entrypoints del runtime |
| Memoria YAML | `orchestrator-state/memory/**`, `orchestrator-state/agent-memory/**` | SessionStart, SubagentStart, SubagentStop, agents | hooks/scripts y memoria propia del agente |
| Handoff/evidence | `orchestrator-state/tasks/handoffs/**`, `orchestrator-state/tasks/evidence/**` | developer/tester/verifier/closer/hooks | agentes según rol |

## 3. Máquina de estados

La máquina canónica vive en `orchestrator/rules/state-machine.yaml`.

```text
todo -> ready -> claimed -> in_progress -> validator_tester_pending -> ready_for_close -> verified_pending_close -> done
validator_tester_pending -> needs_debug
needs_debug -> validator_tester_pending
* -> blocked cuando el contrato del rol lo permite
```

Roles mutadores: `developer`, `debugger`, `tester`, `slice-verifier`, `deployer`, `closer`.

Roles informativos: `main-orchestrator`, `planner`, `task-planner`, `blueprint-reviewer`, `document-analyzer`, `project-architect`, `official-docs-researcher`, `validator`, `screen-journey-reviewer`.

`closer` es el único que puede cerrar en `done`.

## 4. Agentes y subagentes

Todos los agentes apuntan a `.claude/orchestrator-contract.json`, `orchestrator/rules/state-machine.yaml`, `orchestrator-state/tasks/task-packs/<TASK_ID>.json|md`, `orchestrator-state/tasks/slices/<TASK_ID>.yaml` y `orchestrator-state/agent-memory/<agent>/MEMORY.yaml`.


### Agent model allocation

Agent frontmatter must use explicit role-optimized aliases; do not use `model: inherit` for project agents.

```text
fable[1m]: developer
opus[1m]: main-orchestrator
opus: planner, blueprint-reviewer, project-architect, validator, debugger, slice-verifier
sonnet: tester, deployer, closer, task-planner, document-analyzer, official-docs-researcher, screen-journey-reviewer
```

`check-claude-adapter` and `check-unix-agent-runtime` enforce this matrix so model drift is caught before execution.


## 5. Skills y scripts

La superficie slash del proyecto es `.claude/skills/<skill>/SKILL.md`. Las skills mantienen `disable-model-invocation: false` para que el Skill tool pueda invocarlas desde main y subagentes; las skills con efectos laterales delegan al script correspondiente y la seguridad la aplican scripts/hooks.

El flujo manual normal queda reducido a `/next-wave`, `/next-slice <TASK_ID>` y `/closer <TASK_ID>`. `verify-slice` sigue existiendo como skill completa, pero `/next-slice` la invoca automáticamente cuando `tester` deja la slice en `ready_for_close`. `slice-maintain` y `compact-agent-memory` son housekeeping automático y también permanecen disponibles como skills manuales para diagnóstico.

## 6. Hooks y memoria

`.claude/settings.json` cablea `SessionStart`, `SubagentStart`, `SubagentStop`, `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop` y `ConfigChange`. La memoria de agentes se compacta automáticamente antes de `/next-wave` y antes de una compactación de Claude Code (`PreCompact`). El operador puede forzar el mismo flujo con `/compact-agent-memory`.

## 7. Verify-slice

`journey_refs` no implica UI. La superficie se decide por `verification_surface` y `evidence_contract`.

UI/browser/mobile exige reproducción humana-real con MCP visual o Dart/Flutter MCP. Backend/no-UI no bloquea por falta de navegador, pero debe declarar:

```text
MCP_BROWSER: not_applicable:no_ui_surface
VISUAL_CHECK_METHOD: backend
NO_STUB_DATA: yes
REAL_DATA_SOURCE: <datos, migraciones, wheels o comandos reales>
FLOWS_TESTED: <flujos/comandos reales>
DATA_SETUP: <setup real>
DATA_CONTRACT_ROWS: <real> | not_applicable:<razón>
PERSISTED_DATA_OBSERVED: <real> | not_applicable:<razón>
ERROR_LOGS_STATUS: clean
RUNTIME_LOG_ERRORS: 0
```

## 8. Locks y paralelismo

`/next-wave` selecciona solo nodos con dependencias `done`, sin blockers de journey y sin conflictos activos de `write_set` o `conflict_group`. `claim_task` repite la comprobación bajo lock antes de reservar una task. Los locks son POSIX `fcntl.flock`, compatibles con Linux, Darwin/macOS y WSL2 ejecutado como Linux.

## 8.1 Follow-ups

Los follow-ups nacen solo como YAML propuesto bajo `orchestrator-state/tasks/follow-ups/`. Sirven para trabajo que no cabe razonablemente en la slice activa: fuera de scope, cobertura ausente que exige blueprint nuevo, datos reales ausentes, dependencia externa, scope expansion, write_set externo o decisión humana. No son una vía para saltarse debugger/retest.

La propuesta exige triage de reparabilidad (`repair_decision`, `files_estimate`, `fits_current_write_set` y triggers duros). Si el hallazgo cabe en el write_set actual, toca pocos ficheros y no requiere nuevos IDs/dependencias/datos/decisión humana, el runtime rechaza el FU y manda a developer/debugger/retest dentro del mismo `TASK_ID`.

La promoción crea `orchestrator-state/tasks/source-doc-patches/<FOLLOWUP_ID>.md`; el cambio aceptado se añade a `inputs/BLUEPRINT.md` y bootstrap regenera registry/DAG.

## 8.2 Plataformas

El runtime soporta Linux, macOS y Windows mediante WSL2. Los scripts son Bash/Python sobre entorno Unix; usan locks POSIX `fcntl.flock`, rutas exact-case y PATH con `~/.rd/bin`, `/opt/homebrew/bin` y `/usr/local/bin`. PowerShell/CMD nativo no es el shell objetivo. En Windows, ejecuta Claude Code dentro de WSL2 y clona el repositorio en el filesystem Linux; `.gitattributes` conserva LF y los checks validan bits ejecutables de entrypoints. En equipos gestionados revisa que settings globales de Claude Code no sustituyan el scope de proyecto; este runtime espera que `.claude/settings.json` gobierne hooks, permisos y spawn budget.

## 9. Cierre

`/closer <TASK_ID>` solo opera sobre `verified_pending_close`. En `pr-flow`, `done` exige report, Git workflow, PR mergeada, main canónico sincronizado y cleanup runtime/worktrees.

## 10. Checks de salud

```bash
./scripts/compile-blueprint.sh
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-claude-adapter.sh
./scripts/check-skills-runtime.sh
./scripts/check-task-dag.sh
./scripts/check-parallel-locks.sh
./scripts/check-memory-yaml.sh
./scripts/check-blueprint-lossless-flow.sh
./scripts/check-blueprint-machine-contract.sh
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-verify-surface.sh
./scripts/check-git-pr-flow.sh
./scripts/orchestrator-doctor.sh
./scripts/simulate-blueprint-to-claude-flow.sh
./scripts/run-golden-e2e.sh
```


## Active-slice test safety

During an active `/next-slice <TASK_ID>`, tester and verifier must run product/task-pack tests only. The orchestrator maintainer self-tests (`tests/test_*.py`, `scripts/run-all-tests.sh` in full/no-argument mode, `scripts/run-golden-e2e.sh`, `scripts/simulate-blueprint-to-claude-flow.sh`) can reset/compile/bootstrap scheduler state and therefore are blocked when `CLAUDE_ACTIVE_TASK_ID`, `CLAUDE_TASK_ID` or a `SLICE-*` worktree is detected, unless a maintainer sets the explicit override env vars. `scripts/run-all-tests.sh lint` is read-only/static and does not reset, compile or bootstrap state; it is still a maintainer/runtime check, not a substitute for product task-pack tests.

## Linked worktree state topology

The scheduler has exactly one authoritative state directory: `<canonical-root>/orchestrator-state`. A linked task worktree must not carry its own scheduler state or orchestrator-state symlink. `ensure-task-worktree.sh` provisions/checks this topology and `repair-worktree-state.sh` archives local divergent state instead of deleting it. Older projects may still have tracked blueprint memory JSON mirrors under `orchestrator-state/memory/`; those are classified as `local_commit_artifacts_only`, not split-brain.

`SubagentStart` prints canonical handoff/evidence paths. In a linked worktree those paths may be absolute; agents should preserve them. `git-add-slice.sh` mirrors selected canonical evidence into the branch only during closer so PR-flow can transport durable audit artifacts without letting hooks mutate a local registry.

### Git hygiene and hook-safe cleanup

Do not include `Co-Authored-By: Claude ...` or Anthropic noreply trailers in commits. If the last local commit has one, amend the message before push. During `/closer`, do not remove the active task worktree directly; run `scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active  # task worktrees are deferred even when cleanup runs from canonical root; Stop/next-wave removes after done`. `active_deferred=1` is the safe path because `SubagentStop` still needs the checkout/session alive to record `done`; Stop/next-wave retries deferred cleanup from the canonical root.
