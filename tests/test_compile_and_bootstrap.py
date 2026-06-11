from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def test_smoke_compile_and_bootstrap():
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "examples/smoke/BLUEPRINT.md"])
    data = json.loads((ROOT / "orchestrator-state/compiled/orchestrator-input.json").read_text())
    assert len(data["slices"]) == 2
    assert all(s.get("description") and len(s["description"]) >= 120 for s in data["slices"])
    assert data["derived"]["write_sets"]["SLICE-F1-001"]
    second = next(sl for sl in data["slices"] if sl["id"] == "SLICE-F1-001")
    assert second["depends_on_rationale"]["SLICE-F0-001"]
    assert second["dependency_edges"][0]["reason"] == second["depends_on_rationale"]["SLICE-F0-001"]

    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])
    reg = json.loads((ROOT / "orchestrator-state/tasks/registry.json").read_text())
    assert len(reg["tasks"]) == 2
    assert reg["tasks"][0]["status"] == "ready"
    assert reg["tasks"][0]["description"] == data["slices"][0]["description"]
    assert reg["tasks"][0]["dependency_rationale"] == data["slices"][0]["dependency_rationale"]
    assert reg["tasks"][0]["resolved_specs"]
    assert all(spec.get("description") for spec in reg["tasks"][0]["resolved_specs"])
    second_task = next(t for t in reg["tasks"] if t["id"] == "SLICE-F1-001")
    assert second_task["depends_on_rationale"]["SLICE-F0-001"]
    assert second_task["dependency_edges"][0]["reason"] == second_task["depends_on_rationale"]["SLICE-F0-001"]
    assert second_task["resolved_dependencies"][0]["id"] == "SLICE-F0-001"
    assert second_task["resolved_dependencies"][0]["description"]

    dag = json.loads((ROOT / "orchestrator-state/tasks/task-dag.json").read_text())
    assert dag["nodes"][0]["description"] == reg["tasks"][0]["description"]
    assert dag["nodes"][0]["dependency_rationale"] == reg["tasks"][0]["dependency_rationale"]
    assert any(edge.get("reason") for edge in dag["edges"])

    pack_json = json.loads((ROOT / "orchestrator-state/tasks/task-packs/SLICE-F0-001.json").read_text())
    assert pack_json["description"] == reg["tasks"][0]["description"]
    assert pack_json["dependency_rationale"] == reg["tasks"][0]["dependency_rationale"]
    assert pack_json["resolved_specs"]
    pack_json_2 = json.loads((ROOT / "orchestrator-state/tasks/task-packs/SLICE-F1-001.json").read_text())
    assert pack_json_2["resolved_dependencies"][0]["id"] == "SLICE-F0-001"
    pack_md_2 = (ROOT / "orchestrator-state/tasks/task-packs/SLICE-F1-001.md").read_text()
    assert "## Dependency edges" in pack_md_2
    assert "## Resolved dependency tasks" in pack_md_2
    pack_md = (ROOT / "orchestrator-state/tasks/task-packs/SLICE-F0-001.md").read_text()
    assert "## Human task description" in pack_md
    assert reg["tasks"][0]["description"] in pack_md
    assert "- none\nBuilds:" not in pack_md
    assert "- missing" not in pack_md.split("## Resolved blueprint specs", 1)[0]


def test_compiler_preserves_authored_slice_scope(tmp_path):
    source = ROOT / "examples" / "smoke" / "BLUEPRINT.md"
    text = source.read_text()
    text = text.replace(
        "  builds:\n  - BB-core\n  depends_on: []\n",
        "  builds:\n"
        "  - BB-core\n"
        "  write_set:\n"
        "  - explicit/a.py\n"
        "  - explicit/b.py\n"
        "  conflict_groups:\n"
        "  - explicit-group\n"
        "  write_set_override:\n"
        "  - override/c.py\n"
        "  conflict_group_override:\n"
        "  - override-group\n"
        "  depends_on: []\n",
        1,
    )
    bp = tmp_path / "BLUEPRINT.md"
    bp.write_text(text, encoding="utf-8")

    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", str(bp)])
    data = json.loads((ROOT / "orchestrator-state/compiled/orchestrator-input.json").read_text())
    first = next(sl for sl in data["slices"] if sl["id"] == "SLICE-F0-001")

    assert first["write_set"] == ["explicit/a.py", "explicit/b.py", "override/c.py"]
    assert first["conflict_groups"] == ["explicit-group", "override-group"]
    assert first["conflict_group"] == ["explicit-group", "override-group"]
    assert data["derived"]["write_sets"]["SLICE-F0-001"] == first["write_set"]
    assert data["derived"]["conflict_groups"]["SLICE-F0-001"] == first["conflict_groups"]
    assert "orchestrator-smoke/core/**" not in first["write_set"]
    assert "orchestrator-smoke:core" not in first["conflict_groups"]

    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])
    reg = json.loads((ROOT / "orchestrator-state/tasks/registry.json").read_text())
    task = next(t for t in reg["tasks"] if t["id"] == "SLICE-F0-001")
    assert task["write_set"] == ["explicit/a.py", "explicit/b.py", "override/c.py"]
    assert task["conflict_groups"] == ["explicit-group", "override-group"]


def test_compile_fails_when_slice_description_missing(tmp_path):
    source = ROOT / "examples" / "smoke" / "BLUEPRINT.md"
    text = source.read_text()
    marker = "- id: SLICE-F0-001\n"
    start = text.index(marker)
    desc_start = text.index("  description:", start)
    dep_start = text.index("  dependency_rationale:", desc_start)
    text = text[:desc_start] + text[dep_start:]
    bad = tmp_path / "BLUEPRINT.md"
    bad.write_text(text)

    proc = subprocess.run(
        ["bash", "scripts/compile-blueprint.sh", str(bad)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode == 2
    assert "slice must declare description" in proc.stderr
