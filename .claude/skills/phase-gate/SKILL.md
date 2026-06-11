---
name: "phase-gate"
description: "Comprueba si una fase compilada puede darse por cerrada."
argument-hint: "<PHASE_ID>"
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill
---
# phase-gate

This is the active Claude Code project skill for `/phase-gate`. It is self-contained and delegates directly to scripts, hooks, trailers and generated state.

# /phase-gate <PHASE_ID>

```bash
./scripts/phase-gate.sh $ARGUMENTS
```

A phase passes only when all tasks are `done` or explicitly waived by the accepted human process.

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
