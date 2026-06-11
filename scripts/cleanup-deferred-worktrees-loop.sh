#!/usr/bin/env bash
set -euo pipefail

# Detached janitor used by the Claude Stop hook. It retries deferred worktree
# cleanup for a bounded window because the old Claude process/terminal may keep
# the just-closed worktree alive for a few seconds after SubagentStop/Stop.

INITIAL_DELAY=10
INTERVAL=15
TIMEOUT=600
QUIET=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

usage() {
  cat <<'USAGE'
Usage: scripts/cleanup-deferred-worktrees-loop.sh [--initial-delay N] [--interval N] [--timeout N] [--quiet]

Retry cleanup-deferred-worktrees.sh from the canonical root until cleanup requests
are gone or the timeout expires. This script never forces dirty/live worktrees.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --initial-delay)
      INITIAL_DELAY="${2:-}"; [ -n "$INITIAL_DELAY" ] || { echo "ERROR: --initial-delay requires seconds" >&2; exit 2; }; shift 2 ;;
    --interval)
      INTERVAL="${2:-}"; [ -n "$INTERVAL" ] || { echo "ERROR: --interval requires seconds" >&2; exit 2; }; shift 2 ;;
    --timeout)
      TIMEOUT="${2:-}"; [ -n "$TIMEOUT" ] || { echo "ERROR: --timeout requires seconds" >&2; exit 2; }; shift 2 ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$INITIAL_DELAY$INTERVAL$TIMEOUT" in *[!0-9]*) echo "ERROR: delays/timeouts must be integer seconds" >&2; exit 2 ;; esac

REQ_DIR="$ROOT/orchestrator-state/tasks/cleanup-requests"
request_count() {
  if [ ! -d "$REQ_DIR" ]; then
    printf '0\n'
    return 0
  fi
  find "$REQ_DIR" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | wc -l | tr -d ' '
}

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }

sleep "$INITIAL_DELAY"
start="$(date +%s)"
while :; do
  count="$(request_count)"
  [ "$count" = "0" ] && { say "cleanup-deferred-loop: requests=0"; exit 0; }

  # Best effort: cleanup-deferred-worktrees exits non-zero when a closed worktree
  # is dirty/live. That should not kill the janitor; we retry until timeout.
  (cd "$ROOT" && bash scripts/cleanup-deferred-worktrees.sh --apply --quiet) || true

  count="$(request_count)"
  [ "$count" = "0" ] && { say "cleanup-deferred-loop: cleaned"; exit 0; }

  now="$(date +%s)"
  elapsed=$((now - start))
  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    say "cleanup-deferred-loop: pending=$count timeout=${TIMEOUT}s; will retry on next-wave/next-slice/session"
    exit 0
  fi
  sleep "$INTERVAL"
done
