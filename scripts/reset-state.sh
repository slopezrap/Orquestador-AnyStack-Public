#!/usr/bin/env bash
set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ORCHESTRATOR_CALLER_PWD="$(pwd -P)"
ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
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
if _active_slice_context && [ "${ORCHESTRATOR_ALLOW_DESTRUCTIVE_STATE_RESET:-0}" != "1" ]; then
  echo "ERROR: refusing to reset orchestrator-state while a slice/worktree context is active." >&2
  echo "This protects handoff/evidence/registry for ${CLAUDE_ACTIVE_TASK_ID:-${CLAUDE_TASK_ID:-the active slice}}. Run from the canonical root outside /next-slice, or set ORCHESTRATOR_ALLOW_DESTRUCTIVE_STATE_RESET=1 for maintainer-only cleanup." >&2
  exit 4
fi

rm -rf \
  orchestrator-state/compiled/* \
  orchestrator-state/tasks/* \
  orchestrator-state/memory/* \
  orchestrator-state/agent-memory/* \
  orchestrator-state/dev-ports \
  orchestrator-state/dev-logs \
  orchestrator-state/runs \
  orchestrator-state/archive \
  orchestrator-state/hook-errors.log
mkdir -p \
  orchestrator-state/compiled \
  orchestrator-state/tasks/task-packs \
  orchestrator-state/tasks/slices \
  orchestrator-state/tasks/handoffs \
  orchestrator-state/tasks/evidence \
  orchestrator-state/tasks/reports \
  orchestrator-state/tasks/lifecycle-events \
  orchestrator-state/memory/official-doc-notes \
  orchestrator-state/memory/archive \
  orchestrator-state/agent-memory \
  orchestrator-state/dev-ports \
  orchestrator-state/dev-logs \
  orchestrator-state/runs
