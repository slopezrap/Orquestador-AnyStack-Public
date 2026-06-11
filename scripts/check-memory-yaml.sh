#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
. "$ROOT/scripts/unix-runtime-env.sh" 2>/dev/null || true
python3 -B -S "$ROOT/.claude/bin/check_memory_yaml.py" "$@"
