#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: promote-followup-task.sh <FOLLOWUP_ID>"
  echo "Promotes a proposed follow-up to a blueprint patch request; it never edits generated registry/DAG files directly."
  exit 0
fi
FOLLOWUP_ID="${1:-}"
[ -n "$FOLLOWUP_ID" ] || { echo "ERROR: missing FOLLOWUP_ID" >&2; exit 2; }
exec "$ROOT/scripts/python-safe.sh" "$ROOT/.claude/bin/register_followup_task.py" promote "$FOLLOWUP_ID"
