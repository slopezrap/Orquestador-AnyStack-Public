from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skills_only_runtime_surface():
    assert not (ROOT / ".claude" / "commands").exists()
    assert (ROOT / ".claude" / "skills" / "next-slice" / "SKILL.md").exists()
    assert (ROOT / ".claude" / "skills" / "verify-slice" / "SKILL.md").exists()
    assert (ROOT / ".claude" / "skills" / "closer" / "SKILL.md").exists()
    assert (ROOT / "scripts" / "check-skills-runtime.sh").exists()


def test_run_hook_root_discovery_ignores_missing_optional_roots_under_set_e():
    env = os.environ.copy()
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT / "definitely_missing_root")
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    proc = subprocess.run(
        ["bash", ".claude/bin/run_hook.sh", "definitely_missing_hook.py"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout
    assert "HOOK_ROOT_WARN: missing definitely_missing_hook.py" in proc.stdout


def test_trailers_and_state_machine_smoke():
    from tests.helpers import trailer_smoke
    trailer_smoke.combined_flow()


def test_subagent_stop_blocks_mutating_role_without_required_trailer():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    snippet = r'''
import io, json, os, sys, subprocess
from pathlib import Path
ROOT = Path.cwd()
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
os.environ["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
reg_path = ROOT / "orchestrator-state" / "tasks" / "registry.json"
reg_path.parent.mkdir(parents=True, exist_ok=True)
reg_path.write_text(json.dumps({
    "schema_version": "2.0",
    "tasks": [{
        "id": "SLICE-F0-001",
        "task_id": "SLICE-F0-001",
        "status": "in_progress",
        "title": "Test task",
        "description": "Production-grade hook validation task used only to verify SubagentStop blocking semantics and trailer enforcement."
    }],
    "phases": [],
    "task_dag": {"nodes": [], "edges": []}
}), encoding="utf-8")
from orchestrator.hooks import hook_capture_subagent_stop
os.environ["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
payload = {"hook_event_name": "SubagentStop", "agent_id": "agent-test", "agent_type": "developer", "last_assistant_message": "implemented without trailer"}
sys.stdin = io.StringIO(json.dumps(payload))
hook_capture_subagent_stop.main()
'''
    proc = subprocess.run(["python3", "-S", "-c", snippet], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout
    assert '"decision": "block"' in proc.stdout
    assert "Missing required CLAUDE_TRAILER keys" in proc.stdout



def test_handoff_contract_checker_accepts_required_trailers():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/compile-blueprint.sh", "examples/smoke/BLUEPRINT.md"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    handoff = ROOT / "orchestrator-state" / "tasks" / "handoffs" / "SLICE-F0-001.md"
    evidence = ROOT / "orchestrator-state" / "tasks" / "evidence" / "SLICE-F0-001"
    evidence.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        "task_id": "SLICE-F0-001",
        "mcp_browser": "not_applicable:no_ui_surface",
        "visual_check_method": "backend",
        "real_or_provided_data_used": "yes",
        "real_data_source": "examples/smoke/BLUEPRINT.md compiled fixture",
        "no_stub_data": "yes",
        "no_stub_data_used": "yes",
        "flows_tested": "scripts/reset-state.sh; scripts/compile-blueprint.sh; scripts/bootstrap-registry.sh; endpoint_service; migration_ddl_data; pipeline_worker_queue; dependency_runtime; integration_provider; core_logic; permission_state_error; runtime_contract_fallback",
        "data_setup": "reset, compile and bootstrap smoke blueprint",
        "data_contract_rows": "not_applicable:handoff contract test does not persist app rows",
        "persisted_data_observed": "not_applicable:handoff contract test does not persist app rows",
        "runtime_logs_checked": "yes",
        "error_logs_status": "clean",
        "runtime_log_errors": 0,
        "runtime_command_output_captured": "yes",
        "evidence_endpoint_service": "compiled runtime command output observed",
        "evidence_migration_ddl_data": "bootstrap registry output observed",
        "evidence_pipeline_worker_queue": "worker or queue not_applicable: no async worker in smoke, runtime command proof captured",
        "evidence_dependency_runtime": "dependency runtime command proof captured",
        "evidence_integration_provider": "integration provider not_applicable: no external provider in smoke, runtime command proof captured",
        "evidence_core_logic": "state machine contract asserted",
        "evidence_permission_state_error": "guardrail contract asserted",
        "evidence_runtime_contract_fallback": "runtime fallback command output observed",
    }
    (evidence / "slice-verifier.json").write_text(json.dumps(evidence_payload, indent=2), encoding="utf-8")
    (evidence / "evidence.json").write_text(json.dumps(evidence_payload, indent=2), encoding="utf-8")
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "# Handoff SLICE-F0-001\n\n"
        "## developer\n"
        "CLAUDE_TRAILER:\nAGENT: developer\nTASK_ID: SLICE-F0-001\nOUTCOME: success\nNEXT_STATUS: validator_tester_pending\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\n\n"
        "## tester\n"
        "CLAUDE_TRAILER:\nAGENT: tester\nTASK_ID: SLICE-F0-001\nOUTCOME: pass\nNEXT_STATUS: ready_for_close\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\n\n"
        "## verify-slice\n"
        "MCP_BROWSER: not_applicable:no_ui_surface\nVISUAL_CHECK_METHOD: backend\nREAL_OR_PROVIDED_DATA_USED: yes\nREAL_DATA_SOURCE: examples/smoke/BLUEPRINT.md compiled fixture\nNO_STUB_DATA: yes\nFLOWS_TESTED: scripts/reset-state.sh; scripts/compile-blueprint.sh; scripts/bootstrap-registry.sh; endpoint_service; migration_ddl_data; pipeline_worker_queue; dependency_runtime; integration_provider; core_logic; permission_state_error; runtime_contract_fallback\nDATA_SETUP: reset, compile and bootstrap smoke blueprint\nDATA_CONTRACT_ROWS: not_applicable:handoff contract test does not persist app rows\nPERSISTED_DATA_OBSERVED: not_applicable:handoff contract test does not persist app rows\nRUNTIME_LOGS_CHECKED: yes\nERROR_LOGS_STATUS: clean\nRUNTIME_LOG_ERRORS: 0\nRUNTIME_COMMAND_OUTPUT_CAPTURED: yes\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001/slice-verifier.json\nEVIDENCE_ENDPOINT_SERVICE: compiled runtime command output observed\nEVIDENCE_MIGRATION_DDL_DATA: bootstrap registry output observed\nEVIDENCE_PIPELINE_WORKER_QUEUE: worker or queue not_applicable: no async worker in smoke, runtime command proof captured\nEVIDENCE_DEPENDENCY_RUNTIME: dependency runtime command proof captured\nEVIDENCE_INTEGRATION_PROVIDER: integration provider not_applicable: no external provider in smoke, runtime command proof captured\nEVIDENCE_CORE_LOGIC: state machine contract asserted\nEVIDENCE_PERMISSION_STATE_ERROR: guardrail contract asserted\nEVIDENCE_RUNTIME_CONTRACT_FALLBACK: runtime fallback command output observed\n\n"
        "## slice verifier\n"
        "CLAUDE_TRAILER:\nAGENT: slice-verifier\nTASK_ID: SLICE-F0-001\nOUTCOME: verified\nNEXT_STATUS: verified_pending_close\nVERIFY_OUTCOME: verified\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\nEVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\nREAL_DATA_OR_USER_PROVIDED: yes\nNO_STUB_DATA_USED: yes\nRUNTIME_LOGS_CHECKED: yes\n\n"
        "## validator\n"
        "CLAUDE_TRAILER:\nAGENT: validator\nTASK_ID: SLICE-F0-001\nOUTCOME: approved\nHANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["bash", "scripts/check-handoff-contract.sh", "SLICE-F0-001", "--require-developer", "--require-tester", "--require-verify-slice", "--require-validator", "--require-production-observability"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout
    assert '"ok": true' in proc.stdout


def test_handoff_contract_static_mode_after_bootstrap():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env.pop("CLAUDE_ACTIVE_TASK_ID", None)
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/compile-blueprint.sh", "examples/smoke/BLUEPRINT.md"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    proc = subprocess.run(["bash", "scripts/check-handoff-contract.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout
    assert '"mode": "static"' in proc.stdout


def test_agent_trailer_examples_match_contract():
    import json, re
    contract = json.loads((ROOT / ".claude" / "orchestrator-contract.json").read_text())
    roles = contract["trailer_schema"]["roles"]
    for agent_file in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        role = agent_file.stem
        spec = roles[role]
        body = agent_file.read_text()
        blocks = []
        for part in body.split("CLAUDE_TRAILER:")[1:]:
            chunk = part.split("```", 1)[0]
            data = {}
            for raw in chunk.splitlines():
                line = raw.strip().lstrip("-* ").strip()
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().upper()
                if re.match(r"^[A-Z][A-Z0-9_]*$", key):
                    data[key] = value.strip()
            if data:
                blocks.append(data)
        assert blocks, f"{agent_file} has no parseable CLAUDE_TRAILER"
        for block in blocks:
            assert block.get("AGENT", "").replace("_", "-") == role
            for key in spec.get("required_keys", []):
                if spec.get("mutates_registry_lifecycle") and key not in {"AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF"}:
                    continue
                assert key in block, f"{agent_file} trailer missing {key}: {block}"


def test_check_handoff_contract_without_task_id_audits_globally():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env.pop("CLAUDE_ACTIVE_TASK_ID", None)
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    proc = subprocess.run(["bash", "scripts/check-handoff-contract.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 0, proc.stdout
    assert '"mode":' in proc.stdout


def test_subagent_stop_accepts_underscore_agent_type_alias():
    from tests.helpers import trailer_smoke
    trailer_smoke.bootstrap()
    trailer_smoke.set_status("ready_for_close")
    message = """CLAUDE_TRAILER:
AGENT: slice-verifier
TASK_ID: SLICE-F0-001
OUTCOME: blocked
NEXT_STATUS: blocked
HANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md
EVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001
VERIFY_OUTCOME: blocked
BLOCKER_REASON: alias smoke
"""
    trailer_smoke.stop("slice_verifier", message)
    task = trailer_smoke.read_task()
    assert task["status"] == "blocked"
