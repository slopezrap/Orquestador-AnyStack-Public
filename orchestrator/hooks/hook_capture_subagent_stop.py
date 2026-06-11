from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Any

from orchestrator.common import (
    append_jsonl,
    bump_spawn_count,
    configured_git_workflow,
    dag_worker_task_id,
    file_lock,
    find_task,
    get_spawn_budget,
    handoff_path,
    evidence_dir,
    reports_dir,
    ledger_path,
    load_registry,
    load_runtime_state,
    log_hook_error,
    now_iso,
    project_root,
    read_json,
    registry_path,
    runtime_state_path,
    save_registry,
    save_runtime_state,
)
from orchestrator.runtime.state_machine import allowed_transition, info_only_roles
from orchestrator.runtime.verify_requirements import validate_verify_acceptance
from orchestrator.runtime.handoff import append_handoff_event, ensure_handoff_header
from orchestrator.runtime.memory_yaml import record_agent_stop, write_memory_snapshot, record_task_transition, append_lifecycle_event

TRAILER_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(?P<key>[A-Z][A-Z0-9_]*):\s*(?P<value>.*?)\s*$", re.MULTILINE)
JSON_TRAILER_RE = re.compile(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", re.DOTALL)

OUTCOME_TO_STATUS = {
    "developer": {"success": "validator_tester_pending", "blocked": "blocked", "failed": "blocked"},
    "debugger": {"fixed": "validator_tester_pending", "blocked": "blocked", "failed": "blocked"},
    "tester": {"pass": "ready_for_close", "fail": "needs_debug", "blocked": "blocked"},
    "slice-verifier": {"verified": "verified_pending_close", "issues_found": "needs_debug", "blocked": "blocked"},
    "deployer": {"deployed": "ready_for_close", "planned": "ready_for_close", "blocked": "blocked", "failed": "blocked"},
}


def emit_stop_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


def parse_trailer(text: str) -> dict[str, str]:
    """Parse only explicit final trailers.

    The hook must not infer lifecycle mutations from arbitrary KEY: value lines in
    prose, task-pack examples or draft handoffs. State can move only when the
    final answer, transcript fallback, or role-scoped handoff contains an
    explicit `CLAUDE_TRAILER:` marker or JSON object carrying `claude_trailer`.
    """
    text = text or ""
    out: dict[str, str] = {}
    if "CLAUDE_TRAILER:" in text:
        segment = text.rsplit("CLAUDE_TRAILER:", 1)[-1]
        duplicates: list[str] = []
        for m in TRAILER_LINE_RE.finditer(segment):
            key = m.group("key").lower()
            if key in out and key not in duplicates:
                duplicates.append(key)
            out[key] = m.group("value").strip()
        if duplicates:
            out["__duplicate_keys__"] = ",".join(sorted(duplicates))
        if out:
            return out
    for raw in JSON_TRAILER_RE.findall(text):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("claude_trailer"), dict):
                obj = obj["claude_trailer"]
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if v is not None:
                        out[str(k).lower()] = str(v).strip()
                if out:
                    return out
        except Exception:
            pass
    return {}


def parse_all_trailers(text: str) -> list[dict[str, str]]:
    trailers: list[dict[str, str]] = []
    for part in (text or "").split("CLAUDE_TRAILER:")[1:]:
        parsed = parse_trailer("CLAUDE_TRAILER:" + part)
        if parsed:
            trailers.append(parsed)
    return trailers


def handoff_sections(text: str) -> list[tuple[str, str]]:
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


def recover_role_trailer_from_handoff(text: str, role: str) -> dict[str, str]:
    role_l = (role or "").lower().replace("_", "-")
    candidates: list[dict[str, str]] = []
    for heading, body in handoff_sections(text):
        heading_matches = role_l and role_l in heading.replace("_", "-")
        for trailer in parse_all_trailers(body):
            agent = trailer.get("agent", "").lower().replace("_", "-")
            if agent == role_l or (not agent and heading_matches):
                candidates.append(trailer)
    if candidates:
        return candidates[-1]
    for trailer in parse_all_trailers(text):
        if trailer.get("agent", "").lower().replace("_", "-") == role_l:
            candidates.append(trailer)
    return candidates[-1] if candidates else {}


def contract_roles() -> dict[str, dict[str, Any]]:
    c = read_json(project_root() / ".claude" / "orchestrator-contract.json", {})
    return ((c.get("trailer_schema") or {}).get("roles") or {})


def role_spec(role: str) -> dict[str, Any]:
    return contract_roles().get(role) or {}


def required_missing(trailer: dict[str, str], role: str) -> list[str]:
    spec = role_spec(role)
    keys = [str(k) for k in spec.get("required_keys", [])]
    outcome = trailer.get("outcome", "").lower()
    next_status = trailer.get("next_status", "").lower()
    # Some roles have success-only evidence/report keys.  A blocked trailer must
    # still be machine-readable enough to move to blocked, but it cannot be
    # required to claim production verification or completed Git/report work.
    if next_status == "blocked" or outcome == "blocked":
        if role == "closer":
            keys = ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "BLOCKER_REASON"]
        elif role == "slice-verifier":
            keys = ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "EVIDENCE", "VERIFY_OUTCOME", "BLOCKER_REASON"]
    return [str(k).lower() for k in keys if not trailer.get(str(k).lower())]


def value_errors(trailer: dict[str, str], role: str) -> list[str]:
    spec = role_spec(role)
    errors: list[str] = []
    if trailer.get("__duplicate_keys__"):
        errors.append(f"duplicate CLAUDE_TRAILER keys: {trailer.get('__duplicate_keys__')}")
    if not spec:
        return errors
    outcome = trailer.get("outcome", "").lower()
    next_status = trailer.get("next_status", "").lower()
    allowed = {str(x).lower() for x in spec.get("outcome_values", []) or []}
    if outcome and allowed and outcome not in allowed:
        errors.append(f"OUTCOME={outcome} not allowed for {role}")
    allowed_ns = {str(x).lower() for x in spec.get("next_status_values", []) or []}
    if next_status:
        if allowed_ns and next_status not in allowed_ns:
            errors.append(f"NEXT_STATUS={next_status} not allowed for {role}")
        elif not allowed_ns:
            errors.append(f"NEXT_STATUS supplied for {role}, but the contract declares no lifecycle targets")
    return errors


def role_mutates(role: str) -> bool:
    return bool(role_spec(role).get("mutates_registry_lifecycle"))


def role_info_only(role: str) -> bool:
    return bool(role_spec(role).get("info_only")) or role in info_only_roles()


def normalize_role_trailer(trailer: dict[str, str], role: str) -> dict[str, str]:
    if not role_mutates(role) or role == "closer":
        return trailer
    outcome = trailer.get("outcome", "").lower()
    target = OUTCOME_TO_STATUS.get(role, {}).get(outcome)
    if target and trailer.get("next_status", "").lower() != target:
        trailer = dict(trailer)
        trailer["reported_next_status"] = trailer.get("next_status", "")
        trailer["next_status"] = target
        trailer["guardrail"] = f"{role}_status_rewrite_from_outcome"
    return trailer


def _cleanup_value_ok(value: str) -> bool:
    text = (value or "").strip().lower()
    return text == "yes" or text.startswith("not_applicable:") or text in {"not_applicable", "skipped_no_compose_file"}


def enforce_closer(trailer: dict[str, str], role: str, task: dict[str, Any] | None) -> dict[str, str]:
    if role != "closer" or trailer.get("next_status", "").lower() != "done":
        return trailer
    required_yes = ["report_ready", "baseline_sync_ready", "git_ready", "push_ready", "git_workflow_ready", "runtime_cleaned", "worktrees_cleaned"]
    if configured_git_workflow() == "pr-flow":
        required_yes.extend(["pr_ready", "merged", "canonical_main_synced"])
    bad = [k for k in required_yes if trailer.get(k, "").lower() != "yes"]
    cleanup_required = ["docker_runtime_cleaned", "rancher_runtime_cleaned", "dev_ports_released"]
    for k in cleanup_required:
        if not _cleanup_value_ok(trailer.get(k, "")):
            bad.append(k)
    if trailer.get("outcome", "").lower() != "committed":
        bad.append("outcome")
    if task and task.get("status") != "verified_pending_close":
        bad.append(f"current_status={task.get('status')}")
    if bad:
        log_hook_error("hook_capture_subagent_stop.closer_guardrail", "blocked false done: " + ", ".join(bad))
        trailer = dict(trailer)
        trailer["next_status"] = "blocked"
        trailer["outcome"] = "blocked"
        trailer["blocker_reason"] = "closer_guardrail_failed"
        trailer["guardrail"] = "blocked_false_done"
    return trailer




def _load_verify_evidence_artifact(path_value: str | None) -> Any:
    ep = _rel_artifact(path_value)
    if ep is None or not ep.exists():
        return {}
    candidates: list[Path] = []
    if ep.is_file():
        candidates = [ep]
    elif ep.is_dir():
        preferred = [ep / "slice-verifier.json", ep / "verify-slice.json", ep / "evidence.json"]
        candidates.extend([p for p in preferred if p.exists()])
        candidates.extend(sorted(p for p in ep.glob("*.json") if p not in candidates))
    merged: dict[str, Any] = {"__evidence_path__": str(ep)}
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


def _read_handoff_text_for_verify(trailer: dict[str, str], task_id: str | None) -> str:
    candidates: list[Path] = []
    hp = _rel_artifact(trailer.get("handoff"))
    if hp is not None:
        candidates.append(hp)
    if task_id:
        candidates.append(handoff_path(task_id))
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log_hook_error("hook_capture_subagent_stop.verify_handoff_read", exc)
    return ""


def enforce_slice_verifier(trailer: dict[str, str], role: str, task: dict[str, Any] | None) -> dict[str, str]:
    if role != "slice-verifier" or trailer.get("next_status", "").lower() != "verified_pending_close":
        return trailer
    required = {"verify_outcome": "verified", "handoff": None, "evidence": None}
    bad: list[str] = []
    for key, expected in required.items():
        value = trailer.get(key, "")
        if not value or (expected is not None and value.lower() != expected):
            bad.append(key)
    if task and task.get("status") != "ready_for_close":
        bad.append(f"current_status={task.get('status')}")
    evidence_obj = _load_verify_evidence_artifact(trailer.get("evidence"))
    handoff_text = _read_handoff_text_for_verify(trailer, trailer.get("task_id"))
    bad.extend(validate_verify_acceptance(task, trailer, handoff_text, evidence_obj))
    if bad:
        log_hook_error("hook_capture_subagent_stop.verifier_guardrail", "blocked false verification: " + ", ".join(bad))
        trailer = dict(trailer)
        trailer["next_status"] = "blocked"
        trailer["outcome"] = "blocked"
        trailer["blocker_reason"] = "slice_verifier_guardrail_failed"
        trailer["guardrail"] = "blocked_false_verification"
        trailer["verify_acceptance_errors"] = " | ".join(bad)[:1000]
    return trailer


def enforce_deployer(trailer: dict[str, str], role: str, task: dict[str, Any] | None) -> dict[str, str]:
    if role != "deployer" or trailer.get("next_status", "").lower() != "ready_for_close":
        return trailer
    if trailer.get("outcome", "").lower() == "blocked":
        return trailer
    bad: list[str] = []
    if trailer.get("deploy_ready", "").lower() != "yes":
        bad.append("deploy_ready")
    if not trailer.get("deploy_url"):
        bad.append("deploy_url")
    if bad:
        log_hook_error("hook_capture_subagent_stop.deployer_guardrail", "blocked false deploy: " + ", ".join(bad))
        trailer = dict(trailer)
        trailer["next_status"] = "blocked"
        trailer["outcome"] = "blocked"
        trailer["blocker_reason"] = "deployer_guardrail_failed"
        trailer["guardrail"] = "blocked_false_deploy"
    return trailer

def recover_from_handoff(task_id: str | None, role: str) -> dict[str, str]:
    if not task_id:
        return {}
    p = handoff_path(task_id)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8", errors="replace")
    trailer = recover_role_trailer_from_handoff(text, role)
    if not trailer:
        return {}
    role_key = (role or "").lower().replace("_", "-")
    agent = trailer.get("agent", "").lower().replace("_", "-")
    if agent != role_key:
        log_hook_error("hook_capture_subagent_stop.handoff_agent_scope", f"handoff agent={agent or 'missing'} role={role_key} task={task_id}")
        return {}
    if trailer.get("task_id") and trailer.get("task_id") != task_id:
        log_hook_error("hook_capture_subagent_stop.handoff_task_scope", f"handoff task={trailer.get('task_id')} active={task_id} role={role_key}")
        return {}
    if trailer.get("accepted_by_hook", "").lower() == "yes":
        log_hook_error("hook_capture_subagent_stop.handoff_replay_guard", f"ignored accepted hook trailer role={role_key} task={task_id}")
        return {}
    if trailer.get("outcome", "").lower() in {"pending", "draft", "template"}:
        return {}
    return trailer


def recover_from_transcript(path_value: str | None) -> dict[str, str]:
    if not path_value:
        return {}
    try:
        p = Path(str(path_value)).expanduser()
        if not p.exists() or not p.is_file():
            return {}
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-160:]
        for raw in reversed(lines):
            chunks: list[str] = []
            try:
                obj = json.loads(raw)
            except Exception:
                obj = {}
            if isinstance(obj, dict):
                msg = obj.get("message")
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str):
                        chunks.append(content)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                chunks.append(part["text"])
                if isinstance(obj.get("text"), str):
                    chunks.append(obj["text"])
            if chunks:
                parsed = parse_trailer("\n".join(chunks))
                if parsed:
                    return parsed
    except Exception as exc:
        log_hook_error("hook_capture_subagent_stop.transcript_fallback", exc)
    return {}


def _record_info_only(task: dict[str, Any], role: str, trailer: dict[str, str]) -> None:
    task[f"{role}_outcome"] = trailer.get("outcome")
    if trailer.get("next_status"):
        task[f"{role}_next_status"] = trailer.get("next_status")
    if trailer.get("blocker_reason"):
        task[f"{role}_blocker_reason"] = trailer.get("blocker_reason")
    task["last_info_agent"] = role
    task["last_info_at"] = now_iso()




def _rel_artifact(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    p = Path(str(path_value)).expanduser()
    if not p.is_absolute():
        p = project_root() / p
    try:
        return p.resolve()
    except Exception:
        return p.absolute()


def _under(parent: Path, child: Path | None) -> bool:
    if child is None:
        return False
    try:
        child.relative_to(parent.resolve())
        return True
    except Exception:
        return False


def artifact_errors(trailer: dict[str, str], role: str, task_id: str | None) -> list[str]:
    if not task_id or not role_mutates(role):
        return []
    errors: list[str] = []
    root = project_root().resolve()
    hp = _rel_artifact(trailer.get("handoff"))
    if trailer.get("handoff"):
        expected = handoff_path(task_id).resolve()
        if hp != expected:
            errors.append(f"HANDOFF must be {expected.relative_to(root).as_posix()} for {role}")
        elif not expected.exists():
            errors.append(f"HANDOFF path does not exist for {role}: {expected.relative_to(root).as_posix()}")
    ep = _rel_artifact(trailer.get("evidence"))
    if trailer.get("evidence"):
        expected_parent = evidence_dir(task_id).resolve()
        if not _under(expected_parent, ep):
            errors.append(f"EVIDENCE must be under {expected_parent.relative_to(root).as_posix()} for {role}")
        elif not ep.exists():
            errors.append(f"EVIDENCE path does not exist for {role}: {ep.relative_to(root).as_posix()}")
    rp = _rel_artifact(trailer.get("report"))
    if trailer.get("report"):
        expected_parent = reports_dir().resolve()
        if not _under(expected_parent, rp):
            errors.append(f"REPORT must be under {expected_parent.relative_to(root).as_posix()} for {role}")
        elif role == "closer" and not rp.exists():
            errors.append(f"REPORT path does not exist for closer: {rp.relative_to(root).as_posix()}")
    return errors

def main() -> int:
    journeys_to_add: list[str] = []
    journeys_to_clear: list[str] = []
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return 0
        data = json.loads(raw)
        role = str(data.get("agent_type") or data.get("subagent_type") or "unknown").strip().replace("_", "-")
        msg = data.get("last_assistant_message", "") or ""
        trailer = parse_trailer(msg)
        override = dag_worker_task_id()
        # Claude Code provides last_assistant_message as the subagent final answer.
        # Treat it as authoritative: if it is non-empty but does not contain a
        # valid trailer, do not rescue the lifecycle mutation from an older
        # handoff/transcript. Fallbacks are only for hook payloads that omit the
        # final message entirely.
        final_message_missing = not msg.strip()
        if final_message_missing and (not trailer or len(trailer) < 2) and override:
            rec = recover_from_handoff(override, role)
            if rec:
                rec.update(trailer)
                trailer = rec
        if final_message_missing and (not trailer or len(trailer) < 2):
            rec = recover_from_transcript(data.get("agent_transcript_path"))
            if rec:
                rec.update(trailer)
                trailer = rec
        reported = trailer.get("task_id")
        allow = True
        block_reasons: list[str] = []
        reported_agent = trailer.get("agent", "").lower().replace("_", "-")
        role_key = role.lower().replace("_", "-")
        if reported_agent and reported_agent != role_key:
            allow = False
            block_reasons.append(f"Trailer AGENT {reported_agent} does not match SubagentStop role {role_key}.")
            log_hook_error("hook_capture_subagent_stop.agent_scope", f"reported={reported_agent} effective={role_key} task={override or trailer.get('task_id')}")
        if override:
            if reported and reported != override:
                trailer["reported_task_id"] = reported
                trailer["task_id_mismatch"] = "true"
                allow = False
                block_reasons.append(f"Trailer TASK_ID {reported} does not match active TASK_ID {override}.")
                log_hook_error("hook_capture_subagent_stop.task_scope", f"reported={reported} effective={override} role={role}")
            trailer["task_id"] = override
        tid = trailer.get("task_id") or override
        trailer = normalize_role_trailer(trailer, role)
        if tid and role_mutates(role) and trailer.get("handoff"):
            expected = handoff_path(tid).resolve()
            provided = _rel_artifact(trailer.get("handoff"))
            try:
                if provided == expected:
                    ensure_handoff_header(tid)
            except Exception as exc:
                log_hook_error("hook_capture_subagent_stop.handoff_init", exc)
        missing = required_missing(trailer, role)
        if missing:
            log_hook_error("hook_capture_subagent_stop.trailer", f"missing={missing} role={role} got={sorted(trailer)}")
            allow = False
            block_reasons.append(f"Missing required CLAUDE_TRAILER keys for {role}: {', '.join(missing)}.")
        verr = value_errors(trailer, role)
        if verr:
            log_hook_error("hook_capture_subagent_stop.trailer_schema", "; ".join(verr))
            allow = False
            block_reasons.extend(verr)
        aerr = artifact_errors(trailer, role, tid)
        if aerr:
            log_hook_error("hook_capture_subagent_stop.artifacts", "; ".join(aerr))
            allow = False
            block_reasons.extend(aerr)
        append_jsonl(ledger_path(), {"ts": now_iso(), "event": "subagent_stop", "agent_type": role, "task_id": tid, "trailer": trailer})
        try:
            count = bump_spawn_count(tid, role)
            budget = get_spawn_budget()
            if count > budget:
                log_hook_error("hook_capture_subagent_stop.spawn_budget", f"task={tid} count={count} budget={budget}")
        except Exception as exc:
            log_hook_error("hook_capture_subagent_stop.bump", exc)
        lifecycle_mutated = False
        from_status_for_memory = None
        to_status_for_memory = None
        with file_lock(registry_path()):
            reg = load_registry()
            task = find_task(reg, tid)
            trailer = enforce_slice_verifier(trailer, role, task)
            trailer = enforce_deployer(trailer, role, task)
            trailer = enforce_closer(trailer, role, task)
            if tid and not trailer.get("handoff") and role_mutates(role):
                trailer["handoff"] = handoff_path(tid).resolve().relative_to(project_root().resolve()).as_posix()
            if tid and (role_mutates(role) or role_info_only(role)):
                try:
                    append_handoff_event(tid, role, trailer, task, accepted=allow, note="subagent_stop")
                except Exception as exc:
                    log_hook_error("hook_capture_subagent_stop.handoff_append", exc)
            # Re-validate after guardrails may have rewritten outcome/status.
            # A closer false-done guardrail is itself a legal lifecycle decision:
            # move the slice to blocked so the terminal does not keep pretending
            # it is merely verified_pending_close after a failed PR/runtime cleanup.
            if role == "closer" and trailer.get("guardrail") == "blocked_false_done" and trailer.get("next_status") == "blocked":
                allow = True
            verr2 = value_errors(trailer, role)
            if verr2:
                log_hook_error("hook_capture_subagent_stop.trailer_schema", "; ".join(verr2))
                allow = False
                block_reasons.extend(verr2)
            if allow and role_mutates(role) and not task:
                allow = False
                block_reasons.append(f"No registry task found for TASK_ID {tid}.")
            if allow and task and role_mutates(role) and trailer.get("next_status"):
                current = str(task.get("status"))
                target = trailer.get("next_status", "").lower()
                if allowed_transition(role, current, target):
                    task["status"] = target
                    task["last_outcome"] = trailer.get("outcome")
                    task["last_updated_by"] = role
                    task["last_stop_at"] = now_iso()
                    lifecycle_mutated = True
                    from_status_for_memory = current
                    to_status_for_memory = target
                    if target == "blocked":
                        task["last_blocker"] = {"reason": trailer.get("blocker_reason") or trailer.get("guardrail") or "blocked_by_agent", "agent": role, "at": now_iso()}
                    if trailer.get("handoff"):
                        task["handoff_path"] = trailer["handoff"]
                    if trailer.get("evidence"):
                        task["evidence_dir"] = trailer["evidence"]
                    if trailer.get("report"):
                        task["report_path"] = trailer["report"]
                    if role == "closer" and target == "done":
                        # Defined from the orchestrator: when a slice closes a journey,
                        # gate only dependent journey branches until /verify-journey records the result.
                        for jid in (task.get("closes_journeys") or task.get("journey_refs") or []):
                            j = str(jid).strip()
                            if j:
                                journeys_to_add.append(j)
                    pending_raw = trailer.get("journey_pending_verify") or trailer.get("journey_id") if trailer.get("journey_verify_outcome") else ""
                    if pending_raw:
                        for chunk in str(pending_raw).replace(";", ",").split(","):
                            j = chunk.strip()
                            if j:
                                journeys_to_add.append(j)
                    if trailer.get("journey_verify_outcome", "").lower() == "verified" or trailer.get("journey_verify_waived"):
                        for chunk in str(trailer.get("journey_id") or "").replace(";", ",").split(","):
                            j = chunk.strip()
                            if j:
                                journeys_to_clear.append(j)
                    save_registry(reg)
                else:
                    reason = f"Illegal state-machine transition for {role}: {current}->{target} on task {tid}."
                    block_reasons.append(reason)
                    log_hook_error("hook_capture_subagent_stop.state_machine", f"denied {role} {current}->{target} task={tid}")
            elif allow and task and role_info_only(role):
                _record_info_only(task, role, trailer)
                save_registry(reg)
        with file_lock(runtime_state_path()):
            rt = load_runtime_state()
            rt["last_worker"] = role
            rt["last_trailer"] = trailer
            rt["last_stop_at"] = now_iso()
            pending = [str(x) for x in (rt.get("pending_journey_verifications") or []) if str(x).strip()]
            for jid in journeys_to_add:
                if jid not in pending:
                    pending.append(jid)
            if journeys_to_clear:
                pending = [j for j in pending if j not in set(journeys_to_clear)]
            rt["pending_journey_verifications"] = pending
            if journeys_to_add or journeys_to_clear:
                rt["last_journey_gate_event"] = {"add": journeys_to_add, "clear": journeys_to_clear, "at": now_iso(), "agent": role, "task_id": tid}
            save_runtime_state(rt)
        try:
            accepted = allow and not bool(block_reasons)
            if lifecycle_mutated and tid:
                record_task_transition(str(tid), role, from_status_for_memory, to_status_for_memory, trailer.get("guardrail") or trailer.get("blocker_reason") or trailer.get("outcome") or "subagent_stop")
            else:
                append_lifecycle_event({"kind": "subagent_stop", "task_id": tid, "agent": role, "outcome": trailer.get("outcome"), "next_status": trailer.get("next_status"), "accepted": accepted, "lifecycle_mutated": False})
            record_agent_stop(role, tid, trailer, accepted=accepted, lifecycle_mutated=bool(lifecycle_mutated), note="subagent_stop_hook")
            write_memory_snapshot()
        except Exception as exc:
            log_hook_error("hook_capture_subagent_stop.memory_yaml", exc)
        if block_reasons:
            emit_stop_block(" ".join(block_reasons)[:1800])
    except Exception as exc:
        log_hook_error("hook_capture_subagent_stop", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
