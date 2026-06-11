from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _minimal_registry(task_id: str = "SLICE-F0-001", status: str = "ready_for_close") -> None:
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=_env(), check=True, stdout=subprocess.DEVNULL)
    tasks = ROOT / "orchestrator-state" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "2.0",
        "tasks": [
            {
                "id": task_id,
                "task_id": task_id,
                "status": status,
                "title": "Verify guard test",
                "description": "Verify-slice guard test task with enough descriptive context for generated handoff.",
                "verification_surface": {
                    "kind": "backend",
                    "requires_visual_mcp": False,
                    "method": "backend",
                    "required_evidence_categories": ["runtime_contract_fallback"],
                },
            }
        ],
        "phases": [],
        "task_dag": {"nodes": [], "edges": []},
    }
    (tasks / "registry.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_verify_slice_wrapper_does_not_mask_init_failure() -> None:
    text = (ROOT / "scripts" / "verify-slice.sh").read_text(encoding="utf-8")
    assert './scripts/init-verify-slice-handoff.sh "$TASK_ID" >/dev/null || true' not in text
    assert './scripts/init-verify-slice-handoff.sh "$TASK_ID" >/dev/null' in text
    assert './scripts/init-verify-slice-handoff.sh "$TASK_ID" >/dev/null\n./scripts/verify-slice-state.sh' in text


def test_subagent_start_initializes_verify_slice_skeleton() -> None:
    _minimal_registry()
    handoff = ROOT / "orchestrator-state" / "tasks" / "handoffs" / "SLICE-F0-001.md"
    assert not handoff.exists()
    payload = {"agent_type": "slice-verifier", "task_id": "SLICE-F0-001"}
    proc = subprocess.run(
        ["python3", "-S", "-m", "orchestrator.hooks.hook_subagent_start_context"],
        cwd=ROOT,
        env=_env(),
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    assert "verify-slice bootstrap" in proc.stdout
    text = handoff.read_text(encoding="utf-8")
    assert "## verify-slice" in text
    assert "EVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001/slice-verifier.json" in text


def test_reset_state_refuses_active_slice_without_override() -> None:
    env = _env()
    env["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
    proc = subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 4
    assert "refusing to reset orchestrator-state" in proc.stdout


def test_orchestrator_selftests_refuse_active_slice_context() -> None:
    env = _env()
    env["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
    proc = subprocess.run(["python3", "scripts/run-tests-one-by-one.py", "--python", "python3", "tests/test_state_machine.py"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.returncode == 4
    assert "refusing to run orchestrator self-tests" in proc.stdout


def _bash_guard(command: str, *, active: bool = True) -> subprocess.CompletedProcess[str]:
    env = _env()
    if active:
        env["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        ["python3", "-m", "orchestrator.hooks.hook_bash_command_guard"],
        cwd=ROOT,
        env=env,
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def test_bash_guard_blocks_broad_root_pytest_and_runtime_selftests() -> None:
    root_pytest = _bash_guard("python -m pytest -q")
    assert "permissionDecision" in root_pytest.stdout
    assert "deny" in root_pytest.stdout
    assert "broad/root pytest" in root_pytest.stdout
    run_all = _bash_guard("./scripts/run-all-tests.sh")
    assert "deny" in run_all.stdout
    assert "maintainer self-test" in run_all.stdout


def test_bash_guard_allows_explicit_product_test_path() -> None:
    proc = _bash_guard("pytest backend/tests/test_api.py")
    assert proc.stdout.strip() == ""
