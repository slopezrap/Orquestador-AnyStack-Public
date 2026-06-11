from pathlib import Path
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def ensure_root_runtime():
    reg = ROOT / "orchestrator-state" / "tasks" / "registry.json"
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        memory_ready = (ROOT / "orchestrator-state" / "memory" / "PROGRESS.yaml").exists()
        if memory_ready and any(t.get("id") == "SLICE-F5-001" for t in data.get("tasks", [])):
            return
    except Exception:
        pass
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    subprocess.run(["bash", "scripts/reset-state.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", "scripts/check-memory-yaml.sh"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)


def test_memory_files_include_native_orchestrator_equivalents():
    ensure_root_runtime()
    mem = ROOT / "orchestrator-state" / "memory"
    required = [
        "PROGRESS.yaml",
        "PROGRESS.md",
        "project-context.yaml",
        "source-manifest.yaml",
        "project-brief.yaml",
        "project-brief.md",
        "architecture-contract.yaml",
        "architecture-contract.md",
        "stack-profile.yaml",
    ]
    for name in required:
        path = mem / name
        assert path.exists(), f"missing {name}"
        assert path.stat().st_size > 0, f"empty {name}"


def test_all_agent_prompts_point_to_yaml_memory_contract():
    for prompt in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        text = prompt.read_text(encoding="utf-8")
        for token in ["PROGRESS.yaml", "project-context.yaml", "source-manifest.yaml", "project-brief.yaml", "architecture-contract.yaml", "MEMORY.yaml", "handoffs/<TASK_ID>.yaml"]:
            assert token in text, f"{prompt.name} missing {token}"


def test_backend_journey_refs_do_not_force_ui_mcp():
    ensure_root_runtime()
    registry = json.loads((ROOT / "orchestrator-state" / "tasks" / "registry.json").read_text(encoding="utf-8"))
    found = False
    for task in registry.get("tasks", []):
        surface = task.get("verification_surface") or {}
        if task.get("journey_refs") and not surface.get("ui_spec_refs") and not surface.get("route_refs") and not (surface.get("signals") or {}).get("ui_write_paths"):
            found = True
            assert surface.get("kind") == "journey_backend_contract"
            assert surface.get("requires_visual_mcp") is False
            assert surface.get("requires_screen_journey_reviewer") is False
            assert surface.get("journey_refs_are_ui_signals") is False
    assert found, "fixture should include a backend/API/worker journey task without UI route"


def test_verify_slice_docs_reference_verification_surface():
    text = (ROOT / ".claude" / "skills" / "verify-slice" / "SKILL.md").read_text(encoding="utf-8")
    assert "verification_surface" in text or "verify_routing" in text
    assert "journey_refs" in text
    assert "not_applicable:no_ui_surface" in text
    assert "VISUAL_CHECK_METHOD: backend" in text or "visual_check_method" in text


def test_verify_routing_backend_journey_no_screen_reviewer():
    ensure_root_runtime()
    from orchestrator.runtime.verify_requirements import classify_task_verification
    registry = json.loads((ROOT / "orchestrator-state" / "tasks" / "registry.json").read_text(encoding="utf-8"))
    task = next(t for t in registry["tasks"] if t.get("id") == "SLICE-F5-001")
    routing = classify_task_verification(task)
    assert routing["visual_required"] is False
    assert routing["screen_journey_reviewer_required"] is False
    assert routing["journey_verification_required"] is True
    assert routing["mcp_requirement"]["mcp_browser"] == "not_applicable:no_ui_surface"
    assert routing["mcp_requirement"]["visual_check_method"] == "backend"
