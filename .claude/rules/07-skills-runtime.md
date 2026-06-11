# 07 - Skills runtime

Project skills under `.claude/skills/<name>/SKILL.md` are the only Claude Code slash entrypoints for this orchestrator profile.

Claude Code resolves the slash name from the skill directory name, so `.claude/skills/next-slice/SKILL.md` is invoked as `/next-slice`. Do not create or depend on alternate Markdown slash Markdown files.

## Active entrypoints

```text
/compile-blueprint
/bootstrap-registry
/next-wave
/next-slice <TASK_ID>
/verify-slice <TASK_ID>
/closer <TASK_ID>
/verify-journey <JOURNEY_ID> [--verified|--waived|--issues-found]
/phase-gate <PHASE_ID>
/register-followup propose --origin-task <TASK_ID> --scope-classification <classification> --why-not-debugger <reason> --title <title> --severity <severity>
/promote-followup <FOLLOWUP_ID>
/revise-slice <TASK_ID>
/slice-maintain <TASK_ID>
```

## Skill file contract

Every `SKILL.md` must contain valid YAML frontmatter with:

```yaml
description: "what this skill does and when to use it"
user-invocable: true
```

Manual workflow skills with lifecycle, filesystem, git, Docker/Rancher or verification side effects must set:

```yaml
disable-model-invocation: false
```

That keeps side effects user-timed while preserving `/skill-name` invocation. Safety remains enforced by hooks, trailers, locks, `.claude/orchestrator-contract.json` and `orchestrator/rules/state-machine.yaml`.

## Required body content

A project skill must state:

- the primary script or runtime action;
- the source chain `inputs/BLUEPRINT.md -> orchestrator-input.json -> registry.json -> task-dag.json -> task-packs`;
- lifecycle/trailer reminders when applicable;
- production evidence rules;
- no manual edits to generated state.

## Single skill layer

Do not create a parallel Markdown slash directory. Do not ask agents to read separate slash files. If a workflow needs a new Claude Code slash entrypoint, create `.claude/skills/<name>/SKILL.md` and, when deterministic execution is needed, delegate from that skill directly to `./scripts/*.sh`.
