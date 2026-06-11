#!/usr/bin/env bash
set -euo pipefail
# ORQ_HELP_GUARD
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: phase-gate.sh <PHASE_ID>"
  exit 0
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
PHASE="${1:-}"; [ -n "$PHASE" ] || { echo "ERROR: missing PHASE_ID" >&2; exit 2; }
python3 - "$PHASE" <<'PY'
import json, sys
from orchestrator.common import load_registry
phase=sys.argv[1]; reg=load_registry(); tasks=[t for t in reg.get('tasks',[]) if str(t.get('phase_id'))==phase]
not_done=[t.get('id') for t in tasks if t.get('status')!='done']
print(json.dumps({'ok': not not_done, 'phase_id': phase, 'tasks': len(tasks), 'not_done': not_done}, indent=2))
raise SystemExit(0 if not not_done else 3)
PY
