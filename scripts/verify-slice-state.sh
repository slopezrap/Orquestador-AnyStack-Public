#!/usr/bin/env bash
set -euo pipefail
# ORQ_HELP_GUARD
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: verify-slice-state.sh <TASK_ID> [--json]"
  exit 0
fi
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
TASK_ID="${1:-}"; [ -n "$TASK_ID" ] || { echo "ERROR: missing TASK_ID" >&2; exit 2; }
python3 -B -S "$ROOT/.claude/bin/verify_slice_state.py" "$TASK_ID"
