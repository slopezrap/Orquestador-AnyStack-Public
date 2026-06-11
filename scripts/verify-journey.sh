#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  cat <<'EOF'
usage: scripts/verify-journey.sh <JOURNEY_ID> [--verified|--waived|--issues-found]

Without a status flag, prints journey closures and current pending gates.
With --verified/--waived, clears the pending journey gate for that JOURNEY_ID.
With --issues-found, keeps/adds the journey as pending.
EOF
  exit 0
fi
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops update_journey_verification "$@"
