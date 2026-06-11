#!/usr/bin/env bash
set -euo pipefail

# Remove task worktrees that were deliberately deferred by cleanup-worktrees.sh
# because Claude Code was still running hooks from inside that worktree.
# This script is safe to run from the canonical root before /next-wave or
# /next-slice. It refuses to remove the checkout it is currently running from.

APPLY=0
TASK_ID=""
QUIET=0
VERBOSE=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

usage() {
  cat <<'USAGE'
Usage: scripts/cleanup-deferred-worktrees.sh [--apply] [--task TASK_ID] [--quiet] [--verbose]

Scans orchestrator-state/tasks/cleanup-requests/*.json and removes completed
per-slice worktrees from a safe checkout. Default is dry-run. This is the
hook-safe follow-up for cleanup-worktrees.sh when it reports active_deferred=1.
Requests for tasks that are not closed yet stay pending; dirty closed worktrees
are never discarded automatically and must be reviewed manually.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --dry-run) APPLY=0; shift ;;
    --task)
      TASK_ID="${2:-}"
      [ -n "$TASK_ID" ] || { echo "ERROR: --task requires TASK_ID" >&2; exit 2; }
      shift 2
      ;;
    --quiet) QUIET=1; shift ;;
    --verbose) VERBOSE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  say "cleanup-deferred-worktrees: git_repository=no requests=0 removed=0 skipped=0 mode=$([ "$APPLY" -eq 1 ] && echo apply || echo dry-run)"
  exit 0
fi

CURRENT_ROOT="$(git rev-parse --show-toplevel)"
resolve_canonical_root() {
  local common_dir
  common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
    (cd "$(dirname "$common_dir")" && pwd -P)
  else
    (cd "$CURRENT_ROOT" && pwd -P)
  fi
}
ROOT="$(resolve_canonical_root)"
ROOT_REAL="$(cd "$ROOT" && pwd -P)"
CURRENT_REAL="$(cd "$CURRENT_ROOT" && pwd -P)"
CLEANUP_WORKTREES_SCRIPT="$ROOT_REAL/scripts/cleanup-worktrees.sh"
if [ ! -f "$CLEANUP_WORKTREES_SCRIPT" ] && [ -f "$SCRIPT_DIR/cleanup-worktrees.sh" ]; then
  CLEANUP_WORKTREES_SCRIPT="$SCRIPT_DIR/cleanup-worktrees.sh"
fi
REQ_DIR="$ROOT_REAL/orchestrator-state/tasks/cleanup-requests"

if [ ! -d "$REQ_DIR" ]; then
  say "cleanup-deferred-worktrees: requests=0 removed=0 skipped=0 mode=$([ "$APPLY" -eq 1 ] && echo apply || echo dry-run)"
  exit 0
fi

# Bash 3/macOS compatible: cleanup request filenames are generated as
# <TASK_ID>.json by cleanup-worktrees.sh, so newline-safe sorting is enough.
# Do not use an array here: Bash 3.2 + set -u can raise "unbound variable" for
# empty array expansion, which would make /next-wave warn even when there is
# simply nothing to clean. A temp file is boring but portable.
REQUESTS_FILE="$(mktemp "${TMPDIR:-/tmp}/cleanup-deferred-requests.XXXXXX")"
LOG_TMP="${TMPDIR:-/tmp}/cleanup-deferred-$$.log"
cleanup_tmp_files() {
  rm -f "$REQUESTS_FILE" "$LOG_TMP"
}
trap cleanup_tmp_files EXIT HUP INT TERM

if [ -n "$TASK_ID" ]; then
  [ -f "$REQ_DIR/$TASK_ID.json" ] && printf '%s\n' "$REQ_DIR/$TASK_ID.json" >"$REQUESTS_FILE"
else
  find "$REQ_DIR" -maxdepth 1 -type f -name '*.json' -print | LC_ALL=C sort >"$REQUESTS_FILE"
fi

path_has_live_usage() {
  if [ "${CLAUDE_DEFERRED_CLEANUP_ASSUME_INACTIVE:-0}" = "1" ]; then
    return 1
  fi
  local target="$1"
  local target_real cwd link
  target_real="$(cd "$target" 2>/dev/null && pwd -P || printf '%s' "$target")"

  # Never remove a checkout that this cleanup process is currently inside.
  cwd="$(pwd -P)"
  case "$cwd" in
    "$target_real"|"$target_real"/*) return 0 ;;
  esac

  # Linux: detect shells/Claude processes whose cwd is still inside the worktree.
  if [ -d /proc ]; then
    for link in /proc/[0-9]*/cwd; do
      [ -e "$link" ] || continue
      cwd="$(readlink "$link" 2>/dev/null || true)"
      case "$cwd" in
        "$target_real"|"$target_real"/*) return 0 ;;
      esac
    done
  fi

  # macOS / fallback: lsof is broader than cwd-only, but safe. A live editor,
  # shell, watcher, or Claude process means this cleanup can be retried later.
  if command -v lsof >/dev/null 2>&1; then
    if lsof +D "$target_real" >/dev/null 2>&1; then
      return 0
    fi
  fi

  return 1
}

cleanup_ready_state() {
  local tid="$1"
  python3 -B -S - "$ROOT_REAL" "$tid" <<'PY_READY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
tid = sys.argv[2]

def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None

event = load_json(root / 'orchestrator-state' / 'tasks' / 'lifecycle-events' / f'{tid}.json')
if isinstance(event, dict):
    if (event.get('schema') == 'orquestador.lifecycle-event.v1'
        and event.get('task_id') == tid
        and event.get('agent_type') == 'closer'
        and event.get('outcome') == 'committed'
        and event.get('next_status') == 'done'):
        print('ready:lifecycle-event')
        raise SystemExit(0)

registry = load_json(root / 'orchestrator-state' / 'tasks' / 'registry.json')
status = ''
if isinstance(registry, dict):
    tasks = registry.get('tasks')
    task = None
    if isinstance(tasks, list):
        task = next((t for t in tasks if isinstance(t, dict) and str(t.get('id') or t.get('task_id') or '') == tid), None)
    elif isinstance(tasks, dict):
        obj = tasks.get(tid)
        task = obj if isinstance(obj, dict) else None
    if isinstance(task, dict):
        status = str(task.get('status') or '')
        if status == 'done':
            print('ready:registry-done')
            raise SystemExit(0)
print('pending:' + (status or 'unknown'))
raise SystemExit(1)
PY_READY
}

TOTAL=0
REMOVED=0
SKIPPED=0
STALE=0
PENDING=0

while IFS= read -r req; do
  [ -n "$req" ] || continue
  [ -f "$req" ] || continue
  TOTAL=$((TOTAL + 1))
  fields_out="$(python3 -B -S - "$req" <<'PY' || true
import json, sys
from pathlib import Path
try:
    data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
except Exception:
    data={}
for key in ('task_id','worktree','branch'):
    print(str(data.get(key) or ''))
PY
)"
  tid="$(printf '%s\n' "$fields_out" | sed -n '1p')"
  wt="$(printf '%s\n' "$fields_out" | sed -n '2p')"
  branch="$(printf '%s\n' "$fields_out" | sed -n '3p')"
  if [ -z "$tid" ] || [ -z "$wt" ]; then
    SKIPPED=$((SKIPPED + 1))
    say "skip malformed cleanup request: $req"
    continue
  fi
  if [ -n "$TASK_ID" ] && [ "$tid" != "$TASK_ID" ]; then
    continue
  fi
  if [ ! -e "$wt" ]; then
    rm -f "$req"
    STALE=$((STALE + 1))
    [ "$VERBOSE" -eq 1 ] && say "removed stale cleanup request: $req"
    continue
  fi
  ready_state="$(cleanup_ready_state "$tid" 2>/dev/null || true)"
  case "$ready_state" in
    ready:*)
      [ "$VERBOSE" -eq 1 ] && say "cleanup ready: $tid (${ready_state#ready:})"
      ;;
    *)
      PENDING=$((PENDING + 1))
      [ "$VERBOSE" -eq 1 ] && say "defer cleanup pending close/merge: $tid (${ready_state#pending:})"
      continue
      ;;
  esac
  wt_real="$(cd "$wt" 2>/dev/null && pwd -P || printf '%s' "$wt")"
  if [ "$wt_real" = "$CURRENT_REAL" ]; then
    SKIPPED=$((SKIPPED + 1))
    say "skip active current checkout: $wt ($branch)"
    say "auto cleanup pending: Stop hook janitor/next-wave will retry; fallback command: cd '$ROOT_REAL' && bash scripts/cleanup-deferred-worktrees.sh --apply --task '$tid'"
    continue
  fi
  if path_has_live_usage "$wt"; then
    SKIPPED=$((SKIPPED + 1))
    say "skip live deferred worktree: $wt ($branch)"
    say "auto cleanup will retry later; fallback command: cd '$ROOT_REAL' && bash scripts/cleanup-deferred-worktrees.sh --apply --task '$tid'"
    continue
  fi
  if [ "$APPLY" -ne 1 ]; then
    say "would remove deferred worktree: $wt ($branch)"
    continue
  fi

  # Ignore stale Claude env vars from the old worker; current cwd is the safety signal.
  if env -u CLAUDE_PROJECT_DIR -u CLAUDE_WORKTREE_ROOT -u CLAUDE_WORKSPACE_ROOT \
      CLAUDE_CLEANUP_EXPLAIN_DIRTY=1 \
      bash "$CLEANUP_WORKTREES_SCRIPT" --apply --task "$tid" --remove-active >"$LOG_TMP" 2>&1; then
    [ "$QUIET" -eq 1 ] || cat "$LOG_TMP"
    rm -f "$LOG_TMP"
    if [ ! -e "$wt" ]; then
      rm -f "$req"
      REMOVED=$((REMOVED + 1))
    else
      SKIPPED=$((SKIPPED + 1))
      say "deferred cleanup did not remove path: $wt"
    fi
  else
    rc=$?
    cat "$LOG_TMP" >&2 || true
    rm -f "$LOG_TMP"
    SKIPPED=$((SKIPPED + 1))
    say "deferred cleanup failed for $tid with status $rc"
  fi
done <"$REQUESTS_FILE"

say "cleanup-deferred-worktrees: requests=$TOTAL removed=$REMOVED skipped=$SKIPPED pending=$PENDING stale=$STALE mode=$([ "$APPLY" -eq 1 ] && echo apply || echo dry-run) task=${TASK_ID:-all}"

if [ "$APPLY" -eq 1 ] && [ "$SKIPPED" -gt 0 ]; then
  exit 3
fi
