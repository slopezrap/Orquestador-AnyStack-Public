from __future__ import annotations
import argparse, hashlib, json, re, sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from orchestrator.common import write_json
from orchestrator.runtime.blueprint_lossless import create_lossless_context, enrich_orchestrator_input, mirror_lossless_to_memory

import yaml

ID_PREFIXES = "ARC|PRJ|BB|DR|DI|UC|ALG|J|PG|PERM|SM|ERR|INT|SCR|VIEW|EVT|DATA|VER|ADR|AD|RISK|CFG|EXT|SLICE|API|WORKER|FU|REP|HANDOFF"
ID_RE = re.compile(rf"\b(?:{ID_PREFIXES})-[A-Za-z0-9_.:-]+\b")
FENCE_RE = re.compile(r"```(?:yaml\s+orchestrator|orchestrator)\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
MIN_SLICE_DESCRIPTION_CHARS = 240
MIN_SPEC_DESCRIPTION_CHARS = 240
MIN_DEPENDENCY_RATIONALE_CHARS = 180
REQUIRED_DETAIL_HINTS = {"must", "debe", "verifica", "bloquea", "produce", "integra", "persiste", "evidencia", "runtime", "operator", "operador", "real", "production", "productivo"}
FORBIDDEN_HUMAN_TEXT_PATTERNS = [
    (re.compile(r"\b(?:TODO|TBD|FIXME)\b|(?i:\b(?:lorem\s+ipsum|placeholder|monkey|foo|bar|baz)\b)|\bXXX\b"), "placeholder_or_open_work"),
    (re.compile(r"\b(?:dummy|fake|stubbed|stub\s+implementation|runtime\s+stub|temporary\s+implementation|fake\s+data|mock\s+data|sample\s+data|seed\s+data|hardcoded\s+demo)\b", re.IGNORECASE), "non_production_wording"),
    (re.compile(r"\bNotImplementedError\b|^\s*pass\s*(?:#.*)?$", re.IGNORECASE | re.MULTILINE), "unfinished_runtime_marker"),
    (re.compile(r"This\s+dependency\s+rationale\s+is\s+part\s+of\s+the(?:\s+production)?\s+DAG\s+contract", re.IGNORECASE), "boilerplate_dependency_rationale"),
    (re.compile(r"\bis\s+resolved\s+into\b", re.IGNORECASE), "generic_contract_projection_boilerplate"),
    (re.compile(r"It carries arc42 intent into resolved_specs|without reinterpreting prose or falling back to secondary documents", re.IGNORECASE), "generic_arc42_projection_boilerplate"),
]
LOGIC_KEYS = ["domain","application","algorithms","journey","permission","state","error","integration","ui"]
AUX_KEYS = ["arc42","data","config","verification","adr","risks","glossary","external_refs","waivers","manual_decisions"]
REQUIRED_LOGIC_KEYS = ["domain", "application", "journey", "permission", "state", "error", "integration", "ui"]
REQUIRED_AUX_KEYS = ["arc42", "data", "config", "verification", "adr", "risks", "glossary", "external_refs"]

class CompileError(Exception):
    pass


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def stable_unique(values: list[Any]) -> list[str]:
    """Return non-empty string values in first-seen order.

    Scope lists are human-authored contracts, so explicit blueprint order must
    not be lost by set/sort normalization. Overrides are appended after the
    authoritative/fallback scope and deduplicated without reordering.
    """
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def item_id(item: dict[str, Any]) -> str | None:
    raw = item.get("id")
    return str(raw).strip() if raw not in (None, "") else None


def source_line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def normalize_kind(kind: str) -> str:
    return str(kind or "").strip().lower().replace("_", ".")


def init_output(blueprint_path: Path, text: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "compiler": {
            "name": "blueprint-compiler",
            "mode": "lossless-by-reference",
            "blueprint_path": str(blueprint_path),
            "blueprint_sha256": sha256_text(text),
        },
        "project": {},
        "stack": {},
        "building_blocks": [],
        "logic": {k: [] for k in LOGIC_KEYS},
        "auxiliary": {k: [] for k in AUX_KEYS},
        "slices": [],
        "derived": {"dependency_graph": {}, "write_sets": {}, "conflict_groups": {}, "coverage": {}, "compile_decisions": []},
        "source_map": {},
    }


def append_items(out: dict[str, Any], kind: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    # Human-friendly aliases. Canonical machine kinds are auxiliary.*.
    alias = {"data":"auxiliary.data", "verification":"auxiliary.verification", "config":"auxiliary.config", "external.refs":"auxiliary.external_refs", "external_refs":"auxiliary.external_refs", "adr":"auxiliary.adr", "risks":"auxiliary.risks", "glossary":"auxiliary.glossary", "waivers":"auxiliary.waivers", "manual.decisions":"auxiliary.manual_decisions", "manual_decisions":"auxiliary.manual_decisions", "arc42":"auxiliary.arc42"}.get(kind)
    if alias:
        kind = alias
    if kind == "auxiliary.external.refs":
        kind = "auxiliary.external_refs"
    if kind == "auxiliary.manual.decisions":
        kind = "auxiliary.manual_decisions"
    items = data.get("items")
    if items is None:
        # Support a single object under the terminal kind key.
        terminal = kind.split(".")[-1]
        if terminal in data and isinstance(data[terminal], list):
            items = data[terminal]
        elif terminal in data and isinstance(data[terminal], dict):
            items = [data[terminal]]
        else:
            items = []
    if not isinstance(items, list):
        raise CompileError(f"kind={kind}: items must be a list")
    if kind == "building.blocks":
        kind = "building_blocks"
    if kind == "building_blocks":
        out["building_blocks"].extend(items)
    elif kind.startswith("logic."):
        key = kind.split(".", 1)[1]
        if key not in out["logic"]:
            raise CompileError(f"unsupported logic kind {kind}")
        out["logic"][key].extend(items)
    elif kind.startswith("auxiliary."):
        key = kind.split(".", 1)[1]
        if key not in out["auxiliary"]:
            out["auxiliary"][key] = []
        out["auxiliary"][key].extend(items)
    elif kind == "registry.slices":
        out["slices"].extend(items)
    else:
        raise CompileError(f"unsupported list kind {kind}")
    return [i for i in items if isinstance(i, dict)]


def extract_blocks(blueprint_path: Path, text: str) -> tuple[dict[str, Any], list[str]]:
    out = init_output(blueprint_path, text)
    warnings: list[str] = []
    blocks = list(FENCE_RE.finditer(text))
    if not blocks:
        raise CompileError("No ```yaml orchestrator blocks found. Prose is not compiled.")
    for idx, match in enumerate(blocks, start=1):
        raw = match.group(1)
        try:
            data = yaml.safe_load(raw) or {}
        except Exception as exc:
            raise CompileError(f"YAML error in block {idx} at line {source_line(text, match.start())}: {exc}") from exc
        if not isinstance(data, dict):
            raise CompileError(f"Block {idx} must be a YAML mapping")
        kind = normalize_kind(data.get("kind"))
        if not kind:
            raise CompileError(f"Block {idx} missing kind")
        line = source_line(text, match.start())
        if kind == "project":
            project = data.get("project") or {k:v for k,v in data.items() if k != "kind"}
            if not isinstance(project, dict):
                raise CompileError("project block must contain mapping")
            out["project"].update(project)
            pid = project.get("id")
            if pid:
                out["source_map"][str(pid)] = {"file": str(blueprint_path), "line": line, "kind": kind, "block_index": idx}
        elif kind == "stack":
            stack = data.get("stack") or {k:v for k,v in data.items() if k != "kind"}
            if not isinstance(stack, dict):
                raise CompileError("stack block must contain mapping")
            out["stack"].update(stack)
            sid = stack.get("id")
            if sid:
                out["source_map"][str(sid)] = {"file": str(blueprint_path), "line": line, "kind": kind, "block_index": idx}
        else:
            items = append_items(out, kind, data)
            for item in items:
                iid = item_id(item)
                if iid:
                    out["source_map"][iid] = {"file": str(blueprint_path), "line": line, "kind": kind, "block_index": idx}
                    for alias in as_list(item.get("aliases")):
                        if alias:
                            out["source_map"][str(alias)] = {"file": str(blueprint_path), "line": line, "kind": kind, "block_index": idx, "alias_for": iid}
    return out, warnings


def all_items(out: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    pairs=[]
    if out.get("project"):
        pairs.append(("project", out["project"]))
    if out.get("stack"):
        pairs.append(("stack", out["stack"]))
    for item in out.get("building_blocks", []) or []:
        pairs.append(("building_blocks", item))
    for k, items in (out.get("logic") or {}).items():
        for item in items or []:
            pairs.append((f"logic.{k}", item))
    for k, items in (out.get("auxiliary") or {}).items():
        for item in items or []:
            pairs.append((f"auxiliary.{k}", item))
    for item in out.get("slices", []) or []:
        pairs.append(("registry.slices", item))
    return pairs


def build_symbols(out: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str]]:
    symbols: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    errors=[]
    for kind, item in all_items(out):
        iid = item_id(item)
        if not iid:
            if kind not in {"stack"}:
                errors.append(f"{kind}: item missing id")
            continue
        if iid in symbols:
            errors.append(f"duplicate id {iid}")
        symbols[iid] = {"kind": kind, "item": item}
        for alias in as_list(item.get("aliases")):
            alias=str(alias).strip()
            if not alias:
                continue
            if alias in symbols or alias in aliases:
                errors.append(f"duplicate alias {alias}")
            aliases[alias] = iid
    return symbols, aliases, errors


def canonical(ref: str, symbols: dict[str, Any], aliases: dict[str, str]) -> str:
    return aliases.get(ref, ref)


def iter_id_refs(value: Any) -> list[str]:
    refs=[]
    if isinstance(value, str):
        refs.extend(ID_RE.findall(value))
    elif isinstance(value, list):
        for x in value:
            refs.extend(iter_id_refs(x))
    elif isinstance(value, dict):
        for x in value.values():
            refs.extend(iter_id_refs(x))
    return refs


def validate_refs(out: dict[str, Any], symbols: dict[str, Any], aliases: dict[str, str]) -> list[str]:
    errors=[]
    known=set(symbols)|set(aliases)
    ignored_prefixes=("PRJ-",)  # project IDs can be used in text without item refs
    for kind,item in all_items(out):
        iid=item_id(item) or f"<{kind}>"
        for ref in iter_id_refs(item):
            if ref == iid or ref in as_list(item.get("aliases")):
                continue
            if ref.startswith(ignored_prefixes):
                continue
            if ref not in known:
                errors.append(f"{iid} references unknown id {ref}")
    return sorted(set(errors))


def detect_prose_id_warnings(text: str, symbols: dict[str, Any], aliases: dict[str,str]) -> list[str]:
    known=set(symbols)|set(aliases)
    warnings=[]
    for ref in sorted(set(ID_RE.findall(text))):
        # Ignore placeholder/range notation in human prose: UC-x, SM-x, AD-11..17, UC-10-11.
        low = ref.lower()
        if low.endswith("-x") or ".." in ref or re.match(r"^[A-Z]+-[0-9]+-[0-9]+$", ref):
            continue
        if ref not in known:
            warnings.append(f"prose mentions {ref} but no YAML item/alias declares it")
    return warnings[:200]


def bb_paths(bb: dict[str, Any]) -> list[str]:
    paths=[]
    for key in ("path","paths"):
        v=bb.get(key)
        if isinstance(v, str):
            paths.append(v)
        elif isinstance(v, list):
            paths.extend(str(x) for x in v if str(x).strip())
    return paths


def normalize_human_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def validate_slice_human_fields(slice_id: str, title: str, description: str, dependency_rationale: str = "", depends_on: list[str] | None = None, depends_on_rationale: dict[str, str] | None = None) -> list[str]:
    errors: list[str] = []
    if not title:
        errors.append(f"{slice_id}: slice must declare title")
    if not description:
        errors.append(f"{slice_id}: slice must declare description")
    elif len(description) < MIN_SLICE_DESCRIPTION_CHARS:
        errors.append(f"{slice_id}: description must be at least {MIN_SLICE_DESCRIPTION_CHARS} characters and explain the human task scope")
    elif description.strip().lower() == title.strip().lower():
        errors.append(f"{slice_id}: description must add detail beyond title")
    if not dependency_rationale:
        errors.append(f"{slice_id}: slice must declare dependency_rationale")
    elif len(dependency_rationale) < MIN_DEPENDENCY_RATIONALE_CHARS:
        errors.append(f"{slice_id}: dependency_rationale must be at least {MIN_DEPENDENCY_RATIONALE_CHARS} characters")
    deps = [str(x) for x in (depends_on or []) if str(x).strip()]
    dep_map = depends_on_rationale or {}
    if deps:
        if not isinstance(dep_map, dict):
            errors.append(f"{slice_id}: depends_on_rationale must be a mapping of dependency slice id to human rationale")
        else:
            for dep in deps:
                reason = normalize_human_text(dep_map.get(dep))
                if not reason:
                    errors.append(f"{slice_id}: missing depends_on_rationale for dependency {dep}")
                elif len(reason) < MIN_DEPENDENCY_RATIONALE_CHARS:
                    errors.append(f"{slice_id}: depends_on_rationale[{dep}] must be at least {MIN_DEPENDENCY_RATIONALE_CHARS} characters")
            extra = sorted(set(str(k) for k in dep_map) - set(deps))
            if extra:
                errors.append(f"{slice_id}: depends_on_rationale has keys not present in depends_on: {', '.join(extra)}")
    elif isinstance(dep_map, dict) and dep_map:
        errors.append(f"{slice_id}: depends_on_rationale must be empty when depends_on is empty")
    for field_name, text in (("title", title), ("description", description), ("dependency_rationale", dependency_rationale)):
        for pattern, reason in FORBIDDEN_HUMAN_TEXT_PATTERNS:
            if pattern.search(text or ""):
                errors.append(f"{slice_id}: {field_name} contains {reason}; task text must be production-ready and not placeholder/mock/stub wording")
    if isinstance(dep_map, dict):
        for dep, text in dep_map.items():
            for pattern, reason in FORBIDDEN_HUMAN_TEXT_PATTERNS:
                if pattern.search(text or ""):
                    errors.append(f"{slice_id}: depends_on_rationale[{dep}] contains {reason}; dependency text must be production-ready")
    return errors






def _description_quality_errors(iid: str, kind: str, desc: str, min_chars: int) -> list[str]:
    errors: list[str] = []
    if not desc:
        errors.append(f"{iid}: {kind} must declare a detailed description")
        return errors
    if len(desc) < min_chars:
        errors.append(f"{iid}: {kind} description must be at least {min_chars} characters")
    # A detailed machine description should carry a verb/constraint/evidence cue,
    # not just a noun phrase copied from the title.  This remains language-light
    # and intentionally avoids NLP dependencies.
    lowered = desc.lower()
    if len(desc.split()) < 12:
        errors.append(f"{iid}: {kind} description must be sentence-level human scope, not a label")
    return errors


def validate_machine_descriptions(out: dict[str, Any]) -> list[str]:
    """Require every machine contract item to carry human-readable detail.

    Slices are checked separately with a longer threshold.  All other blueprint
    items still need enough description for a subagent task pack to stand alone
    without forcing the LLM to infer product intent from prose or IDs.
    """
    errors: list[str] = []
    for kind, item in all_items(out):
        iid = item_id(item) or kind
        if kind == "registry.slices":
            continue
        if kind == "stack" and not item.get("id"):
            # stack has no mandatory requirement for id, but this project declares one.
            iid = str(item.get("id") or "stack")
        desc = normalize_human_text(item.get("description") or item.get("summary"))
        errors.extend(_description_quality_errors(iid, kind, desc, MIN_SPEC_DESCRIPTION_CHARS))
        title = normalize_human_text(item.get("title") or item.get("name") or item.get("id"))
        for field_name, text in (("title/name", title), ("description", desc)):
            for pattern, reason in FORBIDDEN_HUMAN_TEXT_PATTERNS:
                if pattern.search(text or ""):
                    errors.append(f"{iid}: {field_name} contains {reason}; blueprint machine text must be production-ready")
    return errors


def validate_blueprint_completeness(out: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not out.get("project"):
        errors.append("missing project block")
    if not out.get("stack"):
        errors.append("missing stack block")
    if not out.get("building_blocks"):
        errors.append("missing building_blocks block; write_set/conflict_group derivation needs canonical locations")
    for key in REQUIRED_LOGIC_KEYS:
        if not (out.get("logic") or {}).get(key):
            errors.append(f"missing logic.{key} block; blueprint must cover all orchestrator logic dimensions")
    for key in REQUIRED_AUX_KEYS:
        if not (out.get("auxiliary") or {}).get(key):
            errors.append(f"missing auxiliary.{key} block; every slice must have a verification contract")
    if not out.get("slices"):
        errors.append("missing registry.slices block")
    return errors


def slice_ref_text(sl: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("implements", "builds", "verifies", "closes_journeys", "depends_on"):
        for value in as_list(sl.get(key)):
            if value:
                refs.add(str(value))
    return refs

def derive(out: dict[str, Any], symbols: dict[str, Any], aliases: dict[str, str]) -> list[str]:
    errors=[]
    bb_by_id={item["id"]: item for item in out.get("building_blocks", []) if isinstance(item, dict) and item.get("id")}
    impl_to_slices: dict[str, list[str]] = defaultdict(list)
    slice_ids={str(s.get("id")) for s in out.get("slices", []) if s.get("id")}

    # Map explicit implementations/builds.
    for sl in out.get("slices", []) or []:
        sid=str(sl.get("id") or "").strip()
        if not sid:
            errors.append("slice missing id")
            continue
        for ref in as_list(sl.get("implements")) + as_list(sl.get("builds")):
            if ref:
                impl_to_slices[canonical(str(ref), symbols, aliases)].append(sid)

    dep_graph={}
    write_sets={}
    conflict_groups={}
    coverage={}

    for sl in out.get("slices", []) or []:
        sid=str(sl.get("id") or "").strip()
        if not sid:
            continue
        title = normalize_human_text(sl.get("title") or sl.get("name") or sid)
        description = normalize_human_text(sl.get("description"))
        dependency_rationale = normalize_human_text(sl.get("dependency_rationale"))
        raw_dep_map = sl.get("depends_on_rationale") or {}
        if not isinstance(raw_dep_map, dict):
            dep_map: dict[str, str] = {}
        else:
            dep_map = {str(k): normalize_human_text(v) for k, v in raw_dep_map.items()}
        sl["title"] = title
        sl["description"] = description
        sl["dependency_rationale"] = dependency_rationale
        if not (as_list(sl.get("implements")) or as_list(sl.get("builds"))):
            errors.append(f"{sid}: slice must declare implements or builds")
        if not as_list(sl.get("verifies")) and not as_list(sl.get("verification")):
            errors.append(f"{sid}: slice must declare verifies")
        if not as_list(sl.get("arc42_refs")):
            errors.append(f"{sid}: slice must declare arc42_refs so task packs carry arc42 context")

        # Dependency resolution.
        deps=[]
        for dep in as_list(sl.get("depends_on")) + as_list(sl.get("depends")):
            dep=str(dep).strip()
            if not dep:
                continue
            cdep=canonical(dep, symbols, aliases)
            if cdep in slice_ids:
                deps.append(cdep)
            elif cdep in impl_to_slices:
                deps.extend(x for x in impl_to_slices[cdep] if x != sid)
            else:
                errors.append(f"{sid}: depends_on unknown slice or implemented id {dep}")
        deps=sorted(set(deps))
        sl["depends_on"] = deps
        dep_map = {dep: dep_map.get(dep, "") for dep in deps}
        sl["depends_on_rationale"] = dep_map
        sl["dependency_edges"] = [{"from": dep, "to": sid, "reason": dep_map.get(dep, "")} for dep in deps]
        errors.extend(validate_slice_human_fields(sid, title, description, dependency_rationale, deps, dep_map))
        dep_graph[sid] = deps

        # Location derivation: from explicit builds and from implemented item locations.
        bbs=[]
        for ref in as_list(sl.get("builds")):
            cref=canonical(str(ref), symbols, aliases)
            if cref in bb_by_id:
                bbs.append(cref)
        for ref in as_list(sl.get("implements")):
            cref=canonical(str(ref), symbols, aliases)
            spec=symbols.get(cref)
            item=(spec or {}).get("item") or {}
            loc=item.get("location") or item.get("building_block") or item.get("owner")
            if isinstance(loc, str) and canonical(loc, symbols, aliases) in bb_by_id:
                bbs.append(canonical(loc, symbols, aliases))
        bbs=sorted(set(bbs))
        derived_ws: list[Any] = []
        derived_cg: list[Any] = []
        for bbid in bbs:
            bb=bb_by_id[bbid]
            derived_ws.extend(bb_paths(bb))
            derived_ws.extend(as_list(bb.get("write_surface")))
            derived_cg.extend(as_list(bb.get("conflict_group")))
            if not bb.get("conflict_group"):
                derived_cg.extend(as_list(bb.get("write_surface")))

        # Author-declared slice scope is authoritative. Building-block scope is
        # only a fallback for older/minimal blueprints that omit explicit scope.
        # *_override remains append-only for backwards compatibility.
        authored_ws = as_list(sl.get("write_set"))
        authored_cg = as_list(sl.get("conflict_groups")) or as_list(sl.get("conflict_group"))
        ws_source = authored_ws if authored_ws else derived_ws
        cg_source = authored_cg if authored_cg else derived_cg
        ws = stable_unique(ws_source + as_list(sl.get("write_set_override")))
        cg = stable_unique(cg_source + as_list(sl.get("conflict_group_override")))
        sl["write_set"] = ws
        sl["conflict_group"] = cg
        sl["conflict_groups"] = cg
        sl["building_block_refs"] = bbs
        write_sets[sid]=ws
        conflict_groups[sid]=cg
        coverage[sid]={"implements":[canonical(str(x), symbols, aliases) for x in as_list(sl.get("implements"))], "builds": bbs, "verifies":[canonical(str(x), symbols, aliases) for x in as_list(sl.get("verifies"))]}
        if not ws:
            errors.append(f"{sid}: write_set missing and could not be derived; add explicit write_set or builds/location pointing to building_blocks")

    out["derived"]["dependency_graph"] = dep_graph
    out["derived"]["write_sets"] = write_sets
    out["derived"]["conflict_groups"] = conflict_groups
    out["derived"]["coverage"] = coverage
    out["derived"]["compile_decisions"].append("slice-authored write_set/conflict_groups are authoritative; building-block scope is fallback; *_override fields append")

    # Cycle detection
    visiting=set(); visited=set(); stack=[]
    def dfs(n):
        if n in visiting:
            i=stack.index(n) if n in stack else 0
            errors.append("cycle in slice DAG: " + " -> ".join(stack[i:]+[n]))
            return
        if n in visited:
            return
        visiting.add(n); stack.append(n)
        for m in dep_graph.get(n, []):
            dfs(m)
        stack.pop(); visiting.remove(n); visited.add(n)
    for sid in dep_graph:
        dfs(sid)
    return sorted(set(errors))


def compile_blueprint(blueprint_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    text = blueprint_path.read_text(encoding="utf-8")
    out, warnings = extract_blocks(blueprint_path, text)
    symbols, aliases, errors = build_symbols(out)
    errors += validate_blueprint_completeness(out)
    errors += validate_machine_descriptions(out)
    errors += validate_refs(out, symbols, aliases)
    errors += derive(out, symbols, aliases)
    warnings += detect_prose_id_warnings(text, symbols, aliases)
    report={
        "ok": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "block_count": len(FENCE_RE.findall(text)),
        "symbol_count": len(symbols),
        "alias_count": len(aliases),
        "slice_count": len(out.get("slices", [])),
        "blueprint_sha256": out["compiler"]["blueprint_sha256"],
    }
    if errors:
        raise CompileError(json.dumps(report, ensure_ascii=False, indent=2))
    out["compiler"]["symbol_count"] = len(symbols)
    out["compiler"]["alias_count"] = len(aliases)
    return out, report


def write_report(path: Path, report: dict[str, Any]) -> None:
    lines=["# Compile report", "", f"ok: `{report.get('ok')}`", f"blocks: `{report.get('block_count')}`", f"symbols: `{report.get('symbol_count')}`", f"aliases: `{report.get('alias_count')}`", f"slices: `{report.get('slice_count')}`", ""]
    if report.get("errors"):
        lines.append("## Errors")
        lines.extend(f"- {e}" for e in report["errors"])
    if report.get("warnings"):
        lines.append("## Warnings")
        lines.extend(f"- {w}" for w in report["warnings"][:200])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines)+"\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("blueprint", nargs="?", default="inputs/BLUEPRINT.md")
    p.add_argument("--out", default="orchestrator-state/compiled/orchestrator-input.json")
    p.add_argument("--source-map", default="orchestrator-state/compiled/source-map.json")
    p.add_argument("--lock", default="orchestrator-state/compiled/orchestrator-input.lock.json")
    p.add_argument("--report", default="orchestrator-state/compiled/compile-report.md")
    args=p.parse_args(argv)
    blueprint=Path(args.blueprint)
    try:
        out, report = compile_blueprint(blueprint)
    except CompileError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    manifest = create_lossless_context(blueprint)
    out = enrich_orchestrator_input(out, manifest)
    mirror_lossless_to_memory()
    out_path=Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, out)
    sm_path=Path(args.source_map); sm_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(sm_path, out.get("source_map", {}))
    lock={"schema_version":out["schema_version"], "compiler_mode":out["compiler"].get("mode", "lossless-by-reference"), "blueprint_sha256":out["compiler"]["blueprint_sha256"], "symbol_count":report["symbol_count"], "block_count":report["block_count"], "errors":0, "warnings":len(report.get("warnings") or [])}
    write_json(Path(args.lock), lock)
    write_report(Path(args.report), report)
    print(json.dumps({"ok": True, "out": str(out_path), "slices": report["slice_count"], "warnings": len(report.get("warnings") or [])}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
