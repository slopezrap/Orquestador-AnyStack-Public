#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-${CLAUDE_PROJECT_DIR:-$SCRIPT_ROOT}}"
ROOT="$ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$ROOT_CANDIDATE")"
fi
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.check_gold_blueprint "${1:-inputs/BLUEPRINT.md}"
