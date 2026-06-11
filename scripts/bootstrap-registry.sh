#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
INPUT="${1:-orchestrator-state/compiled/orchestrator-input.json}"
# The compiler normally writes the input immediately before bootstrap. Wait until
# the file is visible, non-empty and parseable before handing it to Python.  Use
# `python -c` rather than `python -` so this check never consumes inherited stdin
# from Claude hooks, tests, or subprocess harnesses.
for _ in $(seq 1 40); do
  if "${PYTHON_BIN:-python3}" -B -S -c 'import json, sys; from pathlib import Path; p=Path(sys.argv[1]);
import sys as _sys
if (not p.exists()) or p.stat().st_size <= 0: raise SystemExit(1)
with p.open(encoding="utf-8") as f: data=json.load(f)
if (not isinstance(data, dict)) or (not data.get("schema_version")): raise SystemExit(1)' "$INPUT" >/dev/null 2>&1
  then
    break
  fi
  sleep 0.05
done
"$ROOT/scripts/python-safe.sh" -m orchestrator.bootstrap.bootstrap_registry "$@"
