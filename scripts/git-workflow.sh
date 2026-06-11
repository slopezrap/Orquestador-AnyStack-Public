#!/usr/bin/env bash
set -euo pipefail
# ORQ_HELP_GUARD
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: git-workflow.sh [workflow args...]"
  exit 0
fi
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORKSPACE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || printf '%s\n' "$SCRIPT_ROOT")"
resolve_canonical_root() {
  local common_dir
  if git -C "$WORKSPACE_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    common_dir="$(git -C "$WORKSPACE_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
      (cd "$(dirname "$common_dir")" && pwd -P)
      return 0
    fi
  fi
  printf '%s\n' "$SCRIPT_ROOT"
}
CONFIG_ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-$(resolve_canonical_root)}"
CONFIG_ROOT="$CONFIG_ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  CONFIG_ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$CONFIG_ROOT_CANDIDATE")"
fi
cd "$WORKSPACE_ROOT"
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "GIT_WORKFLOW_READY: no"
  echo "Reason: not inside a git repository"
  exit 2
fi
# Resolve workflow from the canonical orchestrator root, not from the current
# linked task worktree. In pr-flow, closer runs inside dev/<TASK_ID>; generated
# runtime files may be ignored or absent in that linked worktree, so reading
# workflow from CWD can incorrectly fall back to push-to-main. This preserves
# the branch-per-task PR flow while keeping blueprint-first state under
# CONFIG_ROOT.
WORKFLOW="$(python3 -B -S "$CONFIG_ROOT/.claude/bin/stack_profile.py" --root "$CONFIG_ROOT" --get git_workflow.mode --default "" 2>/dev/null || true)"
if [ -z "$WORKFLOW" ] || [ "$WORKFLOW" = "None" ]; then
  WORKFLOW="$(python3 -B -S "$CONFIG_ROOT/.claude/bin/stack_profile.py" --root "$CONFIG_ROOT" --get git_workflow --default push-to-main 2>/dev/null || echo push-to-main)"
fi
WORKFLOW="$(printf '%s' "$WORKFLOW" | tr -cd 'A-Za-z0-9_-')"
case "$WORKFLOW" in
  direct-main|direct-main-push|push-main) WORKFLOW="push-to-main" ;;
  gitflow) WORKFLOW="git-flow" ;;
  prflow) WORKFLOW="pr-flow" ;;
esac
PLUGIN="$CONFIG_ROOT/.claude/git-workflows/${WORKFLOW}.sh"
if [ ! -x "$PLUGIN" ]; then
  echo "GIT_WORKFLOW_READY: no"
  echo "Reason: git workflow plugin not found or not executable: $PLUGIN"
  exit 2
fi
# Branch-based DAG transport must happen from the exact per-task branch/worktree.
# This preserves the orchestrator-AnyStack invariant: each parallel DAG slice
# is isolated in its own branch (`dev/<TASK_ID>` for pr-flow, `feature/<TASK_ID>`
# for git-flow) and only merged into the target main after verification/closer.
TASK_ID_ARG="${1:-${CLAUDE_ACTIVE_TASK_ID:-}}"
if [ "$WORKFLOW" = "pr-flow" ] || [ "$WORKFLOW" = "git-flow" ]; then
  if [ -z "$TASK_ID_ARG" ]; then
    echo "GIT_WORKFLOW_READY: no"
    echo "Reason: $WORKFLOW requires TASK_ID argument or CLAUDE_ACTIVE_TASK_ID so branch/worktree scope can be verified."
    exit 2
  fi
  if [ ! -x "$CONFIG_ROOT/scripts/ensure-task-worktree.sh" ]; then
    echo "GIT_WORKFLOW_READY: no"
    echo "Reason: missing scripts/ensure-task-worktree.sh for branch/worktree guard."
    exit 2
  fi
  WORKTREE_GUARD_LOG="${TMPDIR:-/tmp}/orq-git-worktree-check.$$"
  if ! bash "$CONFIG_ROOT/scripts/ensure-task-worktree.sh" --check-current "$TASK_ID_ARG" >"$WORKTREE_GUARD_LOG" 2>&1; then
    echo "GIT_WORKFLOW_READY: no"
    echo "Reason: $WORKFLOW must run inside the exact task worktree/branch for $TASK_ID_ARG before PR merge to origin/main."
    sed 's/^/WORKTREE_GUARD: /' "$WORKTREE_GUARD_LOG" || true
    rm -f "$WORKTREE_GUARD_LOG"
    exit 2
  fi
  sed 's/^/WORKTREE_GUARD: /' "$WORKTREE_GUARD_LOG" || true
  rm -f "$WORKTREE_GUARD_LOG"
fi
if grep -Ev '^[[:space:]]*#' "$PLUGIN" | grep -Eq '(^|[;&|[:space:]])git[[:space:]]+stash([[:space:]]|$)'; then
  echo "GIT_WORKFLOW_READY: no"
  echo "Reason: git workflow plugin uses git stash, which is unsafe in production DAG mode."
  exit 2
fi

if [ -x "$CONFIG_ROOT/scripts/check-git-identity.sh" ]; then
  bash "$CONFIG_ROOT/scripts/check-git-identity.sh" --strict || {
    echo "GIT_WORKFLOW_READY: no"
    echo "Reason: Git identity guard failed."
    exit 3
  }
fi

# Protect local blueprint runtime artifacts before dirty checks. The native
# orchestrator allowed local runtime files to exist without blocking transport;
# the blueprint-first runtime has JSON/YAML mirrors under orchestrator-state/.
if [ -x "$CONFIG_ROOT/scripts/runtime-git-guard.sh" ]; then
  bash "$CONFIG_ROOT/scripts/runtime-git-guard.sh" protect --root "$WORKSPACE_ROOT" >/dev/null 2>&1 || true
fi

# Preserve the late-trace behavior: if Claude hooks wrote known runtime
# traces after closer's commit, amend only those tracked runtime traces. This
# never stages product code and never uses stash/pop.
amend_late_trace_files() {
  local found=0
  local path
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
      if ! git diff --quiet -- "$path" 2>/dev/null || ! git diff --cached --quiet -- "$path" 2>/dev/null; then
        git add -- "$path" 2>/dev/null || true
        found=1
      fi
    fi
  done <<'EOF_LATE_TRACE_PATHS'
orchestrator-state/tasks/ledger.jsonl
orchestrator-state/tasks/bash-ledger.jsonl
orchestrator-state/tasks/runtime-state.json
orchestrator-state/tasks/runtime-state.yaml
orchestrator-state/tasks/lifecycle-events.yaml
orchestrator-state/tasks/handoff-index.yaml
orchestrator-state/memory/PROGRESS.yaml
orchestrator-state/memory/PROGRESS.md
EOF_LATE_TRACE_PATHS
  if [ "$found" -eq 0 ]; then
    return 0
  fi
  if git diff --cached --quiet; then
    return 0
  fi
  if git rev-parse --verify HEAD >/dev/null 2>&1; then
    git commit --amend --no-edit --no-verify >/dev/null
    echo "GIT_WORKFLOW_TRACE_AMENDED: yes"
  else
    git commit --allow-empty -m "chore(orchestrator): sync late runtime trace files" --no-verify >/dev/null
    echo "GIT_WORKFLOW_TRACE_COMMITTED: yes"
  fi
}

# The closer must commit before this transport script. Do not hide product changes with stash.
if [ "${GIT_WORKFLOW_ALLOW_DIRTY:-0}" != "1" ]; then
  amend_late_trace_files
  dirty="$(git status --porcelain=v1 --untracked-files=all)"
  if [ -n "$dirty" ]; then
    echo "GIT_WORKFLOW_READY: no"
    echo "Reason: working tree is dirty before git workflow; closer must stage and commit intended changes first. Runtime mirrors are protected; remaining dirty paths are product or slice artifacts that must be explicitly staged."
    echo "$dirty" | sed 's/^/DIRTY: /'
    exit 2
  fi
fi
exec "$PLUGIN" "$@"
