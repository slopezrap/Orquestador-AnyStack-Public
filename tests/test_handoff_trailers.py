from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
os.environ["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)


def test_parse_trailer_rejects_duplicate_keys_marker():
    from orchestrator.hooks.hook_capture_subagent_stop import parse_trailer, value_errors

    trailer = parse_trailer(
        "CLAUDE_TRAILER:\n"
        "AGENT: developer\n"
        "TASK_ID: SLICE-TEST-INFO\n"
        "OUTCOME: success\n"
        "OUTCOME: blocked\n"
        "NEXT_STATUS: validator_tester_pending\n"
        "HANDOFF: orchestrator-state/tasks/handoffs/SLICE-TEST-INFO.md\n"
        "EVIDENCE: orchestrator-state/tasks/evidence/SLICE-TEST-INFO\n"
    )
    assert trailer.get("__duplicate_keys__") == "outcome"
    assert any("duplicate" in err for err in value_errors(trailer, "developer"))


def test_info_only_handoff_with_next_status_is_invalid(tmp_path):
    from orchestrator.runtime.handoff import validate_handoff

    handoff = ROOT / "orchestrator-state/tasks/handoffs/SLICE-TEST-INFO.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "# Handoff SLICE-TEST-INFO\n\n"
        "## validator handoff\n"
        "CLAUDE_TRAILER:\n"
        "AGENT: validator\n"
        "TASK_ID: SLICE-TEST-INFO\n"
        "OUTCOME: approved\n"
        "NEXT_STATUS: done\n"
        "HANDOFF: orchestrator-state/tasks/handoffs/SLICE-TEST-INFO.md\n",
        encoding="utf-8",
    )
    result = validate_handoff("SLICE-TEST-INFO", require_roles=["validator"])
    assert result["ok"] is False
    assert any("NEXT_STATUS supplied" in err for err in result["errors"])


def test_append_handoff_event_preserves_planner_required_keys():
    from tests.helpers import trailer_smoke
    trailer_smoke.bootstrap()
    from orchestrator.runtime.handoff import append_handoff_event, validate_handoff
    from orchestrator.common import handoff_path

    append_handoff_event(
        "SLICE-F0-001",
        "planner",
        {
            "agent": "planner",
            "task_id": "SLICE-F0-001",
            "outcome": "ready",
            "context_ready": "yes",
            "needs_official_docs": "no",
        },
        accepted=True,
        note="pytest",
    )
    text = handoff_path("SLICE-F0-001").read_text(encoding="utf-8")
    assert "- CONTEXT_READY: yes" in text
    assert "- NEEDS_OFFICIAL_DOCS: no" in text
    result = validate_handoff("SLICE-F0-001", require_roles=["planner"])
    assert result["ok"] is True, result


def test_handoff_validator_merges_full_yaml_trailer_for_compat_markdown_allowlist():
    from tests.helpers import trailer_smoke
    trailer_smoke.bootstrap()
    from orchestrator.common import write_yaml
    from orchestrator.runtime.handoff import handoff_path, handoff_yaml_path, validate_handoff

    handoff_path("SLICE-F0-001").parent.mkdir(parents=True, exist_ok=True)
    handoff_path("SLICE-F0-001").write_text(
        "# Handoff SLICE-F0-001\n\n"
        "## planner handoff — compat\n"
        "CLAUDE_TRAILER:\n"
        "- AGENT: planner\n"
        "- TASK_ID: SLICE-F0-001\n"
        "- OUTCOME: ready\n"
        "- ACCEPTED_BY_HOOK: yes\n",
        encoding="utf-8",
    )
    write_yaml(
        handoff_yaml_path("SLICE-F0-001"),
        {
            "schema_version": "1.0",
            "task_id": "SLICE-F0-001",
            "events": [
                {
                    "at": "2026-01-01T00:00:00Z",
                    "agent": "planner",
                    "task_id": "SLICE-F0-001",
                    "outcome": "ready",
                    "accepted_by_hook": True,
                    "trailer": {
                        "agent": "planner",
                        "task_id": "SLICE-F0-001",
                        "outcome": "ready",
                        "context_ready": "yes",
                        "needs_official_docs": "no",
                    },
                }
            ],
        },
    )
    result = validate_handoff("SLICE-F0-001", require_roles=["planner"])
    assert result["ok"] is True, result


def test_subagent_stop_rejects_info_only_missing_required_keys():
    from tests.helpers import trailer_smoke
    trailer_smoke.bootstrap()
    import io
    import json
    import os
    import sys
    from orchestrator.hooks import hook_capture_subagent_stop
    from orchestrator.runtime.handoff import validate_handoff

    old_task = os.environ.get("CLAUDE_ACTIVE_TASK_ID")
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    try:
        os.environ["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
        payload = {
            "hook_event_name": "SubagentStop",
            "agent_id": "planner-test",
            "agent_type": "planner",
            "last_assistant_message": "CLAUDE_TRAILER:\nAGENT: planner\nTASK_ID: SLICE-F0-001\nOUTCOME: ready\n",
        }
        sys.stdin = io.StringIO(json.dumps(payload))
        out = io.StringIO()
        sys.stdout = out
        hook_capture_subagent_stop.main()
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout
        if old_task is None:
            os.environ.pop("CLAUDE_ACTIVE_TASK_ID", None)
        else:
            os.environ["CLAUDE_ACTIVE_TASK_ID"] = old_task
    output = out.getvalue()
    assert '"decision": "block"' in output
    result = validate_handoff("SLICE-F0-001", require_roles=["planner"])
    assert result["ok"] is False
    assert any("only has rejected" in e for e in result["errors"]), result
