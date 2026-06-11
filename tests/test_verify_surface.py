from __future__ import annotations

from orchestrator.common import find_task, load_registry
from orchestrator.runtime.verify_requirements import classify_task_verification

from pathlib import Path
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def ensure_root_runtime():
    reg = ROOT / "orchestrator-state" / "tasks" / "registry.json"
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        if any(t.get("id") == "SLICE-F8-001" for t in data.get("tasks", [])) and any(t.get("id") == "SLICE-F5-001" for t in data.get("tasks", [])):
            return
    except Exception:
        pass
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)


def test_backend_journey_refs_do_not_force_ui_mcp():
    ensure_root_runtime()
    task = find_task(load_registry(), "SLICE-F5-001")
    result = classify_task_verification(task)
    assert result["surface_kind"] == "journey_backend_contract"
    assert result["visual_required"] is False
    assert result["screen_journey_reviewer_required"] is False
    assert result["mcp_requirement"]["mcp_browser"] == "not_applicable:no_ui_surface"
    assert result["mcp_requirement"]["visual_check_method"] == "backend"
    required = set(result["required_evidence_categories"])
    assert {"endpoint_service", "pipeline_worker_queue", "core_logic"} <= required


def test_foundation_non_ui_has_real_evidence_matrix():
    ensure_root_runtime()
    task = find_task(load_registry(), "SLICE-F0-001")
    result = classify_task_verification(task)
    assert result["surface_kind"] == "non_ui_runtime_contract"
    assert result["visual_required"] is False
    required = set(result["required_evidence_categories"])
    assert "migration_ddl_data" in required
    assert "permission_state_error" in required
    assert result["minimum_runtime_proof"]


def test_ui_slice_requires_visual_mcp():
    ensure_root_runtime()
    task = find_task(load_registry(), "SLICE-F8-001")
    result = classify_task_verification(task)
    assert result["surface_kind"] == "browser_ui"
    assert result["visual_required"] is True
    assert result["screen_journey_reviewer_required"] is True
    assert "chrome-devtools" in result["mcp_requirement"]["mcp_browser"]
