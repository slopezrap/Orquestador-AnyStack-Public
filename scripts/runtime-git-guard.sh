#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
ROOT="$ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$ROOT_CANDIDATE")"
fi
exec python3 -B -S "$ROOT/.claude/bin/runtime_git_guard.py" "$@"
