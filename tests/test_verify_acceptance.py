from __future__ import annotations

from orchestrator.common import find_task, load_registry
from orchestrator.runtime.verify_requirements import validate_verify_acceptance

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


def _backend_evidence(task_id: str = "SLICE-F0-001") -> dict[str, object]:
    return {
        "task_id": task_id,
        "mcp_browser": "not_applicable:no_ui_surface",
        "visual_check_method": "backend",
        "real_or_provided_data_used": "yes",
        "real_data_source": "pytest fixture exercising compiled backend verification contract",
        "no_stub_data": "yes",
        "no_stub_data_used": "yes",
        "flows_tested": "endpoint_service; migration_ddl_data; pipeline_worker_queue; dependency_runtime; integration_provider; core_logic; permission_state_error; runtime_contract_fallback; scripts/check-verify-routing.sh",
        "data_setup": "compiled registry fixture plus runtime evidence fixture",
        "data_contract_rows": "not_applicable:unit-level contract test without app DB rows",
        "persisted_data_observed": "not_applicable:unit-level contract test without app DB rows",
        "runtime_logs_checked": "yes",
        "error_logs_status": "clean",
        "runtime_log_errors": 0,
        "runtime_command_output_captured": "yes",
        "evidence_endpoint_service": "real command output captured in fixture",
        "evidence_migration_ddl_data": "schema/bootstrap command output captured in fixture",
        "evidence_pipeline_worker_queue": "worker or queue not_applicable: no async worker in fixture, runtime command proof captured",
        "evidence_dependency_runtime": "dependency runtime command proof captured in fixture",
        "evidence_integration_provider": "integration provider not_applicable: no external provider in fixture, runtime command proof captured",
        "evidence_core_logic": "domain invariant command output captured in fixture",
        "evidence_permission_state_error": "guardrail command output captured in fixture",
        "evidence_runtime_contract_fallback": "fallback runtime command output captured in fixture",
    }


def test_backend_verified_acceptance_requires_no_ui_surface_backend_contract():
    ensure_root_runtime()
    task = find_task(load_registry(), "SLICE-F0-001")
    trailer = {
        "agent": "slice-verifier",
        "task_id": "SLICE-F0-001",
        "outcome": "verified",
        "next_status": "verified_pending_close",
        "verify_outcome": "verified",
        "handoff": "orchestrator-state/tasks/handoffs/SLICE-F0-001.md",
        "evidence": "orchestrator-state/tasks/evidence/SLICE-F0-001/slice-verifier.json",
        "real_data_or_user_provided": "yes",
        "no_stub_data_used": "yes",
        "runtime_logs_checked": "yes",
    }
    handoff = "## verify-slice\n" + "\n".join(f"{k.upper()}: {v}" for k, v in _backend_evidence().items())
    assert validate_verify_acceptance(task, trailer, handoff, _backend_evidence()) == []


def test_backend_verified_acceptance_blocks_missing_backend_evidence():
    ensure_root_runtime()
    task = find_task(load_registry(), "SLICE-F0-001")
    trailer = {
        "agent": "slice-verifier",
        "task_id": "SLICE-F0-001",
        "outcome": "verified",
        "next_status": "verified_pending_close",
        "verify_outcome": "verified",
        "handoff": "orchestrator-state/tasks/handoffs/SLICE-F0-001.md",
        "evidence": "orchestrator-state/tasks/evidence/SLICE-F0-001/slice-verifier.json",
        "real_data_or_user_provided": "yes",
        "no_stub_data_used": "yes",
        "runtime_logs_checked": "yes",
    }
    errors = validate_verify_acceptance(task, trailer, "## verify-slice\nMCP_BROWSER: not_applicable:no_ui_surface\n", {"ok": True})
    assert any("VISUAL_CHECK_METHOD" in e for e in errors)
    assert any("REAL_DATA_SOURCE" in e for e in errors)
    assert any("ERROR_LOGS_STATUS" in e for e in errors)


def test_ui_slice_cannot_escape_with_backend_mode():
    ensure_root_runtime()
    task = find_task(load_registry(), "SLICE-F8-001")
    trailer = {
        "agent": "slice-verifier",
        "task_id": "SLICE-F8-001",
        "outcome": "verified",
        "next_status": "verified_pending_close",
        "verify_outcome": "verified",
        "handoff": "orchestrator-state/tasks/handoffs/SLICE-F8-001.md",
        "evidence": "orchestrator-state/tasks/evidence/SLICE-F8-001/slice-verifier.json",
        "real_data_or_user_provided": "yes",
        "no_stub_data_used": "yes",
        "runtime_logs_checked": "yes",
    }
    evidence = _backend_evidence("SLICE-F8-001")
    handoff = "## verify-slice\n" + "\n".join(f"{k.upper()}: {v}" for k, v in evidence.items())
    errors = validate_verify_acceptance(task, trailer, handoff, evidence)
    assert any("UI verification requires browser MCP" in e for e in errors)
    assert any("UI slice cannot declare backend/no-ui" in e for e in errors)
