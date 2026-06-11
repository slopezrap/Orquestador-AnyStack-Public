#!/usr/bin/env bash
set -euo pipefail

# PR flow plugin for Claude closer.
# DAG success means the PR is created automatically and actually merged. An
# open/queued PR is transport progress, not a closed DAG slice.

TARGET_BRANCH="${GIT_DEFAULT_BRANCH:-main}"
BRANCH="$(git branch --show-current 2>/dev/null || true)"
RUN_ID="${CLAUDE_RUN_ID:-$$}-$(date +%s)"
LOG_DIR="${TMPDIR:-/tmp}/claude-git-workflows"
mkdir -p "$LOG_DIR"
FETCH_LOG="$LOG_DIR/pr-flow-${RUN_ID}-fetch.log"
REBASE_LOG="$LOG_DIR/pr-flow-${RUN_ID}-rebase.log"
PUSH_LOG="$LOG_DIR/pr-flow-${RUN_ID}-push.log"
CREATE_LOG="$LOG_DIR/pr-flow-${RUN_ID}-create.log"
MERGE_LOG="$LOG_DIR/pr-flow-${RUN_ID}-merge.log"
SYNC_LOG="$LOG_DIR/pr-flow-${RUN_ID}-sync-main.log"
REMOTE_BRANCH_DELETE_LOG="$LOG_DIR/pr-flow-${RUN_ID}-remote-branch-delete.log"
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"

blocked() {
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: ${PUSH_READY_SEEN:-no}"
  printf '%s\n' "$@"
  exit 3
}

wrong_workflow() {
  echo "GIT_WORKFLOW_READY: no"
  echo "PUSH_READY: no"
  printf '%s\n' "$@"
  exit 2
}


cleanup_remote_head_branch() {
  case "$BRANCH" in
    ""|main|master|develop|"$TARGET_BRANCH")
      echo "REMOTE_BRANCH_CLEANED: skipped"
      return 0
      ;;
  esac
  if git ls-remote --exit-code --heads "$TARGET_REMOTE" "$BRANCH" >/dev/null 2>&1; then
    if git push "$TARGET_REMOTE" --delete "$BRANCH" >"$REMOTE_BRANCH_DELETE_LOG" 2>&1; then
      git fetch "$TARGET_REMOTE" --prune >/dev/null 2>&1 || true
      echo "REMOTE_BRANCH_CLEANED: yes"
    else
      echo "REMOTE_BRANCH_CLEANED: no"
      printf 'REMOTE_BRANCH_CLEANUP_COMMAND: git push %q --delete %q\n' "$TARGET_REMOTE" "$BRANCH"
      echo "Reason: remote branch still exists after merge and automatic delete failed. See $REMOTE_BRANCH_DELETE_LOG"
    fi
  else
    echo "REMOTE_BRANCH_CLEANED: not_found"
  fi
}

resolve_canonical_root() {
  local current_root common_dir candidate
  for candidate in "${CLAUDE_ORCHESTRATOR_ROOT:-}" "$PLUGIN_ROOT"; do
    if [ -n "$candidate" ] && [ -d "$candidate/.claude" ] && [ -d "$candidate/scripts" ]; then
      (cd "$candidate" && pwd -P)
      return 0
    fi
  done
  current_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
  common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
    (cd "$(dirname "$common_dir")" && pwd -P)
    return 0
  fi
  case "$current_root" in
    *-worktrees/*)
      candidate="${current_root%%-worktrees/*}"
      if [ -d "$candidate/.claude" ] && [ -d "$candidate/scripts" ]; then
        (cd "$candidate" && pwd -P)
        return 0
      fi
      ;;
  esac
  printf '%s\n' "$current_root"
}

gh_pr_merge() {
  # macOS still ships Bash 3.2 in many environments. Avoid empty arrays under
  # `set -u` here; `${arr[@]}` can throw "unbound variable" and leave PRs open.
  if [ -n "${CLAUDE_PR_MERGE_AUTHOR_EMAIL:-}" ]; then
    gh pr merge "$@" --author-email "$CLAUDE_PR_MERGE_AUTHOR_EMAIL"
  else
    gh pr merge "$@"
  fi
}

if [ -z "$BRANCH" ] || [ "$BRANCH" = "$TARGET_BRANCH" ] || [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ] || [ "$BRANCH" = "develop" ]; then
  wrong_workflow "Reason: pr-flow requires a feature branch for the TASK_ID, current=${BRANCH:-detached}. Use push-to-main/direct-main only when orchestrator-input.json stack.git_workflow declares it."
fi

if ! command -v gh >/dev/null 2>&1; then
  blocked "Reason: gh CLI is required for pr-flow."
fi

# DAG pr-flow integrates each task branch into origin/main by default.
# Allow an explicit override for forks, but do not silently follow a local
# branch.main.remote that might point at upstream and bypass the expected origin.
TARGET_REMOTE="${GIT_TARGET_REMOTE:-${CLAUDE_GIT_REMOTE:-origin}}"
TARGET_REMOTE="${TARGET_REMOTE:-origin}"
if ! git remote get-url "$TARGET_REMOTE" >/dev/null 2>&1; then
  blocked "Reason: remote '$TARGET_REMOTE' not configured. pr-flow expects origin/main unless GIT_TARGET_REMOTE or CLAUDE_GIT_REMOTE is set intentionally."
fi

if [ -n "$(git status --porcelain=v1 --untracked-files=all)" ]; then
  blocked "Reason: working tree dirty before PR flow. Commit slice changes first."
fi

FETCH_REFSPEC="+refs/heads/${TARGET_BRANCH}:refs/remotes/${TARGET_REMOTE}/${TARGET_BRANCH}"
if ! git fetch "$TARGET_REMOTE" --prune "$FETCH_REFSPEC" >"$FETCH_LOG" 2>&1; then
  blocked "Reason: could not fetch '$TARGET_REMOTE/$TARGET_BRANCH'. See $FETCH_LOG"
fi
TARGET_REF="$TARGET_REMOTE/$TARGET_BRANCH"
BASE="$(git merge-base "$TARGET_REF" HEAD 2>/dev/null || echo)"
TARGET_SHA="$(git rev-parse "$TARGET_REF" 2>/dev/null || echo)"
if [ -z "$BASE" ] || [ -z "$TARGET_SHA" ]; then
  blocked "Reason: branch '$BRANCH' has no merge-base with '$TARGET_REF'."
fi

if [ "$BASE" != "$TARGET_SHA" ]; then
  if git rebase "$TARGET_REF" >"$REBASE_LOG" 2>&1; then
    echo "REBASED_ON_MAIN: yes (rebased onto $TARGET_REF)"
  else
    git rebase --abort >/dev/null 2>&1 || true
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: no"
    echo "PR_READY: no"
    echo "REBASE_CONFLICT: yes"
    echo "Reason: rebase conflict against $TARGET_REF. See $REBASE_LOG"
    sed 's/^/  /' "$REBASE_LOG" >&2 || true
    exit 4
  fi
else
  echo "REBASED_ON_MAIN: no (already up to date with $TARGET_REF)"
fi

if [ -n "$(git status --porcelain=v1 --untracked-files=all)" ]; then
  blocked "Reason: working tree dirty after rebase. Resolve before pushing."
fi

if ! git push --force-with-lease -u "$TARGET_REMOTE" "$BRANCH" >"$PUSH_LOG" 2>&1; then
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: no"
  echo "PR_READY: no"
  echo "Reason: push failed. See $PUSH_LOG"
  sed 's/^/  /' "$PUSH_LOG" >&2 || true
  exit 3
fi
PUSH_READY_SEEN=yes
echo "PUSH_READY: yes"

if gh pr view "$BRANCH" >/dev/null 2>&1; then
  echo "PR_CREATE: reused"
else
  if ! gh pr create --fill --base "$TARGET_BRANCH" --head "$BRANCH" >"$CREATE_LOG" 2>&1; then
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: yes"
    echo "PR_READY: no"
    echo "Reason: PR creation failed. See $CREATE_LOG"
    sed 's/^/  /' "$CREATE_LOG" >&2 || true
    exit 3
  fi
  echo "PR_CREATE: done"
fi

PR_NUMBER="$(gh pr view "$BRANCH" --json number -q .number 2>/dev/null || echo '')"
PR_URL="$(gh pr view "${PR_NUMBER:-$BRANCH}" --json url -q .url 2>/dev/null || echo '')"
if [ -z "$PR_NUMBER" ]; then
  blocked "Reason: PR exists/was created but its number could not be resolved."
fi
echo "PR_READY: yes"
echo "PR_URL: ${PR_URL:-unknown}"

STATE="$(gh pr view "$PR_NUMBER" --json state -q .state 2>/dev/null || echo '')"
if [ "$STATE" != "MERGED" ]; then
  if [ "${CLAUDE_PR_FLOW_ADMIN_MERGE:-0}" = "1" ]; then
    if gh_pr_merge "$PR_NUMBER" --squash --delete-branch --admin >"$MERGE_LOG" 2>&1; then
      echo "MERGE_MODE: admin-squash-explicit"
    else
      echo "GIT_WORKFLOW_READY: blocked"
      echo "PUSH_READY: yes"
      echo "PR_READY: yes"
      echo "MERGED: no"
      echo "Reason: explicit admin squash merge failed. See $MERGE_LOG"
      sed 's/^/  /' "$MERGE_LOG" >&2 || true
      exit 3
    fi
  elif gh_pr_merge "$PR_NUMBER" --squash --delete-branch --auto >"$MERGE_LOG" 2>&1; then
    echo "MERGE_MODE: auto-squash"
    echo "MERGED: auto-queued"
  elif grep -Eiq '(already.*auto.?merge|auto.?merge.*already|already.*enabled)' "$MERGE_LOG" 2>/dev/null; then
    echo "MERGE_MODE: auto-squash-already-enabled"
    echo "MERGED: auto-queued"
  elif grep -Eiq '(delete.*branch|branch.*delete|merge queue)' "$MERGE_LOG" 2>/dev/null && gh_pr_merge "$PR_NUMBER" --squash --auto >>"$MERGE_LOG" 2>&1; then
    echo "MERGE_MODE: auto-squash"
    echo "MERGED: auto-queued"
    echo "REMOTE_DELETE_MODE: post-merge-fallback"
  else
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: yes"
    echo "PR_READY: yes"
    echo "MERGED: no"
    echo "Reason: PR created but auto-merge could not be enabled. See $MERGE_LOG"
    sed 's/^/  /' "$MERGE_LOG" >&2 || true
    exit 3
  fi
fi

WAIT_SECONDS="${CLAUDE_PR_FLOW_WAIT_SECONDS:-900}"
POLL_SECONDS="${CLAUDE_PR_FLOW_POLL_SECONDS:-10}"
elapsed=0
while [ "$elapsed" -le "$WAIT_SECONDS" ]; do
  STATE="$(gh pr view "$PR_NUMBER" --json state -q .state 2>/dev/null || echo '')"
  if [ "$STATE" = "MERGED" ]; then
    echo "MERGED: yes"
    break
  fi
  if [ "$STATE" = "CLOSED" ]; then
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: yes"
    echo "PR_READY: yes"
    echo "MERGED: no"
    echo "Reason: PR closed without merging: ${PR_URL:-unknown}"
    exit 3
  fi
  sleep "$POLL_SECONDS"
  elapsed=$((elapsed + POLL_SECONDS))
done

if [ "${STATE:-}" != "MERGED" ]; then
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: yes"
  echo "PR_READY: yes"
  echo "MERGED: no"
  echo "Reason: PR not merged after ${WAIT_SECONDS}s. DAG close remains blocked until integration is real: ${PR_URL:-unknown}"
  exit 3
fi

cleanup_remote_head_branch

ROOT="$(resolve_canonical_root)"
ROOT_BRANCH="$(git -C "$ROOT" branch --show-current 2>/dev/null || true)"
if [ "$ROOT_BRANCH" = "$TARGET_BRANCH" ]; then
  RUNTIME_BACKUP_DIR=""
  if [ -x "$ROOT/scripts/runtime-git-guard.sh" ]; then
    RUNTIME_GUARD_OUTPUT="$(bash "$ROOT/scripts/runtime-git-guard.sh" backup --root "$ROOT" 2>&1)" || {
      echo "CANONICAL_MAIN_SYNCED: no"
      echo "Reason: canonical root has non-runtime dirty files; refusing to fast-forward blindly."
      printf '%s\n' "$RUNTIME_GUARD_OUTPUT"
      echo "GIT_WORKFLOW_READY: blocked"
      exit 3
    }
    printf '%s\n' "$RUNTIME_GUARD_OUTPUT" | grep -E '^(RUNTIME_PATHS_BACKED_UP|RUNTIME_PATHS_PROTECTED):' || true
    RUNTIME_BACKUP_DIR="$(printf '%s\n' "$RUNTIME_GUARD_OUTPUT" | awk -F': ' '/^RUNTIME_BACKUP_DIR: / {print $2; exit}')"
  fi

  ROOT_STATUS="$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"
  if [ -n "$ROOT_STATUS" ]; then
    echo "CANONICAL_MAIN_SYNCED: no"
    echo "Reason: canonical root has real dirty files after runtime guard; refusing to fast-forward blindly."
    printf '%s\n' "$ROOT_STATUS" | sed 's/^/DIRTY_ROOT: /'
    echo "GIT_WORKFLOW_READY: blocked"
    exit 3
  fi
  if ! git -C "$ROOT" fetch "$TARGET_REMOTE" --prune "$FETCH_REFSPEC" >"$SYNC_LOG" 2>&1; then
    echo "CANONICAL_MAIN_SYNCED: no"
    echo "Reason: canonical root fetch failed. See $SYNC_LOG"
    echo "GIT_WORKFLOW_READY: blocked"
    exit 3
  fi
  if ! git -C "$ROOT" merge --ff-only "$TARGET_REF" >>"$SYNC_LOG" 2>&1; then
    echo "CANONICAL_MAIN_SYNCED: no"
    echo "Reason: canonical main could not fast-forward to $TARGET_REF. See $SYNC_LOG"
    echo "GIT_WORKFLOW_READY: blocked"
    exit 3
  fi
  if [ -n "$RUNTIME_BACKUP_DIR" ] && [ -d "$RUNTIME_BACKUP_DIR" ] && [ -x "$ROOT/scripts/runtime-git-guard.sh" ]; then
    bash "$ROOT/scripts/runtime-git-guard.sh" restore --root "$ROOT" --backup-dir "$RUNTIME_BACKUP_DIR" 2>&1 | grep -E '^(RUNTIME_PATHS_RESTORED|RUNTIME_PATHS_PROTECTED):' || true
  fi
  if [ -x "$ROOT/scripts/sync-lifecycle-events.sh" ]; then
    bash "$ROOT/scripts/sync-lifecycle-events.sh" --apply 2>&1 | grep -E '^(LIFECYCLE_EVENTS_APPLIED|RUNTIME_GIT_PROTECTED):' || true
  fi
  echo "CANONICAL_MAIN_SYNCED: yes"
else
  CURRENT_CHECKOUT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
  if [ "$ROOT" = "$CURRENT_CHECKOUT_ROOT" ]; then
    # Single-checkout repositories are supported, but pr-flow must still end
    # with the local checkout on an integrated target branch. A skipped main
    # sync is not a closed DAG slice because dependents would not necessarily
    # start from merged code.
    RUNTIME_BACKUP_DIR=""
    if [ -x "$ROOT/scripts/runtime-git-guard.sh" ]; then
      RUNTIME_GUARD_OUTPUT="$(bash "$ROOT/scripts/runtime-git-guard.sh" backup --root "$ROOT" 2>&1)" || {
        echo "CANONICAL_MAIN_SYNCED: no"
        echo "Reason: single-checkout root has non-runtime dirty files; refusing to switch to $TARGET_BRANCH."
        printf '%s
' "$RUNTIME_GUARD_OUTPUT"
        echo "GIT_WORKFLOW_READY: blocked"
        exit 3
      }
      printf '%s
' "$RUNTIME_GUARD_OUTPUT" | grep -E '^(RUNTIME_PATHS_BACKED_UP|RUNTIME_PATHS_PROTECTED):' || true
      RUNTIME_BACKUP_DIR="$(printf '%s
' "$RUNTIME_GUARD_OUTPUT" | awk -F': ' '/^RUNTIME_BACKUP_DIR: / {print $2; exit}')"
    fi

    ROOT_STATUS="$(git status --porcelain=v1 --untracked-files=all 2>/dev/null || true)"
    if [ -n "$ROOT_STATUS" ]; then
      echo "CANONICAL_MAIN_SYNCED: no"
      echo "Reason: single-checkout root has real dirty files after runtime guard; refusing to switch to $TARGET_BRANCH."
      printf '%s
' "$ROOT_STATUS" | sed 's/^/DIRTY_ROOT: /'
      echo "GIT_WORKFLOW_READY: blocked"
      exit 3
    fi

    if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
      if ! git switch "$TARGET_BRANCH" >>"$SYNC_LOG" 2>&1; then
        echo "CANONICAL_MAIN_SYNCED: no"
        echo "Reason: could not switch single-checkout repo to $TARGET_BRANCH. See $SYNC_LOG"
        echo "GIT_WORKFLOW_READY: blocked"
        exit 3
      fi
    elif ! git switch --track "$TARGET_REF" >>"$SYNC_LOG" 2>&1; then
      if ! git switch -C "$TARGET_BRANCH" "$TARGET_REF" >>"$SYNC_LOG" 2>&1; then
        echo "CANONICAL_MAIN_SYNCED: no"
        echo "Reason: could not create local $TARGET_BRANCH from $TARGET_REF. See $SYNC_LOG"
        echo "GIT_WORKFLOW_READY: blocked"
        exit 3
      fi
    fi

    if ! git fetch "$TARGET_REMOTE" --prune "$FETCH_REFSPEC" >>"$SYNC_LOG" 2>&1; then
      echo "CANONICAL_MAIN_SYNCED: no"
      echo "Reason: single-checkout fetch failed after switching to $TARGET_BRANCH. See $SYNC_LOG"
      echo "GIT_WORKFLOW_READY: blocked"
      exit 3
    fi
    if ! git merge --ff-only "$TARGET_REF" >>"$SYNC_LOG" 2>&1; then
      echo "CANONICAL_MAIN_SYNCED: no"
      echo "Reason: single-checkout $TARGET_BRANCH could not fast-forward to $TARGET_REF. See $SYNC_LOG"
      echo "GIT_WORKFLOW_READY: blocked"
      exit 3
    fi
    if [ -n "$RUNTIME_BACKUP_DIR" ] && [ -d "$RUNTIME_BACKUP_DIR" ] && [ -x "$ROOT/scripts/runtime-git-guard.sh" ]; then
      bash "$ROOT/scripts/runtime-git-guard.sh" restore --root "$ROOT" --backup-dir "$RUNTIME_BACKUP_DIR" 2>&1 | grep -E '^(RUNTIME_PATHS_RESTORED|RUNTIME_PATHS_PROTECTED):' || true
    fi
    if [ -x "$ROOT/scripts/sync-lifecycle-events.sh" ]; then
      bash "$ROOT/scripts/sync-lifecycle-events.sh" --apply 2>&1 | grep -E '^(LIFECYCLE_EVENTS_APPLIED|RUNTIME_GIT_PROTECTED):' || true
    fi
    echo "CANONICAL_MAIN_SYNCED: yes"
  else
    echo "CANONICAL_MAIN_SYNCED: no"
    echo "Reason: canonical root branch is ${ROOT_BRANCH:-detached}, expected $TARGET_BRANCH. DAG close requires local main to be fast-forwarded after merge so the next slice starts from integrated code."
    echo "GIT_WORKFLOW_READY: blocked"
    exit 3
  fi
fi

echo "GIT_WORKFLOW_READY: yes"
exit 0
