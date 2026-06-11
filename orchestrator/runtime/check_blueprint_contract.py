from __future__ import annotations
import json, re, time
from pathlib import Path
from typing import Any
from orchestrator.common import compiled_dir, project_root, tasks_dir

MIN_DESCRIPTION_CHARS = 240
MIN_DEPENDENCY_RATIONALE_CHARS = 180
REQUIRED_LOGIC = ["domain","application","journey","permission","state","error","integration","ui"]
REQUIRED_AUX = ["arc42","data","config","verification","adr","risks","glossary","external_refs"]
FORBIDDEN = re.compile(r"(?i)\b(TODO|TBD|FIXME|XXX|placeholder|dummy|monkey|lorem ipsum|fake data|mock data|sample data|seed data|stubbed|stub implementation|runtime stub|NotImplementedError)\b")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def load_json_retry(path: Path, default: dict[str, Any] | None = None, attempts: int = 20, delay: float = 0.05) -> dict[str, Any]:
    default = {} if default is None else default
    for _ in range(attempts):
        try:
            if path.exists() and path.stat().st_size > 0:
                return load_json(path)
        except Exception:
            pass
        time.sleep(delay)
    return default

def as_list(v: Any) -> list[Any]:
    if v is None: return []
    return v if isinstance(v, list) else [v]

def norm(v: Any) -> str:
    return " ".join(str(v or "").split())

def check_text(errors: list[str], label: str, value: Any, minimum: int) -> None:
    text = norm(value)
    if not text:
        errors.append(f"{label}: missing description")
    elif len(text) < minimum:
        errors.append(f"{label}: description shorter than {minimum} characters")
    if text and FORBIDDEN.search(text):
        errors.append(f"{label}: contains non-production wording")

def item_pairs(inp: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(inp.get("project"), dict): out.append(("project", inp["project"]))
    if isinstance(inp.get("stack"), dict): out.append(("stack", inp["stack"]))
    for item in inp.get("building_blocks") or []:
        if isinstance(item, dict): out.append(("building_blocks", item))
    for kind, items in (inp.get("logic") or {}).items():
        for item in items or []:
            if isinstance(item, dict): out.append((f"logic.{kind}", item))
    for kind, items in (inp.get("auxiliary") or {}).items():
        for item in items or []:
            if isinstance(item, dict): out.append((f"auxiliary.{kind}", item))
    return out

def check() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    inp = load_json_retry(compiled_dir() / "orchestrator-input.json")
    reg = load_json_retry(tasks_dir() / "registry.json", {"tasks": []})
    dag = load_json_retry(tasks_dir() / "task-dag.json", {"nodes": []})
    logic = inp.get("logic") or {}; aux = inp.get("auxiliary") or {}
    for key in REQUIRED_LOGIC:
        if not logic.get(key): errors.append(f"missing logic.{key}")
    for key in REQUIRED_AUX:
        if not aux.get(key): errors.append(f"missing auxiliary.{key}")
    known = {str(item.get("id")) for _, item in item_pairs(inp) if item.get("id")}
    known.update(str(sl.get("id")) for sl in inp.get("slices") or [] if isinstance(sl, dict) and sl.get("id"))
    for kind, item in item_pairs(inp):
        iid = str(item.get("id") or kind)
        check_text(errors, f"{kind}.{iid}", item.get("description") or item.get("summary"), MIN_DESCRIPTION_CHARS)
    tasks = {str(t.get("id")): t for t in reg.get("tasks") or [] if isinstance(t, dict)}
    nodes = {str(n.get("id")): n for n in dag.get("nodes") or [] if isinstance(n, dict)}
    for sl in inp.get("slices") or []:
        if not isinstance(sl, dict): continue
        sid = str(sl.get("id"))
        check_text(errors, f"slice.{sid}", sl.get("description"), MIN_DESCRIPTION_CHARS)
        check_text(errors, f"slice.{sid}.dependency_rationale", sl.get("dependency_rationale"), MIN_DEPENDENCY_RATIONALE_CHARS)
        for key in ["implements","builds","verifies","arc42_refs"]:
            if not as_list(sl.get(key)): errors.append(f"{sid}: missing {key}")
        for key in ["implements","builds","verifies","closes_journeys","arc42_refs"]:
            for ref in as_list(sl.get(key)):
                if str(ref) not in known: errors.append(f"{sid}: unknown {key} ref {ref}")
        task = tasks.get(sid)
        if not task:
            errors.append(f"{sid}: missing registry task")
            continue
        for field in ["title","description","dependency_rationale","arc42_refs"]:
            if task.get(field) != sl.get(field): errors.append(f"{sid}: registry {field} drift")
        expected = {str(x) for k in ["implements","builds","verifies","closes_journeys","arc42_refs"] for x in as_list(sl.get(k)) if str(x) in known}
        resolved = {str(spec.get("id")) for spec in task.get("resolved_specs") or [] if isinstance(spec, dict)}
        if expected - resolved: errors.append(f"{sid}: missing resolved_specs {sorted(expected-resolved)}")
        if not any(spec.get("kind") == "auxiliary.arc42" for spec in task.get("resolved_specs") or [] if isinstance(spec, dict)):
            errors.append(f"{sid}: missing auxiliary.arc42 resolved spec")
        for spec in task.get("resolved_specs") or []:
            if isinstance(spec, dict): check_text(errors, f"{sid}.resolved_specs.{spec.get('id')}", spec.get("description"), MIN_DESCRIPTION_CHARS)
        node = nodes.get(sid)
        if node:
            for field in ["title","description","dependency_rationale","arc42_refs"]:
                if node.get(field) != task.get(field): errors.append(f"{sid}: DAG {field} drift")
        pack_md = tasks_dir() / "task-packs" / f"{sid}.md"
        if pack_md.exists():
            text = pack_md.read_text(encoding="utf-8", errors="replace")
            for phrase in ["## Human task description","## Dependency rationale","## Resolved blueprint specs","## Arc42 refs","Arc42 refs:","## Handoff contract","AGENT: developer","AGENT: tester","AGENT: slice-verifier","AGENT: closer"]:
                if phrase not in text: errors.append(f"{sid}: task-pack missing {phrase}")
        else:
            warnings.append(f"{sid}: task-pack Markdown not generated yet")
    return {"ok": not errors, "logic_counts": {k: len(logic.get(k) or []) for k in REQUIRED_LOGIC}, "auxiliary_counts": {k: len(aux.get(k) or []) for k in REQUIRED_AUX}, "slices": len(inp.get("slices") or []), "registry_tasks": len(reg.get("tasks") or []), "errors": errors, "warnings": warnings}

def main() -> int:
    out = check()
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if out["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
