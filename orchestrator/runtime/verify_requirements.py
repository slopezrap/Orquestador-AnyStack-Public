from __future__ import annotations

import json
import re
from typing import Any

from orchestrator.common import find_task, load_registry

UI_KIND_SET = {"logic.ui", "ui", "screen", "screens", "ux"}
UI_PATH_RE = re.compile(r"(^|/)(frontend|front-end|web|ui|views?|screens?|pages?|routes?|components?|mobile|flutter|ios|android)(/|$)", re.I)
MOBILE_PATH_RE = re.compile(r"(^|/)(mobile|flutter|ios|android)(/|$)", re.I)
WEB_PATH_RE = re.compile(r"(^|/)(frontend|front-end|web|ui|views?|screens?|pages?|routes?|components?)(/|$)", re.I)
VISUAL_TEXT_RE = re.compile(r"\b(VISUAL_CONTRACT_CHECK|visual|screenshot|browser|mobile|simulator|emulator|device|mcp|screen|route|UI\b|UX\b)\b", re.I)
API_BACKEND_PATH_RE = re.compile(r"(^|/)(backend|api|server|services?|controllers?|routers?|routes?|repositories?)(/|$)", re.I)
DB_PATH_RE = re.compile(r"(^|/)(db|database|migrations?|alembic|sql|schemas?)(/|$)|(^|:)db(:|$)|migration|ddl", re.I)
WORKER_PATH_RE = re.compile(r"(^|/)(workers?|pipelines?|jobs?|queues?|consumers?|scheduler|tasks?)(/|$)|worker|pipeline|queue|dlq", re.I)
DEPENDENCY_PATH_RE = re.compile(r"(^|/)(pyproject\.toml|uv\.lock|requirements.*\.txt|poetry\.lock|package\.json|pnpm-lock\.yaml|yarn\.lock|package-lock\.json)$|dependency|dependencies|lockfile|venv|uv sync|pip install", re.I)
CORE_PATH_RE = re.compile(r"(^|/)(core|domain|engine|features?|rules?|logic|scoring|detection|strategy)(/|$)|CORE-", re.I)
INTEGRATION_PATH_RE = re.compile(r"(^|/)(adapters?|providers?|integrations?|clients?)(/|$)|provider|external|api client", re.I)
PERMISSION_STATE_ERROR_RE = re.compile(r"permission|auth|token|state|state-machine|error|exception|failure|guard|gate|policy", re.I)
RUNTIME_PERSISTENCE_RE = re.compile(r"(^|/)(orchestrator-state|registry|runtime-state|task-dag|task-packs|handoffs?|evidence|memory-yaml)(/|$)|\b(registry|runtime-state|task-dag|task-pack|handoff|memory yaml|persistent state)\b", re.I)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _texts(value: Any, limit: int = 60000) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:limit]
    except Exception:
        return str(value)[:limit]


def _spec_kind(spec: dict[str, Any]) -> str:
    return str(spec.get("kind") or spec.get("type") or "").strip().lower()


def _spec_id(spec: dict[str, Any]) -> str:
    return str(spec.get("id") or "").strip()


def _spec_has_route(spec: dict[str, Any]) -> bool:
    if not isinstance(spec, dict):
        return False
    raw = spec.get("raw") if isinstance(spec.get("raw"), dict) else {}
    details = spec.get("details") if isinstance(spec.get("details"), dict) else {}
    for obj in (spec, raw, details):
        if not isinstance(obj, dict):
            continue
        for key in ("route", "routes", "screen", "screens", "path"):
            value = obj.get(key)
            if value:
                if key == "path":
                    s = str(value)
                    if UI_PATH_RE.search(s):
                        return True
                else:
                    return True
    return False


def _owns_ui(spec: dict[str, Any]) -> bool:
    sid = _spec_id(spec)
    return _spec_kind(spec) in UI_KIND_SET or sid.startswith(("SCR-", "UI-", "VIEW-", "EVT-"))


def _contains_any(blob: str, *patterns: re.Pattern[str]) -> bool:
    return any(p.search(blob) for p in patterns)


def _category(required: bool, kind: str, label: str, signals: list[str], verify: list[str], evidence: list[str]) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "required": bool(required),
        "signals": sorted(set(str(x) for x in signals if str(x).strip())),
        "what_to_verify": verify,
        "required_evidence": evidence,
    }


def _non_ui_matrix(task: dict[str, Any], specs: list[dict[str, Any]], write_set: list[str], blob: str) -> list[dict[str, Any]]:
    kinds = {_spec_kind(s) for s in specs}
    ids = [_spec_id(s) for s in specs]
    paths_blob = "\n".join(write_set + [str(x) for x in _as_list(task.get("builds"))] + [str(x) for x in _as_list(task.get("implements"))])
    matrix: list[dict[str, Any]] = []

    endpoint = bool(API_BACKEND_PATH_RE.search(paths_blob) or re.search(r"\b(endpoint|route|httpx|curl|fastapi|api service|REST|server vivo|verify-slice|evidence-contract)\b", blob, re.I))
    matrix.append(_category(endpoint, "endpoint_service", "Endpoint / service", [*write_set, *ids], [
        "hard reset of the runtime when the stack declares one",
        "start or reuse the live server for the slice",
        "perform a real HTTP/API/service call with httpx/curl/CLI, not only a unit test",
        "assert response body/status/headers match the resolved_specs and acceptance contract",
        "observe persistence side effects in the real DB when the slice writes data",
        "check backend/service logs are clean and contain the expected correlation/evidence markers",
    ], ["server command/output", "request/response transcript", "DB query output when applicable", "runtime logs", "no-stub/no-mock declaration"]))

    db = bool(DB_PATH_RE.search(paths_blob) or RUNTIME_PERSISTENCE_RE.search(paths_blob) or ("auxiliary.data" in kinds) or any(i.startswith("DATA-") for i in ids) or re.search(r"\b(table|database|migration|constraint|index|DDL|upsert|persist|durable state|runtime state|registry)\b", blob, re.I))
    matrix.append(_category(db, "migration_ddl_data", "Migration / DDL / data persistence", [*write_set, *ids], [
        "apply real migrations up to head against the runtime database",
        "inspect the actual schema: tables, indexes, constraints, hypertables or policies declared by the blueprint",
        "prove idempotence by re-running the migration or write path when safe",
        "if reversible migrations exist, verify downgrade/rollback path or document why not applicable",
        "verify persisted rows use real/provided data and keep missing values as missing, never as zero",
    ], ["output", "schema/introspection query", "idempotence proof", "sample persisted rows", "DB logs when applicable"]))

    worker = bool(WORKER_PATH_RE.search(paths_blob) or any("worker" in json.dumps(s, ensure_ascii=False).lower() for s in specs) or re.search(r"\b(worker|pipeline|queue|scheduler|consumer|DLQ|cron|job)\b", blob, re.I))
    matrix.append(_category(worker, "pipeline_worker_queue", "Pipeline / worker / queue", [*write_set, *ids], [
        "run the real worker/pipeline/queue consumer with real or provided input",
        "observe the durable output it produces in DB, files, queue, event stream or logs",
        "check retry/backoff/idempotence/error path when the slice declares one",
        "verify worker/Rancher/Docker logs and exit/health status",
    ], ["worker invocation", "input fixture/provided payload", "persisted output", "worker logs", "health/status output"]))

    dep = bool(DEPENDENCY_PATH_RE.search(paths_blob) or re.search(r"\b(uv sync|pip|venv|lockfile|dependency|package|version|__version__|__file__)\b", blob, re.I))
    matrix.append(_category(dep, "dependency_runtime", "Dependency introduction", [*write_set, *ids], [
        "run the real dependency install/sync command for the stack, e.g. uv sync when declared",
        "import the dependency from the real venv/runtime, not from a local shadow module",
        "verify the installed version and path against the lockfile",
        "run a cross-regression smoke test for adjacent libraries touched by the dependency",
    ], ["install/sync output", "python/node import transcript", "version and __file__/path proof", "lockfile diff", "regression command output"]))

    integration = bool(INTEGRATION_PATH_RE.search(paths_blob) or ("logic.integration" in kinds) or any(i.startswith("INT-") for i in ids))
    matrix.append(_category(integration, "integration_provider", "External/internal integration adapter", [*write_set, *ids], [
        "run adapter boot/probe or a real contract call when credentials/data are available",
        "if external credentials are absent, use the declared provided-data contract and mark live call not_applicable with reason",
        "verify auth, pagination/rate-limit/degradation/provider-health behavior described by resolved_specs",
        "persist raw redacted responses or integration evidence when the blueprint requires it",
    ], ["probe/call output", "provider-health or adapter status", "redacted raw/evidence reference", "degradation/log output"]))

    core = bool(CORE_PATH_RE.search(paths_blob) or (kinds & {"logic.domain", "logic.application"}) or any(i.startswith(("DR-", "UC-", "CORE-")) for i in ids))
    matrix.append(_category(core, "core_logic", "Pure/domain/application logic", [*write_set, *ids], [
        "execute the real calculation or use-case with real/provided fixtures",
        "assert expected output against DR-* invariants, UC-* behavior and edge cases",
        "run property/boundary/error tests when declared by the blueprint",
        "prove no production path contains NotImplementedError/pass/TODO/stub behavior",
    ], ["command/test transcript", "input/output fixture evidence", "domain invariant assertions", "anti-stub grep/check output"]))

    pse = bool(PERMISSION_STATE_ERROR_RE.search(paths_blob) or (kinds & {"logic.permission", "logic.state", "logic.error"}) or any(i.startswith(("PG-", "SM-", "ERR-")) for i in ids))
    matrix.append(_category(pse, "permission_state_error", "Permission / state / error contract", [*write_set, *ids], [
        "exercise legal and illegal state transitions or permission gates described by the blueprint",
        "verify blocked/error/degraded paths produce the declared code, message, state and audit evidence",
        "confirm the lifecycle does not advance when the guard fails",
    ], ["allowed/denied command output", "state transition record", "error payload/log", "audit/handoff evidence"]))

    # Always include the fallback so a backend slice cannot pass with 'no UI' and no real evidence plan.
    fallback_required = not any(c["required"] for c in matrix)
    matrix.append(_category(fallback_required, "runtime_contract_fallback", "Generic runtime contract", [*write_set, *ids], [
        "run the strongest real runtime check available for the slice's write_set and evidence_contract",
        "combine automated tests with runtime logs and concrete filesystem/DB/API observations",
        "explain why endpoint, DB, worker, dependency and UI evidence are not applicable",
    ], ["runtime command output", "evidence_contract proof", "not_applicable rationale for skipped surfaces"]))
    return matrix


def classify_task_verification(task: dict[str, Any]) -> dict[str, Any]:
    """Classify verification needs for a compiled task.

    Important invariant: ``journey_refs`` alone is NOT a UI/visual signal. Backend,
    worker, integration and data slices may participate in an operator journey without
    owning a route/screen.  Those slices require real API/backend/runtime evidence, not
    browser/mobile MCP evidence.  UI evidence is required only when the task owns UI
    specs, screen/route data, frontend/mobile write surfaces, or an explicit visual
    contract.
    """
    specs = [s for s in _as_list(task.get("resolved_specs")) if isinstance(s, dict)]
    write_set = [str(x) for x in _as_list(task.get("write_set"))]
    builds = [str(x) for x in _as_list(task.get("builds"))]
    implements = [str(x) for x in _as_list(task.get("implements"))]
    verification_refs = [str(x) for x in _as_list(task.get("verification_refs"))]
    journey_refs = [str(x) for x in _as_list(task.get("journey_refs")) if str(x).strip()]
    closes_journeys = [str(x) for x in _as_list(task.get("closes_journeys")) if str(x).strip()]

    spec_kinds = {_spec_kind(s) for s in specs}
    ui_specs = [s for s in specs if _owns_ui(s)]
    # A Journey spec often mentions screens/routes as narrative flow, but that does not mean this slice owns a UI surface.
    route_specs = [s for s in specs if _owns_ui(s) and _spec_has_route(s)]
    ui_write_paths = [p for p in write_set if UI_PATH_RE.search(p)]
    mobile_write_paths = [p for p in write_set if MOBILE_PATH_RE.search(p)]
    web_write_paths = [p for p in write_set if WEB_PATH_RE.search(p)]

    evidence_blob = _texts({
        "acceptance": task.get("acceptance"),
        "evidence_contract": task.get("evidence_contract"),
        "verify_mode": task.get("verify_mode"),
        "verification_refs": verification_refs,
        "resolved_specs": specs,
        "write_set": write_set,
        "builds": builds,
        "implements": implements,
    })
    explicit_visual = bool(VISUAL_TEXT_RE.search(evidence_blob))
    ui_surface = bool(ui_specs or route_specs or ui_write_paths)
    backend_surface = bool([p for p in write_set if API_BACKEND_PATH_RE.search(p)]) or bool(spec_kinds & {"logic.application", "logic.integration", "logic.domain", "logic.error", "auxiliary.data", "logic.permission", "logic.state"})
    visual_required = bool(ui_surface or (explicit_visual and not backend_surface and not journey_refs))

    if mobile_write_paths or (visual_required and any("flutter" in p.lower() or "mobile" in p.lower() for p in write_set + builds + implements)):
        visual_mode = "mobile"
        surface_kind = "mobile_ui"
        method = "flutter_mobile_visual_runtime"
        mcp_requirement = {
            "mcp_browser": "not_applicable:flutter_mobile",
            "mcp_client": "dart|flutter|flutter-driver",
            "visual_check_method": "simulator|emulator|device",
        }
    elif visual_required:
        visual_mode = "web"
        surface_kind = "browser_ui"
        method = "browser_visual_runtime"
        mcp_requirement = {
            "mcp_browser": "chrome-devtools|claude-in-chrome|agent360-browser-mcp|browser-mcp",
            "visual_check_method": "browser",
        }
    elif journey_refs or closes_journeys:
        visual_mode = "non_ui_journey_dependency"
        surface_kind = "journey_backend_contract"
        method = "backend_db_worker_pipeline_runtime"
        mcp_requirement = {
            "mcp_browser": "not_applicable:no_ui_surface",
            "visual_check_method": "backend",
        }
    else:
        visual_mode = "non_ui"
        surface_kind = "non_ui_runtime_contract"
        method = "backend_db_worker_pipeline_runtime"
        mcp_requirement = {
            "mcp_browser": "not_applicable:no_ui_surface",
            "visual_check_method": "backend",
        }

    evidence_matrix = [] if visual_required else _non_ui_matrix(task, specs, write_set, evidence_blob)
    required_evidence_categories = [c["kind"] for c in evidence_matrix if c.get("required")]
    if visual_required:
        required_evidence_categories = ["visual_ui_runtime"]

    return {
        "task_id": task.get("id") or task.get("task_id"),
        "surface_kind": surface_kind,
        "method": method,
        "visual_required": visual_required,
        "visual_mode": visual_mode,
        "screen_journey_reviewer_required": bool(visual_required),
        "journey_verification_required": bool((journey_refs or closes_journeys) and not visual_required),
        "journey_participation_only": bool((journey_refs or closes_journeys) and not visual_required),
        "journey_refs": journey_refs,
        "closes_journeys": closes_journeys,
        "ui_surface": ui_surface,
        "backend_surface": backend_surface,
        "evidence_route": "visual_ui" if visual_required else ("non_ui_journey_dependency" if (journey_refs or closes_journeys) else "non_ui_runtime"),
        "mcp_requirement": mcp_requirement,
        "evidence_matrix": evidence_matrix,
        "required_evidence_categories": required_evidence_categories,
        "minimum_runtime_proof": [
            "hard_reset_or_declared_not_applicable",
            "real_or_provided_data_used",
            "runtime_command_output_captured",
            "logs_checked_when_runtime_exists",
            "no_stub_no_fake_no_mock_runtime_path",
        ],
        "signals": {
            "ui_specs": [s.get("id") for s in ui_specs],
            "route_specs": [s.get("id") for s in route_specs],
            "ui_write_paths": ui_write_paths,
            "web_write_paths": web_write_paths,
            "mobile_write_paths": mobile_write_paths,
            "explicit_visual_contract": explicit_visual,
            "spec_kinds": sorted(spec_kinds),
        },
        "explanation": (
            "UI/browser/mobile evidence is required because the task owns UI/route/visual surfaces. Run hard reset, real data, visual MCP and screen journey review."
            if visual_required else
            "journey_refs/closes_journeys do not imply UI evidence; verify with API/backend/DB/worker/pipeline/runtime evidence and use /verify-journey or a later UI slice for visual journey closure."
            if (journey_refs or closes_journeys) else
            "No UI surface detected; verify with the non-UI runtime evidence matrix derived from write_set and resolved_specs."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    import sys
    argv = list(argv or sys.argv[1:])
    tid = next((a for a in argv if not a.startswith("-")), None)
    if not tid:
        print("Usage: check-verify-routing.py <TASK_ID>", file=sys.stderr)
        return 2
    reg = load_registry()
    task = find_task(reg, tid)
    if not task:
        print(json.dumps({"ok": False, "error": "task not found", "task_id": tid}, indent=2))
        return 2
    result = classify_task_verification(task)
    result["ok"] = True
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

VERIFY_FIELD_RE = re.compile(r"^[ \t]*(?:[-*][ \t]*)?(?P<key>[A-Z][A-Z0-9_]*):[ \t]*(?P<value>.*?)[ \t]*$", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"^(?:<.*>|todo|tbd|pending|pendiente|fill_me|fill|n/a\??|none|null|\.\.\.|-)$", re.I)


def _normalize_verify_key(key: str) -> str:
    return str(key or "").strip().lower().replace("-", "_")


def _usable(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if _PLACEHOLDER_RE.match(text):
        return False
    return True


def _yes(value: Any) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1", "ok", "clean"}


def _not_applicable_with_reason(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("not_applicable:") and len(text.split(":", 1)[1].strip()) >= 3


def _zero(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if text in {"0", "zero", "none", "no_errors"}:
        return True
    try:
        return int(text) == 0
    except Exception:
        return False


def _rows_or_na(value: Any) -> bool:
    if not _usable(value):
        return False
    text = str(value).strip().lower()
    if _not_applicable_with_reason(text):
        return True
    if text in {"yes", "observed", "true"}:
        return True
    try:
        int(text)
        return True
    except Exception:
        return False


def parse_verify_fields_from_text(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in VERIFY_FIELD_RE.finditer(text or ""):
        key = _normalize_verify_key(match.group("key"))
        value = match.group("value").strip()
        if key and _usable(value):
            fields[key] = value
    return fields


def _flatten_evidence(value: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            norm = _normalize_verify_key(str(key))
            full = f"{prefix}_{norm}" if prefix else norm
            if isinstance(item, (dict, list)):
                out.update(_flatten_evidence(item, full))
            elif item is not None and _usable(item):
                out[full] = str(item).strip()
                out.setdefault(norm, str(item).strip())
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            out.update(_flatten_evidence(item, f"{prefix}_{idx}" if prefix else str(idx)))
    return out


def _merge_verify_sources(trailer: dict[str, Any], handoff_text: str, evidence: Any) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in (
        _flatten_evidence(evidence),
        parse_verify_fields_from_text(handoff_text),
        {_normalize_verify_key(k): str(v).strip() for k, v in (trailer or {}).items() if _usable(v)},
    ):
        for key, value in source.items():
            if _usable(value):
                merged[key] = value
    return merged


def _lookup(fields: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = fields.get(_normalize_verify_key(key))
        if _usable(value):
            return value
    return ""


def _evidence_blob(fields: dict[str, str], evidence: Any, handoff_text: str) -> str:
    # Use parsed fields rather than raw handoff text so placeholder template lines
    # such as EVIDENCE_ENDPOINT_SERVICE: <...> cannot satisfy acceptance.
    try:
        evidence_text = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    except Exception:
        evidence_text = str(evidence)
    try:
        fields_text = json.dumps(fields, ensure_ascii=False, sort_keys=True)
    except Exception:
        fields_text = str(fields)
    return f"{fields_text}\n{evidence_text}".lower()


def validate_verify_acceptance(task: dict[str, Any] | None, trailer: dict[str, Any], handoff_text: str = "", evidence: Any = None) -> list[str]:
    """Return hard acceptance errors for slice-verifier verified_pending_close.

    This validates the durable ## verify-slice evidence contract without changing
    the base CLAUDE_TRAILER schema.  The final trailer may remain compact, but the
    handoff/evidence must prove the verification modality with real runtime data.
    """
    task = task or {}
    surface = task.get("verification_surface") or classify_task_verification(task)
    fields = _merge_verify_sources(trailer or {}, handoff_text or "", evidence or {})
    errors: list[str] = []

    if "## verify-slice" not in (handoff_text or "").lower() and "verify_slice" not in fields:
        errors.append("handoff missing ## verify-slice evidence section")

    if not (_yes(_lookup(fields, "real_data_or_user_provided", "real_or_provided_data_used"))):
        errors.append("REAL_DATA_OR_USER_PROVIDED/REAL_OR_PROVIDED_DATA_USED must be yes")
    if not _usable(_lookup(fields, "real_data_source")):
        errors.append("REAL_DATA_SOURCE must name the real/provided data, migration, wheel or command source")
    if not (_yes(_lookup(fields, "no_stub_data", "no_stub_data_used"))):
        errors.append("NO_STUB_DATA/NO_STUB_DATA_USED must be yes")
    if not _usable(_lookup(fields, "flows_tested")):
        errors.append("FLOWS_TESTED must list the real commands or flows executed")
    if not _usable(_lookup(fields, "data_setup")):
        errors.append("DATA_SETUP must describe real setup: reset, migrations, data load or dependency sync")
    if not _usable(_lookup(fields, "evidence")):
        errors.append("EVIDENCE must point to durable evidence")
    rows = _lookup(fields, "data_contract_rows")
    persisted = _lookup(fields, "persisted_data_observed")
    if not (_rows_or_na(rows) or _rows_or_na(persisted)):
        errors.append("DATA_CONTRACT_ROWS or PERSISTED_DATA_OBSERVED must be real/observed or not_applicable:<reason>")
    if not (_yes(_lookup(fields, "runtime_logs_checked"))):
        errors.append("RUNTIME_LOGS_CHECKED must be yes")
    if str(_lookup(fields, "error_logs_status")).strip().lower() != "clean":
        errors.append("ERROR_LOGS_STATUS must be clean")
    if not _zero(_lookup(fields, "runtime_log_errors")):
        errors.append("RUNTIME_LOG_ERRORS must be 0")

    visual_required = bool(surface.get("requires_visual_mcp"))
    mcp_browser = _lookup(fields, "mcp_browser")
    visual_method = _lookup(fields, "visual_check_method")
    if visual_required:
        mode = str(surface.get("visual_mode") or "web")
        if mode == "mobile":
            if str(mcp_browser).strip().lower() != "not_applicable:flutter_mobile":
                errors.append("mobile UI verification requires MCP_BROWSER: not_applicable:flutter_mobile")
            if str(visual_method).strip().lower() not in {"simulator", "emulator", "device"}:
                errors.append("mobile UI verification requires VISUAL_CHECK_METHOD: simulator|emulator|device")
        else:
            accepted = {"chrome-devtools", "claude-in-chrome", "agent360", "agent360-browser-mcp", "browser-mcp"}
            mcp_l = str(mcp_browser).strip().lower()
            if mcp_l not in accepted:
                errors.append("UI verification requires browser MCP: chrome-devtools|claude-in-chrome|agent360-browser-mcp|browser-mcp")
            if str(visual_method).strip().lower() not in {"browser", "web", "chrome-devtools", "claude-in-chrome", "agent360", "agent360-browser-mcp", "browser-mcp"}:
                errors.append("UI verification requires VISUAL_CHECK_METHOD: browser/web MCP")
        if str(mcp_browser).strip().lower().startswith("not_applicable:no_ui_surface"):
            errors.append("UI slice cannot declare backend/no-ui verification")
    else:
        if str(mcp_browser).strip().lower() != "not_applicable:no_ui_surface":
            errors.append("non-UI verification requires MCP_BROWSER: not_applicable:no_ui_surface")
        if str(visual_method).strip().lower() != "backend":
            errors.append("non-UI verification requires VISUAL_CHECK_METHOD: backend")
        required_categories = [str(x) for x in (surface.get("required_evidence_categories") or []) if str(x).strip()]
        if not required_categories:
            required_categories = [str(c.get("kind")) for c in (surface.get("evidence_matrix") or []) if isinstance(c, dict) and c.get("required")]
        blob = _evidence_blob(fields, evidence, handoff_text)
        for category in required_categories:
            category_l = category.lower()
            aliases = {category_l, category_l.replace("_", " "), f"evidence_{category_l}", f"flow_{category_l}"}
            if not any(alias in blob for alias in aliases):
                errors.append(f"missing real evidence for required non-UI category {category}")

    return sorted(set(errors))

