#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.check_claude_adapter "$@"
