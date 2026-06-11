#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
# Safe bootstrap guard: this script may run after ZIP extraction or a Windows/WSL checkout.
bash "$ROOT/scripts/fix-permissions.sh" >/dev/null 2>&1 || true
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops setup_from_scratch --help
  exit 0
fi
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops setup_from_scratch "$@"
