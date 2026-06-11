# inputs

This package is intentionally clean. Put your project blueprint at:

```text
inputs/BLUEPRINT.md
```

Optional design/prototype ZIPs can go under:

```text
inputs/design/
```

Then run:

```bash
./scripts/reset-state.sh
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
```

Después de bootstrap, usa `/next-wave`, `/next-slice <TASK_ID>` y `/closer <TASK_ID>`. Durante una slice activa, no uses los self-tests del orquestador como evidencia; ejecuta los tests de producto que declare el task-pack.

## Root-split / linked worktree guard

When a slice runs in a linked worktree, the worktree is only the code workspace. The scheduler truth remains in the canonical root returned by `scripts/ensure-task-worktree.sh --print-root`. Tracked compatibility blueprint memory JSON mirrors under `orchestrator-state/memory/` are classified as `local_commit_artifacts_only`, not split-brain. Do not inspect, mutate or symlink a local worktree `orchestrator-state/` as authority.

Before resuming a suspicious worktree, run:

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root)"
bash "$ROOT/scripts/repair-worktree-state.sh" --check "$PWD"
```

If it reports split-brain, archive the local state and resume from canonical:

```bash
bash "$ROOT/scripts/repair-worktree-state.sh" --apply "$PWD"
```

Never create per-file symlinks for `registry.json`, `runtime-state.json`, `task-dag.json` or task-packs. Use the canonical handoff/evidence paths injected by `SubagentStart`; if they are absolute, keep them absolute.
