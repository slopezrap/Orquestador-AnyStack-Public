from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.common import project_root, read_json, read_yaml, registry_path, tasks_dir, memory_dir


def _rel(path: Path) -> str:
    try:
        return path.relative_to(project_root()).as_posix()
    except Exception:
        return path.as_posix()


def _load_required_json(path: Path, errors: list[str]) -> Any:
    data = read_json(path, None)
    if data in (None, {}, []):
        errors.append(f"missing_or_empty {_rel(path)}")
    return data


def check_blueprint_lossless_flow() -> dict[str, Any]:
    root = project_root()
    cdir = root / "orchestrator-state" / "compiled"
    errors: list[str] = []
    warnings: list[str] = []
    required = [
        "BLUEPRINT.snapshot.md",
        "blueprint-manifest.json",
        "blueprint-manifest.yaml",
        "blueprint-lossless.json",
        "blueprint-lossless.yaml",
        "blueprint-sections.json",
        "blueprint-sections.yaml",
        "blueprint-blocks.json",
        "blueprint-blocks.yaml",
        "orchestrator-input.json",
        "source-map.json",
    ]
    for name in required:
        p = cdir / name
        if not p.exists() or p.stat().st_size == 0:
            errors.append(f"missing_or_empty {_rel(p)}")
    inp = _load_required_json(cdir / "orchestrator-input.json", errors) or {}
    manifest = inp.get("blueprint") or {}
    if not isinstance(manifest, dict) or not manifest:
        errors.append("orchestrator-input.json missing blueprint lossless manifest")
    ids_to_sections = manifest.get("ids_to_sections") or {}
    if not ids_to_sections:
        errors.append("blueprint.ids_to_sections is empty")
    for required_id in ["DR-001", "UC-001", "UC-002", "J-001", "SM-001", "BB-dag-runtime", "SLICE-F0-001"]:
        if required_id not in ids_to_sections:
            warnings.append(f"id_not_indexed {required_id}")
    sections = _load_required_json(cdir / "blueprint-sections.json", errors) or {}
    blocks = _load_required_json(cdir / "blueprint-blocks.json", errors) or {}
    section_count = len((sections or {}).get("sections") or [])
    block_count = len((blocks or {}).get("blocks") or [])
    if section_count <= 0:
        errors.append("blueprint-sections.json has no sections")
    if block_count <= 0:
        errors.append("blueprint-blocks.json has no orchestrator blocks")

    registry = read_json(registry_path(), {}) or {}
    tasks = [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]
    if not tasks:
        errors.append("registry has no tasks")
    for task in tasks:
        tid = str(task.get("id") or "unknown")
        if not task.get("source_sections"):
            errors.append(f"task {tid} missing source_sections")
        if not task.get("blueprint_lossless_refs"):
            errors.append(f"task {tid} missing blueprint_lossless_refs")
        for spec in task.get("resolved_specs") or []:
            sid = spec.get("id")
            if not isinstance(spec.get("raw"), dict) or not spec.get("raw"):
                errors.append(f"task {tid} spec {sid} missing raw YAML payload")
            if not isinstance(spec.get("source_sections"), list):
                errors.append(f"task {tid} spec {sid} missing source_sections")
            if not isinstance(spec.get("blueprint_lossless_refs"), dict):
                errors.append(f"task {tid} spec {sid} missing blueprint_lossless_refs")
        pack_json = tasks_dir() / "task-packs" / f"{tid}.json"
        pack_md = tasks_dir() / "task-packs" / f"{tid}.md"
        pjson = read_json(pack_json, {})
        if not pjson.get("source_sections"):
            errors.append(f"task-pack json {tid} missing source_sections")
        if not pjson.get("blueprint_lossless_refs"):
            errors.append(f"task-pack json {tid} missing blueprint_lossless_refs")
        if not pack_md.exists() or "## Blueprint source sections" not in pack_md.read_text(encoding="utf-8", errors="replace"):
            errors.append(f"task-pack markdown {tid} missing Blueprint source sections")
        slice_yaml = read_yaml(tasks_dir() / "slices" / f"{tid}.yaml", {}) or {}
        sd = slice_yaml.get("slice") or {}
        if not sd.get("source_sections"):
            errors.append(f"slice yaml {tid} missing source_sections")
        if not sd.get("blueprint_lossless_refs"):
            errors.append(f"slice yaml {tid} missing blueprint_lossless_refs")
    # DAG nodes are intentionally slim scheduling records. Lossless context is verified on registry tasks, task-packs and slice YAML above.
    for rel in ["blueprint-manifest.yaml", "blueprint-sections.yaml", "blueprint-blocks.yaml", "blueprint-lossless.yaml"]:
        data = read_yaml(memory_dir() / rel, None)
        if data in (None, {}, []):
            errors.append(f"memory mirror missing_or_empty orchestrator-state/memory/{rel}")
    # Agent prompts must point to lossless sources and own memory.
    agent_errors = 0
    for agent_file in sorted((root / ".claude" / "agents").glob("*.md")):
        text = agent_file.read_text(encoding="utf-8", errors="replace")
        for token in ["BLUEPRINT.snapshot.md", "source_sections", "blueprint_lossless_refs", "MEMORY.yaml"]:
            if token not in text:
                agent_errors += 1
                errors.append(f"agent {agent_file.name} missing lossless/memory token {token}")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "sections": section_count,
        "orchestrator_blocks": block_count,
        "ids_indexed": len(ids_to_sections),
        "tasks": len(tasks),
        "agent_prompt_errors": agent_errors,
    }


def main() -> int:
    result = check_blueprint_lossless_flow()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
