---
name: "closer"
description: "Cierre manual de una slice ya verificada. Sólo corre después de /verify-slice con VERIFY_OUTCOME=verified; genera report, runtime snapshot, commit, Git workflow, pr-flow proof y cleanup."
argument-hint: "<TASK_ID>|--task <TASK_ID>  (o terminal con CLAUDE_ACTIVE_TASK_ID exportado)"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# closer

This is the active Claude Code project skill for `/closer`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /closer <TASK_ID>

## Propósito

Único punto manual para cerrar una slice en `verified_pending_close`:

```text
/next-slice <TASK_ID>  -> implementation/test -> ready_for_close
/verify-slice <TASK_ID> -> real verification   -> verified_pending_close
/closer <TASK_ID>      -> report + runtime snapshot + git workflow + cleanup -> done
```

`/closer` no implementa, no verifica visualmente y no corrige producto. Si falta verificación, vuelve a `/verify-slice`. Si hay defecto in-scope, vuelve a debugger/tester/verifier.

## Preflight obligatorio

```bash
./scripts/closer.sh <TASK_ID>
./scripts/check-handoff-contract.sh <TASK_ID> --require-ready-for-close --require-verify-slice --require-production-observability
./scripts/check-task-dag.sh
```

Lee:

- task-pack JSON/Markdown;
- handoff completo;
- evidence directory;
- `verify-slice` table/result;
- `registry.json`, `task-dag.json`, `runtime-state.json`;
- `.claude/orchestrator-contract.json` y `state-machine.yaml`;
- git workflow mode compilado desde stack.

## Contratos de cierre activos

Antes de emitir `done`, el closer debe probar:

```text
REPORT_READY: yes
BASELINE_SYNC_READY: yes
GIT_READY: yes
PUSH_READY: yes
GIT_WORKFLOW_READY: yes
RUNTIME_CLEANED: yes
DOCKER_RUNTIME_CLEANED: yes|not_applicable:no_compose_file
RANCHER_RUNTIME_CLEANED: yes|not_applicable:no_rancher_cleanup_cmd
DEV_PORTS_RELEASED: yes|not_applicable:no_port_files
WORKTREES_CLEANED: yes
```

En `pr-flow` también:

```text
PR_READY: yes
MERGED: yes
CANONICAL_MAIN_SYNCED: yes
```

Una PR abierta, merge queued, CI pendiente, branch no sincronizada o falta de `gh`/auth no cuenta como `done`; bloquea con `BLOCKER_REASON` y no muevas estado.

## Workflow Git

## pr-flow integrado

Usa siempre el plugin configurado:

```bash
./scripts/sync-runtime-snapshot.sh <TASK_ID>
./scripts/git-workflow.sh <TASK_ID>
```

En `pr-flow`, el flujo correcto es: rebase contra `origin/main`, push `--force-with-lease` de la rama de la task, crear/reusar PR con `gh`, habilitar merge squash/auto, esperar merge real, borrar rama remota cuando GitHub lo permita, y fast-forward del root canónico a `main`. Una PR creada, abierta, queued o con CI pendiente es transporte incompleto: `GIT_WORKFLOW_READY: blocked`, no `done`. No uses `git stash`, no hagas fallback manual a `git push origin main`, y no cambies de workflow salvo que el stack compilado lo declare.


Usa scripts, no skills improvisados:

```bash
./scripts/sync-runtime-snapshot.sh <TASK_ID>
./scripts/git-workflow.sh <TASK_ID>
./scripts/cleanup-slice-runtime.sh --task <TASK_ID> --apply --strict
./scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active
```

No uses `git stash`. No borres worktrees sucias. No hagas squash/rebase/merge manual fuera del workflow declarado. No borres ninguna worktree de la task antes de emitir el trailer: usa `cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active`. Con `--schedule-active`, el cleanup difiere toda worktree limpia que coincida con la task, aunque el comando se ejecute desde la raíz canónica y no pueda detectar el cwd activo; acepta `active_deferred=1` y deja una petición en `orchestrator-state/tasks/cleanup-requests/` para que el Stop hook/next-wave la retire después de que `SubagentStop` registre `done`. Si el workflow es `push-to-main`, el cierre aún exige commit/push y cleanup; si es `pr-flow`, exige PR merged y main synced.


## Runtime cleanup obligatorio

El cierre debe ejecutar el cleanup real antes de emitir `NEXT_STATUS: done`:

```bash
./scripts/cleanup-slice-runtime.sh --task <TASK_ID> --apply --strict
```

El cleanup del runtime debe probar, activo del runtime blueprint-first pero adaptado a `orchestrator-input.json`:

- `docker compose -p <compose_project> down -v --remove-orphans` si hay compose file;
- borrado de contenedores, redes, volúmenes e imágenes locales/labelled del project de la slice, nunca `docker system prune` global;
- liberación de `orchestrator-state/dev-ports/<compose_project>.env|json`;
- ejecución de `verification.rancher.cleanup_cmd` u `observability.rancher_cleanup_cmd` si el stack compilado declara limpieza Rancher;
- evidencia bajo `orchestrator-state/tasks/evidence/<TASK_ID>/runtime-cleanup/`;
- salida final con `RUNTIME_CLEANED`, `DOCKER_RUNTIME_CLEANED`, `RANCHER_RUNTIME_CLEANED` y `DEV_PORTS_RELEASED`.

Después ejecuta `./scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active`. `WORKTREES_CLEANED: yes` es válido cuando el script termina sin candidatos dirty/skipped, aunque haya diferido la worktree activa (`active_deferred=1`) para proteger `SubagentStop`. Si el cleanup falla por dirty/skipped, el closer debe emitir `OUTCOME: blocked`, `NEXT_STATUS: blocked`, `BLOCKER_REASON: cleanup_failed`; no crees follow-up de producto por un fallo mecánico de runtime.

## Journey gates

Si la task cierra journeys (`closes_journeys`/`journey_refs`), el closer debe registrar:

- `JOURNEY_VERIFIED_INLINE: <JID>` si ya existe `## verify-journey` verified;
- o `JOURNEY_PENDING_VERIFY: <JID>` para que `runtime-state.pending_journey_verifications` bloquee solo tasks de ese journey hasta `/verify-journey <JID>`.

## Trailer final de closer

```text
CLAUDE_TRAILER:
AGENT: closer
TASK_ID: <TASK_ID>
OUTCOME: committed
NEXT_STATUS: done
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
REPORT: orchestrator-state/tasks/reports/<TASK_ID>.md
REPORT_READY: yes
BASELINE_SYNC_READY: yes
GIT_READY: yes
PUSH_READY: yes
GIT_WORKFLOW_READY: yes
RUNTIME_CLEANED: yes
DOCKER_RUNTIME_CLEANED: yes|not_applicable:no_compose_file
RANCHER_RUNTIME_CLEANED: yes|not_applicable:no_rancher_cleanup_cmd
DEV_PORTS_RELEASED: yes|not_applicable:no_port_files
WORKTREES_CLEANED: yes
PR_READY: yes
MERGED: yes
CANONICAL_MAIN_SYNCED: yes
```

Blocked closer:

```text
CLAUDE_TRAILER:
AGENT: closer
TASK_ID: <TASK_ID>
OUTCOME: blocked
NEXT_STATUS: blocked
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
REPORT: orchestrator-state/tasks/reports/<TASK_ID>.md
BLOCKER_REASON: pr_not_merged|main_not_synced|missing_report|cleanup_failed|stale_verification
```

The `SubagentStop` hook validates all closure signals and may block/rewrite unsafe `done` attempts.

## macOS / case-sensitive

Paths, command names, agent names and MCP/tool strings are case-sensitive. Use exact filenames and names: `scripts/git-workflow.sh`, `.claude/agents/closer.md`, `AGENT: closer`, `Skill(closer *)` if referenced in permissions. Do not rely on macOS default case-insensitive behavior.


## Blueprint-first source chain

- Active source chain: `inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> task-pack -> resolved_specs`.
- The runtime is generated from `orchestrator-input.json`; do not read non-active source documents as active input.


## Skills runtime runtime

This `SKILL.md` is the canonical Claude Code entrypoint for `/closer`. The project intentionally has one slash surface: project skills.


## Git commit hygiene

Commit messages must not include `Co-Authored-By: Claude ...`, `Co-Authored-By: Claude Sonnet ...`, or any Anthropic noreply trailer. If such a trailer is already in the last local commit, amend the commit message before push/PR.
