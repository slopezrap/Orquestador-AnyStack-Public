#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ORCHESTRATOR_CALLER_PWD="$(pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
[ -f "$ROOT/scripts/unix-runtime-env.sh" ] && . "$ROOT/scripts/unix-runtime-env.sh"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"

_active_slice_context() {
  [ -n "${CLAUDE_ACTIVE_TASK_ID:-}" ] || [ -n "${CLAUDE_TASK_ID:-}" ] && return 0
  local caller_branch=""
  caller_branch="$(git -C "$ORCHESTRATOR_CALLER_PWD" branch --show-current 2>/dev/null || true)"
  case "$caller_branch" in dev/SLICE-*|slice/*|SLICE-*) return 0 ;; esac
  case "$ORCHESTRATOR_CALLER_PWD" in *-worktrees/SLICE-*|*/worktrees/SLICE-*) return 0 ;; esac
  return 1
}
if _active_slice_context && [ "${ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE:-0}" != "1" ]; then
  echo "ERROR: refusing to run orchestrator self-tests while a slice is active." >&2
  echo "Run only the task-pack/product tests for ${CLAUDE_ACTIVE_TASK_ID:-${CLAUDE_TASK_ID:-the active slice}}, or set ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE=1 for maintainer-only runtime tests." >&2
  exit 4
fi

MODE="${1:-all}"
if [ "$MODE" = "--help" ] || [ "$MODE" = "-h" ]; then
  cat <<'HELP'
usage: scripts/run-all-tests.sh [lint|all|backend|frontend]

lint: read-only static/runtime checks only; never resets, compiles or bootstraps state.
Set ORCHESTRATOR_RUN_SIMULATION=1 to include the full blueprint-to-Claude simulation.
all/backend/frontend: lint + destructive bootstrap smoke + pytest.
HELP
  exit 0
fi
run() {
  printf '[run-all-tests] running: %s\n' "$*"
  "$@"
  printf '[run-all-tests] ok: %s\n' "$*"
}
if [ "$MODE" = "lint" ] || [ "$MODE" = "all" ]; then
  run bash scripts/python-safe.sh -m compileall -q orchestrator .claude/bin scripts
  run bash scripts/python-safe.sh scripts/check-python-runtime.py --min-version 3.13
  run bash scripts/check-claude-adapter.sh
  run bash scripts/check-skills-runtime.sh
  run bash scripts/check-git-pr-flow.sh
  run bash scripts/check-unix-agent-runtime.sh
  run bash scripts/validate-orchestrator-schemas.sh
  run bash scripts/audit-runtime-surface.sh
  run bash scripts/audit-state-machine-contract.sh
fi
if [ "$MODE" = "all" ]; then
  run bash scripts/reset-state.sh
  run bash scripts/compile-blueprint.sh inputs/BLUEPRINT.md
  run bash scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
  run bash scripts/check-task-dag.sh
  run bash scripts/check-parallel-locks.sh
  run bash scripts/check-task-descriptions.sh
  run bash scripts/check-verify-surface.sh
  run bash scripts/check-blueprint-machine-contract.sh
  run bash scripts/check-blueprint-contract.sh
  run bash scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
  run bash scripts/check-gold-blueprint.sh examples/gold/BLUEPRINT.md
  run bash scripts/check-orchestrator-gaps.sh
  run bash scripts/orchestrator-doctor.sh
  run bash scripts/run-golden-e2e.sh
  if [ "${ORCHESTRATOR_RUN_SIMULATION:-0}" = "1" ]; then
    run bash scripts/simulate-blueprint-to-claude-flow.sh
  fi
fi
if [ "$MODE" = "all" ] || [ "$MODE" = "backend" ] || [ "$MODE" = "frontend" ]; then
  export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-1}"
  run bash scripts/python-safe.sh -m pytest -q --cache-clear
fi
printf '{"ok": true, "mode": "%s"}\n' "$MODE"
