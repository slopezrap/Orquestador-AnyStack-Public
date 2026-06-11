from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> str:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout


def ensure_root_blueprint_runtime() -> None:
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"])
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def test_blueprint_lossless_checker_passes_and_indexes_tasks():
    ensure_root_blueprint_runtime()
    data = json.loads(run(["bash", "scripts/check-blueprint-lossless-flow.sh"]))
    assert data["ok"] is True
    assert data["sections"] >= 1
    assert data["orchestrator_blocks"] >= 1
    assert data["tasks"] == 11


def test_registry_task_pack_and_slice_yaml_carry_lossless_refs():
    ensure_root_blueprint_runtime()
    registry = json.loads((ROOT / "orchestrator-state/tasks/registry.json").read_text(encoding="utf-8"))
    task = registry["tasks"][0]
    assert task["source_sections"]
    assert task["blueprint_lossless_refs"]["snapshot"] == "orchestrator-state/compiled/BLUEPRINT.snapshot.md"
    pack = json.loads((ROOT / "orchestrator-state/tasks/task-packs" / f"{task['id']}.json").read_text(encoding="utf-8"))
    assert pack["source_sections"]
    md = (ROOT / "orchestrator-state/tasks/task-packs" / f"{task['id']}.md").read_text(encoding="utf-8")
    assert "## Blueprint source sections" in md
    slice_yaml = (ROOT / "orchestrator-state/tasks/slices" / f"{task['id']}.yaml").read_text(encoding="utf-8")
    assert "source_sections" in slice_yaml
    assert "blueprint_lossless_refs" in slice_yaml


def test_subagent_context_mentions_lossless_blueprint_paths():
    ensure_root_blueprint_runtime()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env["CLAUDE_ACTIVE_TASK_ID"] = "SLICE-F0-001"
    payload = '{"agent_type":"developer","agent_id":"dev-test"}'
    proc = subprocess.run(
        ["./scripts/python-safe.sh", "-m", "orchestrator.hooks.hook_subagent_start_context"],
        cwd=ROOT,
        env=env,
        input=payload,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    out = proc.stdout
    assert "BLUEPRINT.snapshot.md" in out
    assert "blueprint-sections" in out
    assert "blueprint_lossless_refs" in out
