from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_AGENT_MODELS = {
    "developer": "fable[1m]",
    "main-orchestrator": "opus[1m]",
    "planner": "opus",
    "blueprint-reviewer": "opus",
    "project-architect": "opus",
    "validator": "opus",
    "debugger": "opus",
    "slice-verifier": "opus",
    "tester": "sonnet",
    "deployer": "sonnet",
    "closer": "sonnet",
    "task-planner": "sonnet",
    "document-analyzer": "sonnet",
    "official-docs-researcher": "sonnet",
    "screen-journey-reviewer": "sonnet",
}


def _env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return env


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    raw = text.split("---", 2)[1]
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out



def _split_tools(raw: str) -> set[str]:
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in raw or "":
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                out.append(item)
            buf = []
        else:
            buf.append(ch)
    item = "".join(buf).strip()
    if item:
        out.append(item)
    return {item.split("(", 1)[0].strip() for item in out if item.strip()}

def test_active_agents_are_blueprint_first_with_final_rule_set():
    rule_names = {path.name for path in (ROOT / ".claude" / "rules").glob("*.md")}
    assert "07-skills-runtime.md" in rule_names
    assert not any(re.search(r"v\d", name.lower()) for name in rule_names)
    assert not any(token in name.lower() for name in rule_names for token in ["dual-runtime-rule", "noncanonical-runtime-rule", "archived-runtime-rule"])
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "inputs/BLUEPRINT.md" in text
        assert "orchestrator-state/agent-memory/" in text
        assert "CLAUDE_TRAILER" in text


def test_agent_frontmatter_preserves_budget_config_without_nested_agent_spawns():
    for path in sorted((ROOT / ".claude/agents").glob("*.md")):
        fm = _frontmatter(path)
        tools = _split_tools(fm.get("tools", ""))
        assert fm.get("maxTurns"), path.name
        assert fm.get("effort"), path.name
        assert fm.get("model") == EXPECTED_AGENT_MODELS[path.stem], path.name
        assert fm.get("model") != "inherit", path.name
        assert "Skill" in tools, path.name
        assert "orchestrator-state/agent-memory/" in path.read_text(encoding="utf-8"), path.name
        if path.stem == "main-orchestrator":
            assert "Agent" in tools
        else:
            assert "Agent" not in tools


def test_claude_adapter_checker_enforces_agent_runtime_contract():
    subprocess.run(["bash", "scripts/check-claude-adapter.sh"], cwd=ROOT, env=_env(), check=True)


def test_journey_gate_is_added_by_closer_and_cleared_by_verify_journey(tmp_path):
    env = _env()
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True)

    # This test exercises the closer -> pending journey gate in isolation.
    # Build the smallest runtime fixture instead of bootstrapping a full blueprint;
    # the compiler/bootstrap path is covered by dedicated tests.
    task_id = "SLICE-F0-001"
    reg_path = ROOT / "orchestrator-state/tasks/registry.json"
    reg = {
        "schema_version": "test",
        "tasks": [{
            "id": task_id,
            "task_id": task_id,
            "title": "Journey gate fixture",
            "description": "Small runtime fixture for closer journey gate validation.",
            "status": "verified_pending_close",
            "phase_id": "F0",
            "depends_on": [],
            "write_set": [],
            "conflict_groups": [],
            "closes_journeys": ["J-001"],
            "journey_refs": [],
        }],
        "phases": [],
        "task_dag": {"nodes": [], "edges": []},
    }
    reg_path.write_text(json.dumps(reg), encoding="utf-8")
    runtime_path = ROOT / "orchestrator-state/tasks/runtime-state.json"
    runtime_path.write_text(json.dumps({
        "schema_version": "test",
        "active_task_id": None,
        "pending_journey_verifications": [],
        "spawn_counts": {},
    }), encoding="utf-8")

    (ROOT / f"orchestrator-state/tasks/handoffs/{task_id}.md").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / f"orchestrator-state/tasks/handoffs/{task_id}.md").write_text("# Handoff\n", encoding="utf-8")
    (ROOT / f"orchestrator-state/tasks/evidence/{task_id}").mkdir(parents=True, exist_ok=True)
    (ROOT / "orchestrator-state/tasks/reports").mkdir(parents=True, exist_ok=True)
    (ROOT / f"orchestrator-state/tasks/reports/{task_id}.md").write_text("# Report\n", encoding="utf-8")

    payload = {
        "agent_type": "closer",
        "last_assistant_message": "\n".join([
            "CLAUDE_TRAILER:",
            "AGENT: closer",
            f"TASK_ID: {task_id}",
            "OUTCOME: committed",
            "NEXT_STATUS: done",
            f"HANDOFF: orchestrator-state/tasks/handoffs/{task_id}.md",
            f"REPORT: orchestrator-state/tasks/reports/{task_id}.md",
            "REPORT_READY: yes",
            "BASELINE_SYNC_READY: yes",
            "GIT_READY: yes",
            "PUSH_READY: yes",
            "GIT_WORKFLOW_READY: yes",
            "RUNTIME_CLEANED: yes",
            "DOCKER_RUNTIME_CLEANED: yes",
            "RANCHER_RUNTIME_CLEANED: yes",
            "DEV_PORTS_RELEASED: yes",
            "WORKTREES_CLEANED: yes",
            "PR_READY: yes",
            "MERGED: yes",
            "CANONICAL_MAIN_SYNCED: yes",
        ]),
    }
    env2 = dict(env)
    env2["CLAUDE_ACTIVE_TASK_ID"] = task_id
    subprocess.run([sys.executable, "-B", "-S", ".claude/bin/hook_capture_subagent_stop.py"], cwd=ROOT, env=env2, input=json.dumps(payload), text=True, check=True)
    runtime = json.loads((ROOT / "orchestrator-state/tasks/runtime-state.json").read_text(encoding="utf-8"))
    assert "J-001" in runtime.get("pending_journey_verifications", [])

    subprocess.run(["bash", "scripts/verify-journey.sh", "J-001", "--verified"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    runtime = json.loads((ROOT / "orchestrator-state/tasks/runtime-state.json").read_text(encoding="utf-8"))
    assert "J-001" not in runtime.get("pending_journey_verifications", [])
