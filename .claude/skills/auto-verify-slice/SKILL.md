---
name: "auto-verify-slice"
description: "Ejecuta verificación automática auxiliar de una slice, sin sustituir el gate humano-real de /verify-slice cuando el task-pack lo exige."
argument-hint: "<TASK_ID>"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# auto-verify-slice

This is the active Claude Code project skill for `/auto-verify-slice`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /auto-verify-slice <TASK_ID>

```bash
./scripts/auto-verify-slice.sh $ARGUMENTS
```

Uso activo: preparar o ampliar evidencia automatizada para `tester`/`slice-verifier`. No mueve a `done`, no invoca closer y no sustituye MCP visual/mobile cuando `verify_mode`, `journey_refs`, `ui` o `evidence_contract` declaran reproducción humana-real.

Debe leer task-pack y `resolved_specs`, escribir evidencia bajo `orchestrator-state/tasks/evidence/<TASK_ID>/`, y dejar claro qué verificaciones son automatizadas y cuáles siguen pendientes de `/verify-slice`.

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
