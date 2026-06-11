#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-$SCRIPT_ROOT}"
ROOT="$ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$ROOT_CANDIDATE")"
fi
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
exec python3 -B -S "$ROOT/scripts/sync_main_before_wave.py" "$@"
