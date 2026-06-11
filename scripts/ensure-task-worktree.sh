#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF_USAGE'
Usage:
  scripts/ensure-task-worktree.sh <TASK_ID>
  scripts/ensure-task-worktree.sh --check-current <TASK_ID>
  scripts/ensure-task-worktree.sh --print-root
  scripts/ensure-task-worktree.sh --repair-current-state [TASK_ID]

Creates or locates the per-TASK_ID git worktree for branch-based workflows,
provisions it so generated orchestrator-state cannot split from the canonical
scheduler root, and prints its path. For push-to-main/direct-main projects it prints the canonical
root because that workflow intentionally does not use feature branches.

Branch conventions:
  pr-flow  -> dev/<TASK_ID>, based on the default branch / origin main
  git-flow -> feature/<TASK_ID>, based on develop

--print-root prints the canonical/main repository root, not the current linked
worktree. Do not fall back to canonical root in $WORKFLOW check mode. --check-current validates the caller's current worktree, not the
location of this script. The script is safe in non-git checkouts.
EOF_USAGE
}

MODE="ensure"
if [ "${1:-}" = "--print-root" ]; then
  MODE="print-root"
  shift
elif [ "${1:-}" = "--check-current" ]; then
  MODE="check"
  shift
elif [ "${1:-}" = "--repair-current-state" ]; then
  MODE="repair-current-state"
  shift
elif [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi
TASK_ID="${1:-}"

CALL_DIR="$(pwd -P)"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
GIT_PROBE_DIR="$SCRIPT_ROOT"
if [ "$MODE" = "check" ] || [ "$MODE" = "repair-current-state" ]; then
  GIT_PROBE_DIR="$CALL_DIR"
fi

if ! git -C "$GIT_PROBE_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  if [ "$MODE" = "check" ]; then
    echo "TASK_WORKTREE_READY: yes"
    echo "Worktree: $CALL_DIR"
  else
    printf '%s\n' "$SCRIPT_ROOT"
  fi
  exit 0
fi

canonical_root_from() {
  local context="$1" common_dir current_root
  current_root="$(git -C "$context" rev-parse --show-toplevel 2>/dev/null || printf '%s\n' "$context")"
  common_dir="$(git -C "$context" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
    (cd "$(dirname "$common_dir")" && pwd -P)
  else
    printf '%s\n' "$current_root"
  fi
}

if [ "$MODE" = "check" ] || [ "$MODE" = "repair-current-state" ]; then
  ACTIVE_ROOT="$(git -C "$CALL_DIR" rev-parse --show-toplevel)"
  ROOT="$(canonical_root_from "$CALL_DIR")"
else
  ACTIVE_ROOT="$(git -C "$SCRIPT_ROOT" rev-parse --show-toplevel)"
  ROOT="$(canonical_root_from "$SCRIPT_ROOT")"
fi

git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
if [ -x "$ROOT/scripts/sync-lifecycle-events.sh" ]; then
  bash "$ROOT/scripts/sync-lifecycle-events.sh" --apply >/dev/null 2>&1 || true
fi


provision_worktree_state() {
  local wt="$1"
  [ -n "${wt:-}" ] || return 0
  [ -d "$wt" ] || return 0
  [ "$wt" = "$ROOT" ] && return 0
  if [ -x "$ROOT/scripts/repair-worktree-state.sh" ]; then
    local report
    report="$(bash "$ROOT/scripts/repair-worktree-state.sh" --provision "$wt" 2>&1)" || {
      echo "TASK_WORKTREE_READY: no" >&2
      echo "SPLIT_BRAIN_DETECTED: linked worktree has local generated orchestrator-state that would split scheduler truth." >&2
      printf '%s\n' "$report" >&2
      echo "Repair: bash $ROOT/scripts/repair-worktree-state.sh --apply $wt" >&2
      exit 4
    }
  fi
}

repair_current_state() {
  local wt="${ACTIVE_ROOT:-$CALL_DIR}"
  if [ ! -x "$ROOT/scripts/repair-worktree-state.sh" ]; then
    echo "TASK_WORKTREE_READY: no" >&2
    echo "Reason: missing scripts/repair-worktree-state.sh" >&2
    exit 4
  fi
  bash "$ROOT/scripts/repair-worktree-state.sh" --apply "$wt"
}

if [ "$MODE" = "print-root" ]; then
  printf '%s\n' "$ROOT"
  exit 0
fi

if [ "$MODE" = "repair-current-state" ]; then
  repair_current_state
  exit 0
fi

if [ -z "$TASK_ID" ]; then
  usage >&2
  exit 2
fi
if ! printf '%s' "$TASK_ID" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.-]*$'; then
  echo "ERROR: invalid TASK_ID: $TASK_ID" >&2
  exit 2
fi

WORKFLOW="$(python3 -B -S "$ROOT/.claude/bin/stack_profile.py" --root "$ROOT" --get git_workflow.mode --default "" 2>/dev/null || true)"
if [ -z "$WORKFLOW" ] || [ "$WORKFLOW" = "None" ]; then
  WORKFLOW="$(python3 -B -S "$ROOT/.claude/bin/stack_profile.py" --root "$ROOT" --get git_workflow --default push-to-main 2>/dev/null || echo push-to-main)"
fi
WORKFLOW="$(printf '%s' "$WORKFLOW" | tr -cd 'A-Za-z0-9_-')"
case "$WORKFLOW" in
  direct-main|direct-main-push|push-main) WORKFLOW="push-to-main" ;;
  gitflow) WORKFLOW="git-flow" ;;
  prflow) WORKFLOW="pr-flow" ;;
esac
[ -n "$WORKFLOW" ] || WORKFLOW="push-to-main"

DEFAULT_BRANCH="${GIT_DEFAULT_BRANCH:-main}"
DEVELOP_BRANCH="${GIT_FLOW_DEVELOP:-develop}"
CURRENT_BRANCH="$(git -C "$ACTIVE_ROOT" branch --show-current 2>/dev/null || true)"

if [ "$WORKFLOW" = "push-to-main" ]; then
  if [ "$MODE" = "check" ]; then
    if [ "$CURRENT_BRANCH" != "$DEFAULT_BRANCH" ]; then
      echo "TASK_WORKTREE_READY: no"
      echo "Reason: git_workflow=$WORKFLOW requires branch $DEFAULT_BRANCH, current=${CURRENT_BRANCH:-detached}"
      exit 2
    fi
    provision_worktree_state "$ACTIVE_ROOT"
    echo "TASK_WORKTREE_READY: yes"
    echo "Worktree: $ACTIVE_ROOT"
  else
    printf '%s\n' "$ROOT"
  fi
  exit 0
fi

if [ "$WORKFLOW" = "git-flow" ]; then
  BRANCH="feature/$TASK_ID"
else
  BRANCH="dev/$TASK_ID"
fi

if [ "$MODE" = "check" ]; then
  if [ "$CURRENT_BRANCH" = "$BRANCH" ]; then
    provision_worktree_state "$ACTIVE_ROOT"
    echo "TASK_WORKTREE_READY: yes"
    echo "Branch: $CURRENT_BRANCH"
    echo "ExpectedBranch: $BRANCH"
    echo "Worktree: $ACTIVE_ROOT"
    exit 0
  fi
  echo "TASK_WORKTREE_READY: no"
  echo "Reason: current branch ${CURRENT_BRANCH:-detached} is not the exact task branch $BRANCH for git_workflow=$WORKFLOW"
  exit 2
fi

existing="$(git -C "$ROOT" worktree list --porcelain | awk -v branch="refs/heads/$BRANCH" '
  /^worktree / {wt=$0; sub(/^worktree /,"",wt)}
  /^branch / {br=$0; sub(/^branch /,"",br); if (br==branch) print wt}
' | head -1)"
if [ -n "$existing" ] && [ -d "$existing" ]; then
  provision_worktree_state "$existing"
  printf '%s\n' "$existing"
  exit 0
fi

base_ref_for_workflow() {
  if [ "$WORKFLOW" = "git-flow" ]; then
    if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$DEVELOP_BRANCH"; then
      printf '%s\n' "$DEVELOP_BRANCH"
      return 0
    fi
    printf '%s\n' "HEAD"
    return 0
  fi
  local remote
  remote="$(git -C "$ROOT" config "branch.${DEFAULT_BRANCH}.remote" 2>/dev/null || echo origin)"
  if git -C "$ROOT" remote get-url "$remote" >/dev/null 2>&1; then
    git -C "$ROOT" fetch "$remote" --prune "+refs/heads/$DEFAULT_BRANCH:refs/remotes/$remote/$DEFAULT_BRANCH" >/dev/null 2>&1 || true
    if git -C "$ROOT" show-ref --verify --quiet "refs/remotes/$remote/$DEFAULT_BRANCH"; then
      printf '%s\n' "$remote/$DEFAULT_BRANCH"
      return 0
    fi
  fi
  if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
    printf '%s\n' "$DEFAULT_BRANCH"
  else
    printf '%s\n' "HEAD"
  fi
}

BASE_REF="$(base_ref_for_workflow)"
if ! git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  if ! git -C "$ROOT" branch "$BRANCH" "$BASE_REF" >/dev/null 2>&1; then
    echo "TASK_WORKTREE_READY: no" >&2
    echo "Reason: could not create task branch $BRANCH from $BASE_REF" >&2
    exit 3
  fi
fi

WT_PARENT="${CLAUDE_TASK_WORKTREES_DIR:-$(dirname "$ROOT")/$(basename "$ROOT")-worktrees}"
WT="$WT_PARENT/$TASK_ID"
mkdir -p "$WT_PARENT"
if [ -d "$WT/.git" ] || [ -f "$WT/.git" ]; then
  provision_worktree_state "$WT"
  printf '%s\n' "$WT"
  exit 0
fi
if [ -e "$WT" ] && [ -n "$(ls -A "$WT" 2>/dev/null || true)" ]; then
  echo "TASK_WORKTREE_READY: no" >&2
  echo "Reason: target worktree path exists but is not empty: $WT" >&2
  exit 3
fi

if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  if ! git -C "$ROOT" worktree add "$WT" "$BRANCH" >/dev/null 2>&1; then
    echo "TASK_WORKTREE_READY: no" >&2
    echo "Reason: could not create task worktree $WT for branch $BRANCH. Do not fall back to canonical root in $WORKFLOW; fix/prune worktrees and retry." >&2
    exit 3
  fi
  provision_worktree_state "$WT"
  printf '%s\n' "$WT"
else
  echo "TASK_WORKTREE_READY: no" >&2
  echo "Reason: task branch $BRANCH does not exist after creation attempt" >&2
  exit 3
fi
