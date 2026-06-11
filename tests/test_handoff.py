from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

from tests.helpers import trailer_smoke

ROOT = Path(__file__).resolve().parents[1]


def test_subagent_stop_does_not_reuse_stale_handoff_when_final_message_lacks_trailer():
    trailer_smoke.bootstrap()
    trailer_smoke.set_status("in_progress")
    handoff, evidence, _report = trailer_smoke.ensure_artifacts("SLICE-F0-001")
    handoff.write_text(
        "# Handoff SLICE-F0-001\n\n"
        "## developer\n"
        "CLAUDE_TRAILER:\n"
        "AGENT: developer\n"
        "TASK_ID: SLICE-F0-001\n"
        "OUTCOME: success\n"
        "NEXT_STATUS: validator_tester_pending\n"
        "HANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\n"
        "EVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001\n",
        encoding="utf-8",
    )
    from orchestrator.hooks import hook_capture_subagent_stop

    os.environ["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_id": "agent-test",
        "agent_type": "developer",
        "last_assistant_message": "I changed code but forgot the required final trailer.",
    }
    sys.stdin = io.StringIO(json.dumps(payload))
    hook_capture_subagent_stop.main()
    assert trailer_smoke.read_task()["status"] == "in_progress"


def test_handoff_checker_ignores_rejected_sections_for_required_roles():
    trailer_smoke.bootstrap()
    handoff, evidence, _report = trailer_smoke.ensure_artifacts("SLICE-F0-001")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "slice-verifier.json").write_text('{"ok": true}\n', encoding="utf-8")
    handoff.write_text(
        "# Handoff SLICE-F0-001\n\n"
        "## slice-verifier rejected\n"
        "CLAUDE_TRAILER:\n"
        "AGENT: slice-verifier\n"
        "TASK_ID: SLICE-F0-001\n"
        "OUTCOME: verified\n"
        "NEXT_STATUS: verified_pending_close\n"
        "VERIFY_OUTCOME: verified\n"
        "HANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\n"
        "EVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001/slice-verifier.json\n"
        "ACCEPTED_BY_HOOK: no\n",
        encoding="utf-8",
    )
    from orchestrator.runtime.handoff import validate_handoff
    result = validate_handoff("SLICE-F0-001", require_verify_slice=True)
    assert result["ok"] is False
    assert any("only has rejected" in e for e in result["errors"])


def test_duplicate_trailer_keys_are_rejected_by_handoff_validator():
    trailer_smoke.bootstrap()
    handoff, evidence, _report = trailer_smoke.ensure_artifacts("SLICE-F0-001")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "tester.json").write_text('{"ok": true}\n', encoding="utf-8")
    handoff.write_text(
        "# Handoff SLICE-F0-001\n\n"
        "## tester\n"
        "CLAUDE_TRAILER:\n"
        "AGENT: tester\n"
        "TASK_ID: SLICE-F0-001\n"
        "OUTCOME: pass\n"
        "NEXT_STATUS: ready_for_close\n"
        "HANDOFF: orchestrator-state/tasks/handoffs/SLICE-F0-001.md\n"
        "EVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001/tester.json\n"
        "EVIDENCE: orchestrator-state/tasks/evidence/SLICE-F0-001/tester.json\n",
        encoding="utf-8",
    )
    from orchestrator.runtime.handoff import validate_handoff
    result = validate_handoff("SLICE-F0-001", require_ready_for_close=True)
    assert result["ok"] is False
    assert any("duplicate" in e.lower() for e in result["errors"])
