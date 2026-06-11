from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, env=None):
    merged = os.environ.copy()
    merged["PYTHONPATH"] = str(ROOT) + os.pathsep + merged.get("PYTHONPATH", "")
    merged["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=ROOT, env=merged, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)


def bootstrap_smoke():
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "examples/smoke/BLUEPRINT.md"])
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def test_bootstrap_creates_structured_yaml_memory():
    bootstrap_smoke()
    out = run(["bash", "scripts/check-memory-yaml.sh"]).stdout
    data = json.loads(out)
    assert data["ok"] is True
    assert data["agents"] == 15
    assert data["tasks"] == 2
    for rel in [
        "orchestrator-state/memory/PROGRESS.yaml",
        "orchestrator-state/memory/project-context.yaml",
        "orchestrator-state/memory/decisions.yaml",
        "orchestrator-state/memory/risk-register.yaml",
        "orchestrator-state/tasks/task-index.yaml",
        "orchestrator-state/tasks/slices/SLICE-F0-001.yaml",
        "orchestrator-state/agent-memory/developer/MEMORY.yaml",
    ]:
        assert (ROOT / rel).exists(), rel




def test_wrong_case_memory_check_uses_directory_entries_not_case_insensitive_exists():
    source = (ROOT / "orchestrator" / "runtime" / "memory_yaml.py").read_text(encoding="utf-8")
    assert "memory_names = {child.name for child in memory_dir().iterdir()}" in source
    assert "wrong_name in memory_names" in source
    assert "memory_dir() / \"progress.yaml\"" not in source

def test_agent_prompts_declare_official_and_runtime_memory():
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        assert "memory: project" in frontmatter, path.name
        assert "MEMORY.yaml" in text, path.name
        assert "PROGRESS.yaml" in text, path.name
        assert "project-context.yaml" in text, path.name


def test_subagent_stop_updates_agent_memory_and_progress():
    from tests.helpers import trailer_smoke

    bootstrap_smoke()
    trailer_smoke.combined_flow()
    out = run(["bash", "scripts/check-memory-yaml.sh"]).stdout
    assert json.loads(out)["ok"] is True
    developer_memory = (ROOT / "orchestrator-state/agent-memory/developer/MEMORY.yaml").read_text(encoding="utf-8")
    progress = (ROOT / "orchestrator-state/memory/PROGRESS.yaml").read_text(encoding="utf-8")
    assert "SubagentStop" in developer_memory
    assert "subagent_stop" in progress
    assert (ROOT / "orchestrator-state/tasks/handoffs/SLICE-F0-001.yaml").exists()
