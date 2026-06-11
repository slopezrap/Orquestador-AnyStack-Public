#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091
[ -f "$ROOT/scripts/unix-runtime-env.sh" ] && . "$ROOT/scripts/unix-runtime-env.sh"
cd "$ROOT"
TASK_ID="${1:-}"
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "--help" ] || [ "$TASK_ID" = "-h" ]; then
  echo 'usage: scripts/closer.sh <TASK_ID>'
  echo 'Runs closer preflight context. The closer subagent must perform report, git workflow, cleanup and CLAUDE_TRAILER.'
  exit 0
fi
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
"$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops inspect_task_state "$TASK_ID"
printf 'CLOSER_PREFLIGHT: task=%s\n' "$TASK_ID"
printf 'CLOSER_RUNTIME_SNAPSHOT_COMMAND: ./scripts/sync-runtime-snapshot.sh %s\n' "$TASK_ID"
printf 'CLOSER_GIT_WORKFLOW_COMMAND: ./scripts/git-workflow.sh %s\n' "$TASK_ID"
printf 'CLOSER_RUNTIME_CLEANUP_COMMAND: ./scripts/cleanup-slice-runtime.sh --task %s --apply --strict\n' "$TASK_ID"
printf 'CLOSER_REQUIRED_TRAILER_KEYS: REPORT_READY BASELINE_SYNC_READY GIT_READY PUSH_READY GIT_WORKFLOW_READY RUNTIME_CLEANED DOCKER_RUNTIME_CLEANED RANCHER_RUNTIME_CLEANED DEV_PORTS_RELEASED WORKTREES_CLEANED\n'
