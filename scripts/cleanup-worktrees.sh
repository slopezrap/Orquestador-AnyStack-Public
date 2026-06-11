#!/usr/bin/env bash
set -euo pipefail

# Safely remove per-slice git worktrees after a closer has committed and run
# the configured Git workflow. Dry-run by default.
#
# Claude Code invariant: by default, never remove the checkout that Claude is
# currently using. SubagentStop/Stop hooks run after the closer response; if the
# cwd disappears first, the hook runner can fail before it records the closer
# trailer. Active task worktrees are recorded as deferred cleanup requests and
# are removed later from the canonical root by cleanup-deferred-worktrees.sh.

APPLY=0
TASK_ID=""
VERBOSE=0
REMOVE_ACTIVE=0
DEFERRED_ONLY=0
SCHEDULE_ACTIVE=0
ACTIVE_CLEANUP_SCHEDULED=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

usage() {
  cat <<'USAGE'
Usage: scripts/cleanup-worktrees.sh [--apply] [--task TASK_ID] [--verbose] [--remove-active] [--schedule-active] [--deferred]

Default is dry-run. A worktree is a candidate when its path or branch name
contains TASK_ID. Without --task, candidates are paths/branches that look like
per-slice worktrees (contain Pxx-Sxx-Txxx or dev/ or feature/). Dirty worktrees
are reported and skipped.

By default the script defers removal of the currently active worktree so Claude
Code Stop/SubagentStop hooks can still spawn. Deferred removals are recorded in
orchestrator-state/tasks/cleanup-requests/ and flushed later with:
  scripts/cleanup-deferred-worktrees.sh --apply [--task TASK_ID]

--schedule-active launches that deferred cleanup automatically from the canonical
root after a short delay. Use --remove-active only from a different shell/session
when you explicitly want to delete that checkout immediately.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --dry-run) APPLY=0; shift ;;
    --task)
      TASK_ID="${2:-}"
      if [ -z "$TASK_ID" ]; then
        echo "ERROR: --task requires a TASK_ID" >&2
        exit 2
      fi
      shift 2
      ;;
    --verbose) VERBOSE=1; shift ;;
    --remove-active) REMOVE_ACTIVE=1; shift ;;
    --schedule-active) SCHEDULE_ACTIVE=1; shift ;;
    --deferred|--flush-deferred) DEFERRED_ONLY=1; APPLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "cleanup-worktrees: git_repository=no matched=0 would_remove=0 removed=0 skipped=0 active_deferred=0 active_cleanup_scheduled=0 missing_pruned=0 branches_deleted=0 branches_skipped=0 mode=$([ "$APPLY" -eq 1 ] && echo apply || echo dry-run) task=${TASK_ID:-all}"
  exit 0
fi

ORIGINAL_ROOT="$(git rev-parse --show-toplevel)"
ORIGINAL_ROOT_REAL="$(cd "$ORIGINAL_ROOT" && pwd -P)"

resolve_canonical_root() {
  local common_dir
  common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
    (cd "$(dirname "$common_dir")" && pwd -P)
  else
    printf '%s\n' "$ORIGINAL_ROOT"
  fi
}

resolve_active_root() {
  local raw top
  for raw in "${CLAUDE_WORKTREE_ROOT:-}" "${CLAUDE_WORKSPACE_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "$ORIGINAL_ROOT"; do
    [ -n "$raw" ] || continue
    [ -d "$raw" ] || continue
    top="$(git -C "$raw" rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$top" ] && [ -d "$top" ]; then
      (cd "$top" && pwd -P)
      return 0
    fi
  done
  printf '%s\n' "$ORIGINAL_ROOT_REAL"
}

ROOT="$(resolve_canonical_root)"
ROOT_REAL="$(cd "$ROOT" && pwd -P)"
ACTIVE_ROOT_REAL="$(resolve_active_root)"
REQ_DIR="$ROOT_REAL/orchestrator-state/tasks/cleanup-requests"
DEFERRED_CLEANUP_SCRIPT="$ROOT_REAL/scripts/cleanup-deferred-worktrees.sh"
if [ ! -f "$DEFERRED_CLEANUP_SCRIPT" ]; then
  DEFERRED_CLEANUP_SCRIPT="$SCRIPT_DIR/cleanup-deferred-worktrees.sh"
fi
DEFERRED_CLEANUP_LOOP_SCRIPT="$ROOT_REAL/scripts/cleanup-deferred-worktrees-loop.sh"
if [ ! -f "$DEFERRED_CLEANUP_LOOP_SCRIPT" ]; then
  DEFERRED_CLEANUP_LOOP_SCRIPT="$SCRIPT_DIR/cleanup-deferred-worktrees-loop.sh"
fi
cd "$ROOT_REAL"

if [ "$DEFERRED_ONLY" -eq 1 ]; then
  if [ -n "$TASK_ID" ]; then
    exec bash "$DEFERRED_CLEANUP_SCRIPT" --apply --task "$TASK_ID"
  fi
  exec bash "$DEFERRED_CLEANUP_SCRIPT" --apply
fi

write_deferred_cleanup_request() {
  local wt_path="$1"
  local wt_branch="$2"
  [ -n "$TASK_ID" ] || return 0
  [ "$APPLY" -eq 1 ] || return 0
  mkdir -p "$REQ_DIR" 2>/dev/null || return 0
  python3 -B -S - "$REQ_DIR" "$TASK_ID" "$wt_path" "$wt_branch" "$ROOT_REAL" "$ACTIVE_ROOT_REAL" <<'PY_DEFER' || true
import json, sys
from datetime import datetime, timezone
from pathlib import Path
req_dir = Path(sys.argv[1])
task_id, wt_path, wt_branch, root_real, active_root = sys.argv[2:7]
branch = wt_branch.removeprefix('refs/heads/')
request = {
    'version': 1,
    'task_id': task_id,
    'worktree': wt_path,
    'branch': branch,
    'canonical_root': root_real,
    'active_root_at_request': active_root,
    'requested_at': datetime.now(timezone.utc).isoformat(),
    'reason': 'active_worktree_deferred_until_after_claude_hooks',
    'cleanup_command': f"cd {root_real!r} && bash scripts/cleanup-deferred-worktrees.sh --apply --task {task_id}",
    'direct_remove_command': f"cd {root_real!r} && bash scripts/cleanup-worktrees.sh --apply --task {task_id} --remove-active",
}
(req_dir / f'{task_id}.json').write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY_DEFER
}

schedule_deferred_cleanup() {
  [ "$APPLY" -eq 1 ] || return 0
  [ "$SCHEDULE_ACTIVE" -eq 1 ] || return 0
  [ -n "$TASK_ID" ] || return 0
  [ "$ACTIVE_CLEANUP_SCHEDULED" -eq 0 ] || return 0
  ACTIVE_CLEANUP_SCHEDULED=1
  local delay log_file root_real task_id
  delay="${CLAUDE_WORKTREE_CLEANUP_DELAY_SECONDS:-60}"
  case "$delay" in ''|*[!0-9]*) delay=60 ;; esac
  root_real="$ROOT_REAL"
  task_id="$TASK_ID"
  log_file="$ROOT_REAL/orchestrator-state/tasks/worktree-cleanup-${task_id}.log"
  mkdir -p "$ROOT_REAL/orchestrator-state/tasks" 2>/dev/null || true
  (
    cd "$root_real" || exit 0
    if [ -f "$DEFERRED_CLEANUP_LOOP_SCRIPT" ]; then
      env -u CLAUDE_PROJECT_DIR -u CLAUDE_WORKTREE_ROOT -u CLAUDE_WORKSPACE_ROOT         bash "$DEFERRED_CLEANUP_LOOP_SCRIPT" --initial-delay "$delay" --interval "${CLAUDE_WORKTREE_CLEANUP_INTERVAL_SECONDS:-15}" --timeout "${CLAUDE_WORKTREE_CLEANUP_TIMEOUT_SECONDS:-600}" --quiet >>"$log_file" 2>&1 || true
    else
      sleep "$delay"
      env -u CLAUDE_PROJECT_DIR -u CLAUDE_WORKTREE_ROOT -u CLAUDE_WORKSPACE_ROOT         bash "$DEFERRED_CLEANUP_SCRIPT" --apply --task "$task_id" --quiet >>"$log_file" 2>&1 || true
    fi
  ) >/dev/null 2>&1 &
  local pid=$!
  disown "$pid" 2>/dev/null || true
  echo "ACTIVE_CLEANUP_SCHEDULED: yes task=$task_id delay=${delay}s retry_window=${CLAUDE_WORKTREE_CLEANUP_TIMEOUT_SECONDS:-600}s log=$log_file"
}

branch_short_name() {
  local branch="$1"
  case "$branch" in
    refs/heads/*) printf '%s\n' "${branch#refs/heads/}" ;;
    *) printf '%s\n' "$branch" ;;
  esac
}

MATCHED=0
WOULD_REMOVE=0
REMOVED=0
SKIPPED=0
BRANCHES_DELETED=0
BRANCHES_SKIPPED=0
ACTIVE_DEFERRED=0
MISSING_PRUNED=0

maybe_delete_local_branch() {
  local wt_branch="$1"
  local short
  short="$(branch_short_name "$wt_branch")"
  case "$short" in
    ""|main|master|HEAD|detached) return 0 ;;
  esac
  if ! git show-ref --verify --quiet "refs/heads/$short"; then
    return 0
  fi

  local develop="${GIT_FLOW_DEVELOP:-develop}"
  local main="${GIT_FLOW_MAIN:-main}"
  local safe_to_delete=0
  # PR squash merges do not make the feature tip an ancestor of main. When the
  # cleanup is scoped to a TASK_ID and the branch belongs to it, the closer has
  # already proven integration before calling this script; local branch deletion
  # is safe.
  if [ -n "$TASK_ID" ]; then
    case "$short" in *"$TASK_ID"*) safe_to_delete=1 ;; esac
  fi
  if [ "$safe_to_delete" -ne 1 ] && git merge-base --is-ancestor "$short" HEAD >/dev/null 2>&1; then
    safe_to_delete=1
  elif [ "$safe_to_delete" -ne 1 ] && git show-ref --verify --quiet "refs/heads/$develop" && git merge-base --is-ancestor "$short" "$develop" >/dev/null 2>&1; then
    safe_to_delete=1
  elif [ "$safe_to_delete" -ne 1 ] && git show-ref --verify --quiet "refs/heads/$main" && git merge-base --is-ancestor "$short" "$main" >/dev/null 2>&1; then
    safe_to_delete=1
  fi

  if [ "$safe_to_delete" -eq 1 ]; then
    if git branch -d "$short" >/dev/null 2>&1 || git branch -D "$short" >/dev/null 2>&1; then
      BRANCHES_DELETED=$((BRANCHES_DELETED + 1))
      echo "deleted local branch: $short"
    else
      BRANCHES_SKIPPED=$((BRANCHES_SKIPPED + 1))
      echo "skip branch delete: $short"
    fi
  else
    BRANCHES_SKIPPED=$((BRANCHES_SKIPPED + 1))
    [ "$VERBOSE" -eq 1 ] && echo "skip branch delete not merged: $short"
  fi
}

process_record() {
  local wt_path="$1"
  local wt_branch="$2"
  [ -n "$wt_path" ] || return 0

  local wt_real
  wt_real="$(cd "$wt_path" 2>/dev/null && pwd -P || printf '%s' "$wt_path")"

  if [ "$wt_real" = "$ROOT_REAL" ]; then
    [ "$VERBOSE" -eq 1 ] && echo "skip canonical root: $wt_path"
    return 0
  fi
  case "$wt_branch" in
    refs/heads/main|refs/heads/master|main|master)
      [ "$VERBOSE" -eq 1 ] && echo "skip main/master: $wt_path ($wt_branch)"
      return 0
      ;;
  esac

  local haystack="$wt_path $wt_branch"
  local candidate=0
  if [ -n "$TASK_ID" ]; then
    case "$haystack" in *"$TASK_ID"*) candidate=1 ;; esac
  else
    if printf '%s\n' "$haystack" | grep -Eq 'P[0-9]+-S[0-9]+-T[0-9]+|dev/|feature/'; then
      candidate=1
    fi
  fi
  if [ "$candidate" -ne 1 ]; then
    [ "$VERBOSE" -eq 1 ] && echo "skip non-candidate: $wt_path ($wt_branch)"
    return 0
  fi

  MATCHED=$((MATCHED + 1))

  if [ ! -d "$wt_path" ]; then
    if [ "$APPLY" -eq 1 ]; then
      MISSING_PRUNED=$((MISSING_PRUNED + 1))
      echo "prune missing worktree metadata: $wt_path"
    else
      WOULD_REMOVE=$((WOULD_REMOVE + 1))
      echo "would prune missing worktree metadata: $wt_path"
    fi
    return 0
  fi

  local status
  status="$(git -C "$wt_path" status --porcelain 2>/dev/null || true)"
  if [ -n "$status" ]; then
    SKIPPED=$((SKIPPED + 1))
    echo "skip dirty: $wt_path ($wt_branch)"
    if [ "$VERBOSE" -eq 1 ] || [ "${CLAUDE_CLEANUP_EXPLAIN_DIRTY:-0}" = "1" ]; then
      local limit shown total
      limit="${CLAUDE_CLEANUP_DIRTY_STATUS_LIMIT:-40}"
      case "$limit" in ''|*[!0-9]*) limit=40 ;; esac
      total="$(printf '%s\n' "$status" | sed '/^$/d' | wc -l | tr -d ' ')"
      shown=0
      echo "DIRTY_STATUS_BEGIN: $wt_path total=$total shown_limit=$limit"
      printf '%s\n' "$status" | sed -n "1,${limit}p" | sed 's/^/  /'
      shown="$(printf '%s\n' "$status" | sed -n "1,${limit}p" | sed '/^$/d' | wc -l | tr -d ' ')"
      if [ "$total" -gt "$shown" ] 2>/dev/null; then
        echo "  ... $((total - shown)) more dirty path(s) omitted"
      fi
      echo "DIRTY_STATUS_END: $wt_path"
      if [ -n "$TASK_ID" ]; then
        echo "MANUAL_REVIEW_COMMAND: git -C '$wt_path' status --short && git -C '$wt_path' diff --stat"
      fi
    fi
    return 0
  fi

  # Hook-safe closer cleanup invariant:
  # - When a closer uses --schedule-active with --task, do not rely on cwd/env
  #   heuristics to identify the active checkout. Claude Code may invoke cleanup
  #   from the canonical root while its session still needs the task worktree for
  #   SubagentStop. Therefore every clean worktree matching TASK_ID is deferred.
  # - The deferred janitor only removes it after a closer lifecycle event or
  #   registry status proves done, so git-side cleanup cannot race lifecycle.
  local defer_due_to_active=0
  if [ "$REMOVE_ACTIVE" -ne 1 ] && [ "$wt_real" != "$ROOT_REAL" ]; then
    if [ "$wt_real" = "$ACTIVE_ROOT_REAL" ]; then
      defer_due_to_active=1
    elif [ "$SCHEDULE_ACTIVE" -eq 1 ] && [ -n "$TASK_ID" ]; then
      defer_due_to_active=1
    fi
  fi
  if [ "$defer_due_to_active" -eq 1 ]; then
    ACTIVE_DEFERRED=$((ACTIVE_DEFERRED + 1))
    write_deferred_cleanup_request "$wt_path" "$wt_branch"
    echo "defer task worktree removal until after closer lifecycle hooks: $wt_path ($wt_branch)"
    if [ -n "$TASK_ID" ]; then
      echo "DEFERRED_CLEANUP_COMMAND: cd '$ROOT_REAL' && bash scripts/cleanup-deferred-worktrees.sh --apply --task '$TASK_ID'"
    fi
    schedule_deferred_cleanup
    return 0
  fi

  if [ "$APPLY" -eq 1 ]; then
    if git worktree remove "$wt_path" 2>/dev/null; then
      REMOVED=$((REMOVED + 1))
      echo "removed: $wt_path ($wt_branch)"
    else
      git worktree remove --force "$wt_path" 2>/dev/null || true
      if [ -d "$wt_path" ]; then
        rm -rf "$wt_path"
      fi
      REMOVED=$((REMOVED + 1))
      echo "removed (forced after git refused, untracked cruft only): $wt_path ($wt_branch)"
    fi
    maybe_delete_local_branch "$wt_branch"
  else
    WOULD_REMOVE=$((WOULD_REMOVE + 1))
    echo "would remove: $wt_path ($wt_branch)"
  fi
}

records="$(git worktree list --porcelain)"
current_path=""
current_branch=""
while IFS= read -r line; do
  if [ -z "$line" ]; then
    process_record "$current_path" "$current_branch"
    current_path=""
    current_branch=""
    continue
  fi
  case "$line" in
    worktree\ *) current_path="${line#worktree }" ;;
    branch\ *) current_branch="${line#branch }" ;;
  esac
done <<EOF2
$records
EOF2
process_record "$current_path" "$current_branch"

git worktree prune

CONTAINER="${CLAUDE_TASK_WORKTREES_DIR:-$(dirname "$ROOT_REAL")/$(basename "$ROOT_REAL")-worktrees}"
if [ "$APPLY" -eq 1 ] && [ -d "$CONTAINER" ] && [ -z "$(ls -A "$CONTAINER" 2>/dev/null)" ]; then
  rmdir "$CONTAINER" 2>/dev/null && echo "removed empty container: $CONTAINER" || true
fi

echo "cleanup-worktrees: matched=$MATCHED would_remove=$WOULD_REMOVE removed=$REMOVED skipped=$SKIPPED active_deferred=$ACTIVE_DEFERRED active_cleanup_scheduled=$ACTIVE_CLEANUP_SCHEDULED missing_pruned=$MISSING_PRUNED branches_deleted=$BRANCHES_DELETED branches_skipped=$BRANCHES_SKIPPED mode=$([ "$APPLY" -eq 1 ] && echo apply || echo dry-run) task=${TASK_ID:-all}"

if [ "$APPLY" -eq 1 ] && [ -n "$TASK_ID" ] && [ "$SKIPPED" -gt 0 ]; then
  echo "cleanup-worktrees: incomplete task cleanup; dirty candidate(s) were skipped" >&2
  exit 3
fi
