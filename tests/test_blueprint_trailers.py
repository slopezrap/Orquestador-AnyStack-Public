from __future__ import annotations
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_smoke() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    print("bootstrap-smoke reset", flush=True)
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    print("bootstrap-smoke compile", flush=True)
    subprocess.run(["bash", "scripts/compile-blueprint.sh", "examples/smoke/BLUEPRINT.md"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    print("bootstrap-smoke bootstrap", flush=True)
    subprocess.run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)


def _fenced_after(marker: str, text: str) -> str:
    start = text.index(marker)
    chunk = text[start:]
    first = chunk.index("```text")
    chunk = chunk[first + len("```text"):]
    end = chunk.index("```")
    return chunk[:end]


def test_subagent_start_injects_role_specific_trailer_templates():
    _bootstrap_smoke()
    print("bootstrap-smoke done", flush=True)
    from orchestrator.hooks.hook_subagent_start_context import build_context

    closer = build_context({"agent_type": "closer", "task_id": "SLICE-F0-001"})
    assert "REPORT_READY: yes" in closer
    assert "CANONICAL_MAIN_SYNCED: yes" in closer
    assert "NEXT_STATUS: done" in closer

    verifier = build_context({"agent_type": "slice-verifier", "task_id": "SLICE-F0-001"})
    assert "VERIFY_OUTCOME: verified" in verifier
    assert "REAL_DATA_OR_USER_PROVIDED: yes" in verifier
    assert "NO_STUB_DATA_USED: yes" in verifier

    planner = build_context({"agent_type": "planner", "task_id": "SLICE-F0-001"})
    assert "AGENT: planner" in planner
    assert "TASK_ID: SLICE-F0-001" in planner
    assert "NEXT_STATUS:" not in planner
    assert "CONTEXT_READY:" in planner
    assert "NEEDS_OFFICIAL_DOCS:" in planner


def test_generated_task_pack_info_only_examples_do_not_emit_next_status():
    _bootstrap_smoke()
    print("bootstrap-smoke done", flush=True)
    pack = (ROOT / "orchestrator-state/tasks/task-packs/SLICE-F0-001.md").read_text(encoding="utf-8")
    validator = _fenced_after("Validator info-only review:", pack)
    screen = _fenced_after("Screen journey reviewer info-only review:", pack)
    assert "AGENT: validator" in validator
    assert "TASK_ID: SLICE-F0-001" in validator
    assert "NEXT_STATUS:" not in validator
    assert "AGENT: screen-journey-reviewer" in screen
    assert "TASK_ID: SLICE-F0-001" in screen
    assert "NEXT_STATUS:" not in screen


def test_handoff_validator_rejects_next_status_for_info_only_role():
    _bootstrap_smoke()
    print("bootstrap-smoke done", flush=True)
    from orchestrator.runtime.handoff import validate_handoff

    handoff = ROOT / "orchestrator-state/tasks/handoffs/SLICE-F0-001.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "# Handoff SLICE-F0-001\n\n"
        "## validator\n"
        "CLAUDE_TRAILER:\n"
        "AGENT: validator\n"
        "TASK_ID: SLICE-F0-001\n"
        "OUTCOME: approved\n"
        "NEXT_STATUS: ready_for_close\n"
        "HANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\n",
        encoding="utf-8",
    )
    result = validate_handoff("SLICE-F0-001", require_roles=["validator"])
    assert result["ok"] is False
    assert any("NEXT_STATUS supplied" in err for err in result["errors"])
