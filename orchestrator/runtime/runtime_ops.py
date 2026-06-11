from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from orchestrator.runtime.handoff import ensure_handoff_header, validate_handoff
from orchestrator.runtime.verify_requirements import classify_task_verification
from orchestrator.common import (
    append_jsonl,
    bash_ledger_path,
    compiled_dir,
    configured_git_workflow,
    ensure_dirs,
    evidence_dir,
    find_task,
    file_lock,
    handoff_path,
    ledger_path,
    load_orchestrator_input,
    load_registry,
    load_runtime_state,
    now_iso,
    project_root,
    read_json,
    read_yaml,
    reports_dir,
    runtime_state_path,
    save_registry,
    save_runtime_state,
    state_dir,
    task_pack_path,
    tasks_dir,
    write_json,
    write_yaml,
    workspace_root,
)
from orchestrator.runtime.check_task_dag import check_registry
from orchestrator.runtime.state_machine import allowed_transition, load_state_machine, state_machine_errors


def _print_json(obj: Any, code: int = 0) -> int:
    print(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True))
    return code


def _ok(**kwargs: Any) -> int:
    data = {"ok": True}
    data.update(kwargs)
    return _print_json(data)


def _fail(message: str, code: int = 2, **kwargs: Any) -> int:
    data = {"ok": False, "error": message}
    data.update(kwargs)
    return _print_json(data, code)


def _task_id_arg(argv: list[str], required: bool = False) -> tuple[str | None, list[str]]:
    rest = list(argv)
    for opt in ("--task-id", "--task_id", "--task"):
        if opt in rest:
            i = rest.index(opt)
            if i + 1 < len(rest):
                val = rest[i + 1]
                del rest[i:i + 2]
                return val, rest
    for item in list(rest):
        if not item.startswith("-"):
            rest.remove(item)
            return item, rest
    val = os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID")
    if val:
        return val, rest
    if required:
        raise SystemExit("missing TASK_ID")
    return None, rest




TRAILER_LINE_RE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*):\s*(?P<value>.*?)\s*$", re.MULTILINE)


def _parse_trailers(text: str) -> list[dict[str, str]]:
    blocks: list[str] = []
    if "CLAUDE_TRAILER:" in text:
        parts = text.split("CLAUDE_TRAILER:")[1:]
        for part in parts:
            # Stop at next markdown heading/fence boundary when possible.
            chunk = part.split("\n## ", 1)[0]
            blocks.append(chunk)
    else:
        blocks.append(text)
    trailers: list[dict[str, str]] = []
    for block in blocks:
        out: dict[str, str] = {}
        duplicates: list[str] = []
        for m in TRAILER_LINE_RE.finditer(block):
            key = m.group("key").lower()
            if key in out and key not in duplicates:
                duplicates.append(key)
            out[key] = m.group("value").strip()
        if duplicates:
            out["__duplicate_keys__"] = ",".join(sorted(duplicates))
        if out:
            trailers.append(out)
    return trailers


def _role_contract(role: str) -> dict[str, Any]:
    contract = read_json(project_root() / ".claude" / "orchestrator-contract.json", {})
    return (((contract.get("trailer_schema") or {}).get("roles") or {}).get(role) or {})


def _validate_trailer_dict(role: str, trailer: dict[str, str], task_id: str | None = None) -> list[str]:
    spec = _role_contract(role)
    errors: list[str] = []
    if not spec:
        errors.append(f"unknown role {role}")
        return errors
    keys = [str(k) for k in spec.get("required_keys") or []]
    outcome = trailer.get("outcome", "").lower()
    next_status = trailer.get("next_status", "").lower()
    if outcome == "blocked" or next_status == "blocked":
        if role == "closer":
            keys = ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "BLOCKER_REASON"]
        elif role == "slice-verifier":
            keys = ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "EVIDENCE", "VERIFY_OUTCOME", "BLOCKER_REASON"]
    if trailer.get("__duplicate_keys__"):
        errors.append(f"{role}: duplicate CLAUDE_TRAILER keys {trailer.get('__duplicate_keys__')}")
    for key in keys:
        if not trailer.get(str(key).lower()):
            errors.append(f"{role}: missing {key}")
    allowed = {str(x).lower() for x in spec.get("outcome_values") or []}
    if outcome and allowed and outcome not in allowed:
        errors.append(f"{role}: OUTCOME {outcome} not allowed")
    allowed_ns = {str(x).lower() for x in spec.get("next_status_values") or []}
    if next_status and allowed_ns and next_status not in allowed_ns:
        errors.append(f"{role}: NEXT_STATUS {next_status} not allowed")
    if task_id and trailer.get("task_id") and trailer.get("task_id") != task_id:
        errors.append(f"{role}: TASK_ID {trailer.get('task_id')} does not match {task_id}")
    return errors


def _schema_paths() -> list[Path]:
    root = project_root()
    paths: list[Path] = []
    paths.extend(sorted((root / "orchestrator" / "schemas").glob("*.json")))
    paths.extend(sorted((root / ".claude" / "schemas").glob("*.json")))
    paths.append(root / ".claude" / "orchestrator-contract.json")
    # Preserve order while removing duplicates.
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = path.resolve().as_posix()
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def validate_orchestrator_schemas(argv: list[str]) -> int:
    errors: list[str] = []
    for path in _schema_paths():
        if not path.exists():
            errors.append(f"missing {path}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON {path}: {exc}")
    sm = load_state_machine()
    if not sm.get("statuses") or not sm.get("transitions"):
        errors.append("state-machine.yaml must define statuses and transitions")
    contract = read_json(project_root() / ".claude" / "orchestrator-contract.json", {})
    roles = ((contract.get("trailer_schema") or {}).get("roles") or {})
    errors.extend(state_machine_errors(roles))
    result = {"ok": not errors, "schemas_checked": [str(p.relative_to(project_root())) for p in _schema_paths()], "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 2


def audit_state_machine_contract(argv: list[str]) -> int:
    contract = read_json(project_root() / ".claude" / "orchestrator-contract.json", {})
    roles = ((contract.get("trailer_schema") or {}).get("roles") or {})
    errors = state_machine_errors(roles)
    sm = load_state_machine()
    return _print_json({"ok": not errors, "schema_version": sm.get("schema_version"), "statuses": sorted((sm.get("statuses") or {}).keys()), "mutating_roles": sorted(r for r, spec in roles.items() if spec.get("mutates_registry_lifecycle")), "info_only_roles": sorted(sm.get("info_only_roles") or []), "errors": errors}, 0 if not errors else 2)


def audit_agent_trailer_vocabulary(argv: list[str]) -> int:
    contract = read_json(project_root() / ".claude" / "orchestrator-contract.json", {})
    roles = ((contract.get("trailer_schema") or {}).get("roles") or {})
    sm = load_state_machine()
    errors: list[str] = []
    global_keys = set(contract.get("trailer_schema", {}).get("global_keys", []))
    for role, spec in roles.items():
        for key in spec.get("required_keys", []) or []:
            if key not in global_keys:
                errors.append(f"{role}: required key {key} is not declared globally")
        for status in spec.get("next_status_values", []) or []:
            if status and status not in (sm.get("statuses") or {}):
                errors.append(f"{role}: unknown NEXT_STATUS {status}")
    return _print_json({"ok": not errors, "roles": sorted(roles), "errors": errors}, 0 if not errors else 2)


def audit_agent_reality(argv: list[str]) -> int:
    root = project_root()
    errors: list[str] = []
    for agent in sorted((root / ".claude" / "agents").glob("*.md")):
        text = agent.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            errors.append(f"{agent.name}: missing YAML frontmatter")
            continue
        if "name:" not in text.split("---", 2)[1] or "description:" not in text.split("---", 2)[1]:
            errors.append(f"{agent.name}: frontmatter must include name and description")
        if "CLAUDE_TRAILER" not in text and agent.stem not in {"main-orchestrator"}:
            errors.append(f"{agent.name}: does not mention CLAUDE_TRAILER")
    return _print_json({"ok": not errors, "errors": errors}, 0 if not errors else 2)


def audit_orchestrator_runtime_consistency(argv: list[str]) -> int:
    root = project_root()
    required = [
        "inputs/BLUEPRINT.md",
        ".claude/skills",
        ".claude/agents",
        ".claude/rules",
        "orchestrator/rules/state-machine.yaml",
        "orchestrator-state/tasks/registry.json",
        "orchestrator-state/tasks/task-dag.json",
        "docs/ORCHESTRATOR.md",
        "docs/CALL_MATRIX.md",
        "docs/prompts",
        "docs/templates",
    ]
    missing = [rel for rel in required if not (root / rel).exists()]
    command_dir = root / ".claude" / "commands"
    if command_dir.exists() and list(command_dir.glob("*.md")):
        missing.append("unexpected project command markdown")
    return _print_json({"ok": not missing, "missing_or_unexpected": missing}, 0 if not missing else 2)


def audit_template_screen_journey_redactor(argv: list[str]) -> int:
    inp = load_orchestrator_input()
    journeys = inp.get("logic", {}).get("journey", []) or []
    ui = inp.get("logic", {}).get("ui", []) or []
    slices = inp.get("slices", []) or []
    journey_ids = {str(x.get("id")) for x in journeys if x.get("id")}
    ui_ids = {str(x.get("id")) for x in ui if x.get("id")}
    errors: list[str] = []
    for sl in slices:
        for ref in sl.get("closes_journeys") or sl.get("journey_refs") or []:
            if str(ref) not in journey_ids:
                errors.append(f"{sl.get('id')}: unknown journey {ref}")
    return _print_json({"ok": not errors, "journeys": sorted(journey_ids), "ui": sorted(ui_ids), "errors": errors}, 0 if not errors else 2)


def check_journey_matrix(argv: list[str]) -> int:
    inp = load_orchestrator_input()
    journeys = inp.get("logic", {}).get("journey", []) or []
    slices = inp.get("slices", []) or []
    closed_by: dict[str, list[str]] = {str(j.get("id")): [] for j in journeys if j.get("id")}
    for sl in slices:
        for j in sl.get("closes_journeys") or sl.get("journey_refs") or []:
            closed_by.setdefault(str(j), []).append(str(sl.get("id")))
    warnings = [j for j, ids in closed_by.items() if not ids]
    return _print_json({"ok": True, "journeys": closed_by, "warnings": [f"journey {j} not closed by any slice" for j in warnings]})


def list_journey_closures(argv: list[str]) -> int:
    reg = load_registry()
    out: dict[str, list[str]] = {}
    for t in reg.get("tasks", []) or []:
        for j in t.get("closes_journeys") or t.get("journey_refs") or []:
            out.setdefault(str(j), []).append(str(t.get("id")))
    return _print_json({"ok": True, "journey_closures": out})


def check_wiring_contract(argv: list[str]) -> int:
    reg = load_registry()
    inp = load_orchestrator_input()
    symbols: set[str] = set()
    for item in inp.get("building_blocks", []) or []:
        if item.get("id"): symbols.add(str(item.get("id")))
    for group in (inp.get("logic") or {}).values():
        for item in group or []:
            if isinstance(item, dict) and item.get("id"): symbols.add(str(item.get("id")))
    for group in (inp.get("auxiliary") or {}).values():
        for item in group or []:
            if isinstance(item, dict) and item.get("id"): symbols.add(str(item.get("id")))
    for sl in inp.get("slices", []) or []:
        if sl.get("id"): symbols.add(str(sl.get("id")))
    errors: list[str] = []
    for task in reg.get("tasks", []) or []:
        for key in ("implements", "builds", "verification_refs", "building_block_refs"):
            for ref in task.get(key) or []:
                if str(ref) not in symbols:
                    errors.append(f"{task.get('id')} {key} unknown ref {ref}")
    return _print_json({"ok": not errors, "errors": errors}, 0 if not errors else 2)


def _handoff_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current = "preamble"
    buf: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("## "):
            if buf:
                sections.append((current, "\n".join(buf)))
            current = line[3:].strip().lower()
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append((current, "\n".join(buf)))
    return sections


def _all_explicit_handoff_trailers(text: str) -> list[dict[str, str]]:
    trailers: list[dict[str, str]] = []
    for heading, body in _handoff_sections(text):
        for part in body.split("CLAUDE_TRAILER:")[1:]:
            parsed = _parse_trailers("CLAUDE_TRAILER:" + part)
            if parsed:
                parsed[-1]["_section"] = heading
                trailers.append(parsed[-1])
    return trailers


def _role_handoff_trailer(text: str, role: str) -> dict[str, str]:
    role_key = (role or "").lower().replace("_", "-")
    candidates: list[dict[str, str]] = []
    for trailer in _all_explicit_handoff_trailers(text):
        agent = trailer.get("agent", "").lower().replace("_", "-")
        section = trailer.get("_section", "").lower().replace("_", "-")
        if agent == role_key or (not agent and role_key in section):
            candidates.append(trailer)
    return candidates[-1] if candidates else {}


def check_handoff_contract(argv: list[str]) -> int:
    explicit_task_arg = any((not str(a).startswith("-")) for a in argv) or any(a in argv for a in ("--task-id", "--task_id", "--task"))
    tid, rest = _task_id_arg(argv, required=True) if explicit_task_arg else (None, list(argv))
    if not explicit_task_arg:
        # Static CI/doctor mode: generated task-packs must contain role-scoped
        # trailer examples, and any existing runtime handoff files must validate.
        # A fresh bootstrap has no handoff ledgers yet, so their absence is not a
        # failure in this mode. Role-specific gates still call this command with
        # TASK_ID plus --require-* flags.
        errors: list[str] = []
        warnings: list[str] = []
        root = project_root()
        pack_dir = tasks_dir() / "task-packs"
        required_roles = [
            "developer",
            "debugger",
            "tester",
            "slice-verifier",
            "deployer",
            "validator",
            "screen-journey-reviewer",
            "closer",
        ]
        def _read_text_retry(path: Path, attempts: int = 20) -> str:
            last_exc: Exception | None = None
            for _ in range(attempts):
                try:
                    if path.exists() and path.stat().st_size > 0:
                        return path.read_text(encoding="utf-8", errors="replace")
                except Exception as exc:  # macOS/Linux fast-filesystem or hook race
                    last_exc = exc
                import time
                time.sleep(0.05)
            if last_exc:
                raise last_exc
            return ""

        task_pack_count = 0
        parsed_examples = 0
        for md in sorted(pack_dir.glob("*.md")) if pack_dir.exists() else []:
            task_pack_count += 1
            text = _read_text_retry(md)
            trailers = _parse_trailers(text)
            parsed_examples += len(trailers)
            by_role = {t.get("agent", "").lower().replace("_", "-"): t for t in trailers}
            for role in required_roles:
                trailer = by_role.get(role)
                if not trailer:
                    errors.append(f"{md.relative_to(root)} missing parseable trailer example for {role}")
                    continue
                local = _validate_trailer_dict(role, trailer, md.stem)
                errors.extend(f"{md.relative_to(root)} {role}: {e}" for e in local)
            if "CLAUDE_TRAILER:" not in text:
                errors.append(f"{md.relative_to(root)} missing CLAUDE_TRAILER marker")
            if "HANDOFF: orchestrator-state/tasks/handoffs/" not in text:
                errors.append(f"{md.relative_to(root)} missing handoff path in trailer examples")
            if "EVIDENCE: orchestrator-state/tasks/evidence/" not in text:
                warnings.append(f"{md.relative_to(root)} has no evidence trailer example")
            if "REPORT: orchestrator-state/tasks/reports/" not in text:
                warnings.append(f"{md.relative_to(root)} has no report trailer example")
        handoff_dir = tasks_dir() / "handoffs"
        checked = 0
        for hf in sorted(handoff_dir.glob("*.md")) if handoff_dir.exists() else []:
            checked += 1
            res = validate_handoff(hf.stem, [])
            errors.extend(f"{hf.stem}: {e}" for e in res.get("errors", []))
        return _print_json({
            "ok": not errors,
            "mode": "static",
            "task_packs": task_pack_count,
            "parsed_trailer_examples": parsed_examples,
            "handoffs_checked": checked,
            "errors": sorted(set(errors)),
            "warnings": sorted(set(warnings)),
        }, 0 if not errors else 3)
    roles_required: list[str] = []
    flag_to_role = {
        "--require-developer": "developer",
        "--require-debugger": "debugger",
        "--require-tester": "tester",
        "--require-ready-for-close": "tester",
        "--require-verify-slice": "slice-verifier",
        "--require-slice-verifier": "slice-verifier",
        "--require-deployer": "deployer",
        "--require-validator": "validator",
        "--require-screen-journey-reviewer": "screen-journey-reviewer",
        "--require-closer": "closer",
    }
    for flag, role in flag_to_role.items():
        if flag in rest and role not in roles_required:
            roles_required.append(role)
    result = validate_handoff(
        tid,
        roles_required,
        require_verify_slice=("--require-verify-slice" in rest or "--require-slice-verifier" in rest),
        require_ready_for_close=("--require-ready-for-close" in rest),
        require_closer_done=("--require-closer" in rest),
    )
    # Optional role flags remain accepted. They are validated through role/evidence sections
    # when those roles are required; otherwise they are runtime contract no-ops.
    return _print_json(result, 0 if result.get("ok") else 3)

def _verify_slice_handoff_template(task: dict[str, Any]) -> str:
    tid = str(task.get("id") or task.get("task_id") or "<TASK_ID>")
    surface = task.get("verification_surface") or classify_task_verification(task)
    visual = bool(surface.get("requires_visual_mcp"))
    categories = [str(x) for x in (surface.get("required_evidence_categories") or []) if str(x).strip()]
    if not categories:
        categories = [str(c.get("kind")) for c in (surface.get("evidence_matrix") or []) if isinstance(c, dict) and c.get("required")]
    if visual:
        modality = "ui_visual"
        mcp = "chrome-devtools|claude-in-chrome|agent360-browser-mcp|browser-mcp"
        visual_method = "browser" if str(surface.get("visual_mode") or "web") != "mobile" else "simulator|emulator|device"
    else:
        modality = "backend"
        mcp = "not_applicable:no_ui_surface"
        visual_method = "backend"
    if categories:
        category_lines = "\n".join(f"- EVIDENCE_{c.upper()}: <real command/output/log/db proof or not_applicable:reason>" for c in categories)
    else:
        category_lines = "- EVIDENCE_RUNTIME_CONTRACT_FALLBACK: <real command/output proof>"
    template = f"""
## verify-slice

VERIFY_MODALITY: {modality}
MCP_BROWSER: {mcp}
VISUAL_CHECK_METHOD: {visual_method}
HARD_RESET_OR_NOT_APPLICABLE: <yes|not_applicable:reason>
REAL_OR_PROVIDED_DATA_USED: <yes>
REAL_DATA_SOURCE: <real data/migration/wheel/command source>
NO_STUB_DATA: <yes>
FLOWS_TESTED: <real commands or human flows executed>
DATA_SETUP: <reset/migrations/seed/provider/dependency setup>
DATA_CONTRACT_ROWS: <row count or not_applicable:reason>
PERSISTED_DATA_OBSERVED: <yes|not_applicable:reason>
RUNTIME_LOGS_CHECKED: <yes>
ERROR_LOGS_STATUS: <clean>
RUNTIME_LOG_ERRORS: <0>
RUNTIME_COMMAND_OUTPUT_CAPTURED: <yes>
EVIDENCE: orchestrator-state/tasks/evidence/{tid}/slice-verifier.json
{category_lines}

### Verification result table

| Area checked | Method/evidence | Expected | Observed | Status | Follow-up needed |
|---|---|---|---|---|---|
| <ui/backend/db/logs/worker/dependency/core> | <real command, MCP step, DB query, log path or evidence file> | <expected contract> | <observed fact> | <pass|fail|blocked> | <none|FU candidate with reason> |

FOLLOWUP_CANDIDATE: <no|yes>
FOLLOWUP_SCOPE_CLASSIFICATION: <out_of_scope|missing_coverage|missing_real_data|external_dependency|future_enhancement|scope_expansion|blocked_by_human_decision|not_applicable>
FOLLOWUP_WHY_NOT_DEBUGGER: <reason or not_applicable>
FOLLOWUP_TITLE: <title or not_applicable>
FOLLOWUP_SEVERITY: <blocker|critical|high|medium|low|not_applicable>
"""
    return template.lstrip()


def _ensure_verify_slice_section(path: Path, task: dict[str, Any]) -> None:
    with file_lock(path):
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        if "## verify-slice" in text.lower():
            return
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(text + "\n" + _verify_slice_handoff_template(task), encoding="utf-8")


def init_verify_slice_handoff(argv: list[str]) -> int:
    tid, _ = _task_id_arg(argv, required=True)
    ensure_dirs()
    reg = load_registry()
    task = find_task(reg, tid) or {"id": tid, "title": tid}
    path = ensure_handoff_header(tid, task)
    _ensure_verify_slice_section(path, task)
    try:
        from orchestrator.runtime.memory_yaml import update_handoff_index
        update_handoff_index(tid)
    except Exception:
        pass
    evidence_dir(tid).mkdir(parents=True, exist_ok=True)
    return _ok(task_id=tid, handoff=str(path), evidence_contract="verify-slice-real-runtime")

def auto_verify_slice(argv: list[str]) -> int:
    tid, _ = _task_id_arg(argv, required=True)
    reg = load_registry(); task = find_task(reg, tid)
    if not task: return _fail("task not found", 2, task_id=tid)
    return _print_json({
        "ok": False,
        "task_id": tid,
        "status": task.get("status"),
        "error": "auto_verify_slice is disabled as a lifecycle mutation; use verify-slice with real UI/backend evidence",
        "required_gate": "slice-verifier CLAUDE_TRAILER plus ## verify-slice handoff/evidence contract",
    }, 3)


def verify_slice_state(argv: list[str]) -> int:
    tid, _ = _task_id_arg(argv, required=True)
    reg = load_registry(); task = find_task(reg, tid)
    if not task: return _fail("task not found", 2, task_id=tid)
    status = str(task.get("status"))
    action = {
        "ready_for_close": "invoke_slice_verifier",
        "verified_pending_close": "invoke_closer",
        "done": "post_closer_done",
        "needs_debug": "invoke_debugger",
        "validator_tester_pending": "wait_validator_tester",
        "ready": "invoke_next_slice",
        "claimed": "continue_next_slice",
        "in_progress": "continue_next_slice",
        "todo": "wait_dependencies",
    }.get(status, "blocked")
    routing = classify_task_verification(task)
    return _print_json({"ok": True, "task_id": tid, "status": status, "action": action, "verify_routing": routing})


def check_phase_gate(argv: list[str]) -> int:
    phase = next((a for a in argv if not a.startswith("-")), None)
    if not phase: return _fail("missing PHASE_ID", 2)
    reg = load_registry(); tasks = [t for t in reg.get("tasks", []) if str(t.get("phase_id")) == phase]
    not_done = [t.get("id") for t in tasks if t.get("status") != "done"]
    return _print_json({"ok": not not_done, "phase_id": phase, "tasks": len(tasks), "not_done": not_done}, 0 if not not_done else 3)


def inspect_task_state(argv: list[str]) -> int:
    tid, _ = _task_id_arg(argv, required=False)
    reg = load_registry()
    if tid:
        return _print_json(find_task(reg, tid) or {"ok": False, "error": "task not found", "task_id": tid}, 0)
    return _print_json({"tasks": [{"id": t.get("id"), "title": t.get("title"), "description": t.get("description"), "status": t.get("status"), "phase_id": t.get("phase_id")} for t in reg.get("tasks", [])]})


def _arg_value(argv: list[str], *names: str) -> str | None:
    for name in names:
        if name in argv:
            idx = argv.index(name)
            if idx + 1 < len(argv):
                return argv[idx + 1]
    return None


def _render_template(template: Any, *, task_id: str, slug: str) -> str:
    text = str(template if template is not None else "").strip() or "{task_slug}"
    replacements = {"task_slug": slug, "TASK_SLUG": slug, "task_id": task_id, "TASK_ID": task_id}
    for key, value in replacements.items():
        text = re.sub(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", value, text)
        text = text.replace("{" + key + "}", value).replace("${" + key + "}", value)
        text = re.sub(r"(?<![A-Za-z0-9_])\$" + re.escape(key) + r"\b", value, text)
    return text


def _normalize_compose_project(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-_")
    raw = re.sub(r"[-_]{2,}", lambda m: m.group(0)[0], raw)
    if not raw:
        raw = "orchestrator-slice"
    if not re.match(r"^[a-z0-9]", raw):
        raw = "p-" + raw
    return raw


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "false", "off", "auto"}:
            return []
        if text.startswith("[") and text.endswith("]"):
            body = text[1:-1].strip()
            items = [x.strip().strip("'\"") for x in body.split(",") if x.strip()] if body else []
        elif "," in text:
            items = [x.strip() for x in text.split(",")]
        else:
            items = [text]
    out: list[str] = []
    for item in items:
        text = str(item).strip().strip("'\"")
        if text and text.lower() not in {"none", "null", "false", "off", "auto"} and text not in out:
            out.append(text)
    return out



def task_slug(task_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_.-]+", "-", str(task_id).lower()).strip(".-_")
    cleaned = re.sub(r"-+", "-", cleaned)
    if not cleaned:
        cleaned = "orchestrator-slice"
    if not re.match(r"^[a-z0-9]", cleaned):
        cleaned = "p-" + cleaned
    return cleaned

def _stack_profile_for_runtime() -> dict[str, Any]:
    from . import runtime_ops as _runtime_ops  # type: ignore
    return {}


def _runtime_profile() -> dict[str, Any]:
    # Reuse compiled stack directly to avoid importing .claude/bin modules from hooks.
    inp = load_orchestrator_input()
    stack = inp.get("stack") if isinstance(inp.get("stack"), dict) else {}
    runtime = stack.get("runtime") if isinstance(stack.get("runtime"), dict) else {}
    verification = stack.get("verification") if isinstance(stack.get("verification"), dict) else {}
    return {"stack": stack, "runtime": runtime, "verification": verification}


def _runtime_context(root: Path, task_id: str, *, workspace_root: Path | None = None, project: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    workspace = (workspace_root or root).resolve()
    slug = task_slug(task_id)
    profile = _runtime_profile()
    verification = profile.get("verification") or {}
    docker = verification.get("docker") if isinstance(verification.get("docker"), dict) else {}
    template = project or docker.get("compose_project_template") or "{task_slug}"
    compose_project = _normalize_compose_project(_render_template(template, task_id=task_id, slug=slug))
    candidates: list[str] = []
    explicit = False
    runtime = profile.get("runtime") or {}
    for raw in (docker.get("compose_file"), docker.get("compose_files"), runtime.get("compose_file"), runtime.get("compose_files")):
        vals = _as_list(raw)
        if vals:
            candidates.extend(vals); explicit = True
    if not candidates:
        candidates = ["compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"]
        explicit = False
    resolved: list[dict[str, Any]] = []
    existing: list[str] = []
    for rel in candidates:
        rendered = _render_template(rel, task_id=task_id, slug=slug)
        path = Path(rendered)
        abs_path = path if path.is_absolute() else workspace / path
        rec = {"configured": rel, "path": str(path), "abs_path": str(abs_path), "exists": abs_path.is_file()}
        resolved.append(rec)
        if rec["exists"]:
            try:
                existing.append(str(abs_path.relative_to(workspace)))
            except Exception:
                existing.append(str(abs_path))
    return {
        "task_id": task_id,
        "task_slug": slug,
        "compose_project_name": compose_project,
        "root": str(root),
        "workspace_root": str(workspace),
        "task_pack": str(task_pack_path(task_id)),
        "handoff": str(handoff_path(task_id)),
        "compose_files_configured": candidates,
        "compose_files_explicit": explicit,
        "compose_files": resolved,
        "existing_compose_files": existing,
        "first_compose_file": existing[0] if existing else "",
        "profile_source": "orchestrator-state/compiled/orchestrator-input.json:stack",
    }


def _shell_exports(ctx: dict[str, Any]) -> str:
    existing = ":".join(ctx.get("existing_compose_files") or [])
    configured = ":".join(str(x) for x in (ctx.get("compose_files_configured") or []))
    lines = [
        f"export CLAUDE_ACTIVE_TASK_ID={shlex.quote(str(ctx['task_id']))}",
        f"export TASK_ID={shlex.quote(str(ctx['task_id']))}",
        f"export TASK_SLUG={shlex.quote(str(ctx['task_slug']))}",
        f"export COMPOSE_PROJECT_NAME={shlex.quote(str(ctx['compose_project_name']))}",
        f"export CLAUDE_COMPOSE_PROJECT_NAME={shlex.quote(str(ctx['compose_project_name']))}",
        f"export CLAUDE_RUNTIME_COMPOSE_FILES={shlex.quote(existing)}",
        f"export CLAUDE_RUNTIME_COMPOSE_FILES_CONFIGURED={shlex.quote(configured)}",
        f"export CLAUDE_COMPOSE_FILE={shlex.quote(str(ctx.get('first_compose_file') or ''))}",
        f"export CLAUDE_COMPOSE_FILE_EXISTS={shlex.quote('yes' if ctx.get('first_compose_file') else 'no')}",
        f"export CLAUDE_RUNTIME_COMPOSE_FILES_EXPLICIT={shlex.quote('yes' if ctx.get('compose_files_explicit') else 'no')}",
    ]
    return "\n".join(lines) + "\n"


def runtime_context(argv: list[str]) -> int:
    root_raw = _arg_value(argv, "--root")
    workspace_raw = _arg_value(argv, "--workspace-root")
    project = _arg_value(argv, "--project")
    tid = _arg_value(argv, "--task", "--task-id", "--task_id")
    if not tid:
        tid, _ = _task_id_arg(argv, required=False)
    tid = tid or "unknown"
    root = Path(root_raw).resolve() if root_raw else project_root()
    workspace = Path(workspace_raw).resolve() if workspace_raw else root
    ctx = _runtime_context(root, tid, workspace_root=workspace, project=project)
    if "--shell" in argv or "--env" in argv or "--print-env" in argv:
        print(_shell_exports(ctx), end="")
        return 0
    return _print_json(ctx)


def _is_free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", int(port)))
            return True
        except OSError:
            return False


def _port_contract() -> tuple[dict[str, int], dict[str, str], int]:
    profile = _runtime_profile()
    runtime = profile.get("runtime") or {}
    defaults = {"frontend": 3000, "backend": 8000, "api": 8080, "db": 5432, "worker": 9000}
    env_names = {"frontend": "CLAUDE_FRONTEND_PORT", "backend": "CLAUDE_BACKEND_PORT", "api": "CLAUDE_API_PORT", "db": "CLAUDE_DB_PORT", "worker": "CLAUDE_WORKER_PORT"}
    if isinstance(runtime.get("port_defaults"), dict):
        for key, value in runtime.get("port_defaults", {}).items():
            try:
                defaults[str(key)] = int(value)
            except Exception:
                pass
    if isinstance(runtime.get("port_env"), dict):
        for key, value in runtime.get("port_env", {}).items():
            if str(value).strip():
                env_names[str(key)] = str(value).strip()
    try:
        span = int(runtime.get("port_scan_span") or 2000)
    except Exception:
        span = 2000
    return defaults, env_names, max(20, span)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "): ]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def _reserved_ports(ports_dir: Path, current_env_file: Path) -> set[int]:
    reserved: set[int] = set()
    for path in ports_dir.glob("*.env"):
        try:
            if path.resolve() == current_env_file.resolve():
                continue
        except Exception:
            pass
        for value in _parse_env_file(path).values():
            if re.fullmatch(r"\d+", value):
                reserved.add(int(value))
    return reserved


def _candidate_ports(base: int, slug: str, key: str, span: int) -> list[int]:
    digest = hashlib.sha256(f"{slug}:{key}".encode("utf-8")).hexdigest()
    offset = int(digest[:8], 16) % span
    out = [base]
    for idx in range(span):
        port = base + ((offset + idx) % span)
        if 0 < port <= 65535 and port not in out:
            out.append(port)
    return out


def _write_port_outputs(env_file: Path, *, task_id: str, slug: str, compose_project: str, ports: dict[str, int], env_names: dict[str, str], reused: bool) -> dict[str, Any]:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    json_file = env_file.with_suffix(".json")
    lines = [
        "# Auto-generated by .claude/bin/allocate_slice_ports.py",
        "# Runtime-only. Do not commit.",
        f"export CLAUDE_ACTIVE_TASK_ID={shlex.quote(task_id)}",
        f"export TASK_SLUG={shlex.quote(slug)}",
        f"export COMPOSE_PROJECT_NAME={shlex.quote(compose_project)}",
        f"export CLAUDE_COMPOSE_PROJECT_NAME={shlex.quote(compose_project)}",
        f"export CLAUDE_PORT_ENV_FILE={shlex.quote(str(env_file))}",
    ]
    by_name: dict[str, Any] = {}
    for key in sorted(ports):
        env_name = env_names.get(key) or f"CLAUDE_{key.upper()}_PORT"
        port = ports[key]
        lines.append(f"export {env_name}={shlex.quote(str(port))}")
        lines.append(f"export CLAUDE_{re.sub(r'[^A-Z0-9]+', '_', key.upper()).strip('_')}_URL={shlex.quote('http://localhost:' + str(port))}")
        by_name[key] = {"env": env_name, "port": port, "url": "http://localhost:" + str(port)}
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {"task_id": task_id, "task_slug": slug, "compose_project_name": compose_project, "env_file": str(env_file), "ports": by_name, "reused_existing_env": reused}
    write_json(json_file, payload)
    return payload


def allocate_slice_ports(argv: list[str]) -> int:
    root_raw = _arg_value(argv, "--root")
    env_file_raw = _arg_value(argv, "--env-file")
    tid = _arg_value(argv, "--task", "--task-id", "--task_id")
    if not tid:
        tid, _ = _task_id_arg(argv, required=False)
    tid = tid or "default"
    root = Path(root_raw).resolve() if root_raw else project_root()
    ctx = _runtime_context(root, tid)
    slug = str(ctx.get("task_slug") or task_slug(tid))
    compose_project = str(ctx.get("compose_project_name") or slug)
    env_file = Path(env_file_raw).resolve() if env_file_raw else root / "orchestrator-state" / "dev-ports" / f"{compose_project}.env"
    ports_dir = env_file.parent
    defaults, env_names, span = _port_contract()
    force = "--force" in argv
    with file_lock(ports_dir / ".port-allocation"):
        existing = _parse_env_file(env_file)
        ports: dict[str, int] = {}
        if existing and not force:
            for key, env_name in env_names.items():
                value = existing.get(env_name)
                if value and re.fullmatch(r"\d+", value):
                    ports[key] = int(value)
            if ports and all(_is_free_port(p) for p in ports.values()):
                result = _write_port_outputs(env_file, task_id=tid, slug=slug, compose_project=compose_project, ports=ports, env_names=env_names, reused=True)
                if "--json" in argv:
                    return _print_json(result)
                if "--print-env" in argv:
                    print(env_file.read_text(encoding="utf-8"), end=""); return 0
                print(f"PORT_ALLOCATION: task={tid} project={compose_project} env={env_file}"); return 0
        reserved = _reserved_ports(ports_dir, env_file)
        for key, base in defaults.items():
            env_name = env_names.get(key) or f"CLAUDE_{key.upper()}_PORT"
            explicit = os.environ.get(env_name)
            if explicit and re.fullmatch(r"\d+", explicit):
                ports[key] = int(explicit); reserved.add(int(explicit)); continue
            selected = None
            for candidate in _candidate_ports(int(base), slug, key, span):
                if candidate in reserved:
                    continue
                if _is_free_port(candidate):
                    selected = candidate; break
            if selected is None:
                return _fail(f"no free contract found for {key}", 2)
            ports[key] = selected; reserved.add(selected)
        result = _write_port_outputs(env_file, task_id=tid, slug=slug, compose_project=compose_project, ports=ports, env_names=env_names, reused=False)
    if "--json" in argv:
        return _print_json(result)
    if "--print-env" in argv:
        print(env_file.read_text(encoding="utf-8"), end=""); return 0
    print(f"PORT_ALLOCATION: task={tid} project={compose_project} env={env_file}")
    for key, info in result.get("ports", {}).items():
        print(f"  {key}: {info['env']}={info['port']} {info['url']}")
    return 0


def reset_orchestrator_state(argv: list[str]) -> int:
    root = project_root()
    for rel in ["orchestrator-state/compiled", "orchestrator-state/tasks", "orchestrator-state/memory"]:
        path = root / rel
        if path.exists(): shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    for sub in ["task-packs", "handoffs", "evidence", "reports", "follow-ups", "lifecycle-events"]:
        (tasks_dir() / sub).mkdir(parents=True, exist_ok=True)
    return _ok(reset=True)


def check_runtime_logs(argv: list[str]) -> int:
    task_id = None
    for i, arg in enumerate(argv):
        if arg == "--task" and i + 1 < len(argv):
            task_id = argv[i + 1]
        elif arg.startswith("--task="):
            task_id = arg.split("=", 1)[1]

    errors_path = state_dir() / "hook-errors.log"
    errors = []
    if errors_path.exists():
        lines = errors_path.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
        errors = [line for line in lines if f"task={task_id}" in line] if task_id else lines

    return _print_json(
        {
            "ok": not errors,
            "hook_errors": errors,
            "scoped_task": task_id,
            "ledger_exists": ledger_path().exists(),
            "bash_ledger_exists": bash_ledger_path().exists(),
        },
        0 if not errors else 3,
    )


def check_worktree_deps_visible(argv: list[str]) -> int:
    root = project_root()
    workspace = workspace_root()
    missing = [p for p in [root / "inputs" / "BLUEPRINT.md", root / "orchestrator-state" / "compiled" / "orchestrator-input.json", root / "orchestrator-state" / "tasks" / "registry.json"] if not p.exists()]
    local_core: list[str] = []
    if workspace.resolve() != root.resolve():
        local_state = workspace / "orchestrator-state"
        core_names = {"registry.json", "registry.yaml", "runtime-state.json", "runtime-state.yaml", "task-dag.json", "task-dag.yaml", "task-index.yaml", "handoff-index.yaml", "lifecycle-events.yaml"}
        if local_state.exists() and not local_state.is_symlink():
            for path in local_state.rglob("*"):
                if path.is_file() and ("compiled" in path.parts or path.name in core_names):
                    local_core.append(str(path))
    ok = not missing and not local_core
    return _print_json({"ok": ok, "canonical_root": str(root), "workspace_root": str(workspace), "missing": [str(p) for p in missing], "local_core_state": local_core}, 0 if ok else 2)


def update_journey_verification(argv: list[str]) -> int:
    # Blueprint-first journey gate runtime contract.  Canonical runtime tracked
    # pending journey verifications in runtime-state;  keeps the behavior
    # while deriving journey ownership from registry.slices.
    jid = next((a for a in argv if a and not a.startswith("--")), None)
    verified = "--verified" in argv
    waived = "--waived" in argv or "--waive" in argv
    issues = "--issues-found" in argv or "--issues" in argv
    out = tasks_dir() / "journey-verification.json"
    reg = load_registry()
    closures: dict[str, list[str]] = {}
    for t in reg.get("tasks", []) or []:
        for j in t.get("closes_journeys") or t.get("journey_refs") or []:
            closures.setdefault(str(j), []).append(str(t.get("id")))
    runtime = load_runtime_state()
    pending = [str(x) for x in (runtime.get("pending_journey_verifications") or []) if str(x).strip()]
    event = {"journey_id": jid, "verified": verified, "waived": waived, "issues_found": issues, "at": now_iso()}
    if jid and (verified or waived):
        pending = [x for x in pending if x != jid]
    elif jid and issues and jid not in pending:
        pending.append(jid)
    runtime["pending_journey_verifications"] = pending
    runtime["last_journey_verification"] = event
    save_runtime_state(runtime)
    write_json(out, {"updated_at": now_iso(), "journey_id": jid, "event": event, "pending": pending, "closures": closures})
    return _ok(path=str(out), journey_id=jid, event=event, pending=pending, closures=closures)


def _read_lifecycle_event_file(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                events.append(obj)
            elif isinstance(obj, list):
                events.extend([x for x in obj if isinstance(x, dict)])
        elif path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        events.append(obj)
                except Exception:
                    continue
        elif path.suffix in {".yaml", ".yml"}:
            from orchestrator.runtime.memory_yaml import read_yaml
            obj = read_yaml(path, {})
            if isinstance(obj, dict) and isinstance(obj.get("events"), list):
                events.extend([x for x in obj.get("events") if isinstance(x, dict)])
            elif isinstance(obj, dict):
                events.append(obj)
    except Exception as exc:
        log_hook_error("sync_lifecycle_events.read", f"{path}: {exc}")
    return events


def sync_lifecycle_events(argv: list[str]) -> int:
    # Rehydrates durable lifecycle-events/<TASK_ID>.json target_status values and delegates promote_ready_tasks to the shared helper.
    # check-token: target_status promote_ready_tasks
    from orchestrator.runtime.lifecycle_events import apply_lifecycle_events_to_registry
    reg = load_registry()
    reg, applied, skipped = apply_lifecycle_events_to_registry(reg)
    save_registry(reg)
    try:
        rt = load_runtime_state()
        rt["last_lifecycle_sync"] = {"at": now_iso(), "applied": len(applied), "skipped": len(skipped), "source": "runtime_ops"}
        save_runtime_state(rt)
    except Exception as exc:
        log_hook_error("sync_lifecycle_events.runtime", exc)
    try:
        from orchestrator.runtime.memory_yaml import write_memory_snapshot, append_lifecycle_event
        if applied:
            append_lifecycle_event({"kind": "sync_lifecycle_events", "applied": applied})
        write_memory_snapshot(registry=reg)
    except Exception as exc:
        log_hook_error("sync_lifecycle_events.memory", exc)
    return _ok(lifecycle_events_applied=True, applied=applied, applied_count=len(applied), skipped=skipped, skipped_count=len(skipped))


def write_lifecycle_event(argv: list[str]) -> int:
    tid, rest = _task_id_arg(argv, required=False)
    event = {"ts": now_iso(), "task_id": tid, "args": rest}
    path = tasks_dir() / "lifecycle-events" / f"{tid or 'global'}.jsonl"
    append_jsonl(path, event)
    return _ok(path=str(path))


def runtime_git_guard(argv: list[str]) -> int:
    mode = next((a for a in argv if not a.startswith("--")), "status")
    labels = {"backup": "RUNTIME_PATHS_PROTECTED", "restore": "RUNTIME_PATHS_RESTORED", "status": "RUNTIME_GIT_PROTECTED"}
    print(f"{labels.get(mode, 'RUNTIME_GIT_PROTECTED')}: yes")
    print(f"ROOT: {project_root()}")
    return 0


def sync_runtime_snapshot(argv: list[str]) -> int:
    """Snapshot compiled blueprint runtime artifacts for audit after verified close.

    This is not a product source tree or secondary input contract. It copies only
    generated blueprint runtime artifacts so closer can provide durable closure
    evidence without creating another source of truth.
    """
    task_id = next((a for a in argv if a and not a.startswith("--")), None) or "global"
    out = tasks_dir() / "runtime-snapshots" / task_id
    out.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    candidates = [
        compiled_dir() / "orchestrator-input.json",
        compiled_dir() / "BLUEPRINT.snapshot.md",
        compiled_dir() / "blueprint-manifest.json",
        compiled_dir() / "blueprint-lossless.json",
        compiled_dir() / "source-map.json",
    ]
    for src in candidates:
        if src.exists():
            dst = out / src.name
            shutil.copy2(src, dst)
            copied.append(str(dst.relative_to(project_root())))
    manifest = {
        "kind": "runtime_snapshot",
        "task_id": task_id,
        "created_at": now_iso(),
        "copied": copied,
        "source": "inputs/BLUEPRINT.md compiled artifacts",
        "policy": "audit snapshot only; inputs/BLUEPRINT.md remains the single human input",
    }
    write_json(out / "manifest.json", manifest)
    return _ok(snapshot_dir=str(out), copied=len(copied), files=copied)


def generate_api_contracts(argv: list[str]) -> int:
    inp = load_orchestrator_input()
    api_items = [x for x in (inp.get("auxiliary", {}).get("data", []) or []) if str(x.get("id", "")).startswith("API-")]
    out = compiled_dir() / "api-contracts.json"
    write_json(out, {"generated_at": now_iso(), "api_contracts": api_items})
    return _ok(api_contracts=len(api_items), path=str(out))


FOLLOWUP_SCOPE_CLASSIFICATIONS = {
    "out_of_scope",
    "missing_coverage",
    "missing_real_data",
    "external_dependency",
    "future_enhancement",
    "scope_expansion",
    "blocked_by_human_decision",
}
FOLLOWUP_REJECTED_SCOPE = "in_scope_defect"
FOLLOWUP_SEVERITIES = {"blocker", "critical", "high", "medium", "low"}
FOLLOWUP_BLOCKING_SEVERITIES = {"blocker", "critical", "high"}

FOLLOWUP_REPAIR_DECISIONS = {
    "followup_required",
    "human_decision_required",
    "fix_in_current_slice",
    "debugger_retest",
    "mechanical_retry",
}
FOLLOWUP_LOCAL_REPAIR_DECISIONS = {"fix_in_current_slice", "debugger_retest", "mechanical_retry"}
YES_VALUES = {"1", "true", "yes", "y", "si", "sí"}
NO_VALUES = {"0", "false", "no", "n"}
UNKNOWN_VALUES = {"", "unknown", "unk", "n/a", "na", "not_applicable"}


def _followup_dir() -> Path:
    directory = tasks_dir() / "follow-ups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _followup_patch_dir() -> Path:
    directory = tasks_dir() / "source-doc-patches"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _followup_id(origin_task_id: str) -> str:
    stamp = re.sub(r"[^0-9A-Za-z_-]", "", now_iso())
    return f"FU-{origin_task_id}-{stamp}"


def _load_followup(path: Path) -> dict[str, Any]:
    data = read_yaml(path, {}) or {}
    if not isinstance(data, dict):
        raise ValueError(f"follow-up file is not a mapping: {path}")
    return data


def _write_followup(path: Path, data: dict[str, Any]) -> None:
    write_yaml(path, data)


def _arg_value(argv: list[str], *names: str, default: str = "") -> str:
    for name in names:
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return str(argv[i + 1])
    return default


def _list_arg_values(argv: list[str], *names: str) -> list[str]:
    out: list[str] = []
    for i, item in enumerate(argv):
        if item in names and i + 1 < len(argv):
            out.append(str(argv[i + 1]))
    return out


def _normal_bool(raw: str | None) -> bool | None:
    val = (raw or "").strip().lower()
    if val in YES_VALUES:
        return True
    if val in NO_VALUES:
        return False
    if val in UNKNOWN_VALUES:
        return None
    return None


def _bool_arg(argv: list[str], *names: str) -> bool | None:
    value = _arg_value(argv, *names, default="")
    return _normal_bool(value)


def _int_arg(argv: list[str], *names: str) -> int | None:
    value = _arg_value(argv, *names, default="").strip().lower()
    if value in UNKNOWN_VALUES:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _followup_help() -> dict[str, Any]:
    return {
        "usage": [
            "register-followup-task.sh propose --origin-task <TASK_ID> --scope-classification <classification> --repair-decision <followup_required|human_decision_required> --why-not-debugger <reason> --title <title> --severity <blocker|critical|high|medium|low> [--description <text>] [--write-set <path>] [--verify <text>] [--files-estimate <n|unknown>] [--fits-current-write-set yes|no|unknown] [--outside-current-write-set yes|no|unknown] [--requires-blueprint-change yes|no|unknown] [--requires-new-dependency yes|no|unknown] [--requires-human-decision yes|no|unknown] [--missing-real-data yes|no|unknown]",
            "register-followup-task.sh waive <FOLLOWUP_ID> --reason <human decision>",
            "register-followup-task.sh promote <FOLLOWUP_ID>",
        ],
        "scope_classifications": sorted(FOLLOWUP_SCOPE_CLASSIFICATIONS),
        "rejected_scope_classification": FOLLOWUP_REJECTED_SCOPE,
        "repair_decisions": sorted(FOLLOWUP_REPAIR_DECISIONS),
        "local_repair_decisions_rejected": sorted(FOLLOWUP_LOCAL_REPAIR_DECISIONS),
        "policy": "In-scope or small fixes that fit the active TASK_ID stay in that slice and go through developer/debugger/retest. Follow-ups require an explicit repair-decision plus a hard trigger such as outside write_set, blueprint change, new dependency, missing real data or human decision.",
    }


def _propose_followup(argv: list[str]) -> int:
    tid = _arg_value(argv, "--origin-task", "--origin_task", "--task", "--task-id")
    if not tid:
        tid, _ = _task_id_arg(argv, required=False)
    title = _arg_value(argv, "--title", default="")
    description = _arg_value(argv, "--description", "--details", default="")
    scope = _arg_value(argv, "--scope-classification", "--scope", default="")
    why = _arg_value(argv, "--why-not-debugger", default="")
    severity = _arg_value(argv, "--severity", default="medium").lower().strip()
    verify = _arg_value(argv, "--verify", "--verify-minimum", default="")
    source_ref = _arg_value(argv, "--source-ref", default="")
    repair_decision = _arg_value(argv, "--repair-decision", "--active-slice-repair", default="").strip().lower()
    files_estimate = _int_arg(argv, "--files-estimate", "--estimated-files", "--touched-files-estimate")
    fits_current_write_set = _bool_arg(argv, "--fits-current-write-set", "--fits-write-set", "--inside-current-write-set")
    outside_current_write_set = _bool_arg(argv, "--outside-current-write-set", "--outside-write-set")
    if outside_current_write_set is None and fits_current_write_set is not None:
        outside_current_write_set = not fits_current_write_set
    requires_blueprint_change = _bool_arg(argv, "--requires-blueprint-change", "--requires-new-blueprint-ids", "--needs-blueprint-change")
    requires_new_dependency = _bool_arg(argv, "--requires-new-dependency", "--new-dependency")
    requires_human_decision = _bool_arg(argv, "--requires-human-decision", "--human-decision")
    missing_real_data_flag = _bool_arg(argv, "--missing-real-data", "--requires-real-data")
    mechanical_runtime_issue = _bool_arg(argv, "--mechanical-runtime-issue", "--runtime-issue")
    if not tid:
        return _fail("missing --origin-task <TASK_ID>", usage=_followup_help())
    if not title:
        # Backward-compatible fallback: any positional words after TASK_ID become the title.
        positional = [x for x in argv if not x.startswith("-")]
        if positional and positional[0] in {"propose", tid}:
            positional = positional[1:]
        title = " ".join(positional) or f"Follow-up from {tid}"
    if scope == FOLLOWUP_REJECTED_SCOPE:
        return _fail("in_scope_defect is not a valid follow-up; use debugger/retest inside the active TASK_ID", code=3)
    if scope not in FOLLOWUP_SCOPE_CLASSIFICATIONS:
        return _fail("invalid or missing scope classification", allowed=sorted(FOLLOWUP_SCOPE_CLASSIFICATIONS), rejected=FOLLOWUP_REJECTED_SCOPE)
    if severity not in FOLLOWUP_SEVERITIES:
        return _fail("invalid severity", allowed=sorted(FOLLOWUP_SEVERITIES))
    if not repair_decision:
        return _fail("missing --repair-decision; choose followup_required only after checking that the work cannot be fixed in the active slice", allowed=sorted(FOLLOWUP_REPAIR_DECISIONS))
    if repair_decision not in FOLLOWUP_REPAIR_DECISIONS:
        return _fail("invalid --repair-decision", allowed=sorted(FOLLOWUP_REPAIR_DECISIONS))
    if repair_decision in FOLLOWUP_LOCAL_REPAIR_DECISIONS:
        return _fail(
            "not a follow-up: this must be corrected inside the active TASK_ID via developer/debugger/retest",
            code=3,
            repair_decision=repair_decision,
            next_action="return to debugger/retest or retry the mechanical step in the same slice",
        )
    if mechanical_runtime_issue is True:
        return _fail(
            "not a product follow-up: mechanical orchestrator/runtime issues must be corrected, retried or blocked mechanically in the same slice",
            code=3,
            next_action="fix/retry the runtime issue; do not open a product FU",
        )
    if not why:
        return _fail("missing --why-not-debugger; every follow-up must explain why debugger/retest cannot solve it inside the active TASK_ID")

    hard_triggers = {
        "outside_current_write_set": outside_current_write_set is True,
        "requires_blueprint_change": requires_blueprint_change is True or scope == "scope_expansion",
        "requires_new_dependency": requires_new_dependency is True or scope == "external_dependency",
        "missing_real_data": missing_real_data_flag is True or scope == "missing_real_data",
        "requires_human_decision": requires_human_decision is True or repair_decision == "human_decision_required" or scope == "blocked_by_human_decision",
    }
    if (
        files_estimate is not None
        and files_estimate <= 3
        and fits_current_write_set is True
        and requires_blueprint_change is not True
        and requires_new_dependency is not True
        and missing_real_data_flag is not True
        and requires_human_decision is not True
        and scope not in {"external_dependency", "missing_real_data", "scope_expansion", "blocked_by_human_decision"}
    ):
        return _fail(
            "not a follow-up: small fix appears to fit the active slice",
            code=3,
            files_estimate=files_estimate,
            fits_current_write_set=True,
            next_action="fix in the active slice or route to debugger/retest",
        )
    if not any(hard_triggers.values()):
        return _fail(
            "follow-up lacks a hard out-of-slice trigger",
            code=3,
            policy="If it fits the current write_set, touches only a few files and needs no blueprint/dependency/human decision, solve it in the current slice via debugger/retest.",
            required_one_of=sorted(hard_triggers),
        )

    fid = _followup_id(tid)
    path = _followup_dir() / f"{fid}.yaml"
    data: dict[str, Any] = {
        "schema_version": "followup.v1",
        "kind": "orchestrator.followup",
        "id": fid,
        "origin_task_id": tid,
        "status": "proposed",
        "title": title,
        "description": description or title,
        "scope_classification": scope,
        "repair_decision": repair_decision,
        "why_not_debugger": why,
        "triage": {
            "files_estimate": files_estimate if files_estimate is not None else "unknown",
            "fits_current_write_set": fits_current_write_set if fits_current_write_set is not None else "unknown",
            "outside_current_write_set": outside_current_write_set if outside_current_write_set is not None else "unknown",
            "requires_blueprint_change": requires_blueprint_change if requires_blueprint_change is not None else "unknown",
            "requires_new_dependency": requires_new_dependency if requires_new_dependency is not None else "unknown",
            "requires_human_decision": requires_human_decision if requires_human_decision is not None else "unknown",
            "missing_real_data": missing_real_data_flag if missing_real_data_flag is not None else "unknown",
            "mechanical_runtime_issue": mechanical_runtime_issue if mechanical_runtime_issue is not None else "unknown",
            "hard_triggers": [name for name, enabled in hard_triggers.items() if enabled],
            "policy": "If a small fix fits the active write_set and needs no blueprint/dependency/human decision, solve it inside the current slice instead of opening a FU.",
        },
        "severity": severity,
        "blocking": severity in FOLLOWUP_BLOCKING_SEVERITIES,
        "created_at": now_iso(),
        "source_ref": source_ref or "handoff/evidence",
        "write_set": _list_arg_values(argv, "--write-set", "--write_set"),
        "verify_minimum": verify or "not_applicable: proposer did not provide a concrete verification command yet",
        "promotion_policy": "Promote by updating inputs/BLUEPRINT.md, then run compile-blueprint and bootstrap-registry. Do not mutate registry/task-dag directly.",
    }
    _write_followup(path, data)
    return _ok(followup_id=fid, file=str(path), status="proposed", blocking=data["blocking"])


def _waive_followup(argv: list[str]) -> int:
    if not argv:
        return _fail("missing FOLLOWUP_ID", usage=_followup_help())
    fid = argv[0]
    reason = _arg_value(argv, "--reason", default="")
    if not reason:
        return _fail("missing --reason <human decision>")
    path = _followup_dir() / f"{fid}.yaml"
    if not path.exists():
        return _fail("follow-up not found", followup_id=fid, file=str(path), code=4)
    data = _load_followup(path)
    data.update({"status": "waived", "waived_at": now_iso(), "waiver_reason": reason})
    _write_followup(path, data)
    return _ok(followup_id=fid, file=str(path), status="waived")


def _promote_followup(argv: list[str]) -> int:
    if not argv:
        return _fail("missing FOLLOWUP_ID", usage=_followup_help())
    fid = argv[0]
    path = _followup_dir() / f"{fid}.yaml"
    if not path.exists():
        return _fail("follow-up not found", followup_id=fid, file=str(path), code=4)
    data = _load_followup(path)
    if data.get("scope_classification") == FOLLOWUP_REJECTED_SCOPE:
        return _fail("in_scope_defect cannot be promoted as a follow-up", followup_id=fid, code=3)
    patch_path = _followup_patch_dir() / f"{fid}.md"
    patch = f"""# Follow-up blueprint patch request: {fid}

Status: promoted_to_blueprint
Origin task: {data.get('origin_task_id', 'unknown')}
Severity: {data.get('severity', 'medium')}
Scope classification: {data.get('scope_classification', 'unknown')}
Repair decision: {data.get('repair_decision', 'unknown')}
Hard triggers: {', '.join((data.get('triage') or {}).get('hard_triggers', []) or ['unknown'])}

## Title

{data.get('title', fid)}

## Description

{data.get('description', '')}

## Why debugger/retest cannot solve it inside the origin TASK_ID

{data.get('why_not_debugger', '')}

## Follow-up triage

```json
{json.dumps(data.get('triage') or {}, indent=2, ensure_ascii=False, sort_keys=True)}
```

## Required operator action

Add this work to `inputs/BLUEPRINT.md` as a normal `registry.slices` item with all required refs, `depends_on`, `write_set`, `conflict_groups`, acceptance and evidence contract. Then run:

```bash
./scripts/compile-blueprint.sh
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-task-dag.sh
```

Do not edit `orchestrator-state/tasks/registry.json` or `task-dag.json` directly.
"""
    patch_path.write_text(patch, encoding="utf-8")
    data.update({"status": "promoted_to_blueprint", "promoted_at": now_iso(), "source_doc_patch": str(patch_path.relative_to(project_root()))})
    _write_followup(path, data)
    return _ok(followup_id=fid, file=str(path), status="promoted_to_blueprint", source_doc_patch=str(patch_path))


def register_followup_task(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        return _print_json({"ok": True, **_followup_help()})
    action = argv[0]
    rest = argv[1:]
    if action == "propose":
        return _propose_followup(rest)
    if action == "waive":
        return _waive_followup(rest)
    if action == "promote":
        return _promote_followup(rest)
    # Backward-compatible short form: <TASK_ID> [title...] becomes propose with
    # explicit safe defaults except the mandatory why-not-debugger rationale.
    if action.startswith("SLICE-") or action.startswith("TASK-") or action.startswith("FU-") is False:
        tid = action
        title = " ".join(rest) or f"Follow-up from {tid}"
        return _propose_followup(["--origin-task", tid, "--scope-classification", "blocked_by_human_decision", "--repair-decision", "human_decision_required", "--requires-human-decision", "yes", "--why-not-debugger", "short form used by operator; human decision is required before this becomes implementation work", "--severity", "medium", "--title", title])
    return _fail(f"unknown follow-up action: {action}", usage=_followup_help())


def check_progress_updated(argv: list[str]) -> int:
    reg = load_registry()
    return _print_json({"ok": True, "tasks": len(reg.get("tasks", [])), "done": len([t for t in reg.get("tasks", []) if t.get("status") == "done"])})


def check_staged_deletions(argv: list[str]) -> int:
    try:
        proc = subprocess.run(["git", "diff", "--cached", "--name-status", "--diff-filter=D"], cwd=project_root(), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        deletions = [line for line in proc.stdout.splitlines() if line.strip()]
    except Exception:
        deletions = []
    return _print_json({"ok": not deletions, "staged_deletions": deletions}, 0 if not deletions else 3)


def design_tokens_check(argv: list[str]) -> int:
    inp = load_orchestrator_input()
    stack = inp.get("stack") or {}
    enforcer = stack.get("enforcer") or stack.get("design_tokens_enforcer") or "none"
    return _print_json({"ok": True, "design_tokens_enforcer": enforcer, "status": "skipped" if str(enforcer).lower() in {"", "none", "null"} else "declared"})


def run_all_tests(argv: list[str]) -> int:
    root = project_root()
    mode = argv[0] if argv and not argv[0].startswith("-") else "all"
    commands = []
    if mode in {"all", "lint"}:
        commands.extend([
            ["bash", "scripts/python-safe.sh", "-m", "compileall", "-q", "orchestrator", ".claude/bin", "scripts"],
            ["bash", "scripts/python-safe.sh", "scripts/check-python-runtime.py", "--min-version", "3.13"],
            ["bash", "scripts/reset-state.sh"],
            ["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"],
            ["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"],
            ["bash", "scripts/check-task-dag.sh"],
            ["bash", "scripts/check-parallel-locks.sh"],
            ["bash", "scripts/check-task-descriptions.sh"],
            ["bash", "scripts/check-blueprint-machine-contract.sh"],
            ["bash", "scripts/check-blueprint-contract.sh"],
            ["bash", "scripts/check-gold-blueprint.sh", "inputs/BLUEPRINT.md"],
            ["bash", "scripts/check-gold-blueprint.sh", "examples/gold/BLUEPRINT.md"],
            ["bash", "scripts/check-orchestrator-gaps.sh"],
            ["bash", "scripts/check-memory-yaml.sh"],
            ["bash", "scripts/check-claude-adapter.sh"],
            ["bash", "scripts/check-skills-runtime.sh"],
            ["bash", "scripts/orchestrator-doctor.sh"],
            ["bash", "scripts/simulate-blueprint-to-claude-flow.sh"],
        ])
    if mode in {"all", "backend", "frontend"}:
        commands.append(["bash", "scripts/python-safe.sh", "-m", "pytest", "-vv", "--cache-clear"])
    results=[]; ok=True
    env=os.environ.copy(); env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", ""); env["CLAUDE_ORCHESTRATOR_ROOT"] = str(root); env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    for cmd in commands:
        label = " ".join(cmd)
        print(f"[run-all-tests] running: {label}", flush=True)
        proc = subprocess.Popen(cmd, cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
        chunks: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            chunks.append(line)
            if len(chunks) > 80:
                chunks = chunks[-80:]
            print(line, end="", flush=True)
        rc = proc.wait()
        tail = "".join(chunks)[-2000:]
        results.append({"cmd": label, "rc": rc, "output_tail": tail})
        print(f"[run-all-tests] rc={rc}: {label}", flush=True)
        ok = ok and rc == 0
    print(json.dumps({"ok": ok, "mode": mode, "results": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 2



def check_gold_blueprint(argv: list[str]) -> int:
    from orchestrator.runtime.check_gold_blueprint import main as gold_main
    return gold_main(argv)


def check_blueprint_contract(argv: list[str]) -> int:
    from orchestrator.runtime.check_blueprint_contract import main as blueprint_main
    return blueprint_main()

def check_orchestrator_gaps(argv: list[str]) -> int:
    from orchestrator.runtime.check_orchestrator_gaps import main as gaps_main
    return gaps_main()


def check_parallel_locks(argv: list[str]) -> int:
    from orchestrator.runtime.check_parallel_locks import main as parallel_main
    return parallel_main()


def check_claude_adapter(argv: list[str]) -> int:
    from orchestrator.runtime.check_claude_adapter import main as adapter_main
    return adapter_main()


def check_memory_yaml(argv: list[str]) -> int:
    from orchestrator.runtime.memory_yaml import main as memory_main
    return memory_main(["check", *argv])


def check_skills_runtime(argv: list[str]) -> int:
    from orchestrator.runtime.check_skills_runtime import main as skills_main
    return skills_main(argv)


def compact_agent_memory(argv: list[str]) -> int:
    import subprocess
    proc = subprocess.run(["python3", "scripts/compact-agent-memory.py", *argv], cwd=project_root(), text=True)
    return proc.returncode


def cleanup_runtime(argv: list[str]) -> int:
    tid, _ = _task_id_arg(argv, required=False)
    return _ok(task_id=tid, cleanup="not_applicable", reason="blueprint-first runtime contract no-op; no task worktree runtime declared")


def unsupported_safe(name: str, argv: list[str]) -> int:
    return _print_json({"ok": True, "command": name, "status": "not_applicable", "reason": "Disabled helper retained as a safe no-op in the blueprint-first orchestrator."})


def ensure_task_worktree(argv: list[str]) -> int:
    if "--print-root" in argv:
        print(project_root())
        return 0
    tid, _ = _task_id_arg(argv, required=False)
    return _ok(task_id=tid, root=str(project_root()), worktree="not_used", reason="blueprint-first runs from canonical root unless a git workflow plugin creates worktrees")


def sync_main_before_wave(argv: list[str]) -> int:
    return _print_json({"ok": True, "synced": False, "reason": "No remote sync performed by this no-op helper. Use git-workflow/pr-flow during closer."})


def setup_from_scratch(argv: list[str]) -> int:
    root = project_root()
    env = os.environ.copy(); env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    steps = [
        ["bash", "scripts/reset-state.sh"],
        ["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"],
        ["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"],
        ["bash", "scripts/orchestrator-doctor.sh"],
    ]
    results=[]; ok=True
    for cmd in steps:
        proc = subprocess.run(cmd, cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({"cmd": " ".join(cmd), "rc": proc.returncode, "output_tail": proc.stdout[-1200:]})
        ok = ok and proc.returncode == 0
        if proc.returncode != 0:
            break
    print(json.dumps({"ok": ok, "results": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 2


def smoke_template_profiles(argv: list[str]) -> int:
    root = project_root()
    env = os.environ.copy(); env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    fixtures = [p for p in [root / "examples" / "smoke" / "BLUEPRINT.md", root / "inputs" / "BLUEPRINT.md"] if p.exists()]
    results=[]; ok=True
    for bp in fixtures:
        proc = subprocess.run(["python3", "-m", "orchestrator.compiler.compile_blueprint", str(bp), "--out", str(compiled_dir()/f"smoke-{bp.parent.name}.json")], cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({"blueprint": str(bp.relative_to(root)), "rc": proc.returncode, "output_tail": proc.stdout[-1200:]})
        ok = ok and proc.returncode == 0
    print(json.dumps({"ok": ok, "fixtures": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 2


def chrome_devtools_isolated_session(argv: list[str]) -> int:
    return _print_json({"ok": True, "status": "not_applicable", "reason": "No Chrome MCP session is required by the blueprint orchestrator core."})


def chrome_mcp_doctor(argv: list[str]) -> int:
    available = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if not available:
        mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if mac.exists():
            available = str(mac)
    return _print_json({"ok": True, "chrome_binary": available, "status": "available" if available else "not_installed_optional", "case_sensitive_note": "MCP server/tool names are exact-case; do not invent Chrome/chrome variants."})


def dev_restart(argv: list[str]) -> int:
    return _print_json({"ok": True, "status": "not_applicable", "reason": "No stack dev command declared for orchestrator core."})


def docker_hard_reset(argv: list[str]) -> int:
    return _print_json({"ok": True, "status": "not_applicable", "reason": "No docker compose runtime declared for orchestrator core."})


def configure_github_pr_cleanup(argv: list[str]) -> int:
    return _print_json({"ok": True, "status": "not_applicable", "reason": "pr-flow cleanup is handled by scripts/git-workflow.sh and .claude/git-workflows/pr-flow.sh."})


COMMANDS = {
    "validate_orchestrator_schemas": validate_orchestrator_schemas,
    "audit_state_machine_contract": audit_state_machine_contract,
    "audit_agent_trailer_vocabulary": audit_agent_trailer_vocabulary,
    "audit_agent_reality": audit_agent_reality,
    "audit_orchestrator_runtime_consistency": audit_orchestrator_runtime_consistency,
    "audit_template_screen_journey_redactor": audit_template_screen_journey_redactor,
    "check_journey_matrix": check_journey_matrix,
    "list_journey_closures": list_journey_closures,
    "check_wiring_contract": check_wiring_contract,
    "check_handoff_contract": check_handoff_contract,
    "init_verify_slice_handoff": init_verify_slice_handoff,
    "auto_verify_slice": auto_verify_slice,
    "verify_slice_state": verify_slice_state,
    "check_phase_gate": check_phase_gate,
    "inspect_task_state": inspect_task_state,
    "runtime_context": runtime_context,
    "allocate_slice_ports": allocate_slice_ports,
    "reset_orchestrator_state": reset_orchestrator_state,
    "check_runtime_logs": check_runtime_logs,
    "check_worktree_deps_visible": check_worktree_deps_visible,
    "update_journey_verification": update_journey_verification,
    "sync_lifecycle_events": sync_lifecycle_events,
    "write_lifecycle_event": write_lifecycle_event,
    "runtime_git_guard": runtime_git_guard,
    "sync_runtime_snapshot": sync_runtime_snapshot,
    "generate_api_contracts": generate_api_contracts,
    "register_followup_task": register_followup_task,
    "check_progress_updated": check_progress_updated,
    "check_staged_deletions": check_staged_deletions,
    "check_blueprint_contract": check_blueprint_contract,
    "check_gold_blueprint": check_gold_blueprint,
    "check_orchestrator_gaps": check_orchestrator_gaps,
    "check_parallel_locks": check_parallel_locks,
    "check_claude_adapter": check_claude_adapter,
    "check_memory_yaml": check_memory_yaml,
    "check_skills_runtime": check_skills_runtime,
    "check_design_tokens": design_tokens_check,
    "check_web_design_tokens": design_tokens_check,
    "run_all_tests": run_all_tests,
    "compact_agent_memory": compact_agent_memory,
    "cleanup_runtime": cleanup_runtime,
    "ensure_task_worktree": ensure_task_worktree,
    "sync_main_before_wave": sync_main_before_wave,
    "setup_from_scratch": setup_from_scratch,
    "smoke_template_profiles": smoke_template_profiles,
    "chrome_devtools_isolated_session": chrome_devtools_isolated_session,
    "chrome_mcp_doctor": chrome_mcp_doctor,
    "dev_restart": dev_restart,
    "docker_hard_reset": docker_hard_reset,
    "configure_github_pr_cleanup": configure_github_pr_cleanup,
}


def main(command: str | None = None, argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if command is None:
        if not argv:
            return _print_json({"ok": False, "error": "missing command", "runtime_entrypoints": sorted(COMMANDS)}, 2)
        command = argv.pop(0)
    command = command.replace("-", "_").replace(".py", "")
    if argv and argv[0] in {"-h", "--help"}:
        return _print_json({"ok": True, "command": command, "usage": f"{command} [args]", "runtime contract": "blueprint-first"})
    func = COMMANDS.get(command)
    if func:
        return func(argv)
    return unsupported_safe(command, argv)


if __name__ == "__main__":
    raise SystemExit(main())
