#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CALL_DIR="$(pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
# shellcheck disable=SC1091
[ -f "$ROOT/scripts/unix-runtime-env.sh" ] && . "$ROOT/scripts/unix-runtime-env.sh"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ] || [ -z "${1:-}" ]; then
  echo "Usage: next-slice.sh <TASK_ID>"
  echo "Atomically claims one ready DAG task, then starts the per-slice Rancher/Docker runtime when compose applies."
  exit 0
fi
TASK_ID="$1"
# Guard the exact active checkout before claiming. In branch-per-task workflows
# this prevents a direct call from canonical main from claiming lifecycle while
# hooks/subagents later run in a different worktree.
(cd "$CALL_DIR" && bash "$ROOT/scripts/ensure-task-worktree.sh" --check-current "$TASK_ID")
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
export CLAUDE_WORKSPACE_ROOT="${CLAUDE_WORKSPACE_ROOT:-${CLAUDE_WORKTREE_ROOT:-$CALL_DIR}}"
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.claim_task "$TASK_ID" --in-progress
# Runtime startup is best-effort when no compose file exists, but blocking when a declared compose runtime cannot start.
"$ROOT/scripts/dev-restart.sh" --task "$TASK_ID" --soft
