from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, check=True):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def compile_root():
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"])
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def conflict_reasons(a, b):
    from orchestrator.common import task_conflict_reasons
    return task_conflict_reasons(a, b)


def test_dag_parallel_groups_and_next_wave_are_conflict_safe():
    compile_root()
    run(["bash", "scripts/check-parallel-locks.sh"])
    reg = json.loads((ROOT / "orchestrator-state/tasks/registry.json").read_text())
    dag = reg["task_dag"]
    assert dag["parallelism"]["max_parallel_slices"] >= 1
    assert dag["lock_model"]["backend"].startswith("fcntl")
    tasks = {t["id"]: t for t in reg["tasks"]}
    for group in dag["parallel_groups"]:
        ids = group["task_ids"]
        for i, tid in enumerate(ids):
            for other in ids[i + 1:]:
                assert conflict_reasons(tasks[tid], tasks[other]) == []
        for tid in ids:
            assert tasks[tid]["parallel"]["safe_group"] == group["id"]
            assert tasks[tid]["locks"]["lock_files"][-1].endswith(f"{tid}.md.lock")

    wave = json.loads(run(["bash", "scripts/next-wave.sh", "--limit", "10", "--json"]).stdout)
    selected = [tasks[t["id"]] for t in wave["ready"]]
    for i, task in enumerate(selected):
        for other in selected[i + 1:]:
            assert conflict_reasons(task, other) == []


def test_claim_task_rejects_active_conflict_under_registry_lock():
    compile_root()
    reg_path = ROOT / "orchestrator-state/tasks/registry.json"
    reg = json.loads(reg_path.read_text())
    by_id = {t["id"]: t for t in reg["tasks"]}
    by_id["SLICE-F1-001"]["status"] = "claimed"
    by_id["SLICE-F1-001"]["conflict_group"] = ["shared:test-lock"]
    by_id["SLICE-F1-001"]["conflict_groups"] = ["shared:test-lock"]
    by_id["SLICE-F2-001"]["status"] = "ready"
    by_id["SLICE-F2-001"]["depends_on"] = []
    by_id["SLICE-F2-001"]["conflict_group"] = ["shared:test-lock"]
    by_id["SLICE-F2-001"]["conflict_groups"] = ["shared:test-lock"]
    reg_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")

    proc = run(["bash", "scripts/next-slice.sh", "SLICE-F2-001"], check=False)
    assert proc.returncode == 5
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "active conflict blockers" in payload["error"]
    assert payload["blockers"][0]["task_id"] == "SLICE-F1-001"


def test_handoff_append_uses_lock_file_contract():
    compile_root()
    from orchestrator.runtime.handoff import append_handoff_event, handoff_path

    task_id = "SLICE-F0-001"
    trailer = {
        "agent": "developer",
        "task_id": task_id,
        "outcome": "success",
        "next_status": "validator_tester_pending",
        "handoff": f"orchestrator-state/tasks/handoffs/{task_id}.md",
        "evidence": f"orchestrator-state/tasks/evidence/{task_id}",
    }
    p = append_handoff_event(task_id, "developer", trailer, accepted=True, note="pytest")
    assert p == handoff_path(task_id)
    assert p.with_suffix(p.suffix + ".lock").exists()
    text = p.read_text()
    assert "ACCEPTED_BY_HOOK: yes" in text
    assert f"TASK_ID: {task_id}" in text
