from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.common import now_iso, promote_ready_tasks, read_yaml, tasks_dir

INITIAL_BOOTSTRAP_STATUSES = {"todo", "ready"}
ACTIVE_LIFECYCLE_STATUSES = {
    "claimed",
    "in_progress",
    "validator_tester_pending",
    "needs_debug",
    "ready_for_close",
    "verified_pending_close",
}


def _read_event_objects(path: Path) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    try:
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                objects.append(obj)
            elif isinstance(obj, list):
                objects.extend([x for x in obj if isinstance(x, dict)])
        elif path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    objects.append(obj)
        elif path.suffix in {".yaml", ".yml"}:
            obj = read_yaml(path, {}) or {}
            if isinstance(obj, dict) and isinstance(obj.get("events"), list):
                objects.extend([x for x in obj.get("events") if isinstance(x, dict)])
            elif isinstance(obj, dict):
                objects.append(obj)
            elif isinstance(obj, list):
                objects.extend([x for x in obj if isinstance(x, dict)])
    except Exception:
        return objects
    return objects


def _status_from_event_object(obj: dict[str, Any]) -> tuple[str | None, str, str, str]:
    """Return (status, actor, outcome, at) for one lifecycle object."""
    status: str | None = None
    actor = str(obj.get("source") or obj.get("agent") or obj.get("actor") or "lifecycle-event")
    outcome = str(obj.get("event_type") or obj.get("reason") or obj.get("outcome") or obj.get("kind") or "lifecycle-event")
    at = str(obj.get("created_at") or obj.get("at") or obj.get("updated_at") or "")
    if obj.get("target_status"):
        status = str(obj.get("target_status"))
    elif obj.get("to_status"):
        status = str(obj.get("to_status"))
    elif obj.get("next_status") and obj.get("lifecycle_mutated") not in (False, "false", "False"):
        status = str(obj.get("next_status"))
    elif obj.get("status"):
        status = str(obj.get("status"))
    events = [e for e in (obj.get("events") or []) if isinstance(e, dict)]
    for ev in events:
        ev_status, ev_actor, ev_outcome, ev_at = _status_from_event_object(ev)
        if ev_status:
            status = ev_status
            actor = ev_actor or actor
            outcome = ev_outcome or outcome
            at = ev_at or at
    if not status and obj.get("last_status"):
        status = str(obj.get("last_status"))
    return status, actor, outcome, at


def lifecycle_event_statuses(base_dir: Path | None = None) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Read durable lifecycle event files and return latest target status by task.

    The per-task files under orchestrator-state/tasks/lifecycle-events are the
    compact durable close signals transported through PR-flow. They are safe to
    apply after bootstrap regenerates local registry/task-dag/task-packs.
    """
    base = base_dir or (tasks_dir() / "lifecycle-events")
    statuses: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    if not base.exists():
        return statuses, skipped
    paths = sorted(list(base.glob("*.json")) + list(base.glob("*.jsonl")) + list(base.glob("*.yaml")) + list(base.glob("*.yml")))
    for path in paths:
        objects = _read_event_objects(path)
        if not objects:
            skipped.append({"path": str(path), "reason": "empty_or_unreadable"})
            continue
        found = False
        for obj in objects:
            tid = str(obj.get("task_id") or obj.get("id") or path.stem)
            status, actor, outcome, at = _status_from_event_object(obj)
            if not status:
                continue
            statuses[tid] = {
                "task_id": tid,
                "status": status,
                "actor": actor,
                "outcome": outcome,
                "at": at,
                "path": str(path),
            }
            found = True
        if not found:
            skipped.append({"path": str(path), "reason": "no_status_event"})
    return statuses, skipped


def refresh_registry_status_indexes(registry: dict[str, Any]) -> dict[str, Any]:
    """Keep registry, DAG nodes and phase summaries in sync after status edits."""
    by_id = {str(t.get("id") or t.get("task_id")): t for t in registry.get("tasks", []) or [] if isinstance(t, dict)}
    for node in ((registry.get("task_dag") or {}).get("nodes") or []):
        tid = str(node.get("id") or node.get("task_id"))
        task = by_id.get(tid)
        if task:
            node["status"] = task.get("status")
    for phase in registry.get("phases", []) or []:
        if not isinstance(phase, dict):
            continue
        statuses = [str((by_id.get(str(tid)) or {}).get("status") or "todo") for tid in phase.get("task_ids", []) or []]
        if not statuses:
            phase["status"] = "todo"
        elif all(s == "done" for s in statuses):
            phase["status"] = "done"
        elif any(s in ACTIVE_LIFECYCLE_STATUSES for s in statuses):
            phase["status"] = "active"
        elif any(s == "ready" for s in statuses):
            phase["status"] = "ready"
        elif any(s == "blocked" for s in statuses):
            phase["status"] = "blocked"
        else:
            phase["status"] = "todo"
    return registry


def apply_lifecycle_events_to_registry(registry: dict[str, Any], *, base_dir: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    statuses, skipped = lifecycle_event_statuses(base_dir)
    by_id = {str(t.get("id") or t.get("task_id")): t for t in registry.get("tasks", []) or [] if isinstance(t, dict)}
    applied: list[dict[str, Any]] = []
    for tid, event in sorted(statuses.items()):
        task = by_id.get(tid)
        if not task:
            skipped.append({"task_id": tid, "path": event.get("path"), "reason": "unknown_task"})
            continue
        before = str(task.get("status") or "")
        target = str(event.get("status") or "")
        if not target:
            continue
        task["status"] = target
        task["last_updated_by"] = event.get("actor") or "sync-lifecycle-events"
        task["last_outcome"] = event.get("outcome") or "lifecycle-event"
        task["last_stop_at"] = event.get("at") or now_iso()
        task.setdefault("rehydrated_from_lifecycle_events", []).append({"path": event.get("path"), "status": target, "at": now_iso()})
        applied.append({"task_id": tid, "from": before, "to": target, "path": event.get("path")})
    registry = promote_ready_tasks(registry)
    registry = refresh_registry_status_indexes(registry)
    return registry, applied, skipped


def bootstrap_reset_guard_errors(existing_registry: dict[str, Any], existing_runtime: dict[str, Any], *, new_task_ids: set[str], lifecycle_task_ids: set[str], allow_reset: bool = False) -> list[str]:
    if allow_reset:
        return []
    errors: list[str] = []
    active_task_id = str(existing_runtime.get("active_task_id") or "").strip()
    if active_task_id and active_task_id.lower() not in {"none", "null", "-"}:
        errors.append(f"active_task_id={active_task_id}; bootstrap would clear active runtime state")
    tasks = [t for t in existing_registry.get("tasks", []) or [] if isinstance(t, dict)]
    active = []
    unprotected_progress = []
    for task in tasks:
        tid = str(task.get("id") or task.get("task_id") or "")
        if not tid or tid not in new_task_ids:
            continue
        status = str(task.get("status") or "")
        if status in ACTIVE_LIFECYCLE_STATUSES:
            active.append(f"{tid}:{status}")
        if status and status not in INITIAL_BOOTSTRAP_STATUSES and tid not in lifecycle_task_ids:
            unprotected_progress.append(f"{tid}:{status}")
    if active:
        errors.append("active lifecycle task(s) would be regenerated: " + ", ".join(active[:12]))
    if unprotected_progress:
        errors.append(
            "existing lifecycle progress has no durable lifecycle-events/<TASK_ID>.json to restore after bootstrap: "
            + ", ".join(unprotected_progress[:12])
        )
    return errors
