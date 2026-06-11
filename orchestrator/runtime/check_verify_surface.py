from __future__ import annotations

import json
from typing import Any

from orchestrator.common import load_registry, tasks_dir, read_json


def _spec_ids(task: dict[str, Any], kind: str | None = None) -> list[str]:
    out: list[str] = []
    for spec in task.get("resolved_specs") or []:
        if not isinstance(spec, dict):
            continue
        if kind is None or spec.get("kind") == kind:
            sid = str(spec.get("id") or "").strip()
            if sid:
                out.append(sid)
    return out


def check() -> dict[str, Any]:
    reg = load_registry()
    dag = read_json(tasks_dir() / "task-dag.json", {})
    errors: list[str] = []
    warnings: list[str] = []
    tasks = [t for t in reg.get("tasks", []) or [] if isinstance(t, dict)]
    nodes = {str(n.get("id")): n for n in (dag.get("nodes") or []) if isinstance(n, dict)}
    for task in tasks:
        tid = str(task.get("id") or task.get("task_id") or "unknown")
        surface = task.get("verification_surface") or {}
        if not isinstance(surface, dict) or not surface:
            errors.append(f"{tid}: missing verification_surface")
            continue
        ui_ids = set(str(x) for x in (surface.get("ui_spec_refs") or []))
        routes = surface.get("route_refs") or []
        signal_payload = surface.get("signals") or {}
        ui_write_paths = signal_payload.get("ui_write_paths") or []
        journey_refs = [str(x) for x in (surface.get("journey_refs") or task.get("journey_refs") or [])]
        resolved_ui = set(_spec_ids(task, "logic.ui"))
        if resolved_ui and not ui_ids:
            errors.append(f"{tid}: resolved logic.ui specs are not reflected in verification_surface.ui_spec_refs")
        has_ui_signal = bool(ui_ids or routes or ui_write_paths)
        if has_ui_signal:
            if not surface.get("requires_visual_mcp"):
                errors.append(f"{tid}: UI/route/write surface must require visual MCP")
            if not surface.get("requires_screen_journey_reviewer"):
                errors.append(f"{tid}: UI/route/write surface must require screen-journey-reviewer")
        if journey_refs and not has_ui_signal:
            if surface.get("kind") != "journey_backend_contract":
                errors.append(f"{tid}: backend journey slice must be journey_backend_contract, got {surface.get('kind')}")
            if surface.get("requires_visual_mcp") or surface.get("requires_screen_journey_reviewer"):
                errors.append(f"{tid}: journey_refs without UI/route must not force browser/mobile verification")
        matrix = surface.get("evidence_matrix") or []
        mcp_req = surface.get("mcp_requirement") or {}
        if not surface.get("requires_visual_mcp"):
            if not isinstance(matrix, list) or not matrix:
                errors.append(f"{tid}: non-UI verification_surface missing evidence_matrix")
            elif not any(isinstance(m, dict) and m.get("required") for m in matrix):
                errors.append(f"{tid}: non-UI evidence_matrix has no required evidence category")
            required_kinds = {str(m.get("kind")) for m in matrix if isinstance(m, dict) and m.get("required")}
            if surface.get("kind") == "journey_backend_contract" and not required_kinds:
                errors.append(f"{tid}: backend journey contract must declare backend/API/DB/worker evidence")
            if mcp_req.get("mcp_browser") != "not_applicable:no_ui_surface":
                errors.append(f"{tid}: non-UI verification must declare MCP_BROWSER not_applicable:no_ui_surface")
            if mcp_req.get("visual_check_method") != "backend":
                errors.append(f"{tid}: non-UI verification must declare VISUAL_CHECK_METHOD backend")
        if surface.get("requires_visual_mcp") and matrix:
            errors.append(f"{tid}: UI visual slice should not carry non-UI evidence_matrix as required route")
        if surface.get("requires_visual_mcp") and str(mcp_req.get("mcp_browser", "")).startswith("not_applicable:no_ui_surface"):
            errors.append(f"{tid}: UI visual slice cannot declare backend/no-UI MCP")
        if not surface.get("minimum_runtime_proof"):
            errors.append(f"{tid}: verification_surface missing minimum_runtime_proof")
        node = nodes.get(tid)
        if not node:
            errors.append(f"{tid}: missing task-dag node")
        elif node.get("verification_surface") != surface:
            errors.append(f"{tid}: task-dag verification_surface drift")
    return {
        "ok": not errors,
        "tasks": len(tasks),
        "errors": sorted(set(errors)),
        "warnings": warnings,
    }


def main() -> int:
    result = check()
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
