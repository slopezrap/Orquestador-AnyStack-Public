#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
# shellcheck disable=SC1091
[ -f "$ROOT/scripts/unix-runtime-env.sh" ] && . "$ROOT/scripts/unix-runtime-env.sh"
cd "$ROOT"
TASK_ID="${1:-}"
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "--help" ] || [ "$TASK_ID" = "-h" ]; then
  echo 'usage: scripts/verify-slice.sh <TASK_ID>'
  echo 'Prepares verification handoff and hard-resets the per-slice Rancher/Docker runtime when compose applies.'
  exit 0
fi
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
./scripts/inspect-task-state.sh "$TASK_ID" >/dev/null
./scripts/init-verify-slice-handoff.sh "$TASK_ID" >/dev/null
./scripts/verify-slice-state.sh "$TASK_ID" --json
./scripts/check-verify-routing.sh "$TASK_ID"
./scripts/docker-hard-reset.sh --task "$TASK_ID"
if ! ./scripts/check-runtime-logs.sh --task "$TASK_ID" --mode hard-reset; then
  echo "WARN: runtime log check reported hook errors for $TASK_ID; continuing verify-slice as warning" >&2
fi
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops verify_slice_state "$TASK_ID"
