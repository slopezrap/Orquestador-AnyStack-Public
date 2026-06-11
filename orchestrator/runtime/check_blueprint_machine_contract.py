from __future__ import annotations

import json
import hashlib
import re
import time

import yaml
from pathlib import Path
from typing import Any

from orchestrator.common import compiled_dir, project_root, read_json, tasks_dir

REQUIRED_KINDS = {
    "project": ["project"],
    "stack": ["stack"],
    "building_blocks": ["building_blocks"],
    "logic.domain": ["logic", "domain"],
    "logic.application": ["logic", "application"],
    "logic.journey": ["logic", "journey"],
    "logic.permission": ["logic", "permission"],
    "logic.state": ["logic", "state"],
    "logic.error": ["logic", "error"],
    "logic.integration": ["logic", "integration"],
    "logic.ui": ["logic", "ui"],
    "auxiliary.arc42": ["auxiliary", "arc42"],
    "auxiliary.data": ["auxiliary", "data"],
    "auxiliary.config": ["auxiliary", "config"],
    "auxiliary.verification": ["auxiliary", "verification"],
    "auxiliary.adr": ["auxiliary", "adr"],
    "auxiliary.risks": ["auxiliary", "risks"],
    "auxiliary.glossary": ["auxiliary", "glossary"],
    "auxiliary.external_refs": ["auxiliary", "external_refs"],
    "registry.slices": ["slices"],
}
MIN_ITEM_DESC = 240
MIN_SLICE_DESC = 240
FORBIDDEN = [
    re.compile(r"\bis\s+resolved\s+into\b", re.IGNORECASE),
    re.compile(r"\b(?:TODO|TBD|FIXME|XXX)\b|(?i:\b(?:lorem\s+ipsum|placeholder|monkey|foo|bar|baz)\b)"),
    re.compile(r"\b(?:dummy|fake|stubbed|stub\s+implementation|runtime\s+stub|temporary\s+implementation|fake\s+data|mock\s+data|sample\s+data|seed\s+data|hardcoded\s+demo)\b", re.I),
    re.compile(r"\bNotImplementedError\b|^\s*pass\s*(?:#.*)?$", re.I | re.M),
    re.compile(r"This\s+dependency\s+rationale\s+is\s+part\s+of\s+the(?:\s+production)?\s+DAG\s+contract", re.I),
    re.compile(r"It carries arc42 intent into resolved_specs|without reinterpreting prose or falling back to secondary documents", re.I),
    re.compile(r"This\s+(?:state|error|integration|UI|data|verification|ADR|risk|glossary|external reference|configuration|config|arc42|building block|domain|application|journey|permission)\s+contract\s+is\s+resolved\s+into", re.I),
]



def read_json_retry(path: Path, default: dict[str, Any] | None = None, attempts: int = 20, delay: float = 0.05) -> dict[str, Any]:
    default = {} if default is None else default
    last: Exception | None = None
    for _ in range(attempts):
        try:
            if path.exists() and path.stat().st_size > 0:
                return read_json(path, default)
        except Exception as exc:  # transient file visibility/truncation on fast CI filesystems
            last = exc
        time.sleep(delay)
    return default

def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _get(data: dict[str, Any], trail: list[str]) -> Any:
    cur: Any = data
    for key in trail:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur



def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _authored_blueprint_slices(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "inputs" / "BLUEPRINT.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict[str, Any]] = {}
    for raw in re.findall(r"```(?:yaml\s+orchestrator|orchestrator)\s*\n(.*?)\n```", text, flags=re.I | re.S):
        try:
            block = yaml.safe_load(raw)
        except Exception:
            continue
        if not isinstance(block, dict) or block.get("kind") != "registry.slices":
            continue
        for sl in block.get("items") or []:
            if isinstance(sl, dict) and sl.get("id"):
                out[str(sl["id"])] = sl
    return out


def _strings(value: Any) -> list[str]:
    return [str(x) for x in _as_list(value)]


def _authored_list(sl: dict[str, Any], *keys: str) -> tuple[bool, list[str]]:
    for key in keys:
        if key in sl and sl.get(key) is not None:
            return True, _strings(sl.get(key))
    return False, []


def _projected_list(obj: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        if key in obj and obj.get(key) is not None:
            return _strings(obj.get(key))
    return []


def _items(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(data.get("project"), dict):
        out.append(("project", data["project"]))
    if isinstance(data.get("stack"), dict):
        out.append(("stack", data["stack"]))
    for item in data.get("building_blocks") or []:
        out.append(("building_blocks", item))
    for key, items in (data.get("logic") or {}).items():
        for item in items or []:
            out.append((f"logic.{key}", item))
    for key, items in (data.get("auxiliary") or {}).items():
        for item in items or []:
            out.append((f"auxiliary.{key}", item))
    for item in data.get("slices") or []:
        out.append(("registry.slices", item))
    return [(k, v) for k, v in out if isinstance(v, dict)]


def _text_errors(label: str, text: str, min_len: int) -> list[str]:
    errors: list[str] = []
    if not text:
        errors.append(f"{label}: missing description")
        return errors
    if len(text) < min_len:
        errors.append(f"{label}: description shorter than {min_len} characters")
    if len(text.split()) < 10:
        errors.append(f"{label}: description is too label-like; expected sentence-level human detail")
    for pat in FORBIDDEN:
        if pat.search(text):
            errors.append(f"{label}: description contains non-production or unfinished wording")
    return errors


def main() -> int:
    root = project_root()
    errors: list[str] = []
    warnings: list[str] = []
    inp = read_json_retry(compiled_dir() / "orchestrator-input.json", {})
    reg = read_json_retry(tasks_dir() / "registry.json", {})
    dag = read_json_retry(tasks_dir() / "task-dag.json", {})
    if not inp:
        errors.append("missing compiled orchestrator-input.json; run ./scripts/compile-blueprint.sh inputs/BLUEPRINT.md")
    else:
        root_blueprint = root / "inputs" / "BLUEPRINT.md"
        if root_blueprint.exists():
            expected_hash = hashlib.sha256(root_blueprint.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            compiled_hash = ((inp.get("compiler") or {}).get("blueprint_sha256"))
            if compiled_hash != expected_hash:
                errors.append("compiled orchestrator-input.json is not derived from the inputs/BLUEPRINT.md; rerun ./scripts/compile-blueprint.sh inputs/BLUEPRINT.md")
        for kind, trail in REQUIRED_KINDS.items():
            value = _get(inp, trail)
            if kind in {"project", "stack"}:
                if not isinstance(value, dict) or not value:
                    errors.append(f"missing {kind} block")
            else:
                if not isinstance(value, list) or not value:
                    errors.append(f"missing {kind} items")
        for kind, item in _items(inp):
            iid = str(item.get("id") or kind)
            desc = norm(item.get("description") or item.get("summary"))
            min_len = MIN_SLICE_DESC if kind == "registry.slices" else MIN_ITEM_DESC
            errors.extend(_text_errors(f"{iid} ({kind})", desc, min_len))
            if kind == "registry.slices":
                dr = norm(item.get("dependency_rationale"))
                if len(dr) < MIN_ITEM_DESC:
                    errors.append(f"{iid}: dependency_rationale missing or too short")
                if not (item.get("implements") or item.get("builds")):
                    errors.append(f"{iid}: slice must implement or build at least one ID")
                if not item.get("verifies"):
                    errors.append(f"{iid}: slice must declare verifies[]")
                if not item.get("arc42_refs"):
                    errors.append(f"{iid}: slice must declare arc42_refs[]")
    task_by_id = {str(t.get("id")): t for t in reg.get("tasks") or [] if isinstance(t, dict)}
    node_by_id = {str(n.get("id")): n for n in dag.get("nodes") or [] if isinstance(n, dict)}
    authored_slices = _authored_blueprint_slices(root)
    compiled_by_id = {str(sl.get("id")): sl for sl in inp.get("slices") or [] if isinstance(sl, dict)}
    for sid, authored in authored_slices.items():
        projections = [("compiled", compiled_by_id.get(sid) or {}), ("registry", task_by_id.get(sid) or {})]
        pack_path = tasks_dir() / "task-packs" / f"{sid}.json"
        if pack_path.exists():
            projections.append(("task-pack", read_json_retry(pack_path, {})))
        for field in ["write_set", "read_set", "journey_refs", "closes_journeys"]:
            present, expected = _authored_list(authored, field)
            if not present:
                continue
            for label, obj in projections:
                got = _projected_list(obj, field)
                if got != expected:
                    errors.append(f"{sid}: {label}.{field} drift from authored blueprint; expected {expected}, got {got}")
        present, expected = _authored_list(authored, "conflict_groups", "conflict_group")
        if present:
            for label, obj in projections:
                got = _projected_list(obj, "conflict_groups", "conflict_group")
                if got != expected:
                    errors.append(f"{sid}: {label}.conflict_groups drift from authored blueprint; expected {expected}, got {got}")
                locks = obj.get("locks") or {}
                if locks and _projected_list(locks, "conflict_groups") != expected:
                    errors.append(f"{sid}: {label}.locks.conflict_groups drift from authored blueprint")
        present, expected = _authored_list(authored, "write_set")
        if present:
            for label, obj in projections:
                locks = obj.get("locks") or {}
                if locks and _projected_list(locks, "write_set") != expected:
                    errors.append(f"{sid}: {label}.locks.write_set drift from authored blueprint")

    for sl in inp.get("slices") or []:
        sid = str(sl.get("id"))
        if not sid or sid == "None":
            continue
        for label, obj in [("registry", task_by_id.get(sid)), ("task-dag", node_by_id.get(sid))]:
            if not obj:
                errors.append(f"{sid}: missing {label} projection")
                continue
            for field in ["title", "description", "dependency_rationale", "arc42_refs"]:
                if norm(obj.get(field)) != norm(sl.get(field)):
                    errors.append(f"{sid}: {label}.{field} drift from compiled slice")
        task = task_by_id.get(sid) or {}
        resolved = task.get("resolved_specs") or []
        expected_refs = set(map(str, (sl.get("implements") or []) + (sl.get("builds") or []) + (sl.get("verifies") or []) + (sl.get("journey_refs") or []) + (sl.get("closes_journeys") or []) + (sl.get("arc42_refs") or [])))
        got_refs = {str(s.get("id")) for s in resolved if isinstance(s, dict)}
        missing = sorted(expected_refs - got_refs)
        if missing:
            errors.append(f"{sid}: resolved_specs missing refs {missing}")
        for spec in resolved:
            if not isinstance(spec, dict):
                continue
            label = f"{sid}:{spec.get('id')}"
            errors.extend(_text_errors(label, norm(spec.get("description")), MIN_ITEM_DESC))
            if not isinstance(spec.get("raw"), dict) or not spec.get("raw"):
                errors.append(f"{label}: missing raw YAML payload")
            if not isinstance(spec.get("details"), dict):
                errors.append(f"{label}: missing details payload")
            if not isinstance(spec.get("source_ref"), dict):
                errors.append(f"{label}: missing source_ref payload")
    result = {
        "ok": not errors,
        "required_kinds": sorted(REQUIRED_KINDS),
        "slices": len(inp.get("slices") or []),
        "registry_tasks": len(task_by_id),
        "dag_nodes": len(node_by_id),
        "errors": sorted(set(errors)),
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
