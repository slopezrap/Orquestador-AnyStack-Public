---
name: "check-skills-runtime"
description: "Validate the skills runtime Claude Code runtime: single skill slash surface, canonical project skills, exact-case tools/MCP names, hooks, scripts and source-chain tokens."
argument-hint: ""
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Skill
---

# check-skills-runtime

Run the skills runtime audit:

```bash
./scripts/check-skills-runtime.sh $ARGUMENTS
```

The active source chain is:

```text
inputs/BLUEPRINT.md -> orchestrator-state/compiled/orchestrator-input.json -> orchestrator-state/tasks/registry.json -> orchestrator-state/tasks/task-dag.json -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
```

This project intentionally has no alternate Markdown slash markdown surface. Project skills under `.claude/skills/<name>/SKILL.md` are the only Claude Code slash entrypoints for orchestrator workflows. Keep `resolved_specs`, `source_sections`, `blueprint_lossless_refs`, hooks, trailers, locks and the state machine unchanged.
