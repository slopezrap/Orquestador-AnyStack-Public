#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  exec "$ROOT/scripts/python-safe.sh" "$ROOT/.claude/bin/register_followup_task.py"
fi
exec "$ROOT/scripts/python-safe.sh" "$ROOT/.claude/bin/register_followup_task.py" "$@"
