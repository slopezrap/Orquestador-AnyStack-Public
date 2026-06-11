---
name: "bootstrap-registry"
description: "Genera registry, task-dag y task-packs desde orchestrator-input.json con descriptions, dependency_rationale, depends_on_rationale, dependency_edges, resolved_dependencies y resolved_specs propagados. Funciona desde estado vacío si ya existe compiled input."
argument-hint: "[orchestrator-input.json]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# bootstrap-registry

Este skill es una excepción de arranque: debe funcionar aunque no exista `registry.json`, `task-dag.json` ni `task-packs/`. Su precondición no es “runtime bootstrapped”; su precondición es que exista `orchestrator-state/compiled/orchestrator-input.json`. Si falta, ejecuta primero `/compile-blueprint` o el script equivalente.

## Root split obligatorio

Si estás dentro de una worktree de slice, la verdad compartida del scheduler vive en la raíz canónica, no en la worktree. Resuelve raíz antes de bootstrappear:

```bash
BOOTSTRAP_ROOT="${CLAUDE_ORCHESTRATOR_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
ROOT="$(bash "$BOOTSTRAP_ROOT/scripts/ensure-task-worktree.sh" --print-root 2>/dev/null || bash "$BOOTSTRAP_ROOT/scripts/resolve-orchestrator-root.sh" "$BOOTSTRAP_ROOT" 2>/dev/null || printf '%s\n' "$BOOTSTRAP_ROOT")"
cd "$ROOT"
```

## Ejecución

Bootstrap runtime artifacts from compiled input.

```bash
./scripts/bootstrap-registry.sh $ARGUMENTS
./scripts/check-task-dag.sh
./scripts/check-task-descriptions.sh
./scripts/check-orchestrator-gaps.sh
```

When `$ARGUMENTS` is empty, run:

```bash
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-task-dag.sh
./scripts/check-task-descriptions.sh
./scripts/check-orchestrator-gaps.sh
```

## Lifecycle rehydration guard

`bootstrap-registry` is a generator, but it is no longer allowed to silently erase local lifecycle progress. After generating the registry/DAG/task-packs it automatically reapplies durable close signals from:

```text
orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json
```

If an existing registry contains progress such as `done`, `in_progress`, `ready_for_close` or `verified_pending_close` and there is no durable lifecycle event able to restore it, bootstrap stops with an error. Do not bypass this in normal model-driven work. For an intentional maintainer reset only, use:

```bash
ORCHESTRATOR_ALLOW_BOOTSTRAP_LIFECYCLE_RESET=1 ./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
```

Do not use `--no-sync-lifecycle` unless you also intend a maintainer reset; it is protected by the same guard when progress exists.

## Resultado esperado

```text
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/task-dag.json
orchestrator-state/tasks/runtime-state.json
orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
orchestrator-state/memory/**
orchestrator-state/agent-memory/**
```

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
