#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops init_verify_slice_handoff --help
  exit 0
fi
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops init_verify_slice_handoff "$@"
