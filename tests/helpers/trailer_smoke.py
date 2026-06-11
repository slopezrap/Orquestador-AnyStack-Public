from __future__ import annotations
import io, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
os.environ["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
DEFAULT_SMOKE_BLUEPRINT = "examples/smoke/BLUEPRINT.md"


def smoke_blueprint() -> str:
    return os.environ.get("CLAUDE_TRAILER_SMOKE_BLUEPRINT", DEFAULT_SMOKE_BLUEPRINT)


def run(cmd):
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise SystemExit(f"failed {' '.join(cmd)}\n{proc.stdout}")


def bootstrap():
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", smoke_blueprint()])
    # On fast macOS/Linux filesystems, immediately spawning bootstrap after an
    # atomic compile can observe the path before directory metadata is visible
    # to a different process. Wait for parseable JSON, matching bootstrap-registry.
    import time
    compiled = ROOT / "orchestrator-state/compiled/orchestrator-input.json"
    for _ in range(100):
        try:
            if compiled.exists() and compiled.stat().st_size > 0:
                json.loads(compiled.read_text(encoding="utf-8"))
                break
        except Exception:
            pass
        time.sleep(0.05)
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def read_task(tid="SLICE-F0-001"):
    # Use the orchestrator reader instead of direct read_text so tests match
    # hook/runtime behavior on macOS/Linux during atomic registry replaces.
    import time
    from orchestrator.common import read_json
    path = ROOT / "orchestrator-state/tasks/registry.json"
    last_reg = {"tasks": []}
    for _ in range(100):
        reg = read_json(path, {"tasks": []})
        last_reg = reg
        for task in reg.get("tasks", []):
            if task.get("id") == tid:
                return task
        time.sleep(0.05)
    raise AssertionError(f"task {tid} not found in {path}; tasks={[t.get('id') for t in last_reg.get('tasks', [])]}")


def ensure_artifacts(task_id="SLICE-F0-001"):
    handoff = ROOT / "orchestrator-state/tasks/handoffs" / f"{task_id}.md"
    evidence = ROOT / "orchestrator-state/tasks/evidence" / task_id
    report = ROOT / "orchestrator-state/tasks/reports" / f"{task_id}.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    if not handoff.exists():
        handoff.write_text(f"# Handoff {task_id}\n\nThis scaffprevious is not a final trailer. The hook appends accepted handoff sections after each SubagentStop.\n", encoding="utf-8")
    text = handoff.read_text(encoding="utf-8", errors="replace")
    if "## verify-slice" not in text.lower() or "<real" in text or "<yes" in text or "<row" in text:
        text += f"\n## verify-slice\n\nMCP_BROWSER: not_applicable:no_ui_surface\nVISUAL_CHECK_METHOD: backend\nREAL_OR_PROVIDED_DATA_USED: yes\nREAL_DATA_SOURCE: tests/helpers/trailer_smoke.py generated runtime fixture\nNO_STUB_DATA: yes\nFLOWS_TESTED: scripts/reset-state.sh; scripts/compile-blueprint.sh; scripts/bootstrap-registry.sh; SubagentStop hook smoke; endpoint_service; migration_ddl_data; pipeline_worker_queue; dependency_runtime; integration_provider; core_logic; permission_state_error; runtime_contract_fallback\nDATA_SETUP: reset state, compile smoke blueprint, bootstrap registry and write hook evidence fixture\nDATA_CONTRACT_ROWS: not_applicable:hook smoke validates lifecycle not domain persistence\nPERSISTED_DATA_OBSERVED: not_applicable:hook smoke validates lifecycle not domain persistence\nRUNTIME_LOGS_CHECKED: yes\nERROR_LOGS_STATUS: clean\nRUNTIME_LOG_ERRORS: 0\nRUNTIME_COMMAND_OUTPUT_CAPTURED: yes\nEVIDENCE: orchestrator-state/tasks/evidence/{task_id}/slice-verifier.json\nEVIDENCE_ENDPOINT_SERVICE: hook smoke command output observed\nEVIDENCE_MIGRATION_DDL_DATA: bootstrap registry output observed\nEVIDENCE_PIPELINE_WORKER_QUEUE: worker or queue not_applicable: no async worker in smoke, runtime command proof captured\nEVIDENCE_DEPENDENCY_RUNTIME: dependency runtime command proof captured\nEVIDENCE_INTEGRATION_PROVIDER: integration provider not_applicable: no external provider in smoke, runtime command proof captured\nEVIDENCE_CORE_LOGIC: state-machine lifecycle transition asserted\nEVIDENCE_PERMISSION_STATE_ERROR: blocked guardrail transition asserted\nEVIDENCE_RUNTIME_CONTRACT_FALLBACK: hook smoke runtime contract observed\n"
        handoff.write_text(text, encoding="utf-8")
    evidence_payload = {
        "task_id": task_id,
        "mcp_browser": "not_applicable:no_ui_surface",
        "visual_check_method": "backend",
        "real_or_provided_data_used": "yes",
        "real_data_source": "tests/helpers/trailer_smoke.py generated runtime fixture",
        "no_stub_data": "yes",
        "no_stub_data_used": "yes",
        "flows_tested": "scripts/reset-state.sh; scripts/compile-blueprint.sh; scripts/bootstrap-registry.sh; SubagentStop hook smoke; endpoint_service; migration_ddl_data; pipeline_worker_queue; dependency_runtime; integration_provider; core_logic; permission_state_error; runtime_contract_fallback",
        "data_setup": "reset state, compile smoke blueprint, bootstrap registry and write hook evidence fixture",
        "data_contract_rows": "not_applicable:hook smoke validates lifecycle not domain persistence",
        "persisted_data_observed": "not_applicable:hook smoke validates lifecycle not domain persistence",
        "runtime_logs_checked": "yes",
        "error_logs_status": "clean",
        "runtime_log_errors": 0,
        "runtime_command_output_captured": "yes",
        "evidence_endpoint_service": "hook smoke command output observed",
        "evidence_migration_ddl_data": "bootstrap registry output observed",
        "evidence_pipeline_worker_queue": "worker or queue not_applicable: no async worker in smoke, runtime command proof captured",
        "evidence_dependency_runtime": "dependency runtime command proof captured",
        "evidence_integration_provider": "integration provider not_applicable: no external provider in smoke, runtime command proof captured",
        "evidence_core_logic": "state-machine lifecycle transition asserted",
        "evidence_permission_state_error": "blocked guardrail transition asserted",
        "evidence_runtime_contract_fallback": "hook smoke runtime contract observed",
    }
    (evidence / "slice-verifier.json").write_text(json.dumps(evidence_payload, indent=2), encoding="utf-8")
    (evidence / "evidence.json").write_text(json.dumps(evidence_payload, indent=2), encoding="utf-8")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"# Report {task_id}\n", encoding="utf-8")
    return handoff, evidence, report

def stop(agent_type: str, message: str, task_id="SLICE-F0-001", workflow: str | None = None):
    from orchestrator.hooks import hook_capture_subagent_stop
    old_task = os.environ.get("CLAUDE_ACTIVE_TASK_ID")
    old_workflow = os.environ.get("CLAUDE_GIT_WORKFLOW")
    old_stdin = sys.stdin
    try:
        os.environ["CLAUDE_ACTIVE_TASK_ID"] = task_id
        if workflow:
            os.environ["CLAUDE_GIT_WORKFLOW"] = workflow
        else:
            os.environ.pop("CLAUDE_GIT_WORKFLOW", None)
        ensure_artifacts(task_id)
        payload = {"hook_event_name": "SubagentStop", "agent_id": "agent-test", "agent_type": agent_type, "last_assistant_message": message}
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


def assert_status(status: str):
    actual = read_task()["status"]
    if actual != status:
        raise AssertionError(f"expected {status}, got {actual}")


def base_flow(close: bool = True):
    bootstrap()
    run(["bash", "scripts/next-slice.sh", "SLICE-F0-001"])
    assert_status("in_progress")
    stop("developer", "CLAUDE_TRAILER:\nAGENT: developer\nTASK_ID: SLICE-F0-001\nOUTCOME: success\nNEXT_STATUS: validator_tester_pending\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\n")
    assert_status("validator_tester_pending")
    # OUTCOME is authoritative: a stale NEXT_STATUS=done from tester is rewritten
    # to ready_for_close before the state-machine transition.
    stop("tester", "CLAUDE_TRAILER:\nAGENT: tester\nTASK_ID: SLICE-F0-001\nOUTCOME: pass\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\n")
    assert_status("ready_for_close")
    stop("slice-verifier", "CLAUDE_TRAILER:\nAGENT: slice-verifier\nTASK_ID: SLICE-F0-001\nOUTCOME: verified\nNEXT_STATUS: ready_for_close\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\nVERIFY_OUTCOME: verified\nREAL_DATA_OR_USER_PROVIDED: yes\nNO_STUB_DATA_USED: yes\nRUNTIME_LOGS_CHECKED: yes\n")
    assert_status("verified_pending_close")
    if close:
        stop("closer", "CLAUDE_TRAILER:\nAGENT: closer\nTASK_ID: SLICE-F0-001\nOUTCOME: committed\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nREPORT: orchestrator-state/tasks/reports/SLICE-F0-001.md\nREPORT_READY: yes\nBASELINE_SYNC_READY: yes\nGIT_READY: yes\nPUSH_READY: yes\nGIT_WORKFLOW_READY: yes\nRUNTIME_CLEANED: yes\nDOCKER_RUNTIME_CLEANED: yes\nRANCHER_RUNTIME_CLEANED: yes\nDEV_PORTS_RELEASED: yes\nWORKTREES_CLEANED: yes\nPR_READY: yes\nMERGED: yes\nCANONICAL_MAIN_SYNCED: yes\n")
        assert_status("done")


def set_status(status: str, task_id="SLICE-F0-001"):
    reg_path = ROOT / "orchestrator-state/tasks/registry.json"
    reg = json.loads(reg_path.read_text())
    for task in reg.get("tasks", []):
        if task.get("id") == task_id:
            task["status"] = status
            task.pop("last_blocker", None)
            break
    reg_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def combined_flow():
    base_flow(close=False)
    stop("closer", "CLAUDE_TRAILER:\nAGENT: closer\nTASK_ID: SLICE-F0-001\nOUTCOME: committed\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nREPORT: orchestrator-state/tasks/reports/SLICE-F0-001.md\nREPORT_READY: yes\nBASELINE_SYNC_READY: yes\nGIT_READY: yes\nPUSH_READY: yes\nGIT_WORKFLOW_READY: yes\nRUNTIME_CLEANED: yes\nDOCKER_RUNTIME_CLEANED: yes\nRANCHER_RUNTIME_CLEANED: yes\nDEV_PORTS_RELEASED: yes\nWORKTREES_CLEANED: yes\n", workflow="pr-flow")
    task = read_task()
    assert task["status"] == "blocked", task
    assert task.get("last_blocker", {}).get("reason") == "closer_guardrail_failed", task
    set_status("verified_pending_close")
    stop("closer", "CLAUDE_TRAILER:\nAGENT: closer\nTASK_ID: SLICE-F0-001\nOUTCOME: committed\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nREPORT: orchestrator-state/tasks/reports/SLICE-F0-001.md\nREPORT_READY: yes\nBASELINE_SYNC_READY: yes\nGIT_READY: yes\nPUSH_READY: yes\nGIT_WORKFLOW_READY: yes\nRUNTIME_CLEANED: yes\nDOCKER_RUNTIME_CLEANED: yes\nRANCHER_RUNTIME_CLEANED: yes\nDEV_PORTS_RELEASED: yes\nWORKTREES_CLEANED: yes\nPR_READY: yes\nMERGED: yes\nCANONICAL_MAIN_SYNCED: yes\n", workflow="pr-flow")
    assert_status("done")


def pr_flow_guardrail():
    base_flow(close=False)
    stop("closer", "CLAUDE_TRAILER:\nAGENT: closer\nTASK_ID: SLICE-F0-001\nOUTCOME: committed\nNEXT_STATUS: done\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nREPORT: orchestrator-state/tasks/reports/SLICE-F0-001.md\nREPORT_READY: yes\nBASELINE_SYNC_READY: yes\nGIT_READY: yes\nPUSH_READY: yes\nGIT_WORKFLOW_READY: yes\nRUNTIME_CLEANED: yes\nDOCKER_RUNTIME_CLEANED: yes\nRANCHER_RUNTIME_CLEANED: yes\nDEV_PORTS_RELEASED: yes\nWORKTREES_CLEANED: yes\n", workflow="pr-flow")
    task = read_task()
    assert task["status"] == "blocked", task
    assert task.get("last_blocker", {}).get("reason") == "closer_guardrail_failed", task


if __name__ == "__main__":
    combined_flow()
    print(json.dumps({"ok": True, "trailer_smoke": "passed"}, indent=2))
