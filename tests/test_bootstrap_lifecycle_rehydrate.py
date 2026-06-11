from __future__ import annotations

import json
import subprocess
from pathlib import Path

from orchestrator.runtime.lifecycle_events import bootstrap_reset_guard_errors

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, check=True):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=60)


def load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def prepare_smoke_runtime():
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "examples/smoke/BLUEPRINT.md"])
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def test_bootstrap_auto_rehydrates_done_from_durable_lifecycle_event():
    prepare_smoke_runtime()
    events_dir = ROOT / "orchestrator-state" / "tasks" / "lifecycle-events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "SLICE-F0-001.json").write_text(
        json.dumps({
            "task_id": "SLICE-F0-001",
            "target_status": "done",
            "source": "closer",
            "event_type": "durable_close_signal",
            "created_at": "2026-06-10T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    proc = run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])
    out = json.loads(proc.stdout)
    assert out["lifecycle_sync_applied"] == 1

    reg = load_json("orchestrator-state/tasks/registry.json")
    by_id = {t["id"]: t for t in reg["tasks"]}
    assert by_id["SLICE-F0-001"]["status"] == "done"
    assert by_id["SLICE-F1-001"]["status"] == "ready"

    dag = load_json("orchestrator-state/tasks/task-dag.json")
    dag_status = {n["id"]: n["status"] for n in dag["nodes"]}
    assert dag_status["SLICE-F0-001"] == "done"

    pack = load_json("orchestrator-state/tasks/task-packs/SLICE-F0-001.json")
    assert pack["status"] == "done"
    runtime = load_json("orchestrator-state/tasks/runtime-state.json")
    assert runtime["last_lifecycle_sync"]["applied"] == 1


def test_bootstrap_guard_refuses_unprotected_existing_progress_without_lifecycle_event():
    existing_registry = {"tasks": [{"id": "SLICE-F0-001", "status": "done"}]}
    errors = bootstrap_reset_guard_errors(
        existing_registry,
        {"spawn_counts": {}},
        new_task_ids={"SLICE-F0-001"},
        lifecycle_task_ids=set(),
    )
    assert errors
    assert "SLICE-F0-001:done" in errors[-1]


def test_bootstrap_guard_refuses_active_runtime_state_before_regenerating():
    errors = bootstrap_reset_guard_errors(
        {"tasks": [{"id": "SLICE-F0-001", "status": "in_progress"}]},
        {"active_task_id": "SLICE-F0-001"},
        new_task_ids={"SLICE-F0-001"},
        lifecycle_task_ids={"SLICE-F0-001"},
    )
    assert any("active_task_id=SLICE-F0-001" in e for e in errors)
    assert any("active lifecycle task" in e for e in errors)


def test_no_sync_lifecycle_is_treated_as_no_rehydration_source():
    existing_registry = {"tasks": [{"id": "SLICE-F0-001", "status": "done"}]}
    # bootstrap-registry passes an empty lifecycle_task_ids set when --no-sync-lifecycle is used.
    errors = bootstrap_reset_guard_errors(
        existing_registry,
        {},
        new_task_ids={"SLICE-F0-001"},
        lifecycle_task_ids=set(),
    )
    assert errors
