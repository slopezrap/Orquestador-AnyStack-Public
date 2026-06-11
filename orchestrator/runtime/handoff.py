from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator.common import ensure_dirs, file_lock, find_task, handoff_path, load_registry, now_iso, project_root, read_yaml, tasks_dir, write_yaml
from orchestrator.runtime.verify_requirements import validate_verify_acceptance
from orchestrator.runtime.memory_yaml import update_handoff_index

KV_RE = re.compile(r"^[ \t]*(?:[-*][ \t]*)?(?P<key>[A-Z][A-Z0-9_]*):[ \t]*(?P<value>.*?)[ \t]*$", re.MULTILINE)
SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
TRAILER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

ROLE_OUTCOMES = {
    "main-orchestrator": {"ready", "blocked"},
    "planner": {"ready", "blocked"},
    "task-planner": {"ready", "blocked"},
    "blueprint-reviewer": {"valid", "invalid", "blocked"},
    "document-analyzer": {"valid", "invalid", "blocked"},
    "project-architect": {"ready", "changes_required", "blocked"},
    "official-docs-researcher": {"verified", "discrepancy", "insufficient"},
    "validator": {"approved", "changes_requested", "blocked"},
    "screen-journey-reviewer": {"approved", "changes_requested", "blocked"},
    "developer": {"success", "blocked", "failed"},
    "debugger": {"fixed", "blocked", "failed"},
    "tester": {"pass", "fail", "blocked"},
    "slice-verifier": {"verified", "issues_found", "blocked"},
    "deployer": {"deployed", "planned", "blocked", "failed"},
    "closer": {"committed", "blocked"},
}


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root().resolve()).as_posix()
    except Exception:
        return str(path)


def handoff_yaml_path(task_id: str) -> Path:
    return handoff_path(task_id).with_suffix(".yaml")


def _handoff_yaml_default(task_id: str, task: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "title": (task or {}).get("title") or task_id,
        "description": (task or {}).get("description") or "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "events": [],
    }


def ensure_handoff_yaml(task_id: str, task: dict[str, Any] | None = None) -> Path:
    p = handoff_yaml_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(p):
        data = read_yaml(p, None)
        if not isinstance(data, dict) or not data:
            data = _handoff_yaml_default(task_id, task)
        else:
            data.setdefault("schema_version", "1.0")
            data.setdefault("task_id", task_id)
            data.setdefault("events", [])
            data["updated_at"] = now_iso()
        write_yaml(p, data)
    return p


def parse_key_values(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    duplicates: list[str] = []
    for m in KV_RE.finditer(text or ""):
        key = m.group("key").lower()
        if key in out and key not in duplicates:
            duplicates.append(key)
        out[key] = m.group("value").strip()
    if duplicates:
        out["__duplicate_keys__"] = ",".join(sorted(duplicates))
    return out


def parse_explicit_trailer_block(text: str) -> dict[str, str]:
    """Parse only the explicit CLAUDE_TRAILER block.

    Handoff ledgers may contain prose, checklists and context notes. Those lines
    must not be treated as a lifecycle mutation request. This parser intentionally
    ignores free-floating KEY: value lines outside the explicit trailer marker.
    """
    body = text or ""
    marker = re.search(r"(?im)^\s*CLAUDE_TRAILER\s*:\s*$", body)
    if not marker:
        return {}
    trailer_text = body[marker.end():]
    return parse_key_values(trailer_text)


def parse_handoff_sections(text: str) -> list[dict[str, Any]]:
    matches = list(SECTION_RE.finditer(text or ""))
    sections: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end]
        data = parse_explicit_trailer_block(body)
        title = match.group("title").strip()
        role = data.get("agent", "").strip().lower().replace("_", "-")
        if not role:
            low = title.lower()
            compact = low.replace("_", "-").replace(" ", "-")
            for candidate in ROLE_OUTCOMES:
                if candidate in compact:
                    role = candidate
                    break
        sections.append({"title": title, "role": role, "data": data, "body": body.strip(), "has_trailer": bool(data)})
    return sections


def role_contracts() -> dict[str, dict[str, Any]]:
    p = project_root() / ".claude" / "orchestrator-contract.json"
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return ((c.get("trailer_schema") or {}).get("roles") or {})


def _effective_required_keys(role: str, spec: dict[str, Any], data: dict[str, str]) -> list[str]:
    """Return required keys for a handoff trailer.

    The base contract lists the successful trailer shape.  Blocked trailers are
    intentionally smaller: they must prove scope (AGENT/TASK_ID/HANDOFF), the
    blocking outcome/status and a durable reason, but they cannot be required to
    claim reports, Git pushes or completed verification evidence they did not
    produce.
    """
    keys = [str(k) for k in (spec.get("required_keys") or [])]
    outcome = data.get("outcome", "").lower()
    next_status = data.get("next_status", "").lower()
    if outcome == "blocked" or next_status == "blocked":
        if role == "closer":
            return ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "BLOCKER_REASON"]
        if role == "slice-verifier":
            return ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "EVIDENCE", "VERIFY_OUTCOME", "BLOCKER_REASON"]
        if spec.get("mutates_registry_lifecycle"):
            base = ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "EVIDENCE", "BLOCKER_REASON"]
            return [k for k in base if k in set(keys) | {"BLOCKER_REASON"}]
        return [k for k in ["AGENT", "TASK_ID", "OUTCOME", "HANDOFF", "BLOCKER_REASON"] if k in set(keys) | {"BLOCKER_REASON"}]
    return keys


def _contract_errors(role: str, data: dict[str, str], task_id: str) -> list[str]:
    roles = role_contracts()
    spec = roles.get(role) or {}
    errors: list[str] = []
    if data.get("__duplicate_keys__"):
        errors.append(f"{role}: duplicate CLAUDE_TRAILER keys {data.get('__duplicate_keys__')}")
    if not spec:
        errors.append(f"{role}: role is not declared in orchestrator-contract.json")
        return errors
    for key in _effective_required_keys(role, spec, data):
        if not data.get(str(key).lower()):
            errors.append(f"{role}: missing {key}")
    agent = data.get("agent", "").lower().replace("_", "-")
    if agent and agent != role:
        errors.append(f"{role}: AGENT mismatch {agent}")
    if data.get("task_id") and data.get("task_id") != task_id:
        errors.append(f"{role}: TASK_ID mismatch {data.get('task_id')} != {task_id}")
    allowed_outcomes = {str(x).lower() for x in spec.get("outcome_values") or []}
    outcome = data.get("outcome", "").lower()
    if outcome and allowed_outcomes and outcome not in allowed_outcomes:
        errors.append(f"{role}: unexpected OUTCOME {data.get('outcome')}")
    allowed_status = {str(x).lower() for x in spec.get("next_status_values") or []}
    next_status = data.get("next_status", "").lower()
    if next_status:
        if allowed_status and next_status not in allowed_status:
            errors.append(f"{role}: unexpected NEXT_STATUS {data.get('next_status')}")
        elif not allowed_status:
            errors.append(f"{role}: NEXT_STATUS supplied but the role has no lifecycle targets")
    return errors


def ensure_handoff_header(task_id: str, task: dict[str, Any] | None = None) -> Path:
    ensure_dirs()
    p = handoff_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(p):
        if p.exists():
            return p
        title = (task or {}).get("title") or task_id
        desc = (task or {}).get("description") or "No task description was available when the handoff ledger was initialized."
        p.write_text(
            f"# Handoff for {task_id}\n\n"
            f"- TASK_ID: {task_id}\n"
            f"- TITLE: {title}\n"
            f"- DESCRIPTION: {desc}\n"
            f"- CREATED_AT: {now_iso()}\n\n"
            "This file is the append-only machine-readable handoff ledger for Claude subagents. "
            "Every lifecycle-mutating subagent appends a section with AGENT/TASK_ID/OUTCOME/NEXT_STATUS before its final CLAUDE_TRAILER.\n\n",
            encoding="utf-8",
        )
    ensure_handoff_yaml(task_id, task)
    try:
        update_handoff_index(task_id)
    except Exception:
        pass
    return p



def _safe_trailer_value(value: Any) -> str:
    """Render one trailer value as a single markdown KEY: value line."""
    rendered = str(value if value is not None else "").strip()
    # Trailer values are line-oriented. Preserve information without allowing a
    # later newline to create synthetic keys in the accepted block.
    return " ".join(rendered.splitlines())


def _normalised_trailer_items(role: str, trailer: dict[str, str]) -> list[tuple[str, str]]:
    """Return schema-flexible trailer keys to persist in hook-accepted markdown.

    The parser and orchestrator-contract.json are intentionally schema-flexible:
    roles can add required UPPER_SNAKE_CASE keys without changing hook code. The
    accepted-block writer must follow that model; otherwise a role can emit a
    valid trailer, the YAML event stores it, but the markdown accepted block loses
    the new keys and check-handoff-contract later reports false "missing" errors.
    """
    trailer_norm = {str(k).strip().lower(): _safe_trailer_value(v) for k, v in (trailer or {}).items() if TRAILER_KEY_RE.match(str(k).strip().lower())}
    roles = role_contracts()
    spec = roles.get(role) or {}
    ordered: list[str] = []
    # Required role keys first, then global known keys, then any future extension
    # keys the parser accepted. This keeps current handoffs readable and future
    # contract additions lossless.
    for key in spec.get("required_keys") or []:
        k = str(key).strip().lower()
        if k and k not in ordered:
            ordered.append(k)
    try:
        contract = json.loads((project_root() / ".claude" / "orchestrator-contract.json").read_text(encoding="utf-8"))
        for key in (contract.get("trailer_schema") or {}).get("global_keys") or []:
            k = str(key).strip().lower()
            if k and k not in ordered:
                ordered.append(k)
    except Exception:
        pass
    for k in sorted(trailer_norm):
        if k not in ordered and not k.startswith("__"):
            ordered.append(k)
    out: list[tuple[str, str]] = []
    for k in ordered:
        if k in {"agent", "task_id", "outcome", "next_status", "handoff", "accepted_by_hook"}:
            continue
        value = trailer_norm.get(k)
        if value not in (None, ""):
            out.append((k.upper(), value))
    return out


def _load_latest_yaml_event_trailers(task_id: str) -> dict[str, dict[str, str]]:
    """Read structured handoff events as a compatibility source for old markdown.

    Older accepted-block writers persisted only a fixed markdown allowlist but
    kept the full trailer in the YAML event. During validation, merge the latest
    accepted YAML trailer per role into the parsed markdown data so existing
    handoffs do not need manual repair when new required keys are added.
    """
    p = handoff_yaml_path(task_id)
    data = read_yaml(p, {}) if p.exists() else {}
    latest: dict[str, dict[str, str]] = {}
    if not isinstance(data, dict):
        return latest
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        role = str(event.get("agent") or "").strip().lower().replace("_", "-")
        if not role or not event.get("accepted_by_hook", True):
            continue
        trailer = event.get("trailer") or {}
        if not isinstance(trailer, dict):
            continue
        norm = {str(k).strip().lower(): str(v).strip() for k, v in trailer.items() if v is not None and not str(k).startswith("__")}
        norm.setdefault("agent", role)
        norm.setdefault("task_id", task_id)
        norm.setdefault("accepted_by_hook", "yes")
        latest[role] = norm
    return latest


def _merge_yaml_compat(role: str, data: dict[str, str], yaml_latest: dict[str, dict[str, str]]) -> dict[str, str]:
    extra = yaml_latest.get(role) or {}
    if not extra:
        return data
    merged = dict(data)
    for key, value in extra.items():
        if value not in (None, "") and not merged.get(key):
            merged[key] = value
    return merged

def append_handoff_event(task_id: str, role: str, trailer: dict[str, str], task: dict[str, Any] | None = None, *, accepted: bool = True, note: str = "") -> Path:
    p = ensure_handoff_header(task_id, task)
    role = str(role or "unknown")
    section = [
        f"## {role} handoff — {now_iso()}",
        "CLAUDE_TRAILER:",
        f"- AGENT: {role}",
        f"- TASK_ID: {task_id}",
        f"- OUTCOME: {_safe_trailer_value(trailer.get('outcome', ''))}",
    ]
    if trailer.get("next_status") not in (None, ""):
        section.append(f"- NEXT_STATUS: {_safe_trailer_value(trailer.get('next_status', ''))}")
    section.extend([
        f"- HANDOFF: {_rel(p)}",
        f"- ACCEPTED_BY_HOOK: {'yes' if accepted else 'no'}",
    ])
    if note:
        section.append(f"- HOOK_NOTE: {_safe_trailer_value(note)}")
    for key, value in _normalised_trailer_items(role, trailer):
        section.append(f"- {key}: {value}")
    section.append("")
    with file_lock(p):
        with p.open("a", encoding="utf-8") as f:
            f.write("\n".join(section) + "\n")
    y = handoff_yaml_path(task_id)
    with file_lock(y):
        data = read_yaml(y, None)
        if not isinstance(data, dict) or not data:
            data = _handoff_yaml_default(task_id, task)
        event = {
            "at": now_iso(),
            "agent": role,
            "task_id": task_id,
            "outcome": trailer.get("outcome", ""),
            "next_status": trailer.get("next_status", ""),
            "accepted_by_hook": bool(accepted),
            "hook_note": note,
            "trailer": {str(k): str(v) for k, v in sorted(trailer.items()) if not str(k).startswith("__")},
        }
        data.setdefault("events", []).append(event)
        data["updated_at"] = now_iso()
        write_yaml(y, data)
    # Keep the structured handoff index in sync. This mirrors the native
    # orchestrator handoff-ledger behavior but is YAML and blueprint-first.
    index_path = tasks_dir() / "handoff-index.yaml"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(index_path):
        idx = read_yaml(index_path, None)
        if not isinstance(idx, dict) or not idx:
            idx = {"schema_version": "1.0", "kind": "orchestrator.handoff_index", "created_at": now_iso(), "handoffs": []}
        idx.setdefault("schema_version", "1.0")
        idx.setdefault("kind", "orchestrator.handoff_index")
        idx.setdefault("handoffs", [])
        idx["updated_at"] = now_iso()
        idx["handoffs"].append({
            "at": event["at"],
            "task_id": task_id,
            "agent": role,
            "outcome": event.get("outcome"),
            "next_status": event.get("next_status"),
            "accepted_by_hook": bool(accepted),
            "handoff_md": _rel(p),
            "handoff_yaml": _rel(y),
        })
        idx["handoffs"] = idx["handoffs"][-500:]
        write_yaml(index_path, idx)
    return p


def _accepted_by_hook(data: dict[str, str]) -> bool:
    raw = str(data.get("accepted_by_hook", "yes")).strip().lower()
    return raw not in {"no", "false", "0", "rejected"}



def _load_handoff_evidence(evidence_value: str | None) -> Any:
    if not evidence_value:
        return {}
    path = Path(str(evidence_value))
    if not path.is_absolute():
        path = project_root() / path
    if not path.exists():
        return {}
    candidates: list[Path] = []
    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        preferred = [path / "slice-verifier.json", path / "verify-slice.json", path / "evidence.json"]
        candidates.extend([p for p in preferred if p.exists()])
        candidates.extend(sorted(p for p in path.glob("*.json") if p not in candidates))
    merged: dict[str, Any] = {"__evidence_path__": str(path)}
    loaded = 0
    for candidate in candidates:
        try:
            obj = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        loaded += 1
        key = candidate.stem.replace("-", "_")
        if isinstance(obj, dict):
            merged.update(obj)
            merged[key] = obj
        else:
            merged[key] = obj
    if loaded:
        merged["__loaded_json_files__"] = loaded
    return merged

def validate_handoff(task_id: str, require_roles: list[str] | None = None, *, require_verify_slice: bool = False, require_ready_for_close: bool = False, require_closer_done: bool = False) -> dict[str, Any]:
    p = handoff_path(task_id)
    errors: list[str] = []
    warnings: list[str] = []
    if not p.exists():
        return {"ok": False, "task_id": task_id, "handoff": str(p), "sections": 0, "errors": [f"missing handoff {_rel(p)}"], "warnings": warnings}
    text = p.read_text(encoding="utf-8", errors="replace")
    sections = parse_handoff_sections(text)
    yaml_latest = _load_latest_yaml_event_trailers(task_id)
    by_role_all: dict[str, list[dict[str, Any]]] = {}
    by_role_accepted: dict[str, list[dict[str, Any]]] = {}
    for sec in sections:
        data = sec.get("data") or {}
        if not sec.get("has_trailer"):
            continue
        role = (sec.get("role") or data.get("agent") or "unknown").lower().replace("_", "-")
        if role != "unknown":
            data = _merge_yaml_compat(role, data, yaml_latest)
            sec["data"] = data
        by_role_all.setdefault(role, []).append(sec)
        if role == "unknown":
            errors.append(f"{sec.get('title')}: CLAUDE_TRAILER missing AGENT")
            continue
        if _accepted_by_hook(data):
            by_role_accepted.setdefault(role, []).append(sec)
        else:
            warnings.append(f"ignored rejected handoff section for {role}: {sec.get('title')}")
            if data.get("__duplicate_keys__"):
                warnings.append(f"rejected section for {role} contains duplicate keys {data.get('__duplicate_keys__')}")
    # A handoff is append-only and roles may write multiple attempts. The latest
    # accepted section per role is the current close-readiness contract; older
    # accepted sections are historical evidence and must not permanently block a
    # slice after a retry or contract evolution.
    for role, secs in by_role_accepted.items():
        if secs:
            role_errors = _contract_errors(role, secs[-1].get("data") or {}, task_id)
            errors.extend(role_errors)
            if len(secs) > 1:
                for old_sec in secs[:-1]:
                    old_data = old_sec.get("data") or {}
                    old_errors = _contract_errors(role, old_data, task_id)
                    if old_errors:
                        warnings.append(f"superseded accepted handoff section for {role} has historical contract errors: {'; '.join(old_errors)}")
    roles = list(require_roles or [])
    if require_verify_slice and "slice-verifier" not in roles:
        roles.append("slice-verifier")
    if require_ready_for_close and "tester" not in roles:
        roles.append("tester")
    if require_closer_done and "closer" not in roles:
        roles.append("closer")
    for role in roles:
        if not by_role_accepted.get(role):
            if by_role_all.get(role):
                errors.append(f"required role {role} only has rejected handoff sections")
            else:
                errors.append(f"missing accepted handoff section for required role {role}")
    latest = {role: secs[-1]["data"] for role, secs in by_role_accepted.items() if secs}
    if require_ready_for_close and latest.get("tester", {}).get("next_status") != "ready_for_close":
        errors.append("tester accepted handoff does not end in ready_for_close")
    if require_verify_slice:
        verifier = latest.get("slice-verifier", {})
        if verifier.get("agent", "").lower().replace("_", "-") != "slice-verifier":
            errors.append("slice-verifier accepted handoff missing AGENT: slice-verifier")
        if verifier.get("next_status") != "verified_pending_close" or verifier.get("verify_outcome") != "verified":
            errors.append("slice-verifier accepted handoff does not prove verified_pending_close")
        ev = verifier.get("evidence")
        if not ev:
            errors.append("slice-verifier accepted handoff missing EVIDENCE")
        elif not (project_root() / ev).exists():
            errors.append(f"slice-verifier evidence path missing: {ev}")
        hp = verifier.get("handoff")
        if hp and (project_root() / hp).resolve() != p.resolve():
            errors.append(f"slice-verifier HANDOFF does not point to {_rel(p)}")
        task = find_task(load_registry(), task_id) or {"id": task_id, "task_id": task_id}
        evidence_obj = _load_handoff_evidence(ev)
        for err in validate_verify_acceptance(task, verifier, text, evidence_obj):
            errors.append(f"slice-verifier verify evidence: {err}")
    if require_closer_done and latest.get("closer", {}).get("next_status") != "done":
        errors.append("closer accepted handoff does not end in done")
    return {
        "ok": not errors,
        "task_id": task_id,
        "handoff": _rel(p),
        "sections": len(sections),
        "roles": sorted(k for k in by_role_accepted if k),
        "all_roles": sorted(k for k in by_role_all if k),
        "errors": sorted(set(errors)),
        "warnings": warnings,
    }


def init_handoff_for_task(task_id: str) -> Path:
    reg = load_registry()
    task = find_task(reg, task_id) or {"id": task_id, "title": task_id}
    return ensure_handoff_header(task_id, task)
