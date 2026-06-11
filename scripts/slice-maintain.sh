#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091
[ -f "$ROOT/scripts/unix-runtime-env.sh" ] && . "$ROOT/scripts/unix-runtime-env.sh"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
TASK_ID="${1:-}"
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "--help" ] || [ "$TASK_ID" = "-h" ]; then
  cat <<'HELP'
usage: scripts/slice-maintain.sh <TASK_ID>

Runs safe per-slice housekeeping without editing generated DAG state by hand:
  - inspect current task state
  - validate existing handoff shape when present
  - check runtime/hook logs
  - compact agent memory opportunistically
HELP
  exit 0
fi
./scripts/inspect-task-state.sh "$TASK_ID" >/dev/null
echo "SLICE_MAINTAIN_TASK_STATE: inspected"
# The handoff may be incomplete while /next-slice is still running; maintenance reports it but does not block the slice loop.
if ! ./scripts/check-handoff-contract.sh "$TASK_ID" >/dev/null 2>&1; then
  echo "SLICE_MAINTAIN_HANDOFF_STATUS: pending_or_incomplete"
else
  echo "SLICE_MAINTAIN_HANDOFF_STATUS: ok"
fi
if ! ./scripts/check-runtime-logs.sh --task "$TASK_ID"; then
  echo "WARN: runtime log check reported hook errors for $TASK_ID; continuing maintenance as warning" >&2
fi
if [ "${CLAUDE_AUTO_COMPACT_AGENT_MEMORY:-1}" != "0" ] && [ -f "$ROOT/scripts/compact-agent-memory.py" ]; then
  threshold="${CLAUDE_AGENT_MEMORY_COMPACT_THRESHOLD_LINES:-250}"
  python3 -B -S "$ROOT/scripts/compact-agent-memory.py" --all --apply --threshold-lines "$threshold" --quiet >/dev/null 2>&1 || \
    echo "WARN: agent memory auto-compaction incomplete; run: python3 -B -S scripts/compact-agent-memory.py --all --apply --threshold-lines $threshold" >&2
fi
echo "SLICE_MAINTAIN: ok"
