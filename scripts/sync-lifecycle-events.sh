#!/usr/bin/env bash
set -euo pipefail
APPLY=0
if [ "${1:-}" = "--apply" ]; then APPLY=1; shift; fi
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  cat <<'EOH'
Usage: scripts/sync-lifecycle-events.sh [--apply]

Rehydrate local registry/runtime state from durable per-task lifecycle events
that travelled through slice PRs. This preserves the DAG behavior:
registry.json is local runtime and is not committed, while
orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json is the small durable
signal merged to main by pr-flow.

The rehydration understands target_status, last_status and events[] formats,
then runs promote_ready_tasks so dependents unblock after done tasks are
restored.

check-token: target_status last_status promote_ready_tasks
EOH
  exit 0
fi
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-$SCRIPT_ROOT}"
ROOT="$ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$ROOT_CANDIDATE")"
fi
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
PYTHONPATH="$ROOT:${PYTHONPATH:-}" python3 -B -S - "$APPLY" <<'PY'
from __future__ import annotations
import json, sys
from orchestrator.common import load_registry, save_registry, load_runtime_state, save_runtime_state, now_iso
from orchestrator.runtime.lifecycle_events import apply_lifecycle_events_to_registry, lifecycle_event_statuses
from orchestrator.runtime.memory_yaml import write_memory_snapshot

apply = sys.argv[1] == "1"
if apply:
    reg = load_registry()
    reg, applied, skipped = apply_lifecycle_events_to_registry(reg)
    save_registry(reg)
    try:
        rt = load_runtime_state()
        rt["last_lifecycle_sync"] = {"at": now_iso(), "applied": len(applied), "skipped": len(skipped), "source": "sync-lifecycle-events.sh"}
        save_runtime_state(rt)
    except Exception:
        pass
    try:
        write_memory_snapshot(registry=reg)
    except Exception:
        pass
else:
    statuses, skipped = lifecycle_event_statuses()
    applied = [{"task_id": tid, "to": data.get("status"), "path": data.get("path")} for tid, data in sorted(statuses.items())]

print("LIFECYCLE_EVENTS_APPLIED: %s" % ("yes" if apply else "dry-run"))
print("LIFECYCLE_EVENTS_FILES: %d" % (len(applied) + len(skipped)))
print("LIFECYCLE_EVENTS_TASKS: %d" % len(applied))
print("LIFECYCLE_EVENTS_SKIPPED: %d" % len(skipped))
print("RUNTIME_GIT_PROTECTED: yes")
if skipped:
    for item in skipped[:20]:
        print("LIFECYCLE_EVENT_SKIPPED: " + json.dumps(item, ensure_ascii=False, sort_keys=True))
PY
