#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.hooks import hook_capture_subagent_stop

TASK_ID = os.environ.get("CLAUDE_ACTIVE_TASK_ID", "SLICE-F0-001")


def read_task() -> dict:
    import time
    path = ROOT / "orchestrator-state/tasks/registry.json"
    last_ids: list[str] = []
    for _ in range(100):
        try:
            if path.exists() and path.stat().st_size > 0:
                reg = json.loads(path.read_text(encoding="utf-8"))
                last_ids = [str(t.get("id")) for t in reg.get("tasks", [])]
                for task in reg.get("tasks", []):
                    if task.get("id") == TASK_ID:
                        return task
        except Exception:
            pass
        time.sleep(0.05)
    raise SystemExit(f"task not found: {TASK_ID}; seen={last_ids}")


def ensure_artifacts() -> tuple[Path, Path, Path]:
    handoff = ROOT / "orchestrator-state/tasks/handoffs" / f"{TASK_ID}.md"
    evidence = ROOT / "orchestrator-state/tasks/evidence" / TASK_ID
    report = ROOT / "orchestrator-state/tasks/reports" / f"{TASK_ID}.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    if not handoff.exists():
        handoff.write_text(f"# Handoff {TASK_ID}\n\n", encoding="utf-8")

    handoff_text = handoff.read_text(encoding="utf-8")
    if "## verify-slice" not in handoff_text or "<real" in handoff_text or "<yes" in handoff_text or "<row" in handoff_text:
        verify_block = f"""
## verify-slice
MCP_BROWSER: not_applicable:no_ui_surface
VISUAL_CHECK_METHOD: backend
REAL_OR_PROVIDED_DATA_USED: yes
REAL_DATA_SOURCE: scripts/smoke-trailers-current-state.py generated runtime fixture
NO_STUB_DATA: yes
NO_STUB_DATA_USED: yes
FLOWS_TESTED: endpoint_service; migration_ddl_data; pipeline_worker_queue; dependency_runtime; integration_provider; core_logic; permission_state_error; runtime_contract_fallback
DATA_SETUP: reset-state plus compile-blueprint plus bootstrap-registry smoke runtime
DATA_CONTRACT_ROWS: not_applicable:smoke verifies lifecycle hooks, not application DB rows
PERSISTED_DATA_OBSERVED: not_applicable:smoke verifies lifecycle hooks, not application DB rows
RUNTIME_LOGS_CHECKED: yes
ERROR_LOGS_STATUS: clean
RUNTIME_LOG_ERRORS: 0
RUNTIME_COMMAND_OUTPUT_CAPTURED: yes
EVIDENCE: orchestrator-state/tasks/evidence/{TASK_ID}/slice-verifier.json
EVIDENCE_ENDPOINT_SERVICE: verified via hook smoke against live registry/runtime lifecycle path
EVIDENCE_MIGRATION_DDL_DATA: not_applicable:smoke task has no application surface
EVIDENCE_PIPELINE_WORKER_QUEUE: not_applicable:smoke task has no worker queue surface
EVIDENCE_DEPENDENCY_RUNTIME: verified by real Python import of hook/runtime modules
EVIDENCE_INTEGRATION_PROVIDER: not_applicable:smoke task has no external provider call
EVIDENCE_CORE_LOGIC: verified by real state-machine transition assertions
EVIDENCE_PERMISSION_STATE_ERROR: verified by blocked/allowed trailer guardrails in smoke path
EVIDENCE_RUNTIME_CONTRACT_FALLBACK: verified by SubagentStop trailer contract path
"""
        handoff.write_text(handoff_text.rstrip() + "\n\n" + verify_block.lstrip(), encoding="utf-8")

    evidence_payload = {
        "task_id": TASK_ID,
        "ok": True,
        "mcp_browser": "not_applicable:no_ui_surface",
        "visual_check_method": "backend",
        "real_or_provided_data_used": "yes",
        "real_data_source": "scripts/smoke-trailers-current-state.py generated runtime fixture",
        "no_stub_data": "yes",
        "no_stub_data_used": "yes",
        "flows_tested": [
            "endpoint_service",
            "migration_ddl_data",
            "pipeline_worker_queue",
            "dependency_runtime",
            "integration_provider",
            "core_logic",
            "permission_state_error",
            "runtime_contract_fallback",
        ],
        "data_setup": "reset-state plus compile-blueprint plus bootstrap-registry smoke runtime",
        "data_contract_rows": "not_applicable:smoke verifies lifecycle hooks, not application DB rows",
        "persisted_data_observed": "not_applicable:smoke verifies lifecycle hooks, not application DB rows",
        "runtime_logs_checked": "yes",
        "error_logs_status": "clean",
        "runtime_log_errors": 0,
        "runtime_command_output_captured": "yes",
        "evidence": f"orchestrator-state/tasks/evidence/{TASK_ID}/slice-verifier.json",
        "evidence_endpoint_service": "verified via hook smoke against live registry/runtime lifecycle path",
        "evidence_migration_ddl_data": "not_applicable:smoke task has no application surface",
        "evidence_pipeline_worker_queue": "not_applicable:smoke task has no worker queue surface",
        "evidence_dependency_runtime": "verified by real Python import of hook/runtime modules",
        "evidence_integration_provider": "not_applicable:smoke task has no external provider call",
        "evidence_core_logic": "verified by real state-machine transition assertions",
        "evidence_permission_state_error": "verified by blocked/allowed trailer guardrails in smoke path",
        "evidence_runtime_contract_fallback": "verified by SubagentStop trailer contract path",
    }
    (evidence / "slice-verifier.json").write_text(json.dumps(evidence_payload, indent=2, sort_keys=True), encoding="utf-8")
    (evidence / "evidence.json").write_text(json.dumps(evidence_payload, indent=2, sort_keys=True), encoding="utf-8")
    report.write_text(f"# Report {TASK_ID}\n", encoding="utf-8")
    return handoff, evidence, report


def stop(agent_type: str, message: str, workflow: str | None = None) -> None:
    old_task = os.environ.get("CLAUDE_ACTIVE_TASK_ID")
    old_workflow = os.environ.get("CLAUDE_GIT_WORKFLOW")
    old_stdin = sys.stdin
    try:
        os.environ["CLAUDE_ACTIVE_TASK_ID"] = TASK_ID
        if workflow:
            os.environ["CLAUDE_GIT_WORKFLOW"] = workflow
        else:
            os.environ.pop("CLAUDE_GIT_WORKFLOW", None)
        payload = {"hook_event_name": "SubagentStop", "agent_id": "smoke", "agent_type": agent_type, "last_assistant_message": message}
        sys.stdin = io.StringIO(json.dumps(payload))
        hook_capture_subagent_stop.main()
    finally:
        sys.stdin = old_stdin
        if old_task is None:
            os.environ.pop("CLAUDE_ACTIVE_TASK_ID", None)
        else:
            os.environ["CLAUDE_ACTIVE_TASK_ID"] = old_task
        if old_workflow is None:
            os.environ.pop("CLAUDE_GIT_WORKFLOW", None)
        else:
            os.environ["CLAUDE_GIT_WORKFLOW"] = old_workflow


def assert_status(expected: str) -> None:
    actual = read_task().get("status")
    if actual != expected:
        raise AssertionError(f"expected {expected}, got {actual}")


def main() -> int:
    ensure_artifacts()
    if read_task().get("status") != "in_progress":
        raise SystemExit(f"{TASK_ID} must start in_progress; got {read_task().get('status')}")
    print("[smoke] developer", flush=True)
    stop("developer", f"CLAUDE_TRAILER:\nAGENT: developer\nTASK_ID: {TASK_ID}\nOUTCOME: success\nNEXT_STATUS: validator_tester_pending\nHANDOFF: orchestrator-state/tasks/handoffs/{TASK_ID}.md\nEVIDENCE: orchestrator-state/tasks/evidence/{TASK_ID}\n")
    assert_status("validator_tester_pending")
    print("[smoke] tester", flush=True)
    stop("tester", f"CLAUDE_TRAILER:\nAGENT: tester\nTASK_ID: {TASK_ID}\nOUTCOME: pass\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/{TASK_ID}.md\nEVIDENCE: orchestrator-state/tasks/evidence/{TASK_ID}\n")
    assert_status("ready_for_close")
    print("[smoke] slice-verifier", flush=True)
    stop("slice-verifier", f"CLAUDE_TRAILER:\nAGENT: slice-verifier\nTASK_ID: {TASK_ID}\nOUTCOME: verified\nNEXT_STATUS: ready_for_close\nHANDOFF: orchestrator-state/tasks/handoffs/{TASK_ID}.md\nEVIDENCE: orchestrator-state/tasks/evidence/{TASK_ID}\nVERIFY_OUTCOME: verified\nREAL_DATA_OR_USER_PROVIDED: yes\nNO_STUB_DATA_USED: yes\nRUNTIME_LOGS_CHECKED: yes\n")
    assert_status("verified_pending_close")
    print("[smoke] closer", flush=True)
    stop("closer", f"CLAUDE_TRAILER:\nAGENT: closer\nTASK_ID: {TASK_ID}\nOUTCOME: committed\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/{TASK_ID}.md\nREPORT: orchestrator-state/tasks/reports/{TASK_ID}.md\nREPORT_READY: yes\nBASELINE_SYNC_READY: yes\nGIT_READY: yes\nPUSH_READY: yes\nGIT_WORKFLOW_READY: yes\nRUNTIME_CLEANED: yes\nDOCKER_RUNTIME_CLEANED: yes\nRANCHER_RUNTIME_CLEANED: yes\nDEV_PORTS_RELEASED: yes\nWORKTREES_CLEANED: yes\nPR_READY: yes\nMERGED: yes\nCANONICAL_MAIN_SYNCED: yes\n", workflow="pr-flow")
    assert_status("done")
    print(json.dumps({"ok": True, "task_id": TASK_ID, "status": "done", "trailers": ["developer", "tester", "slice-verifier", "closer"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
