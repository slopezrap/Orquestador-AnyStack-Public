from __future__ import annotations

import json
import platform
from typing import Any

from orchestrator.common import load_registry, read_json, task_conflict_reasons, tasks_dir


def _by_id(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(t.get("id")): t for t in tasks if isinstance(t, dict) and t.get("id")}


def check() -> dict[str, Any]:
    reg = load_registry()
    dag_file = read_json(tasks_dir() / "task-dag.json", {})
    tasks = _by_id(reg.get("tasks", []) or [])
    dag = reg.get("task_dag") or {}
    # Some hooks/checks may briefly observe a registry fallback while another
    # process has just refreshed runtime memory mirrors. The DAG file is an
    # independent generated artifact, so use it as a read-only fallback for the
    # parallel/lock audit instead of reporting a false empty DAG.
    if not tasks and isinstance(dag_file, dict):
        tasks = _by_id(dag_file.get("nodes", []) or [])
    if not dag and isinstance(dag_file, dict):
        dag = dag_file
    errors: list[str] = []
    warnings: list[str] = []

    par = dag.get("parallelism") or {}
    if not par:
        errors.append("task_dag.parallelism is missing")
    else:
        try:
            if int(par.get("max_parallel_slices") or 0) < 1:
                errors.append("parallelism.max_parallel_slices must be >= 1")
        except Exception:
            errors.append("parallelism.max_parallel_slices must be an integer")
        if par.get("lock_backend") != "posix_fcntl_file_locks":
            errors.append("parallelism.lock_backend must be posix_fcntl_file_locks")
        platforms = set(str(x).lower() for x in par.get("supported_platforms") or [])
        if not {"linux", "darwin"} <= platforms:
            errors.append("parallelism.supported_platforms must include linux and darwin")

    lock_model = dag.get("lock_model") or {}
    for key in ["backend", "registry_lock", "runtime_lock", "handoff_lock_pattern"]:
        if not lock_model.get(key):
            errors.append(f"task_dag.lock_model missing {key}")
    if lock_model.get("backend") and "fcntl" not in str(lock_model.get("backend")):
        errors.append("task_dag.lock_model.backend must document fcntl/flock advisory locks")

    groups = dag.get("parallel_groups") or []
    if not isinstance(groups, list) or not groups:
        errors.append("task_dag.parallel_groups is missing or empty")
    seen_group_tasks: set[str] = set()
    for group in groups:
        tids = [str(x) for x in group.get("task_ids") or []]
        if not tids:
            errors.append(f"parallel group {group.get('id')} has no task_ids")
            continue
        for tid in tids:
            if tid not in tasks:
                errors.append(f"parallel group {group.get('id')} references unknown task {tid}")
            seen_group_tasks.add(tid)
        for idx, tid in enumerate(tids):
            for other in tids[idx + 1:]:
                if tid in tasks and other in tasks:
                    reasons = task_conflict_reasons(tasks[tid], tasks[other])
                    if reasons:
                        errors.append(f"parallel group {group.get('id')} is not safe: {tid}<->{other}: {reasons}")

    if set(tasks) - seen_group_tasks:
        errors.append(f"tasks missing from parallel_groups: {sorted(set(tasks)-seen_group_tasks)}")

    for tid, task in sorted(tasks.items()):
        locks = task.get("locks") or {}
        if not locks:
            errors.append(f"{tid}: missing locks")
            continue
        for key in ["task", "write_set", "conflict_groups", "lock_files"]:
            if key not in locks:
                errors.append(f"{tid}: locks missing {key}")
        for lf in locks.get("lock_files") or []:
            lf = str(lf)
            if not lf.endswith(".lock"):
                errors.append(f"{tid}: lock file does not end with .lock: {lf}")
            if "\\" in lf:
                errors.append(f"{tid}: lock file must use POSIX separators: {lf}")
        parallel = task.get("parallel") or {}
        if not parallel:
            errors.append(f"{tid}: missing parallel metadata")
        elif parallel.get("safe_group") not in {g.get("id") for g in groups}:
            errors.append(f"{tid}: parallel.safe_group does not reference a task_dag.parallel_groups id")

    sysname = platform.system().lower()
    if sysname not in {"linux", "darwin"}:
        warnings.append(f"lock backend is designed for linux/darwin; current platform reports {platform.system()}")

    return {
        "ok": not errors,
        "errors": sorted(set(errors)),
        "warnings": warnings,
        "tasks": len(tasks),
        "parallel_groups": len(groups) if isinstance(groups, list) else 0,
        "max_parallel_slices": par.get("max_parallel_slices"),
        "platform": platform.system(),
    }


def main() -> int:
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
