from __future__ import annotations
from typing import Any
from orchestrator.common import project_root, read_yaml


def load_state_machine() -> dict[str, Any]:
    return read_yaml(project_root() / "orchestrator" / "rules" / "state-machine.yaml", {})


def status_names() -> set[str]:
    return set((load_state_machine().get("statuses") or {}).keys())


def info_only_roles() -> set[str]:
    return set(load_state_machine().get("info_only_roles") or [])


def terminal_statuses() -> set[str]:
    return set(load_state_machine().get("terminal_statuses") or [])


def active_statuses() -> set[str]:
    return set(load_state_machine().get("active_statuses") or [])


def transitions() -> dict[str, list[list[str]]]:
    return load_state_machine().get("transitions", {}) or {}


def allowed_transition(actor: str, from_status: str, to_status: str) -> bool:
    pairs = transitions().get(actor, []) or []
    return [from_status, to_status] in pairs or (from_status, to_status) in [tuple(p) for p in pairs]


def explain_transition(actor: str, from_status: str, to_status: str) -> str:
    if allowed_transition(actor, from_status, to_status):
        return "allowed"
    return f"transition not allowed: actor={actor} {from_status}->{to_status}"


def normalize_actor(actor: str | None) -> str:
    return (actor or "unknown").strip() or "unknown"


def can_close(actor: str | None) -> bool:
    return normalize_actor(actor) == "closer"


def state_machine_errors(contract_roles: dict[str, Any] | None = None) -> list[str]:
    sm = load_state_machine()
    statuses = set((sm.get("statuses") or {}).keys())
    trans = sm.get("transitions") or {}
    info = set(sm.get("info_only_roles") or [])
    errors: list[str] = []
    if not statuses:
        errors.append("state-machine has no statuses")
    for role, pairs in trans.items():
        if role in info:
            errors.append(f"info-only role {role} must not have lifecycle transitions")
        for pair in pairs or []:
            if not isinstance(pair, list) or len(pair) != 2:
                errors.append(f"{role}: invalid transition pair {pair!r}")
                continue
            src, dst = map(str, pair)
            if src not in statuses:
                errors.append(f"{role}: unknown from status {src}")
            if dst not in statuses:
                errors.append(f"{role}: unknown to status {dst}")
            if dst == "done" and role != "closer":
                errors.append(f"{role}: only closer may transition to done")
            if dst == "verified_pending_close" and role != "slice-verifier":
                errors.append(f"{role}: only slice-verifier may transition to verified_pending_close")
            if dst == "ready_for_close" and role not in {"tester", "deployer"}:
                errors.append(f"{role}: only tester/deployer may transition to ready_for_close")
    for s in sm.get("active_statuses") or []:
        if s not in statuses:
            errors.append(f"active_status {s} missing from statuses")
    for s in sm.get("terminal_statuses") or []:
        if s not in statuses:
            errors.append(f"terminal_status {s} missing from statuses")
    if contract_roles:
        mutating = {r for r, spec in contract_roles.items() if spec.get("mutates_registry_lifecycle")}
        declared_info = {r for r, spec in contract_roles.items() if spec.get("info_only") or not spec.get("mutates_registry_lifecycle")}
        for role in mutating:
            if role not in trans:
                errors.append(f"contract mutating role {role} has no state-machine transitions")
            if role in info:
                errors.append(f"contract mutating role {role} is also info-only")
        for role in declared_info:
            if role in trans and role in info:
                errors.append(f"contract info-only role {role} unexpectedly has transitions")
            if role not in info and not contract_roles.get(role, {}).get("mutates_registry_lifecycle"):
                errors.append(f"contract info-only role {role} missing from state-machine.info_only_roles")
    return sorted(set(errors))
