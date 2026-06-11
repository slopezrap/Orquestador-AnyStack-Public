#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-$SCRIPT_ROOT}"
ROOT="$ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$ROOT_CANDIDATE")"
fi
cd "$ROOT"
exec ./scripts/python-safe.sh -m orchestrator.runtime.check_blueprint_lossless_flow "$@"
