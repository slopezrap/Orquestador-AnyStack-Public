from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from orchestrator.bootstrap.bootstrap_registry import build_registry
from orchestrator.compiler.compile_blueprint import compile_blueprint
from orchestrator.common import project_root

REQUIRED_LOGIC = ["domain", "application", "journey", "permission", "state", "error", "integration", "ui"]
REQUIRED_AUX = ["arc42", "data", "config", "verification", "adr", "risks", "glossary", "external_refs"]
MIN_DESC = 240
MIN_SLICE_DESC = 300
MIN_DEP_RATIONALE = 180
GENERIC = re.compile(
    r"This\s+(?:state|error|integration|UI|data|verification|ADR|risk|glossary|external reference|configuration|config|arc42|building block|domain|application|journey|permission)\s+contract\s+is\s+resolved\s+into",
    re.I,
)
FORBIDDEN = [
    re.compile(r"\bis\s+resolved\s+into\b", re.IGNORECASE),
    re.compile(r"\b(?:TODO|TBD|FIXME|XXX)\b|(?i:\b(?:lorem\s+ipsum|placeholder|monkey|foo|bar|baz)\b)"),
    re.compile(r"\b(?:dummy|fake|stubbed|stub\s+implementation|runtime\s+stub|temporary\s+implementation|fake\s+data|mock\s+data|sample\s+data|seed\s+data|hardcoded\s+demo)\b", re.I),
    re.compile(r"\bNotImplementedError\b|^\s*pass\s*(?:#.*)?$", re.I | re.M),
    GENERIC,
]


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def item_iter(compiled: dict[str, Any]):
    if compiled.get("project"):
        yield "project", compiled["project"]
    if compiled.get("stack"):
        yield "stack", compiled["stack"]
    for item in compiled.get("building_blocks") or []:
        yield "building_blocks", item
    for key, items in (compiled.get("logic") or {}).items():
        for item in items or []:
            yield f"logic.{key}", item
    for key, items in (compiled.get("auxiliary") or {}).items():
        for item in items or []:
            yield f"auxiliary.{key}", item
    for item in compiled.get("slices") or []:
        yield "registry.slices", item


def text_errors(label: str, text: str, min_chars: int) -> list[str]:
    errors: list[str] = []
    if not text:
        return [f"{label}: missing detailed description"]
    if len(text) < min_chars:
        errors.append(f"{label}: description shorter than {min_chars} chars")
    if len(text.split()) < 25:
        errors.append(f"{label}: description is too short at sentence level")
    if "blueprint gold" not in text.lower() and label.startswith(("project", "stack")) is False:
        errors.append(f"{label}: description must explicitly carry gold blueprint context")
    for pat in FORBIDDEN:
        if pat.search(text):
            errors.append(f"{label}: description contains placeholder, unfinished or generic projection wording")
    return errors


def validate_compiled(compiled: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not compiled.get("project"):
        errors.append("missing project block")
    if not compiled.get("stack"):
        errors.append("missing stack block")
    else:
        orchestrator_cfg = (compiled.get("stack") or {}).get("orchestrator") or {}
        par = orchestrator_cfg.get("parallelism") or {}
        locks = orchestrator_cfg.get("locks") or {}
        if not par:
            errors.append("stack.orchestrator.parallelism is required for gold blueprint DAG execution")
        else:
            try:
                if int(par.get("max_parallel_slices") or 0) < 1:
                    errors.append("stack.orchestrator.parallelism.max_parallel_slices must be >= 1")
            except Exception:
                errors.append("stack.orchestrator.parallelism.max_parallel_slices must be an integer")
            if par.get("selection_policy") != "dependency_order_then_non_conflicting":
                errors.append("stack.orchestrator.parallelism.selection_policy must be dependency_order_then_non_conflicting")
        if locks.get("backend") != "posix_fcntl_file_locks":
            errors.append("stack.orchestrator.locks.backend must be posix_fcntl_file_locks")
        if not {"linux", "darwin"} <= set(str(x) for x in locks.get("platforms") or []):
            errors.append("stack.orchestrator.locks.platforms must include linux and darwin")
    if not compiled.get("building_blocks"):
        errors.append("missing building_blocks")
    for key in REQUIRED_LOGIC:
        if not (compiled.get("logic") or {}).get(key):
            errors.append(f"missing logic.{key}")
    for key in REQUIRED_AUX:
        if not (compiled.get("auxiliary") or {}).get(key):
            errors.append(f"missing auxiliary.{key}")
    if not compiled.get("slices"):
        errors.append("missing registry.slices")
    for kind, item in item_iter(compiled):
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or kind)
        desc = norm(item.get("description") or item.get("summary"))
        errors.extend(text_errors(f"{iid} ({kind})", desc, MIN_SLICE_DESC if kind == "registry.slices" else MIN_DESC))
        if kind == "registry.slices":
            dep = norm(item.get("dependency_rationale"))
            if len(dep) < MIN_DEP_RATIONALE:
                errors.append(f"{iid}: dependency_rationale shorter than {MIN_DEP_RATIONALE} chars")
            if GENERIC.search(dep):
                errors.append(f"{iid}: dependency_rationale contains generic projection wording")
            deps = [str(x) for x in item.get("depends_on") or []]
            dep_map = item.get("depends_on_rationale") or {}
            if not isinstance(dep_map, dict):
                errors.append(f"{iid}: depends_on_rationale must be a map")
            else:
                for d in deps:
                    reason = norm(dep_map.get(d))
                    if len(reason) < MIN_DEP_RATIONALE:
                        errors.append(f"{iid}: missing detailed depends_on_rationale for {d}")
            for field in ["implements", "builds", "verifies", "arc42_refs"]:
                if not item.get(field):
                    errors.append(f"{iid}: missing {field}")
    return errors


def validate_registry_projection(compiled: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    registry = build_registry(compiled)
    tasks = registry.get("tasks") or []
    dag = registry.get("task_dag") or {}
    if not dag.get("parallelism"):
        errors.append("DAG projection missing parallelism")
    if not dag.get("parallel_groups"):
        errors.append("DAG projection missing parallel_groups")
    if not dag.get("lock_model"):
        errors.append("DAG projection missing lock_model")
    task_by_id = {str(t.get("id")): t for t in tasks if isinstance(t, dict)}
    node_by_id = {str(n.get("id")): n for n in dag.get("nodes") or [] if isinstance(n, dict)}
    for sl in compiled.get("slices") or []:
        sid = str(sl.get("id"))
        task = task_by_id.get(sid)
        node = node_by_id.get(sid)
        if not task:
            errors.append(f"{sid}: missing registry task")
            continue
        if not node:
            errors.append(f"{sid}: missing DAG node")
            continue
        for field in ["title", "description", "dependency_rationale", "depends_on_rationale", "dependency_edges", "resolved_dependencies", "resolved_specs", "locks", "parallel"]:
            if field not in task:
                errors.append(f"{sid}: task missing {field}")
        for field in ["title", "description", "dependency_rationale", "depends_on_rationale", "dependency_edges", "resolved_dependencies", "locks", "parallel", "task_pack"]:
            if field not in node:
                errors.append(f"{sid}: dag missing {field}")
        for obj_name, obj in [("task", task), ("dag", node)]:
            if obj.get("parallel") and not obj.get("parallel", {}).get("safe_group"):
                errors.append(f"{sid}: {obj_name} missing parallel.safe_group")
        expected_refs = set(map(str, (sl.get("implements") or []) + (sl.get("builds") or []) + (sl.get("verifies") or []) + (sl.get("closes_journeys") or []) + (sl.get("arc42_refs") or [])))
        got = {str(s.get("id")) for s in task.get("resolved_specs") or [] if isinstance(s, dict)}
        if expected_refs - got:
            errors.append(f"{sid}: resolved_specs missing {sorted(expected_refs - got)}")
        for spec in task.get("resolved_specs") or []:
            label = f"{sid}:{spec.get('id')}"
            errors.extend(text_errors(label, norm(spec.get("description")), MIN_DESC))
            if not isinstance(spec.get("raw"), dict) or not spec.get("raw"):
                errors.append(f"{label}: missing raw YAML")
            if not isinstance(spec.get("details"), dict):
                errors.append(f"{label}: missing details map")
            if not isinstance(spec.get("source_ref"), dict):
                errors.append(f"{label}: missing source_ref")
    return errors, registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("blueprint", nargs="?", default="inputs/BLUEPRINT.md")
    args = parser.parse_args(argv)
    path = Path(args.blueprint)
    if not path.is_absolute():
        path = project_root() / path
    errors: list[str] = []
    try:
        compiled, report = compile_blueprint(path)
    except Exception as exc:
        print(json.dumps({"ok": False, "blueprint": str(path), "errors": [str(exc)], "warnings": []}, indent=2, ensure_ascii=False))
        return 2
    errors.extend(validate_compiled(compiled))
    projection_errors, registry = validate_registry_projection(compiled)
    errors.extend(projection_errors)
    result = {
        "ok": not errors,
        "blueprint": str(path.relative_to(project_root()) if path.is_relative_to(project_root()) else path),
        "slices": len(compiled.get("slices") or []),
        "registry_tasks": len(registry.get("tasks") or []),
        "dag_edges": (registry.get("task_dag") or {}).get("edge_count"),
        "logic_counts": {k: len(v or []) for k, v in (compiled.get("logic") or {}).items()},
        "auxiliary_counts": {k: len(v or []) for k, v in (compiled.get("auxiliary") or {}).items()},
        "errors": sorted(set(errors)),
        "warnings": report.get("warnings", []),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
