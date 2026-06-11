#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops check_journey_matrix --help
  exit 0
fi
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops check_journey_matrix "$@"
