from __future__ import annotations
import argparse, json, time, copy, os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from orchestrator.common import ensure_dirs, now_iso, write_json, write_yaml, read_json, registry_path, runtime_state_path, tasks_dir, state_dir, task_conflict_reasons, load_registry, load_runtime_state
from orchestrator.runtime.blueprint_lossless import mirror_lossless_to_memory
from orchestrator.runtime.lifecycle_events import apply_lifecycle_events_to_registry, bootstrap_reset_guard_errors, lifecycle_event_statuses, refresh_registry_status_indexes
import re

MIN_TASK_DESCRIPTION_CHARS = 240
MIN_DEPENDENCY_RATIONALE_CHARS = 180
MIN_RESOLVED_DEPENDENCY_DESCRIPTION_CHARS = 240
FORBIDDEN_HUMAN_TEXT_PATTERNS = [
    (re.compile(r"\b(?:TODO|TBD|FIXME)\b|(?i:\b(?:lorem\s+ipsum|placeholder|monkey|foo|bar|baz)\b)|\bXXX\b"), "placeholder_or_open_work"),
    (re.compile(r"\b(?:dummy|fake|stubbed|stub\s+implementation|runtime\s+stub|temporary\s+implementation|fake\s+data|mock\s+data|sample\s+data|seed\s+data|hardcoded\s+demo)\b", re.IGNORECASE), "non_production_wording"),
    (re.compile(r"\bNotImplementedError\b|^\s*pass\s*(?:#.*)?$", re.IGNORECASE | re.MULTILINE), "unfinished_runtime_marker"),
    (re.compile(r"This\s+dependency\s+rationale\s+is\s+part\s+of\s+the(?:\s+production)?\s+DAG\s+contract", re.IGNORECASE), "boilerplate_dependency_rationale"),
    (re.compile(r"\bis\s+resolved\s+into\b", re.IGNORECASE), "generic_contract_projection_boilerplate"),
]


def read_compiled_input(path: Path) -> dict[str, Any]:
    # The compiler writes the input immediately before bootstrap in most workflows.
    # Use a short bounded retry to avoid transient empty/partial reads on filesystems
    # where the next process observes directory entries before contents are visible.
    for _ in range(10):
        data = read_json(path, {})
        if data:
            return data
        time.sleep(0.05)
    return {}


def phase_order_key(phase: str) -> tuple[int, str]:
    import re
    m = re.search(r"(\d+)", str(phase))
    return (int(m.group(1)) if m else 999, str(phase))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _human_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _validate_task_human_text(task_id: str, title: str, description: str, dependency_rationale: str) -> None:
    errors: list[str] = []
    if not title:
        errors.append("missing title")
    if not description:
        errors.append("missing description")
    elif len(description) < MIN_TASK_DESCRIPTION_CHARS:
        errors.append(f"description shorter than {MIN_TASK_DESCRIPTION_CHARS} characters")
    elif description.strip().lower() == title.strip().lower():
        errors.append("description duplicates title")
    if not dependency_rationale:
        errors.append("missing dependency_rationale")
    elif len(dependency_rationale) < MIN_DEPENDENCY_RATIONALE_CHARS:
        errors.append(f"dependency_rationale shorter than {MIN_DEPENDENCY_RATIONALE_CHARS} characters")
    for field_name, text in (("title", title), ("description", description), ("dependency_rationale", dependency_rationale)):
        for pattern, reason in FORBIDDEN_HUMAN_TEXT_PATTERNS:
            if pattern.search(text or ""):
                errors.append(f"{field_name} contains {reason}")
    if errors:
        raise ValueError(f"{task_id}: invalid production task text: " + "; ".join(errors))


def _source_refs(inp: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    sm = inp.get("source_map") or {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        if ref in sm:
            out.append({"id": ref, **sm[ref]})
    return out


def _blueprint_manifest(inp: dict[str, Any]) -> dict[str, Any]:
    bp = inp.get("blueprint") or {}
    return bp if isinstance(bp, dict) else {}


def _id_sections(inp: dict[str, Any], ref: str) -> list[dict[str, Any]]:
    ids_to_sections = (_blueprint_manifest(inp).get("ids_to_sections") or {})
    refs = ids_to_sections.get(str(ref)) or []
    return [dict(x) for x in refs if isinstance(x, dict)]


def _source_sections_for_refs(inp: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any, Any]] = set()
    for ref in refs:
        for sec in _id_sections(inp, str(ref)):
            item = {"id": str(ref), **sec}
            key = (item.get("id"), item.get("section_id"), item.get("line_start"), item.get("line_end"))
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out


def _blueprint_lossless_refs(inp: dict[str, Any], refs: list[str]) -> dict[str, Any]:
    bp = _blueprint_manifest(inp)
    contract = bp.get("lossless_contract") or {}
    return {
        "snapshot": contract.get("full_text_snapshot") or "orchestrator-state/compiled/BLUEPRINT.snapshot.md",
        "manifest_json": contract.get("manifest_json") or "orchestrator-state/compiled/blueprint-manifest.json",
        "sections_json": contract.get("sections_json") or "orchestrator-state/compiled/blueprint-sections.json",
        "blocks_json": contract.get("blocks_json") or "orchestrator-state/compiled/blueprint-blocks.json",
        "lossless_json": contract.get("lossless_json") or "orchestrator-state/compiled/blueprint-lossless.json",
        "section_refs": _source_sections_for_refs(inp, refs),
    }


def _logic_index(inp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for item in inp.get("building_blocks", []) or []:
        if isinstance(item, dict) and item.get("id"):
            idx[str(item["id"])] = {"kind": "building_block", "item": item}
    for bucket, items in (inp.get("logic") or {}).items():
        for item in items or []:
            if isinstance(item, dict) and item.get("id"):
                idx[str(item["id"])] = {"kind": f"logic.{bucket}", "item": item}
    for bucket, items in (inp.get("auxiliary") or {}).items():
        for item in items or []:
            if isinstance(item, dict) and item.get("id"):
                idx[str(item["id"])] = {"kind": f"auxiliary.{bucket}", "item": item}
    return idx


def _slice_index(inp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(sl.get("id")): sl for sl in inp.get("slices", []) or [] if isinstance(sl, dict) and sl.get("id")}


def _compact_dependency_tasks(inp: dict[str, Any], deps: list[str]) -> list[dict[str, Any]]:
    by_id = _slice_index(inp)
    out: list[dict[str, Any]] = []
    for dep in deps:
        sl = by_id.get(str(dep))
        if not sl:
            continue
        out.append({
            "id": str(dep),
            "title": _human_text(sl.get("title") or sl.get("name") or dep),
            "description": _human_text(sl.get("description")),
            "dependency_rationale": _human_text(sl.get("dependency_rationale")),
            "phase_id": str(sl.get("phase") or "F?"),
            "type": sl.get("type") or "slice",
            "implements": [str(x) for x in _as_list(sl.get("implements"))],
            "builds": [str(x) for x in _as_list(sl.get("builds"))],
            "verification_refs": [str(x) for x in _as_list(sl.get("verifies") or sl.get("verification"))],
        })
    return out


def _validate_dependency_contract(task_id: str, deps: list[str], dep_map: dict[str, str], resolved_dependencies: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for dep in deps:
        reason = _human_text(dep_map.get(dep))
        if not reason:
            errors.append(f"missing depends_on_rationale for {dep}")
        elif len(reason) < MIN_DEPENDENCY_RATIONALE_CHARS:
            errors.append(f"depends_on_rationale[{dep}] shorter than {MIN_DEPENDENCY_RATIONALE_CHARS} characters")
        for pattern, marker in FORBIDDEN_HUMAN_TEXT_PATTERNS:
            if pattern.search(reason):
                errors.append(f"depends_on_rationale[{dep}] contains {marker}")
    seen = {str(d.get("id")) for d in resolved_dependencies}
    for dep in deps:
        if dep not in seen:
            errors.append(f"dependency {dep} not present in resolved_dependencies")
    for d in resolved_dependencies:
        desc = _human_text(d.get("description"))
        if len(desc) < MIN_RESOLVED_DEPENDENCY_DESCRIPTION_CHARS:
            errors.append(f"resolved dependency {d.get('id')} description missing or too short")
    if errors:
        raise ValueError(f"{task_id}: invalid dependency contract: " + "; ".join(errors))


def _slice_contract_refs(sl: dict[str, Any], idx: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = defaultdict(list)
    for key in ["implements", "builds", "verifies", "journey_refs", "closes_journeys"]:
        for ref in _as_list(sl.get(key)):
            ref = str(ref)
            spec = idx.get(ref)
            kind = (spec or {}).get("kind", "unresolved")
            refs[kind].append(ref)
    return {k: sorted(set(v)) for k, v in sorted(refs.items())}


def _topological_layers(tasks: list[dict[str, Any]]) -> list[list[str]]:
    ids = {str(t["id"]) for t in tasks}
    deps = {str(t["id"]): [str(d) for d in t.get("depends_on", []) if str(d) in ids] for t in tasks}
    remaining = set(ids)
    layers: list[list[str]] = []
    done: set[str] = set()
    while remaining:
        ready = sorted(tid for tid in remaining if set(deps.get(tid, [])) <= done)
        if not ready:
            layers.append(sorted(remaining))
            break
        layers.append(ready)
        done.update(ready)
        remaining.difference_update(ready)
    return layers


def _parallel_config(inp: dict[str, Any]) -> dict[str, Any]:
    stack = inp.get("stack") or {}
    orchestrator_cfg = stack.get("orchestrator") or {}
    par = orchestrator_cfg.get("parallelism") or {}
    raw_max = par.get("max_parallel_slices") or par.get("max_parallel") or os.environ.get("CLAUDE_MAX_PARALLEL_SLICES") or 3
    try:
        max_parallel = max(1, int(raw_max))
    except Exception:
        max_parallel = 3
    return {
        "max_parallel_slices": max_parallel,
        "selection_policy": str(par.get("selection_policy") or "dependency_order_then_non_conflicting"),
        "intra_wave_conflict_check": bool(par.get("intra_wave_conflict_check", True)),
        "claim_rechecks_active_conflicts": True,
        "lock_backend": "posix_fcntl_file_locks",
        "supported_platforms": ["linux", "darwin", "wsl2"],
    }


def _task_locks(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": f"task:{task.get('id')}",
        "write_set": [str(x) for x in task.get("write_set", []) or []],
        "conflict_groups": [str(x) for x in task.get("conflict_groups") or task.get("conflict_group") or []],
        "lock_files": [
            f"orchestrator-state/tasks/registry.json.lock",
            f"orchestrator-state/tasks/runtime-state.json.lock",
            f"orchestrator-state/tasks/handoffs/{task.get('id')}.md.lock",
        ],
    }


def _parallel_safe_batches(task_ids: list[str], by_id: dict[str, dict[str, Any]], max_parallel: int) -> list[list[str]]:
    batches: list[list[str]] = []
    for tid in task_ids:
        placed = False
        for batch in batches:
            if len(batch) >= max_parallel:
                continue
            if all(not task_conflict_reasons(by_id[tid], by_id[other]) for other in batch):
                batch.append(tid)
                placed = True
                break
        if not placed:
            batches.append([tid])
    return batches


def _parallel_groups(tasks: list[dict[str, Any]], max_parallel: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_id = {str(t["id"]): t for t in tasks}
    groups: list[dict[str, Any]] = []
    group_by_task: dict[str, str] = {}
    for layer_idx, layer in enumerate(_topological_layers(tasks), start=1):
        for batch_idx, batch in enumerate(_parallel_safe_batches(layer, by_id, max_parallel), start=1):
            gid = f"L{layer_idx}-B{batch_idx}"
            for tid in batch:
                group_by_task[tid] = gid
            groups.append({"id": gid, "layer": layer_idx, "batch": batch_idx, "task_ids": batch, "parallel_safe": True})
    return groups, group_by_task


def _build_task_dag(tasks: list[dict[str, Any]], inp: dict[str, Any]) -> dict[str, Any]:
    by_id = {str(t["id"]): t for t in tasks}
    parallelism = _parallel_config(inp)
    parallel_groups, parallel_group_by_task = _parallel_groups(tasks, parallelism["max_parallel_slices"])
    edges = []
    dependents: dict[str, list[str]] = {tid: [] for tid in by_id}
    for t in tasks:
        tid = str(t["id"])
        dep_reasons = t.get("depends_on_rationale") or {}
        for dep in t.get("depends_on", []) or []:
            dep = str(dep)
            edges.append({"from": dep, "to": tid, "type": "build", "reason": dep_reasons.get(dep) or "explicit_or_compiled_depends_on"})
            dependents.setdefault(dep, []).append(tid)
    nodes = []
    for t in tasks:
        tid = str(t["id"])
        nodes.append({
            "id": tid,
            "task_id": tid,
            "title": t.get("title"),
            "description": t.get("description"),
            "phase_id": t.get("phase_id"),
            "step_id": t.get("step_id"),
            "order": t.get("order"),
            "type": t.get("type"),
            "status": t.get("status"),
            "dependency_rationale": t.get("dependency_rationale"),
            "depends_on_rationale": t.get("depends_on_rationale", {}),
            "dependency_edges": t.get("dependency_edges", []),
            "depends_on": t.get("depends_on", []),
            "dependents": sorted(dependents.get(tid, [])),
            "implements": t.get("implements", []),
            "builds": t.get("builds", []),
            "closes_journeys": t.get("closes_journeys", []),
            "journey_refs": t.get("journey_refs", []),
            "arc42_refs": t.get("arc42_refs", []),
            "building_block_refs": t.get("building_block_refs", []),
            "write_set": t.get("write_set", []),
            "read_set": t.get("read_set", []),
            "conflict_group": t.get("conflict_group", []),
            "conflict_groups": t.get("conflict_groups", []),
            "verification_refs": t.get("verification_refs", []),
            "contract_refs": t.get("contract_refs", []),
            "acceptance": t.get("acceptance", []),
            "evidence_contract": t.get("evidence_contract", {}),
            "resolved_dependencies": t.get("resolved_dependencies", []),
            "risk": t.get("risk"),
            "risk_level": t.get("risk_level"),
            "verify_mode": t.get("verify_mode"),
            "verification_surface": t.get("verification_surface", {}),
            "locks": t.get("locks", _task_locks(t)),
            "parallel": {"eligible": True, "safe_group": parallel_group_by_task.get(tid), "conflict_checked": True},
            "task_pack": f"orchestrator-state/tasks/task-packs/{tid}.json",
        })
    return {
        "schema_version": "2.0",
        "mode": "explicit_dag",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "topological_layers": _topological_layers(tasks),
        "parallelism": parallelism,
        "parallel_groups": parallel_groups,
        "ready_rule": "status == ready AND all depends_on.status == done AND no active conflict_group/write_set blocker AND no intra-wave write_set/conflict_group conflict",
        "conflict_model": {
            "write_set": "Preserved from blueprint-authored slice.write_set when present; otherwise derived from building_blocks.path/write_surface plus slice overrides.",
            "node_scope": "DAG nodes intentionally keep scheduling fields only; full lossless source context remains in registry tasks, task-packs and slice YAML to avoid duplicating megabytes of blueprint context.",
            "conflict_groups": "Preserved from blueprint-authored slice.conflict_groups/conflict_group when present; otherwise derived from building_blocks.conflict_group/write_surface plus slice overrides.",
            "intra_wave": "next-wave selects a non-conflicting subset before suggesting parallel execution; claim_task rechecks under registry lock.",
        },
        "lock_model": {
            "backend": "fcntl.flock advisory files",
            "platforms": ["linux", "darwin", "wsl2"],
            "registry_lock": "orchestrator-state/tasks/registry.json.lock",
            "runtime_lock": "orchestrator-state/tasks/runtime-state.json.lock",
            "handoff_lock_pattern": "orchestrator-state/tasks/handoffs/<TASK_ID>.md.lock"
        },
    }



def _spec_text_contains(spec: dict[str, Any], *needles: str) -> bool:
    raw = json.dumps(spec.get("raw") or spec.get("details") or spec, ensure_ascii=False).lower()
    return any(n.lower() in raw for n in needles)


def _derive_verification_surface(task_like: dict[str, Any], resolved_specs: list[dict[str, Any]], inp: dict[str, Any]) -> dict[str, Any]:
    """Compile the verification route used by /verify-slice.

    The orchestrator requires real verification for every slice. This runtime keeps
    that invariant while making non-UI verification explicit: backend/API, DB/DDL,
    worker/pipeline, dependency, integration and pure-core logic slices each get a
    concrete evidence matrix.  A journey reference alone never creates a visual UI
    requirement; only UI specs/routes/frontend write surfaces or explicit visual
    contracts do.
    """
    from orchestrator.runtime.verify_requirements import classify_task_verification

    temp_task = dict(task_like)
    temp_task["resolved_specs"] = resolved_specs
    temp_task.setdefault("write_set", task_like.get("write_set") or [])
    temp_task.setdefault("builds", task_like.get("builds") or [])
    temp_task.setdefault("implements", task_like.get("implements") or [])
    temp_task.setdefault("verification_refs", task_like.get("verifies") or task_like.get("verification") or [])
    classification = classify_task_verification(temp_task)
    signals = classification.get("signals") or {}
    return {
        "kind": classification.get("surface_kind"),
        "method": classification.get("method"),
        "requires_visual_mcp": bool(classification.get("visual_required")),
        "requires_screen_journey_reviewer": bool(classification.get("screen_journey_reviewer_required")),
        "journey_refs_are_ui_signals": bool((classification.get("journey_refs") or []) and bool(classification.get("visual_required"))),
        "journey_refs": classification.get("journey_refs") or [],
        "closes_journeys": classification.get("closes_journeys") or [],
        "ui_spec_refs": signals.get("ui_specs") or [],
        "route_refs": signals.get("route_specs") or [],
        "visual_mode": classification.get("visual_mode"),
        "evidence_route": classification.get("evidence_route"),
        "mcp_requirement": classification.get("mcp_requirement") or {},
        "evidence_matrix": classification.get("evidence_matrix") or [],
        "required_evidence_categories": classification.get("required_evidence_categories") or [],
        "minimum_runtime_proof": classification.get("minimum_runtime_proof") or [],
        "signals": signals,
        "rationale": classification.get("explanation") or "Derived from compiled write_set and resolved_specs.",
    }

def build_registry(inp: dict[str, Any]) -> dict[str, Any]:
    idx = _logic_index(inp)
    tasks: list[dict[str, Any]] = []
    for order, sl in enumerate(inp.get("slices", []) or [], start=1):
        deps = [str(x) for x in sl.get("depends_on", []) or []]
        dep_map = {str(k): _human_text(v) for k, v in (sl.get("depends_on_rationale") or {}).items()} if isinstance(sl.get("depends_on_rationale") or {}, dict) else {}
        dependency_edges = [{"from": dep, "to": str(sl.get("id")), "reason": dep_map.get(dep, "")} for dep in deps]
        resolved_dependencies = _compact_dependency_tasks(inp, deps)
        status = "ready" if not deps else "todo"
        sid = str(sl.get("id"))
        _validate_dependency_contract(sid, deps, dep_map, resolved_dependencies)
        implements = [str(x) for x in _as_list(sl.get("implements"))]
        builds = [str(x) for x in _as_list(sl.get("builds"))]
        verifies = [str(x) for x in _as_list(sl.get("verifies") or sl.get("verification"))]
        closes = [str(x) for x in _as_list(sl.get("closes_journeys") or sl.get("closes_journey"))]
        journey_refs = [str(x) for x in _as_list(sl.get("journey_refs"))]
        arc42_refs = [str(x) for x in _as_list(sl.get("arc42_refs"))]
        conflict_groups = [str(x) for x in _as_list(sl.get("conflict_group") or sl.get("conflict_groups"))]
        scope_refs = implements + builds + verifies + journey_refs + closes + arc42_refs
        all_source_ids = [sid] + scope_refs
        source_refs = _source_refs(inp, all_source_ids)
        source_sections = _source_sections_for_refs(inp, all_source_ids)
        blueprint_lossless_refs = _blueprint_lossless_refs(inp, all_source_ids)
        resolved_specs = _compact_resolved_specs(inp, scope_refs)
        _validate_resolved_specs(sid, resolved_specs)
        phase = str(sl.get("phase") or "F?")
        title = _human_text(sl.get("title") or sl.get("name") or sid)
        description = _human_text(sl.get("description"))
        dependency_rationale = _human_text(sl.get("dependency_rationale"))
        _validate_task_human_text(sid, title, description, dependency_rationale)
        task = {
            "schema_version": "2.0",
            "id": sid,
            "task_id": sid,
            "title": title,
            "description": description,
            "dependency_rationale": dependency_rationale,
            "depends_on_rationale": dep_map,
            "dependency_edges": dependency_edges,
            "resolved_dependencies": resolved_dependencies,
            "phase_id": phase,
            "step_id": sl.get("step_id") or sid,
            "order": order,
            "type": sl.get("type") or "slice",
            "status": status,
            "depends_on": deps,
            "implements": implements,
            "builds": builds,
            "closes_journeys": closes,
            "journey_refs": journey_refs,
            "arc42_refs": arc42_refs,
            "write_set": [str(x) for x in _as_list(sl.get("write_set"))],
            "read_set": [str(x) for x in _as_list(sl.get("read_set"))],
            "conflict_group": conflict_groups,
            "conflict_groups": conflict_groups,
            "building_block_refs": [str(x) for x in _as_list(sl.get("building_block_refs"))],
            "verification_refs": verifies,
            "risk": sl.get("risk") or sl.get("risk_level") or "medium",
            "risk_level": sl.get("risk") or sl.get("risk_level") or "medium",
            "verify_mode": sl.get("verify_mode") or "automated",
            "verification_surface": _derive_verification_surface({**sl, "closes_journeys": closes, "journey_refs": journey_refs}, resolved_specs, inp),
            "acceptance": sl.get("acceptance") or sl.get("acceptance_minimum") or [],
            "evidence_contract": sl.get("evidence") or {"required": ["tests_passed", "files_changed", "handoff", "no_stub_runtime"]},
            "contract_refs": _slice_contract_refs({**sl, "closes_journeys": closes, "journey_refs": journey_refs, "arc42_refs": arc42_refs}, idx),
            "resolved_specs": resolved_specs,
            "source_refs": source_refs,
            "source_sections": source_sections,
            "blueprint_lossless_refs": blueprint_lossless_refs,
            "generated_from": {"compiler": inp.get("compiler", {}), "slice": sid, "blueprint_source_map": source_refs, "blueprint_lossless_refs": blueprint_lossless_refs},
            "locks": {},
            "parallel": {"eligible": True, "safe_group": None, "conflict_checked": True},
            "created_at": now_iso(),
        }
        task["locks"] = _task_locks(task)
        tasks.append(task)
    dag = _build_task_dag(tasks, inp)
    dependents = {n["id"]: n.get("dependents", []) for n in dag["nodes"]}
    parallel_group_by_task = {tid: group.get("id") for group in dag.get("parallel_groups", []) for tid in group.get("task_ids", [])}
    for task in tasks:
        task["dependents"] = dependents.get(task["id"], [])
        task["locks"] = _task_locks(task)
        task["parallel"] = {"eligible": True, "safe_group": parallel_group_by_task.get(task["id"]), "conflict_checked": True}
    phases = []
    by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in tasks:
        by_phase[str(t["phase_id"])].append(t)
    for pid in sorted(by_phase, key=phase_order_key):
        pts = by_phase[pid]
        phases.append({"id": pid, "status": "ready" if any(t["status"] == "ready" for t in pts) else "todo", "task_ids": [t["id"] for t in pts]})
    return {
        "schema_version": "2.0",
        "generated_at": now_iso(),
        "source": {"orchestrator_input_sha256": inp.get("compiler", {}).get("blueprint_sha256"), "compiler": inp.get("compiler", {})},
        "project": inp.get("project", {}),
        "stack": inp.get("stack", {}),
        "tasks": tasks,
        "phases": phases,
        "task_dag": dag,
        "journeys": inp.get("logic", {}).get("journey", []),
    }


def _resolve_items(inp: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    idx = _logic_index(inp)
    out = []
    for ref in refs:
        spec = idx.get(str(ref))
        if spec:
            out.append({"id": str(ref), "kind": spec["kind"], "item": spec["item"]})
    return out






def _validate_resolved_specs(task_id: str, specs: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for spec in specs:
        desc = _human_text(spec.get("description"))
        if not desc:
            errors.append(f"{spec.get('id')}: missing resolved spec description")
        elif len(desc) < 240:
            errors.append(f"{spec.get('id')}: resolved spec description shorter than 240 characters")
        if not isinstance(spec.get("raw"), dict) or not spec.get("raw"):
            errors.append(f"{spec.get('id')}: resolved spec must carry raw blueprint YAML item")
        if not isinstance(spec.get("details"), dict):
            errors.append(f"{spec.get('id')}: resolved spec must carry details map")
        if not isinstance(spec.get("source_ref"), dict):
            errors.append(f"{spec.get('id')}: resolved spec must carry source_ref map")
        if not isinstance(spec.get("source_sections"), list):
            errors.append(f"{spec.get('id')}: resolved spec must carry source_sections list")
        if not isinstance(spec.get("blueprint_lossless_refs"), dict):
            errors.append(f"{spec.get('id')}: resolved spec must carry blueprint_lossless_refs map")
        for pattern, reason in FORBIDDEN_HUMAN_TEXT_PATTERNS:
            if pattern.search(desc):
                errors.append(f"{spec.get('id')}: description contains {reason}")
    if errors:
        raise ValueError(f"{task_id}: invalid resolved_specs: " + "; ".join(errors))

def _compact_resolved_specs(inp: dict[str, Any], refs: list[str]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    source_map = inp.get("source_map") or {}
    seen: set[str] = set()
    for spec in _resolve_items(inp, refs):
        item = copy.deepcopy(spec.get("item") or {})
        sid = str(spec.get("id"))
        if sid in seen:
            continue
        seen.add(sid)
        details = {k: v for k, v in item.items() if k not in {"id", "name", "title", "description", "summary"}}
        compact: dict[str, Any] = {
            "id": sid,
            "kind": spec.get("kind"),
            "name": item.get("name") or item.get("title") or item.get("id"),
            "description": item.get("description") or item.get("summary") or "",
            "details": details,
            "source_ref": source_map.get(sid, {}),
            "source_sections": _id_sections(inp, sid),
            "blueprint_lossless_refs": _blueprint_lossless_refs(inp, [sid]),
            "raw": item,
        }
        # Preserve the most common fields at top-level for easy prompt rendering,
        # while keeping the full YAML item in raw/details so no machine contract
        # information is lost between inputs/BLUEPRINT.md and Claude task context.
        for key in [
            "location", "invariant", "gate", "states", "transitions", "trigger_to_close", "route",
            "provider", "critical", "table", "mode", "proves", "response", "logic_focus",
            "consumes", "produces", "rules", "permissions", "journeys", "errors", "contracts",
            "acceptance", "evidence", "workers", "events", "actions", "reads", "writes"
        ]:
            if key in item:
                compact[key] = item[key]
        specs.append(compact)
    return specs


def _append_bullets(lines: list[str], values: list[Any], empty: str = "none") -> None:
    vals = [str(x) for x in (values or []) if str(x).strip()]
    if vals:
        lines.extend(f"- `{x}`" for x in vals)
    else:
        lines.append(f"- {empty}")


def task_pack_markdown(task: dict[str, Any], inp: dict[str, Any]) -> str:
    resolved = task.get("resolved_specs") or _compact_resolved_specs(inp, task.get("implements", []) + task.get("builds", []) + task.get("verification_refs", []) + task.get("closes_journeys", []) + task.get("arc42_refs", []))
    lines = [
        f"# Task Pack: {task['id']} - {task['title']}",
        "",
        "## Human task description",
        "",
        task.get("description") or "Missing task description.",
        "",
        "## Dependency rationale",
        "",
        task.get("dependency_rationale") or "Dependencies are defined by the explicit DAG.",
        "",
        "## Dependency edges",
        "",
    ]
    if task.get("dependency_edges"):
        for edge in task.get("dependency_edges") or []:
            lines.append(f"- `{edge.get('from')}` -> `{edge.get('to')}`: {edge.get('reason')}")
    else:
        lines.append("- none; this is a root slice in the compiled DAG.")
    lines += ["", "## Resolved dependency tasks", ""]
    if task.get("resolved_dependencies"):
        for dep in task.get("resolved_dependencies") or []:
            lines.append(f"### {dep.get('id')} — {dep.get('title')}")
            lines.append(f"- phase: `{dep.get('phase_id')}`")
            lines.append(f"- description: {dep.get('description')}")
            lines.append(f"- dependency_rationale: {dep.get('dependency_rationale')}")
            lines.append("")
    else:
        lines.append("- none; this root slice has no prerequisite task whose description must be loaded.")
    lines += [
        "",
        "## DAG contract",
        "",
        f"- TASK_ID: `{task['id']}`",
        f"- Title: {task.get('title')}",
        f"- Phase: `{task['phase_id']}`",
        f"- Status: `{task['status']}`",
        f"- Type: `{task['type']}`",
        f"- Risk: `{task['risk_level']}`",
        f"- Verify mode: `{task['verify_mode']}`",
        f"- Verification surface: `{(task.get('verification_surface') or {}).get('kind', 'not_derived')}` — {(task.get('verification_surface') or {}).get('rationale', '')}",
        f"- Depends on: {', '.join(task.get('depends_on') or []) or 'none'}",
        f"- Dependents: {', '.join(task.get('dependents') or []) or 'none'}",
        "",
        "## Scope by IDs",
        "",
        "Implements:",
    ]
    _append_bullets(lines, task.get("implements", []), "none")
    lines.append("Builds:")
    _append_bullets(lines, task.get("builds", []), "none")
    lines += ["", "## Arc42 refs", "", "Arc42 refs:"]
    _append_bullets(lines, task.get("arc42_refs", []), "none")
    lines.append("Closes journeys:")
    _append_bullets(lines, task.get("closes_journeys", []), "none")
    lines += ["", "## Write and conflict contract", "", "Write set:"]
    _append_bullets(lines, task.get("write_set", []), "not_derived")
    lines.append("Conflict groups:")
    _append_bullets(lines, task.get("conflict_groups", []), "not_derived")
    lines += ["", "## Verification contract", ""]
    surface = task.get("verification_surface") or {}
    lines.append(f"- verification_surface.kind: `{surface.get('kind', 'not_derived')}`")
    lines.append(f"- verification_surface.method: `{surface.get('method', 'not_derived')}`")
    lines.append(f"- requires_visual_mcp: `{surface.get('requires_visual_mcp', False)}`")
    lines.append(f"- requires_screen_journey_reviewer: `{surface.get('requires_screen_journey_reviewer', False)}`")
    lines.append(f"- journey_refs_are_ui_signals: `{surface.get('journey_refs_are_ui_signals', False)}`")
    mcp_req = surface.get("mcp_requirement") if isinstance(surface.get("mcp_requirement"), dict) else {}
    if mcp_req:
        lines.append(f"- MCP_BROWSER: `{mcp_req.get('mcp_browser', 'not_derived')}`")
        lines.append(f"- VISUAL_CHECK_METHOD: `{mcp_req.get('visual_check_method', 'not_derived')}`")
    lines.append(f"- rationale: {surface.get('rationale', '')}")
    if surface.get("kind") == "journey_backend_contract":
        lines.append("- backend_journey_note: `journey_refs do not imply UI. Verify API/worker/domain behavior and keep /verify-journey or later UI validation for the human journey; do not force browser/mobile MCP for this backend dependency.`")
    elif surface.get("requires_visual_mcp"):
        lines.append("- visual_review_note: `UI/mobile/browser surface is explicit. Use the exact MCP/tooling named by the stack and call screen-journey-reviewer after real verification.`")
    else:
        lines.append("- non_ui_note: `No UI route is compiled for this slice. Use CLI/API/worker/log/data verification and emit MCP_BROWSER: not_applicable:no_ui_surface plus VISUAL_CHECK_METHOD: backend in evidence.`")
    if not surface.get("requires_visual_mcp"):
        lines.extend([
            "- backend_acceptance_required: `MCP_BROWSER=not_applicable:no_ui_surface, VISUAL_CHECK_METHOD=backend, REAL_DATA_SOURCE, FLOWS_TESTED, DATA_SETUP, DATA_CONTRACT_ROWS or PERSISTED_DATA_OBSERVED, ERROR_LOGS_STATUS=clean, RUNTIME_LOG_ERRORS=0`",
        ])
    _append_bullets(lines, task.get("verification_refs", []), "missing")
    lines += ["", "## Evidence matrix", ""]
    matrix = surface.get("evidence_matrix") or []
    if matrix:
        for item in matrix:
            mark = "required" if item.get("required") else "not-applicable unless manually needed"
            lines.append(f"### {item.get('label') or item.get('kind')} — `{mark}`")
            lines.append(f"- kind: `{item.get('kind')}`")
            if item.get("signals"):
                lines.append("- signals: " + ", ".join(f"`{x}`" for x in (item.get("signals") or [])[:18]))
            lines.append("- verify:")
            for step in item.get("what_to_verify") or []:
                lines.append(f" - {step}")
            lines.append("- evidence:")
            for ev in item.get("required_evidence") or []:
                lines.append(f" - {ev}")
            lines.append("")
    else:
        lines.append("- Visual/UI slice: evidence is governed by the MCP visual/mobile contract above plus real persistence/log checks for touched backend/DB paths.")
    lines += ["", "## Blueprint source sections", ""]
    bp_refs = task.get("blueprint_lossless_refs") or {}
    lines.append(f"- Full snapshot: `{bp_refs.get('snapshot', 'orchestrator-state/compiled/BLUEPRINT.snapshot.md')}`")
    lines.append(f"- Manifest JSON: `{bp_refs.get('manifest_json', 'orchestrator-state/compiled/blueprint-manifest.json')}`")
    lines.append(f"- Sections index: `{bp_refs.get('sections_json', 'orchestrator-state/compiled/blueprint-sections.json')}`")
    lines.append(f"- Blocks index: `{bp_refs.get('blocks_json', 'orchestrator-state/compiled/blueprint-blocks.json')}`")
    if task.get("source_sections"):
        for sec in (task.get("source_sections") or [])[:60]:
            lines.append(f"- `{sec.get('section_id')}` lines `{sec.get('line_start')}-{sec.get('line_end')}` — {sec.get('title')} via `{sec.get('id')}`")
    else:
        lines.append("- No source sections indexed; run `./scripts/check-blueprint-lossless-flow.sh` before delegating this slice.")
    lines += ["", "## Resolved blueprint specs", ""]
    if resolved:
        for spec in resolved:
            lines.append(f"### {spec.get('id')} ({spec.get('kind')})")
            for key in ["name", "description", "section", "location", "invariant", "gate", "route", "provider", "table", "mode", "response", "logic_focus"]:
                if key in spec and spec[key] not in (None, ""):
                    value = spec[key]
                    if key == "description":
                        lines.append(f"- {key}: {value}")
                    else:
                        lines.append(f"- {key}: `{value}`")
            for key in ["states", "transitions", "proves", "consumes", "produces", "rules", "permissions", "journeys", "errors", "contracts", "workers", "events", "actions", "reads", "writes"]:
                if key in spec:
                    value = spec[key]
                    if isinstance(value, list):
                        lines.append(f"- {key}:")
                        lines.extend(f" - `{x}`" for x in value[:30])
                    else:
                        lines.append(f"- {key}: `{value}`")
            if spec.get("source_ref"):
                lines.append("- source_ref:")
                for k, v in (spec.get("source_ref") or {}).items():
                    if k == "source_sections":
                        continue
                    lines.append(f" - {k}: `{v}`")
            if spec.get("source_sections"):
                lines.append("- blueprint_source_sections:")
                for sec in (spec.get("source_sections") or [])[:12]:
                    lines.append(f" - `{sec.get('section_id')}` lines `{sec.get('line_start')}-{sec.get('line_end')}`: {sec.get('title')}")
            if spec.get("details"):
                lines.append("- full_yaml_details:")
                lines.append("```json")
                lines.append(json.dumps(spec.get("details"), indent=2, ensure_ascii=False))
                lines.append("```")
            lines.append("")
    else:
        lines.append("No resolved specs found; bootstrap should normally prevent this.")
    lines += [
        "## Handoff contract",
        "",
        "Every mutating subagent must append a role-scoped handoff section to `orchestrator-state/tasks/handoffs/{task_id}.md` before emitting its final `CLAUDE_TRAILER`. The trailer must include `AGENT` matching the Claude `agent_type`; the SubagentStop hook rejects mismatches and ignores unscoped fallback trailers.",
        "",
        "## Required lifecycle trailers",
        "",
        "Developer success:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: developer",
        f"TASK_ID: {task['id']}",
        "OUTCOME: success",
        "NEXT_STATUS: validator_tester_pending",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        f"EVIDENCE: orchestrator-state/tasks/evidence/{task['id']}",
        "```",
        "",
        "Tester pass:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: tester",
        f"TASK_ID: {task['id']}",
        "OUTCOME: pass",
        "NEXT_STATUS: ready_for_close",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        f"EVIDENCE: orchestrator-state/tasks/evidence/{task['id']}",
        "```",
        "",
        "Verifier success:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: slice-verifier",
        f"TASK_ID: {task['id']}",
        "OUTCOME: verified",
        "NEXT_STATUS: verified_pending_close",
        "VERIFY_OUTCOME: verified",
        "REAL_DATA_OR_USER_PROVIDED: yes",
        "NO_STUB_DATA_USED: yes",
        "RUNTIME_LOGS_CHECKED: yes",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        f"EVIDENCE: orchestrator-state/tasks/evidence/{task['id']}",
        "```",
        "",
        "Debugger fixed:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: debugger",
        f"TASK_ID: {task['id']}",
        "OUTCOME: fixed",
        "NEXT_STATUS: validator_tester_pending",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        f"EVIDENCE: orchestrator-state/tasks/evidence/{task['id']}/debugger.json",
        "```",
        "",
        "Deployer ready:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: deployer",
        f"TASK_ID: {task['id']}",
        "OUTCOME: deployed",
        "NEXT_STATUS: ready_for_close",
        "DEPLOY_READY: yes",
        "DEPLOY_URL: <deployment-url-or-local-runtime-url>",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        "EVIDENCE: orchestrator-state/tasks/evidence/{task_id}/deployer.json",
        "```",
        "",
        "Validator info-only review:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: validator",
        f"TASK_ID: {task['id']}",
        "OUTCOME: approved",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        "```",
        "",
        "Screen journey reviewer info-only review:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: screen-journey-reviewer",
        f"TASK_ID: {task['id']}",
        "OUTCOME: approved",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        "```",
        "",
        "Closer done under pr-flow:",
        "```text",
        "CLAUDE_TRAILER:",
        "AGENT: closer",
        f"TASK_ID: {task['id']}",
        "OUTCOME: committed",
        "NEXT_STATUS: done",
        "REPORT_READY: yes",
        "BASELINE_SYNC_READY: yes",
        "GIT_READY: yes",
        "PUSH_READY: yes",
        "GIT_WORKFLOW_READY: yes",
        "RUNTIME_CLEANED: yes",
        "DOCKER_RUNTIME_CLEANED: yes",
        "RANCHER_RUNTIME_CLEANED: yes",
        "DEV_PORTS_RELEASED: yes",
        "WORKTREES_CLEANED: yes",
        f"HANDOFF: orchestrator-state/tasks/handoffs/{task['id']}.md",
        f"REPORT: orchestrator-state/tasks/reports/{task['id']}.md",
        "PR_READY: yes",
        "MERGED: yes",
        "CANONICAL_MAIN_SYNCED: yes",
        "```",
        "",
    ]
    return "\n".join(lines).replace("{task_id}", task["id"])


def write_task_packs(registry: dict[str, Any], inp: dict[str, Any]) -> None:
    pack_dir = tasks_dir() / "task-packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for task in registry.get("tasks", []) or []:
        write_json(pack_dir / f"{task['id']}.json", task)
        (pack_dir / f"{task['id']}.md").write_text(task_pack_markdown(task, inp), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input", nargs="?", default="orchestrator-state/compiled/orchestrator-input.json")
    p.add_argument("--no-sync-lifecycle", action="store_true", help="maintainer-only: do not rehydrate registry from durable lifecycle-events after bootstrap")
    p.add_argument("--allow-lifecycle-reset", action="store_true", help="maintainer-only: allow bootstrap to discard unprotected lifecycle progress")
    args = p.parse_args(argv)
    ensure_dirs()
    inp = read_compiled_input(Path(args.input))
    if not inp:
        print(json.dumps({"ok": False, "error": f"input not found or invalid: {args.input}"}, ensure_ascii=False))
        return 2

    existing_registry = load_registry()
    existing_runtime = load_runtime_state()
    registry = build_registry(inp)
    new_task_ids = {str(t.get("id") or t.get("task_id")) for t in registry.get("tasks", []) or [] if isinstance(t, dict)}
    lifecycle_statuses, lifecycle_skipped_preflight = lifecycle_event_statuses()
    allow_reset = args.allow_lifecycle_reset or os.environ.get("ORCHESTRATOR_ALLOW_BOOTSTRAP_LIFECYCLE_RESET") == "1"
    guard_errors = bootstrap_reset_guard_errors(
        existing_registry,
        existing_runtime,
        new_task_ids=new_task_ids,
        lifecycle_task_ids=(set() if args.no_sync_lifecycle else set(lifecycle_statuses)),
        allow_reset=allow_reset,
    )
    if guard_errors:
        print(json.dumps({
            "ok": False,
            "error": "bootstrap would reset local lifecycle progress without a durable rehydration source",
            "errors": guard_errors,
            "repair": "commit/restore orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json or rerun with ORCHESTRATOR_ALLOW_BOOTSTRAP_LIFECYCLE_RESET=1 for an intentional maintainer reset",
        }, ensure_ascii=False, indent=2))
        return 4

    applied: list[dict[str, Any]] = []
    lifecycle_skipped: list[dict[str, Any]] = lifecycle_skipped_preflight
    if not args.no_sync_lifecycle:
        registry, applied, lifecycle_skipped = apply_lifecycle_events_to_registry(registry)
    else:
        registry = refresh_registry_status_indexes(registry)

    write_json(registry_path(), registry)
    write_yaml(registry_path().with_suffix(".yaml"), registry)
    write_json(tasks_dir() / "task-dag.json", registry["task_dag"])
    write_yaml(tasks_dir() / "task-dag.yaml", registry["task_dag"])
    execution_graph = {"tasks": [{"id": t["id"], "title": t.get("title"), "description": t.get("description"), "dependency_rationale": t.get("dependency_rationale"), "depends_on_rationale": t.get("depends_on_rationale", {}), "deps": t["depends_on"], "dependents": t.get("dependents", []), "status": t.get("status"), "write_set": t.get("write_set", []), "conflict_groups": t.get("conflict_groups", []), "parallel": t.get("parallel", {})} for t in registry["tasks"]]}
    write_json(state_dir() / "memory" / "execution-graph.json", execution_graph)
    write_yaml(state_dir() / "memory" / "execution-graph.yaml", execution_graph)
    write_task_packs(registry, inp)
    existing_counts = existing_runtime.get("spawn_counts") if isinstance(existing_runtime, dict) else {}
    spawn_counts = {str(k): v for k, v in (existing_counts or {}).items() if str(k) in new_task_ids}
    runtime = {
        "active_task_id": None,
        "spawn_budget": int((existing_runtime or {}).get("spawn_budget") or 70),
        "spawn_counts": spawn_counts,
        "last_bootstrap_at": now_iso(),
        "blueprint_sha256": inp.get("compiler", {}).get("blueprint_sha256"),
        "last_lifecycle_sync": {"at": now_iso(), "applied": len(applied), "skipped": len(lifecycle_skipped), "source": "bootstrap-registry"},
        "bootstrap_preserved_spawn_counts": bool(spawn_counts),
    }
    write_json(runtime_state_path(), runtime)
    write_yaml(runtime_state_path().with_suffix(".yaml"), runtime)
    mirror_lossless_to_memory()
    from orchestrator.runtime.memory_yaml import init_memory_from_bootstrap
    init_memory_from_bootstrap(inp, registry, runtime)
    print(json.dumps({
        "ok": True,
        "registry": str(registry_path()),
        "tasks": len(registry["tasks"]),
        "phases": len(registry["phases"]),
        "edges": registry["task_dag"]["edge_count"],
        "lifecycle_sync_applied": len(applied),
        "lifecycle_sync_skipped": len(lifecycle_skipped),
        "lifecycle_sync_mode": "skipped_by_flag" if args.no_sync_lifecycle else "auto_after_bootstrap",
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
