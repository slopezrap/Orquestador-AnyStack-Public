from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, check=True):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=90)


def compile_root():
    (ROOT / "inputs" / "BLUEPRINT.md").write_text((ROOT / "examples" / "smoke" / "BLUEPRINT.md").read_text(encoding="utf-8"), encoding="utf-8")
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"])
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def next_wave_json(check=True):
    return run(["bash", "scripts/python-safe.sh", "-m", "orchestrator.runtime.next_wave", "--limit", "1", "--json"], check=check)


def test_followup_contract_rejects_in_scope_and_blocks_until_promoted():
    compile_root()

    rejected = run([
        "bash", "scripts/register-followup-task.sh", "propose",
        "--origin-task", "SLICE-F0-001",
        "--scope-classification", "in_scope_defect",
        "--repair-decision", "debugger_retest",
        "--why-not-debugger", "developer can fix it",
        "--title", "Should be rejected",
        "--severity", "high",
    ], check=False)
    assert rejected.returncode == 3
    assert "in_scope_defect" in rejected.stdout

    small_fix = run([
        "bash", "scripts/register-followup-task.sh", "propose",
        "--origin-task", "SLICE-F0-001",
        "--scope-classification", "missing_coverage",
        "--repair-decision", "followup_required",
        "--why-not-debugger", "two-file parser fix fits the active task",
        "--title", "Small in-scope fix",
        "--severity", "medium",
        "--files-estimate", "2",
        "--fits-current-write-set", "yes",
        "--requires-blueprint-change", "no",
        "--requires-new-dependency", "no",
        "--missing-real-data", "no",
        "--requires-human-decision", "no",
    ], check=False)
    assert small_fix.returncode == 3
    assert "small fix" in small_fix.stdout

    mechanical = run([
        "bash", "scripts/register-followup-task.sh", "propose",
        "--origin-task", "SLICE-F0-001",
        "--scope-classification", "future_enhancement",
        "--repair-decision", "followup_required",
        "--mechanical-runtime-issue", "yes",
        "--why-not-debugger", "runtime retry needed",
        "--title", "Runtime retry",
        "--severity", "medium",
    ], check=False)
    assert mechanical.returncode == 3
    assert "mechanical" in mechanical.stdout

    missing_triage = run([
        "bash", "scripts/register-followup-task.sh", "propose",
        "--origin-task", "SLICE-F0-001",
        "--scope-classification", "missing_coverage",
        "--why-not-debugger", "requires new blueprint refs",
        "--title", "Missing triage",
        "--severity", "medium",
    ], check=False)
    assert missing_triage.returncode == 2
    assert "repair-decision" in missing_triage.stdout

    missing_reason = run([
        "bash", "scripts/register-followup-task.sh", "propose",
        "--origin-task", "SLICE-F0-001",
        "--scope-classification", "missing_coverage",
        "--repair-decision", "followup_required",
        "--outside-current-write-set", "yes",
        "--title", "Missing coverage",
        "--severity", "medium",
    ], check=False)
    assert missing_reason.returncode == 2
    assert "why-not-debugger" in missing_reason.stdout

    created = json.loads(run([
        "bash", "scripts/register-followup-task.sh", "propose",
        "--origin-task", "SLICE-F0-001",
        "--scope-classification", "missing_coverage",
        "--repair-decision", "followup_required",
        "--outside-current-write-set", "yes",
        "--requires-blueprint-change", "yes",
        "--files-estimate", "6",
        "--fits-current-write-set", "no",
        "--why-not-debugger", "requires new blueprint refs outside the current write_set",
        "--title", "Add missing coverage",
        "--severity", "high",
        "--verify", "./scripts/check-task-dag.sh",
    ]).stdout)
    assert created["blocking"] is True
    fu_id = created["followup_id"]

    wave = next_wave_json(check=False)
    assert wave.returncode == 2
    payload = json.loads(wave.stdout)
    assert payload["ok"] is False
    assert payload["blocking_followups"][0]["id"] == fu_id

    promoted = json.loads(run(["bash", "scripts/promote-followup.sh", fu_id]).stdout)
    assert promoted["status"] == "promoted_to_blueprint"
    assert (ROOT / "orchestrator-state" / "tasks" / "source-doc-patches" / f"{fu_id}.md").exists()

    wave2 = next_wave_json()
    payload2 = json.loads(wave2.stdout)
    assert payload2["ok"] is True
    assert payload2["ready"]
