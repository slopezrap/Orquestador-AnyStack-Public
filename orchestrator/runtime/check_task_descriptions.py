from __future__ import annotations
import json, re, sys
from pathlib import Path
from orchestrator.common import compiled_dir, project_root, read_json, registry_path, tasks_dir

MIN_DESCRIPTION_CHARS = 240
MIN_SPEC_DESCRIPTION_CHARS = 240
MIN_DEPENDENCY_RATIONALE_CHARS = 180
FORBIDDEN_PATTERNS = [
    (re.compile(r"\b(?:TODO|TBD|FIXME|XXX|foo|bar|baz)\b|(?i:\b(?:lorem\s+ipsum|placeholder|monkey|foo|bar|baz|xxx)\b)"), "placeholder_or_open_work"),
    (re.compile(r"\b(?:dummy|fake|stubs?|stubbed|stub\s+implementation|temporary\s+implementation|fake\s+data|mock\s+data|sample\s+data|seed\s+data|hardcoded\s+demo)\b", re.IGNORECASE), "non_production_wording"),
    (re.compile(r"\bNotImplementedError\b|^\s*pass\s*(?:#.*)?$", re.IGNORECASE | re.MULTILINE), "unfinished_runtime_marker"),
    (re.compile(r"This\s+dependency\s+rationale\s+is\s+part\s+of\s+the(?:\s+production)?\s+DAG\s+contract", re.IGNORECASE), "boilerplate_dependency_rationale"),
]


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def validate_text(task_id: str, field: str, value: object) -> list[str]:
    text = norm(value)
    errors: list[str] = []
    if not text:
        errors.append(f"{task_id}: missing {field}")
        return errors
    if field == "description" and len(text) < MIN_DESCRIPTION_CHARS:
        errors.append(f"{task_id}: description shorter than {MIN_DESCRIPTION_CHARS} characters")
    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            errors.append(f"{task_id}: {field} contains {reason}")
    return errors


def main() -> int:
    inp = read_json(compiled_dir() / "orchestrator-input.json", {})
    reg = read_json(registry_path(), {})
    dag = read_json(tasks_dir() / "task-dag.json", {})
    errors: list[str] = []
    slices = {str(s.get("id")): s for s in inp.get("slices", []) or [] if s.get("id")}
    tasks = {str(t.get("id")): t for t in reg.get("tasks", []) or [] if t.get("id")}
    nodes = {str(n.get("id")): n for n in dag.get("nodes", []) or [] if n.get("id")}
    if not slices:
        errors.append("orchestrator-input has no slices; run compile-blueprint before validating task descriptions")
    if not tasks:
        errors.append("registry has no tasks; run bootstrap-registry before validating task descriptions")
    if not nodes:
        errors.append("task-dag has no nodes; run bootstrap-registry before validating task descriptions")
    for sid, sl in sorted(slices.items()):
        errors.extend(validate_text(sid, "title", sl.get("title")))
        errors.extend(validate_text(sid, "description", sl.get("description")))
        if norm(sl.get("title")).lower() == norm(sl.get("description")).lower():
            errors.append(f"{sid}: description duplicates title")
        drat = norm(sl.get("dependency_rationale"))
        if len(drat) < MIN_SPEC_DESCRIPTION_CHARS:
            errors.append(f"{sid}: dependency_rationale is missing or too short")
        dep_map = sl.get("depends_on_rationale") or {}
        deps = [str(x) for x in sl.get("depends_on") or []]
        if not isinstance(dep_map, dict):
            errors.append(f"{sid}: depends_on_rationale must be an object")
            dep_map = {}
        for dep in deps:
            if len(norm(dep_map.get(dep))) < MIN_DEPENDENCY_RATIONALE_CHARS:
                errors.append(f"{sid}: depends_on_rationale[{dep}] is missing or too short")
        dep_edges = sl.get("dependency_edges") or []
        if len(dep_edges) != len(deps):
            errors.append(f"{sid}: dependency_edges count does not match depends_on")
        task = tasks.get(sid)
        node = nodes.get(sid)
        if not task:
            errors.append(f"{sid}: missing registry task")
            continue
        if norm(task.get("description")) != norm(sl.get("description")):
            errors.append(f"{sid}: registry description does not match orchestrator-input")
        if norm(task.get("dependency_rationale")) != drat:
            errors.append(f"{sid}: registry dependency_rationale does not match orchestrator-input")
        if task.get("depends_on_rationale") != dep_map:
            errors.append(f"{sid}: registry depends_on_rationale does not match orchestrator-input")
        if task.get("dependency_edges") != dep_edges:
            errors.append(f"{sid}: registry dependency_edges does not match orchestrator-input")
        if node and norm(node.get("description")) != norm(sl.get("description")):
            errors.append(f"{sid}: task-dag node description does not match orchestrator-input")
        if node and norm(node.get("dependency_rationale")) != drat:
            errors.append(f"{sid}: task-dag node dependency_rationale does not match orchestrator-input")
        if node and node.get("depends_on_rationale") != dep_map:
            errors.append(f"{sid}: task-dag node depends_on_rationale does not match orchestrator-input")
        if node:
            for key in ["implements", "builds", "verification_refs", "contract_refs", "evidence_contract", "acceptance", "building_block_refs", "read_set", "conflict_group"]:
                if key not in node:
                    errors.append(f"{sid}: task-dag node missing {key}")
            if node.get("contract_refs") != task.get("contract_refs"):
                errors.append(f"{sid}: task-dag node contract_refs drift from registry task")
            if node.get("evidence_contract") != task.get("evidence_contract"):
                errors.append(f"{sid}: task-dag node evidence_contract drift from registry task")
        resolved = task.get("resolved_specs") or []
        if not resolved:
            errors.append(f"{sid}: registry task missing resolved_specs")
        for spec in resolved:
            if len(norm(spec.get("description"))) < MIN_SPEC_DESCRIPTION_CHARS:
                errors.append(f"{sid}: resolved spec {spec.get('id')} description missing or too short")
        pack_json = read_json(tasks_dir() / "task-packs" / f"{sid}.json", {})
        if norm(pack_json.get("description")) != norm(sl.get("description")):
            errors.append(f"{sid}: task-pack JSON description does not match orchestrator-input")
        if norm(pack_json.get("dependency_rationale")) != drat:
            errors.append(f"{sid}: task-pack JSON dependency_rationale does not match orchestrator-input")
        if pack_json.get("depends_on_rationale") != dep_map:
            errors.append(f"{sid}: task-pack JSON depends_on_rationale does not match orchestrator-input")
        if len(pack_json.get("resolved_dependencies") or []) != len(deps):
            errors.append(f"{sid}: task-pack JSON resolved_dependencies count mismatch")
        if not pack_json.get("resolved_specs"):
            errors.append(f"{sid}: task-pack JSON missing resolved_specs")
        pack_md = tasks_dir() / "task-packs" / f"{sid}.md"
        if not pack_md.exists():
            errors.append(f"{sid}: missing task-pack markdown")
        else:
            text = pack_md.read_text(encoding="utf-8", errors="replace")
            ntext = norm(text)
            if norm(sl.get("description")) not in ntext:
                errors.append(f"{sid}: task-pack markdown does not include description")
            if drat and drat not in ntext:
                errors.append(f"{sid}: task-pack markdown does not include dependency_rationale")
            if "## Resolved blueprint specs" not in text:
                errors.append(f"{sid}: task-pack markdown missing resolved blueprint specs section")
            if "## Dependency edges" not in text:
                errors.append(f"{sid}: task-pack markdown missing dependency edges section")
            if deps and "## Resolved dependency tasks" not in text:
                errors.append(f"{sid}: task-pack markdown missing resolved dependency tasks section")
    result = {
        "ok": not errors,
        "slices": len(slices),
        "registry_tasks": len(tasks),
        "dag_nodes": len(nodes),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

# Generic blueprint boilerplate is forbidden by compile_blueprint and check_blueprint_machine_contract.
