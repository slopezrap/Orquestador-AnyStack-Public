#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
# macOS/Linux: add Rancher Desktop and Homebrew tool locations without requiring GNU timeout.
[ -f "$ROOT/scripts/unix-runtime-env.sh" ] && . "$ROOT/scripts/unix-runtime-env.sh"
cd "$ROOT"
if [[ -n "${ORCHESTRATOR_PYTHON:-}" ]]; then
  exec "$ORCHESTRATOR_PYTHON" "$@"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
PY_EXE="$(command -v "$PYTHON_BIN")"
PY_ROOT="$(cd "$(dirname "$PY_EXE")/.." && pwd)"
PY_VER="$($PYTHON_BIN -S -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
SITE_PATHS="${ORCHESTRATOR_EXTRA_PYTHONPATH:-}"
for d in \
  "$PY_ROOT/lib/python$PY_VER/site-packages" \
  "$PY_ROOT/lib/python$PY_VER/dist-packages" \
  /opt/pyvenv/lib/python*/site-packages \
  /usr/local/lib/python*/dist-packages \
  /usr/local/lib/python*/site-packages; do
  if [[ -d "$d" ]]; then
    if [[ -n "$SITE_PATHS" ]]; then SITE_PATHS="$SITE_PATHS:$d"; else SITE_PATHS="$d"; fi
  fi
done
export PYTHONPATH="$ROOT${SITE_PATHS:+:$SITE_PATHS}${PYTHONPATH:+:$PYTHONPATH}"
# Scripts are scoped to the repository that contains this helper. Avoid stale roots across macOS/Linux worktrees.
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
if [[ "${ORCHESTRATOR_DISABLE_PYTHON_SAFE:-0}" == "1" ]]; then
  exec "$PYTHON_BIN" -B "$@"
fi
# Use the same Python 3.13 environment as checks, tests and CI by default.
# Set ORCHESTRATOR_USE_ISOLATED_PYTHON=1 to force the stricter -S mode.
if [[ "${ORCHESTRATOR_USE_ISOLATED_PYTHON:-0}" == "1" ]]; then
  exec "$PYTHON_BIN" -B -S "$@"
fi
exec "$PYTHON_BIN" -B "$@"
