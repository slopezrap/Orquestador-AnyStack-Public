---
name: "verify-journey"
description: "Lista o resuelve gates de journey compilados desde inputs/BLUEPRINT.md; mantiene el bloqueo selectivo del DAG para journeys pendientes."
argument-hint: "<JOURNEY_ID> [--verified|--waived|--issues-found]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# verify-journey

This is the active Claude Code project skill for `/verify-journey`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /verify-journey <JOURNEY_ID> [--verified|--waived|--issues-found]

```bash
./scripts/verify-journey.sh $ARGUMENTS
```

Semántica heredada/adaptada:

- Sin flag: lista closures y gates pendientes.
- `--verified`: limpia el gate tras evidencia de journey real.
- `--waived`: limpia con waiver humano explícito.
- `--issues-found`: mantiene o añade el gate pendiente.

`screen-journey-reviewer` es info-only. No emite `NEXT_STATUS`; lifecycle de slices lo controlan tester, slice-verifier y closer. `/next-wave` debe diferir solo tasks que referencian el journey pendiente, no todo el DAG.

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
