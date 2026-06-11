---
name: "next-wave"
description: "Lista la wave DAG actual desde el registry blueprint-first: tasks ready independientes, deps, conflictos, locks, puertos y skills para terminales paralelos. No implementa ni spawnea agentes."
argument-hint: "[--limit N] [--phase PHASE_ID] [--json]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# next-wave

This is the active Claude Code project skill for `/next-wave`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /next-wave

## Realidad skills runtime

Este skill ejecuta la semántica operativa blueprint-first. La fuente activa no son fuentes secundarias antiguas ni un checklist Markdown:

```text
inputs/BLUEPRINT.md
 -> orchestrator-state/compiled/orchestrator-input.json
 -> orchestrator-state/tasks/registry.json
 -> orchestrator-state/tasks/task-dag.json
 -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```

La unidad ejecutable es siempre un `TASK_ID` canónico compilado desde `registry.slices[]`. No inventes slices efímeras, no uses selectors implícitos y no hagas fallback a modo DAG-disabled.

## Root split obligatorio

- Root canónico: `$CLAUDE_ORCHESTRATOR_ROOT` o el resultado de `scripts/ensure-task-worktree.sh --print-root`.
- Worktree de slice: `$CLAUDE_WORKTREE_ROOT` y `$CLAUDE_WORKSPACE_ROOT`, creados por el skill de terminal que imprime `next-wave` cuando `git_workflow.mode` es `pr-flow` o `git-flow`.
- Runtime generado: leer desde `$CLAUDE_ORCHESTRATOR_ROOT/orchestrator-state/tasks/`.
- Handoff/evidence/report/task-pack local: usar la worktree activa si existe; si falta el pack local, usar fallback al root canónico.
- No registres follow-ups por fallos mecánicos del orquestador: root stale, pack ausente en worktree pero existente en root, cleanup pendiente, CI queued, PR abierta, lint flake o lock stale diagnosticable.

## Ejecución mecánica recomendada

```bash
./scripts/next-wave.sh $ARGUMENTS
```

Por defecto imprime Markdown humano con skills copy/paste. Usa `--json` solo para CI/tests/tooling:

```bash
./scripts/next-wave.sh --limit 1 --json
```

El script hace promoción `todo -> ready` si procede, valida `explicit_dag`, aplica journey gates, filtra conflictos activos y selecciona una wave no conflictiva por `write_set`, `conflict_group`, `parallel.safe_group` y locks. No implementa, no reclama tasks y no invoca agentes.

## Lectura obligatoria si el script necesita interpretación

1. `.claude/CLAUDE.md`
2. `.claude/rules/02-phase-execution.md`
3. `.claude/rules/04-traceability.md`
4. `.claude/rules/05-runtime-write-contract.md`
5. `.claude/rules/07-skills-runtime.md`
6. `.claude/orchestrator-contract.json`
7. `orchestrator/rules/state-machine.yaml`
8. `orchestrator-state/tasks/registry.json`
9. `orchestrator-state/tasks/task-dag.json`
10. `orchestrator-state/tasks/runtime-state.json`

## Gates antes de listar

- `task_dag.mode` debe ser `explicit_dag`.
- Solo se considera la earliest incomplete phase salvo `--phase` explícito.
- Si `runtime-state.pending_journey_verifications` no está vacío, DAG-only difiere únicamente tasks que referencian esos journeys y lista `/verify-journey <JID>`.
- Si hay follow-ups `high|critical|blocker` en estado `proposed`, no deben abrirse waves que dependan de esa deuda; promueve o waiver humano explícito.
- Una task es candidata si `status == ready`, deps `done`, no está claimed/in_progress, no tiene blockers activos y no comparte superficie de escritura/conflicto con otra task seleccionada.
- Conflictos típicos: misma migración, mismo router/API family, misma pantalla, mismo theme/design system, mismo handler de estado, misma config global, mismo generated artifact, mismo compose stack o misma carga global de datos.

## Formato de salida obligatorio

El modo humano debe conservar esta forma operativa:

```md
# DAG wave propuesta

> **Antes de reclamar una task en este terminal**, limpia las 5 variables de scope...

- DAG mode: `explicit_dag`
- Phase: `<PHASE_ID>`
- Ready nodes total: `<N>`
- Ready nodes seguros: `<N>`
- Recomendación de paralelo: `<N>` terminales

| TASK_ID | Título | Depends on | Conflict groups | Write set | Skill terminal |
|---|---|---|---|---|---|
```

El skill terminal debe:

1. limpiar `CLAUDE_ACTIVE_TASK_ID`, `CLAUDE_TASK_PACK`, `CLAUDE_WORKTREE_ROOT`, `CLAUDE_WORKSPACE_ROOT`, `CLAUDE_ORCHESTRATOR_ROOT`, `COMPOSE_PROJECT_NAME` y `CLAUDE_COMPOSE_PROJECT_NAME`;
2. resolver root canónico con `ensure-task-worktree.sh --print-root`;
3. crear/localizar worktree por task si aplica;
4. entrar en esa worktree;
5. resolver `CLAUDE_TASK_PACK` local o fallback al root;
6. ejecutar `.claude/bin/runtime_context.py --print-env`;
7. exportar `CLAUDE_ORCHESTRATOR_ROOT`, `CLAUDE_WORKTREE_ROOT`, `CLAUDE_WORKSPACE_ROOT`, `CLAUDE_ACTIVE_TASK_ID`, `CLAUDE_TASK_PACK`, `CLAUDE_COMPOSE_PROJECT_NAME`;
8. ejecutar `.claude/bin/allocate_slice_ports.py --env-file` y sourcear el env;
9. mostrar el skill final:

```bash
claude --agent main-orchestrator --permission-mode bypassPermissions "/next-slice <TASK_ID>"
```

## Paralelismo

- `recommended_parallel_terminals` es un máximo seguro, no una obligación.
- No ejecutes en paralelo fuera de lo que imprime el script.
- `claim_task` revalida deps/conflictos bajo lock, así que la skill puede bloquear si otra terminal reclamó una superficie en conflicto.
- Locks son POSIX `fcntl.flock` sobre `.lock` adyacentes, válidos en Linux/Ubuntu, macOS/Darwin y WSL2 como entorno Linux. No dependas de comportamiento case-insensitive.

## macOS / case-sensitive

Trata nombres de agentes, skills, skills y MCP tools como case-sensitive. Claude Code usa strings exactos para herramientas, permisos, matchers y MCPs; los MCP tools siguen `mcp__<server>__<tool>`. Usa nombres lower-hyphen/lowercase: `chrome-devtools`, `claude-in-chrome`, `agent360-browser-mcp`, `browser-mcp`, `dart`, `flutter`, `flutter-driver`. No escribas variantes como `Chrome-DevTools`, `Browser_MCP` o `MCP__...`.

## Prohibido

- No abras terminales tú.
- No spawnees agentes.
- No cambies registry manualmente.
- No uses MCP visual desde `/next-wave`; los MCPs pertenecen al preflight de `/verify-slice` y `slice-verifier`.
- No reinterpretes la wave si `scripts/next-wave.sh` dice que no hay nodos seguros.

## Blueprint authority chain

```text
inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> orchestrator-state/tasks/task-dag.json -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```

Use task `title`, `description`, `dependency_rationale`, `depends_on_rationale`, `dependency_edges`, `resolved_dependencies[].description` and `resolved_specs[].description/details/raw/source_ref` as human scope. IDs alone are navigation, not implementation scope. Use the compiled blueprint chain directly.

## Runtime guardrails

- Do not hand-edit generated compiled/runtime artifacts.
- Lifecycle mutations go through hooks, locks, `CLAUDE_TRAILER`, `.claude/orchestrator-contract.json` and `orchestrator/rules/state-machine.yaml`.
- Respect `write_set`, `read_set`, `conflict_group`, `parallel.safe_group` and POSIX lock metadata.
- No fake/mock/stub data can be used as production evidence.
- Keep macOS/Linux exact-case names for agents, skills, MCP servers, tools and paths.
