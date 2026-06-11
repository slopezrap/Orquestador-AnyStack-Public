from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator.common import (
    agent_memory_dir,
    agent_memory_path,
    ensure_dirs,
    file_lock,
    find_task,
    load_registry,
    load_runtime_state,
    memory_dir,
    now_iso,
    progress_md_path,
    progress_yaml_path,
    project_root,
    read_json,
    read_yaml,
    registry_path,
    runtime_state_path,
    runtime_state_yaml_path,
    state_dir,
    tasks_dir,
    write_json,
    write_yaml,
)
from orchestrator.runtime.blueprint_lossless import mirror_lossless_to_memory

SCHEMA_VERSION = "1.0"
MAX_AGENT_EVENTS = 80
MAX_GLOBAL_EVENTS = 160

MUTATING_ROLES = {"developer", "debugger", "tester", "slice-verifier", "deployer", "closer"}
INFO_ONLY_ROLES = {
    "main-orchestrator", "planner", "task-planner", "blueprint-reviewer", "document-analyzer",
    "project-architect", "official-docs-researcher", "validator", "screen-journey-reviewer",
}

ROLE_WRITE_SCOPES = {
    "developer": ["own MEMORY.yaml stable lessons", "handoff md/yaml", "evidence", "PROGRESS.yaml via hook"],
    "debugger": ["own MEMORY.yaml stable lessons", "handoff md/yaml", "evidence", "PROGRESS.yaml via hook"],
    "tester": ["own MEMORY.yaml stable lessons", "handoff md/yaml", "evidence", "PROGRESS.yaml via hook"],
    "slice-verifier": ["own MEMORY.yaml stable lessons", "handoff md/yaml", "evidence", "PROGRESS.yaml via hook"],
    "deployer": ["own MEMORY.yaml stable lessons", "handoff md/yaml", "deployment evidence", "PROGRESS.yaml via hook"],
    "closer": ["own MEMORY.yaml stable lessons", "handoff md/yaml", "reports", "lifecycle events", "PROGRESS.yaml via hook"],
    "validator": ["own MEMORY.yaml stable lessons", "handoff findings only", "risk-register.yaml only through runtime helper"],
    "screen-journey-reviewer": ["own MEMORY.yaml stable lessons", "handoff findings only", "risk-register.yaml only through runtime helper"],
    "planner": ["own MEMORY.yaml stable lessons", "task-pack suggestions", "decisions.yaml only through runtime helper"],
    "task-planner": ["own MEMORY.yaml stable lessons", "task-pack suggestions", "decisions.yaml only through runtime helper"],
    "main-orchestrator": ["own MEMORY.yaml stable lessons", "runtime orchestration via skills/hooks", "decisions.yaml only through runtime helper"],
    "blueprint-reviewer": ["own MEMORY.yaml stable lessons", "blueprint findings", "decisions.yaml only through runtime helper"],
    "document-analyzer": ["own MEMORY.yaml stable lessons", "document findings", "decisions.yaml only through runtime helper"],
    "project-architect": ["own MEMORY.yaml stable lessons", "architecture findings", "decisions.yaml only through runtime helper"],
    "official-docs-researcher": ["own MEMORY.yaml stable lessons", "official-doc notes", "memory/official-doc-notes through runtime helper"],
}

STRUCTURED_MEMORY_CONTRACT = {
    "markdown_progress_index": "orchestrator-state/memory/PROGRESS.md",
    "yaml_progress_authority": "orchestrator-state/memory/PROGRESS.yaml",
    "markdown_agent_memory_index": "orchestrator-state/agent-memory/<agent>/MEMORY.md",
    "yaml_agent_memory_authority": "orchestrator-state/agent-memory/<agent>/MEMORY.yaml",
    "rule": "Structured runtime memory discipline: PROGRESS is read first after /clear, agent memory is per-role, task facts live in handoff/evidence/report, and lifecycle mutation is performed only by hooks from trailers.",
}


AGENT_RUNTIME_CONTRACT: dict[str, dict[str, Any]] = {
    "main-orchestrator": {
        "runtime_role": "main thread coordinator; never a nested sub-orchestrator",
        "runtime_responsibilities": [
            "Own the operator flow across /next-wave, /next-slice, /verify-slice, /closer and /phase-gate.",
            "Delegate to planner/developer/tester/slice-verifier/closer in order while respecting spawn budget and state-machine authority.",
            "Keep runtime truth on disk, not in chat history; after /clear recover from PROGRESS.yaml, registry, task DAG and handoffs.",
        ],
        "writes": ["metadata only", "handoff notes when acting as main thread", "no registry lifecycle mutation"],
    },
    "planner": {
        "runtime_role": "context assembler and DAG/task-pack planner",
        "runtime_responsibilities": [
            "Read the compiled DAG and active task pack before recommending implementation.",
            "Preserve write_set, conflict_group, locks, dependencies and journey gates when proposing a slice plan.",
            "Report source/runtime drift instead of editing generated registry or task packs.",
        ],
        "writes": ["planner findings", "own MEMORY.yaml stable planning lessons", "no task.status mutation"],
    },
    "task-planner": {
        "runtime_role": "fine-grained task planning and follow-up triage",
        "runtime_responsibilities": [
            "Break a registry slice into safe implementation steps without expanding its compiled scope.",
            "Identify true out-of-scope work as follow-up candidates only after repair triage; small/in-scope fixes stay in the active TASK_ID.",
            "Keep dependency and conflict discipline aligned with parallel execution.",
        ],
        "writes": ["planning handoff metadata", "own MEMORY.yaml", "follow-up recommendation only"],
    },
    "blueprint-reviewer": {
        "runtime_role": "new blueprint-first replacement for source-document analyzer gate",
        "runtime_responsibilities": [
            "Audit inputs/BLUEPRINT.md fenced yaml orchestrator blocks before compile/bootstrap.",
            "Ensure arc42, the eight logic groups, auxiliary contracts and registry slices keep detailed human descriptions.",
            "Report broken references or weak descriptions before the compiler turns them into runtime state.",
        ],
        "writes": ["blueprint findings", "own MEMORY.yaml", "no generated artifact mutation"],
    },
    "document-analyzer": {
        "runtime_role": "source document consistency reviewer",
        "runtime_responsibilities": [
            "Review blueprint/source-map/compile-report consistency instead of secondary source pack.",
            "Detect prose-vs-YAML drift, missing description detail and unresolved IDs.",
            "Do not alter generated JSON; recommend blueprint maintenance and recompilation.",
        ],
        "writes": ["analysis findings", "own MEMORY.yaml", "no lifecycle mutation"],
    },
    "project-architect": {
        "runtime_role": "architecture boundary and ADR reviewer",
        "runtime_responsibilities": [
            "Preserve building-block ownership, paths, write surfaces and ADR intent from blueprint to task packs.",
            "Reject hidden architecture changes not represented by inputs/BLUEPRINT.md and compiled resolved_specs.",
            "Ensure new architecture implies new IDs, verification and dependency rationale before implementation.",
        ],
        "writes": ["architecture findings", "own MEMORY.yaml", "decisions.yaml only when explicitly recording a durable decision"],
    },
    "official-docs-researcher": {
        "runtime_role": "official documentation verifier",
        "runtime_responsibilities": [
            "Use official docs for Claude Code, providers, SDKs and volatile platform behavior before giving guidance.",
            "Record exact version/date/source notes as durable memory only when they affect future slices.",
            "Return discrepancy/insufficient instead of inventing current behavior.",
        ],
        "writes": ["official-doc notes", "own MEMORY.yaml", "no lifecycle mutation"],
    },
    "validator": {
        "runtime_role": "static reviewer before tester",
        "runtime_responsibilities": [
            "Review code and contract fit against task description, resolved_specs, acceptance and write_set.",
            "Identify blockers for tester/debugger without mutating task.status.",
            "Preserve security, no-stub and scope boundaries defined by the validator contract.",
        ],
        "writes": ["validator handoff findings", "own MEMORY.yaml", "no NEXT_STATUS"],
    },
    "screen-journey-reviewer": {
        "runtime_role": "info-only screen/journey/visual reviewer",
        "runtime_responsibilities": [
            "Review UI/route/visual-contract slices after real verification, not backend dependencies merely because they reference journeys.",
            "Mark non-UI backend journey dependencies as not_applicable with a reason instead of forcing browser/mobile MCP.",
            "Report UX findings as metadata for debugger/tester/verifier; never mutate lifecycle.",
        ],
        "writes": ["screen/journey findings", "own MEMORY.yaml", "no NEXT_STATUS"],
    },
    "developer": {
        "runtime_role": "single-slice implementer",
        "runtime_responsibilities": [
            "Implement only the active registry slice, using task description and resolved_specs rather than ID names alone.",
            "Respect write_set/conflict_group/locks and leave durable handoff/evidence before success trailer.",
            "Never edit generated registry/runtime/task DAG files by hand.",
        ],
        "writes": ["code within write_set", "handoff/evidence", "own MEMORY.yaml stable lessons"],
    },
    "debugger": {
        "runtime_role": "smallest in-scope repair agent",
        "runtime_responsibilities": [
            "Fix only the blocker reported by tester/slice-verifier/closer guardrails.",
            "Avoid broad replanning or scope expansion; register follow-up candidates only when repair triage proves the work cannot be solved in the active slice.",
            "Return to validator_tester_pending after a focused fix.",
        ],
        "writes": ["smallest code fix", "handoff/evidence", "own MEMORY.yaml stable lessons"],
    },
    "tester": {
        "runtime_role": "test executor and ready-for-close gate",
        "runtime_responsibilities": [
            "Run real relevant tests/commands for the slice and produce durable evidence.",
            "Move only to ready_for_close, needs_debug or blocked through trailer; never verify or close.",
            "Differentiate product failure from mechanical environment failure in handoff YAML/Markdown.",
        ],
        "writes": ["test evidence", "handoff", "own MEMORY.yaml"],
    },
    "slice-verifier": {
        "runtime_role": "human-real verification gate before closer",
        "runtime_responsibilities": [
            "Verify runtime behavior using real/provided data and logs; no fake/mock/stub evidence.",
            "Use API/worker/non-UI verification for backend slices even when they reference journeys; require browser/mobile only when UI surface is declared.",
            "Move only to verified_pending_close, needs_debug or blocked through trailer.",
        ],
        "writes": ["verification evidence", "verify handoff", "own MEMORY.yaml"],
    },
    "deployer": {
        "runtime_role": "deployment helper and deploy readiness gate",
        "runtime_responsibilities": [
            "Prepare deployment artifacts within the active slice and declared stack only.",
            "Prove deploy readiness with evidence and URL/target when applicable.",
            "Do not close; return ready_for_close or blocked.",
        ],
        "writes": ["deployment evidence", "handoff", "own MEMORY.yaml"],
    },
    "closer": {
        "runtime_role": "manual finalizer with report, runtime snapshot, Git workflow, cleanup",
        "runtime_responsibilities": [
            "Close only verified_pending_close slices and never implement fixes.",
            "Run report, runtime snapshot, git workflow/pr-flow, Rancher/Docker cleanup and worktree cleanup before done.",
            "Record journey pending verification when a closed slice owns journeys.",
        ],
        "writes": ["report", "handoff", "git/pr-flow evidence", "runtime cleanup evidence", "own MEMORY.yaml"],
    },
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _safe_id(value: str | None) -> str:
    return str(value or "unknown").strip().replace("_", "-") or "unknown"


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root().resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _contract_roles() -> dict[str, dict[str, Any]]:
    contract = read_json(project_root() / ".claude" / "orchestrator-contract.json", {})
    return ((contract.get("trailer_schema") or {}).get("roles") or {})


def _agent_frontmatter(agent: str) -> dict[str, Any]:
    path = project_root() / ".claude" / "agents" / f"{agent}.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = read_yaml_text(m.group(1))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_yaml_text(text: str) -> Any:
    # Prefer PyYAML through a temp-free fallback: write/read is unnecessary here.
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except Exception:
        out: dict[str, Any] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            v = v.strip()
            if v.lower() in {"true", "false"}:
                out[k.strip()] = v.lower() == "true"
            else:
                out[k.strip()] = v.strip('"\'')
        return out


def _agents() -> list[str]:
    names = set(_contract_roles().keys())
    agents_dir = project_root() / ".claude" / "agents"
    if agents_dir.is_dir():
        names.update(p.stem for p in agents_dir.glob("*.md"))
    return sorted(_safe_id(x) for x in names if x)


def _role_kind(agent: str) -> str:
    spec = _contract_roles().get(agent, {})
    if bool(spec.get("mutates_registry_lifecycle")) or agent in MUTATING_ROLES:
        return "mutating_lifecycle"
    return "info_only"


def _default_agent_memory(agent: str) -> dict[str, Any]:
    spec = _contract_roles().get(agent, {})
    fm = _agent_frontmatter(agent)
    return {
        "schema_version": SCHEMA_VERSION,
        "agent": agent,
        "role_kind": _role_kind(agent),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "source": {
            "agent_prompt": f".claude/agents/{agent}.md",
            "contract": ".claude/orchestrator-contract.json",
            "state_machine": "orchestrator/rules/state-machine.yaml",
            "runtime_truth": "orchestrator-state/tasks/registry.json",
            "skills_runtime_rule": f".claude/rules/07-skills-runtime.md",
            "memory_contract_rule": ".claude/rules/12-memory-yaml-contract.md",
        },
        "native_runtime_contract": AGENT_RUNTIME_CONTRACT.get(agent, {
            "runtime_role": "blueprint-first role generated from orchestrator contract",
            "runtime_responsibilities": [],
            "writes": [],
        }),
        "claude_code": {
            "frontmatter_name": fm.get("name") or agent,
            "permission_mode": fm.get("permissionMode") or "bypassPermissions",
            "max_turns": fm.get("maxTurns"),
            "tools": fm.get("tools"),
            "skills": fm.get("skills"),
            "memory": fm.get("memory") or "project",
            "official_memory_scope": fm.get("memory") or "project",
            "official_project_memory_dir": f".claude/agent-memory/{agent}/",
        },
        "structured_runtime_memory_contract": STRUCTURED_MEMORY_CONTRACT,
        "read_order": [
            "CLAUDE.md",
            ".claude/CLAUDE.md",
            "orchestrator-state/memory/PROGRESS.yaml",
            "orchestrator-state/memory/project-context.yaml",
            "orchestrator-state/memory/source-manifest.yaml",
            "orchestrator-state/memory/blueprint-manifest.yaml",
            "orchestrator-state/memory/blueprint-sections.yaml",
            "orchestrator-state/memory/blueprint-blocks.yaml",
            "orchestrator-state/compiled/BLUEPRINT.snapshot.md",
            "orchestrator-state/compiled/blueprint-sections.json",
            "orchestrator-state/compiled/blueprint-blocks.json",
            "orchestrator-state/tasks/runtime-state.yaml",
            "orchestrator-state/tasks/registry.json",
            "orchestrator-state/tasks/task-dag.json",
            "orchestrator-state/tasks/task-index.yaml",
            "orchestrator-state/tasks/slices/<TASK_ID>.yaml",
            "active task-pack JSON and Markdown",
            "active handoff YAML and Markdown",
            f"orchestrator-state/agent-memory/{agent}/MEMORY.yaml",
        ],
        "write_contract": {
            "canonical_memory_file": f"orchestrator-state/agent-memory/{agent}/MEMORY.yaml",
            "markdown_index": f"orchestrator-state/agent-memory/{agent}/MEMORY.md",
            "allowed_writes": ROLE_WRITE_SCOPES.get(agent, ["own MEMORY.yaml stable lessons", "handoff/evidence if role contract permits"]),
            "never_write": [
                ".claude/**",
                "orchestrator/rules/state-machine.yaml",
                ".claude/orchestrator-contract.json",
                "orchestrator-state/compiled/**",
                "orchestrator-state/tasks/registry.json",
                "orchestrator-state/tasks/runtime-state.json",
                "orchestrator-state/tasks/task-dag.json",
                "orchestrator-state/tasks/task-packs/**",
                "orchestrator-state/memory/PROGRESS.yaml",
                "orchestrator-state/memory/task-dag.yaml",
            ],
            "runtime_writes_go_to": [
                "orchestrator-state/agent-memory/<agent>/MEMORY.yaml",
                "orchestrator-state/tasks/handoffs/<TASK_ID>.yaml|md via hook/write-handoff",
                "orchestrator-state/tasks/evidence/<TASK_ID>/",
                "orchestrator-state/tasks/reports/<TASK_ID>.md for closer",
                "orchestrator-state/tasks/handoff-index.yaml via hook",
                "orchestrator-state/tasks/lifecycle-events.yaml via hook",
                "orchestrator-state/tasks/ledger.jsonl via hooks",
                "orchestrator-state/memory/PROGRESS.yaml via hooks/bootstrap",
                "orchestrator-state/memory/decisions.yaml or risk-register.yaml only through explicit runtime helper/skill",
            ],
        },
        "trailer_contract": {
            "required_keys": spec.get("required_keys") or [],
            "outcome_values": spec.get("outcome_values") or [],
            "next_status_values": spec.get("next_status_values") or [],
            "mutates_registry_lifecycle": bool(spec.get("mutates_registry_lifecycle")),
            "info_only": bool(spec.get("info_only")),
        },
        "verify_slice_memory_contract": {
            "routing_source": "orchestrator-state/tasks/slices/<TASK_ID>.yaml -> slice.verification_surface",
            "visual_trigger": "requires_visual_mcp=true only when UI specs/routes/frontend-mobile write surfaces or explicit visual contract exist",
            "non_ui_evidence_matrix": "verification_surface.evidence_matrix describes endpoint/service, DB/DDL, worker/pipeline, dependency, integration, core and permission/state/error evidence",
            "journey_refs_rule": "journey_refs alone are journey-gate metadata and never browser/mobile proof",
        },
        "stable_lessons": [],
        "active_constraints": [
            "Use inputs/BLUEPRINT.md fenced yaml orchestrator blocks as human source; never reintroduce the secondary source pack.",
            "Use task-pack resolved_specs and description as scope; never infer scope from IDs only.",
            "Do not edit generated registry/task-dag/runtime-state by hand; lifecycle changes go through CLAUDE_TRAILER and hooks.",
            "Write durable observations to MEMORY.yaml, not .claude/.",
        ],
        "counters": {"starts": 0, "stops": 0, "accepted_lifecycle_events": 0, "blocked_events": 0, "info_only_events": 0},
        "recent_events": [],
    }


def ensure_agent_memory(agent: str) -> dict[str, Any]:
    ensure_dirs()
    agent = _safe_id(agent)
    path = agent_memory_path(agent, "yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        try:
            current = read_yaml(path, None)
        except Exception:
            archive_dir = path.parent / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            try:
                path.rename(archive_dir / f"MEMORY.corrupt.{now_iso().replace(':', '').replace('+', 'Z')}.yaml")
            except Exception:
                pass
            current = None
        if not isinstance(current, dict) or not current:
            current = _default_agent_memory(agent)
        else:
            defaults = _default_agent_memory(agent)
            for key, value in defaults.items():
                current.setdefault(key, value)
            # Keep generated structural contracts current even when MEMORY.yaml already exists.
            # Preserve learned stable_lessons/recent_events, but refresh deterministic
            # path contracts from the current agent prompt, state-machine and runtime.
            for inactive_key in ["canonical_runtime_port", "canonical_runtime_memory_port"]:
                current.pop(inactive_key, None)
            if isinstance(current.get("source"), dict):
                for inactive_source_key in ["canonical_prompt_archive", "canonical_port_matrix"]:
                    current["source"].pop(inactive_source_key, None)
            for key in ["source", "native_runtime_contract", "structured_runtime_memory_contract", "claude_code", "read_order", "write_contract", "trailer_contract"]:
                current[key] = defaults.get(key, current.get(key, {}))
            current["updated_at"] = now_iso()
            current.setdefault("counters", {})
            current.setdefault("recent_events", [])
            current.setdefault("stable_lessons", [])
        write_yaml(path, current)
        _write_agent_memory_md(agent, current)
        return current


def _write_agent_memory_md(agent: str, data: dict[str, Any]) -> None:
    path = agent_memory_path(agent, "md")
    path.parent.mkdir(parents=True, exist_ok=True)
    recent = data.get("recent_events") or []
    lines = [
        f"# {agent} memory index",
        "",
        "Canonical memory is YAML. This Markdown file is a human-readable index for Claude and maintainers.",
        "",
        f"- Canonical YAML: `{_rel(agent_memory_path(agent, 'yaml'))}`",
        f"- Updated at: `{data.get('updated_at')}`",
        f"- Role kind: `{data.get('role_kind')}`",
        "",
        "## Stable lessons",
    ]
    for item in (data.get("stable_lessons") or [])[:30]:
        if isinstance(item, dict):
            lines.append(f"- {item.get('text') or item.get('lesson') or item}")
        else:
            lines.append(f"- {item}")
    if not (data.get("stable_lessons") or []):
        lines.append("- none yet")
    lines += ["", "## Recent events"]
    for ev in recent[-12:]:
        lines.append(f"- `{ev.get('at')}` task=`{ev.get('task_id')}` event=`{ev.get('event')}` outcome=`{ev.get('outcome')}` status=`{ev.get('next_status')}`")
    if not recent:
        lines.append("- none yet")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def record_agent_start(agent: str, task_id: str | None) -> dict[str, Any]:
    agent = _safe_id(agent)
    ensure_agent_memory(agent)
    path = agent_memory_path(agent, "yaml")
    with file_lock(path):
        data = read_yaml(path, {})
        if not isinstance(data, dict) or not data:
            data = _default_agent_memory(agent)
        data["updated_at"] = now_iso()
        data.setdefault("counters", {})["starts"] = int(data.get("counters", {}).get("starts") or 0) + 1
        data.setdefault("recent_events", []).append({"at": now_iso(), "event": "SubagentStart", "task_id": task_id})
        data["recent_events"] = data["recent_events"][-MAX_AGENT_EVENTS:]
        write_yaml(path, data)
        _write_agent_memory_md(agent, data)
        return data


def record_agent_stop(agent: str, task_id: str | None, trailer: dict[str, str], *, accepted: bool, lifecycle_mutated: bool, note: str = "") -> dict[str, Any]:
    agent = _safe_id(agent)
    ensure_agent_memory(agent)
    path = agent_memory_path(agent, "yaml")
    with file_lock(path):
        data = read_yaml(path, {})
        if not isinstance(data, dict) or not data:
            data = _default_agent_memory(agent)
        counters = data.setdefault("counters", {})
        counters["stops"] = int(counters.get("stops") or 0) + 1
        if accepted and lifecycle_mutated:
            counters["accepted_lifecycle_events"] = int(counters.get("accepted_lifecycle_events") or 0) + 1
        elif accepted:
            counters["info_only_events"] = int(counters.get("info_only_events") or 0) + 1
        else:
            counters["blocked_events"] = int(counters.get("blocked_events") or 0) + 1
        event = {
            "at": now_iso(),
            "event": "SubagentStop",
            "task_id": task_id,
            "agent": agent,
            "accepted": bool(accepted),
            "lifecycle_mutated": bool(lifecycle_mutated),
            "outcome": trailer.get("outcome"),
            "next_status": trailer.get("next_status"),
            "handoff": trailer.get("handoff"),
            "evidence": trailer.get("evidence"),
            "report": trailer.get("report"),
            "blocker_reason": trailer.get("blocker_reason"),
            "note": note,
        }
        data.setdefault("recent_events", []).append(event)
        data["recent_events"] = data["recent_events"][-MAX_AGENT_EVENTS:]
        data["last_trailer"] = {k: v for k, v in sorted(trailer.items()) if not k.startswith("__")}
        data["updated_at"] = now_iso()
        write_yaml(path, data)
        _write_agent_memory_md(agent, data)
    append_progress_event({"kind": "subagent_stop", **event})
    # Structured lifecycle event mirror. The JSON registry remains canonical; this
    # YAML ledger is for /clear recovery and cross-agent continuity, defined from
    # the durable lifecycle-events workflow.
    lifecycle = tasks_dir() / "lifecycle-events.yaml"
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(lifecycle):
        ledger = read_yaml(lifecycle, None)
        if not isinstance(ledger, dict) or not ledger:
            ledger = {"schema_version": SCHEMA_VERSION, "kind": "orchestrator.lifecycle_events", "events": []}
        ledger.setdefault("schema_version", SCHEMA_VERSION)
        ledger.setdefault("kind", "orchestrator.lifecycle_events")
        ledger.setdefault("events", [])
        ledger["updated_at"] = now_iso()
        ledger["events"].append({"kind": "subagent_stop", **event})
        ledger["events"] = ledger["events"][-500:]
        write_yaml(lifecycle, ledger)
    return data


def build_project_context(inp: dict[str, Any] | None = None, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    if inp is None:
        inp = read_json(state_dir() / "compiled" / "orchestrator-input.json", {})
    if registry is None:
        registry = load_registry()
    logic_counts = {k: len(v or []) for k, v in ((inp.get("logic") or {}).items() if isinstance(inp, dict) else [])}
    aux_counts = {k: len(v or []) for k, v in ((inp.get("auxiliary") or {}).items() if isinstance(inp, dict) else [])}
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now_iso(),
        "project": (inp or {}).get("project") or (registry or {}).get("project") or {},
        "stack": (inp or {}).get("stack") or (registry or {}).get("stack") or {},
        "source_chain": [
            "inputs/BLUEPRINT.md",
            "orchestrator-state/compiled/orchestrator-input.json",
            "orchestrator-state/tasks/registry.json",
            "orchestrator-state/tasks/task-dag.json",
            "orchestrator-state/tasks/task-packs/*.json|md",
            "orchestrator-state/compiled/BLUEPRINT.snapshot.md",
            "orchestrator-state/compiled/blueprint-sections.json",
            "orchestrator-state/compiled/blueprint-blocks.json",
            "orchestrator-state/memory/blueprint-manifest.yaml",
        ],
        "blueprint_lossless": (inp or {}).get("blueprint") or {},
        "logic_counts": logic_counts,
        "auxiliary_counts": aux_counts,
        "slice_count": len((registry or {}).get("tasks", []) or []),
        "blueprint_sha256": ((inp or {}).get("compiler") or {}).get("blueprint_sha256"),
    }


def build_progress(registry: dict[str, Any] | None = None, runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_registry()
    runtime = runtime or load_runtime_state()
    tasks = [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]
    by_status: dict[str, int] = {}
    for task in tasks:
        by_status[str(task.get("status") or "unknown")] = by_status.get(str(task.get("status") or "unknown"), 0) + 1
    ready = [t for t in tasks if t.get("status") == "ready"]
    active = [t for t in tasks if t.get("status") in {"claimed", "in_progress", "validator_tester_pending", "needs_debug", "ready_for_close", "verified_pending_close"}]
    done = [t for t in tasks if t.get("status") == "done"]
    not_done = [t for t in tasks if t.get("status") != "done"]
    next_ready = ready[0] if ready else (not_done[0] if not_done else None)
    last_closed = done[-1] if done else None
    phases = []
    for ph in registry.get("phases", []) or []:
        phases.append({"id": ph.get("id"), "status": ph.get("status"), "task_ids": ph.get("task_ids") or []})
    existing = read_yaml(progress_yaml_path(), {})
    events = []
    if isinstance(existing, dict):
        events = list(existing.get("recent_events") or [])[-MAX_GLOBAL_EVENTS:]
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now_iso(),
        "active_task_id": runtime.get("active_task_id"),
        "spawn_budget": runtime.get("spawn_budget", 70),
        "spawn_counts": runtime.get("spawn_counts") or {},
        "task_counts": {"total": len(tasks), "by_status": by_status},
        "ready_tasks": [{"id": t.get("id"), "title": t.get("title"), "phase_id": t.get("phase_id")} for t in ready[:20]],
        "active_tasks": [{"id": t.get("id"), "title": t.get("title"), "status": t.get("status"), "phase_id": t.get("phase_id")} for t in active[:20]],
        "phases": phases,
        "current_phase": (next_ready or {}).get("phase_id"),
        "last_closed_slice": {"id": last_closed.get("id"), "title": last_closed.get("title"), "phase_id": last_closed.get("phase_id")} if last_closed else None,
        "next_slice": {"id": next_ready.get("id"), "title": next_ready.get("title"), "phase_id": next_ready.get("phase_id"), "status": next_ready.get("status"), "verification_surface": next_ready.get("verification_surface") or {}} if next_ready else None,
        "journey_gates": runtime.get("pending_journey_verifications") or [],
        "operational_summary": {
            "backend": {"note": "Derived from registry/task-pack YAML; product-specific endpoint inventory belongs in task evidence."},
            "frontend": {"note": "Derived from logic.ui resolved_specs and UI slices; do not infer UI from journey_refs alone."},
            "database": {"note": "Derived from auxiliary.data/building_blocks/write_set; migrations are task evidence."},
            "tests": {"note": "Latest test evidence is under orchestrator-state/tasks/evidence/<TASK_ID>/ and handoff YAML."},
        },
        "recent_events": events,
    }


def _write_progress_md(progress: dict[str, Any]) -> None:
    lines = [
        "# Orchestrator progress",
        "",
        "Canonical progress is YAML. This Markdown file is a short recovery view.",
        "",
        f"- YAML: `{_rel(progress_yaml_path())}`",
        f"- Updated at: `{progress.get('updated_at')}`",
        f"- Active task: `{progress.get('active_task_id') or 'none'}`",
        f"- Current phase: `{progress.get('current_phase') or 'none'}`",
        f"- Last closed slice: `{((progress.get('last_closed_slice') or {}).get('id')) or 'none'}`",
        f"- Next slice: `{((progress.get('next_slice') or {}).get('id')) or 'none'}`",
        f"- Spawn budget: `{progress.get('spawn_budget')}`",
        "",
        "## Task counts",
    ]
    counts = progress.get("task_counts") or {}
    for key, value in sorted((counts.get("by_status") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Ready tasks"]
    for task in progress.get("ready_tasks") or []:
        lines.append(f"- `{task.get('id')}` {task.get('title')} ({task.get('phase_id')})")
    if not progress.get("ready_tasks"):
        lines.append("- none")
    lines += ["", "## Recent events"]
    for event in (progress.get("recent_events") or [])[-20:]:
        lines.append(f"- `{event.get('at')}` {event.get('kind') or event.get('event')} task=`{event.get('task_id')}` agent=`{event.get('agent')}` outcome=`{event.get('outcome')}`")
    if not progress.get("recent_events"):
        lines.append("- none")
    progress_md_path().write_text("\n".join(lines) + "\n", encoding="utf-8")



def _task_digest(task: dict[str, Any]) -> dict[str, Any]:
    """Return the durable YAML view of a registry task used by agents.

    The JSON registry stays canonical; this YAML digest is a recovery/readability
    mirror for Claude Code subagents after /clear or cross-terminal handoff.
    """
    fields = [
        "id", "task_id", "title", "description", "phase_id", "step_id", "order", "type",
        "status", "depends_on", "dependents", "dependency_rationale", "depends_on_rationale",
        "dependency_edges", "resolved_dependencies", "implements", "builds", "closes_journeys",
        "journey_refs", "arc42_refs", "write_set", "read_set", "conflict_group",
        "conflict_groups", "building_block_refs", "verification_refs", "risk", "risk_level",
        "verify_mode", "verification_surface", "acceptance", "evidence_contract", "contract_refs", "source_refs", "source_sections", "blueprint_lossless_refs",
        "generated_from", "parallel", "locks", "resolved_specs",
    ]
    return {k: task.get(k) for k in fields if k in task}


def build_task_index(registry: dict[str, Any]) -> dict[str, Any]:
    tasks = [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now_iso(),
        "kind": "orchestrator.task_index",
        "canonical_registry": "orchestrator-state/tasks/registry.json",
        "tasks": [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "description": t.get("description"),
                "phase_id": t.get("phase_id"),
                "status": t.get("status"),
                "verification_surface": t.get("verification_surface") or {},
                "depends_on": t.get("depends_on") or [],
                "write_set": t.get("write_set") or [],
                "conflict_groups": t.get("conflict_groups") or t.get("conflict_group") or [],
                "task_yaml": f"orchestrator-state/tasks/slices/{t.get('id')}.yaml",
                "task_pack_json": f"orchestrator-state/tasks/task-packs/{t.get('id')}.json",
                "task_pack_md": f"orchestrator-state/tasks/task-packs/{t.get('id')}.md",
                "handoff_yaml": f"orchestrator-state/tasks/handoffs/{t.get('id')}.yaml",
                "handoff_md": f"orchestrator-state/tasks/handoffs/{t.get('id')}.md",
            }
            for t in tasks
        ],
    }


def _write_task_yaml_mirrors(registry: dict[str, Any]) -> None:
    slices_dir = tasks_dir() / "slices"
    slices_dir.mkdir(parents=True, exist_ok=True)
    for task in [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]:
        tid = str(task.get("id") or task.get("task_id") or "unknown")
        write_yaml(slices_dir / f"{tid}.yaml", {
            "schema_version": SCHEMA_VERSION,
            "kind": "orchestrator.slice_memory",
            "updated_at": now_iso(),
            "canonical_registry": "orchestrator-state/tasks/registry.json",
            "canonical_task_pack_json": f"orchestrator-state/tasks/task-packs/{tid}.json",
            "canonical_task_pack_md": f"orchestrator-state/tasks/task-packs/{tid}.md",
            "slice": _task_digest(task),
        })


def _build_registry_yaml(registry: dict[str, Any]) -> dict[str, Any]:
    tasks = [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "orchestrator.registry_memory",
        "updated_at": now_iso(),
        "canonical_json": "orchestrator-state/tasks/registry.json",
        "project": registry.get("project") or {},
        "phases": registry.get("phases") or [],
        "tasks": [_task_digest(t) for t in tasks],
    }



def _brief_text(data: dict[str, Any]) -> str:
    project = data.get("project") or {}
    lines = [
        f"# Project brief — {project.get('name') or project.get('id') or 'project'}",
        "",
        f"- Project ID: `{project.get('id') or 'unknown'}`",
        f"- Updated at: `{data.get('updated_at')}`",
        "",
        "## Summary",
        str(project.get("summary") or project.get("description") or "Compiled from inputs/BLUEPRINT.md."),
        "",
        "## Logic counts",
    ]
    for key, value in sorted((data.get("logic_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Auxiliary counts"]
    for key, value in sorted((data.get("auxiliary_counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def _architecture_text(data: dict[str, Any]) -> str:
    lines = [
        "# Architecture contract",
        "",
        f"- Updated at: `{data.get('updated_at')}`",
        "- Source: `inputs/BLUEPRINT.md` fenced `yaml orchestrator` blocks",
        "",
        "## Building blocks",
    ]
    for bb in data.get("building_blocks") or []:
        lines.append(f"- `{bb.get('id')}` — {bb.get('name') or ''}: {bb.get('description') or ''}")
    if not data.get("building_blocks"):
        lines.append("- none")
    lines += ["", "## Runtime/verification policy"]
    policy = data.get("verification_policy") or {}
    for k, v in policy.items():
        lines.append(f"- {k}: `{v}`")
    return "\n".join(lines) + "\n"


def build_source_manifest(inp: dict[str, Any] | None = None) -> dict[str, Any]:
    inp = inp or read_json(state_dir() / "compiled" / "orchestrator-input.json", {})
    compiler = (inp or {}).get("compiler") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "orchestrator.source_manifest",
        "updated_at": now_iso(),
        "source_model": "blueprint_first_arc42_yaml_blocks",
        "blueprint": {
            "path": compiler.get("blueprint_path") or "inputs/BLUEPRINT.md",
            "sha256": compiler.get("blueprint_sha256"),
            "compiled_at": compiler.get("compiled_at"),
            "compiler_mode": compiler.get("mode") or "lossless-by-reference",
        },
        "generated": {
            "orchestrator_input": "orchestrator-state/compiled/orchestrator-input.json",
            "source_map": "orchestrator-state/compiled/source-map.json",
            "registry": "orchestrator-state/tasks/registry.json",
            "task_dag": "orchestrator-state/tasks/task-dag.json",
            "blueprint_snapshot": "orchestrator-state/compiled/BLUEPRINT.snapshot.md",
            "blueprint_manifest": "orchestrator-state/compiled/blueprint-manifest.json",
            "blueprint_sections": "orchestrator-state/compiled/blueprint-sections.json",
            "blueprint_blocks": "orchestrator-state/compiled/blueprint-blocks.json",
            "blueprint_lossless": "orchestrator-state/compiled/blueprint-lossless.json",
        },
        "blueprint_lossless": (inp or {}).get("blueprint") or {},
        "gold_blocks": [
            "project", "stack", "auxiliary.arc42", "building_blocks",
            "logic.domain", "logic.application", "logic.journey", "logic.permission",
            "logic.state", "logic.error", "logic.integration", "logic.ui",
            "auxiliary.data", "auxiliary.config", "auxiliary.verification", "auxiliary.adr",
            "auxiliary.risks", "auxiliary.glossary", "auxiliary.external_refs", "registry.slices",
        ],
    }


def build_project_brief(inp: dict[str, Any] | None = None, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    inp = inp or read_json(state_dir() / "compiled" / "orchestrator-input.json", {})
    registry = registry or load_registry()
    ctx = build_project_context(inp, registry)
    project = ctx.get("project") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "orchestrator.project_brief",
        "updated_at": now_iso(),
        "project": project,
        "goals": project.get("goals") or [],
        "non_goals": project.get("non_goals") or [],
        "logic_counts": ctx.get("logic_counts") or {},
        "auxiliary_counts": ctx.get("auxiliary_counts") or {},
        "slice_count": ctx.get("slice_count"),
        "source_chain": ctx.get("source_chain") or [],
        "notes": [
            "Replaces the previous project-brief.md generated from the secondary source pack.",
            "The rich source remains inputs/BLUEPRINT.md; this file is a compact recovery memory for agents after /clear.",
        ],
    }


def build_architecture_contract(inp: dict[str, Any] | None = None) -> dict[str, Any]:
    inp = inp or read_json(state_dir() / "compiled" / "orchestrator-input.json", {})
    aux = (inp or {}).get("auxiliary") or {}
    logic = (inp or {}).get("logic") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "orchestrator.architecture_contract",
        "updated_at": now_iso(),
        "arc42": aux.get("arc42") or [],
        "building_blocks": (inp or {}).get("building_blocks") or [],
        "integration_logic": logic.get("integration") or [],
        "state_logic": logic.get("state") or [],
        "ui_logic": logic.get("ui") or [],
        "data_contracts": aux.get("data") or [],
        "verification_policy": {
            "journey_refs_alone_require_ui": False,
            "visual_mcp_driver": "registry.tasks[].verification_surface.requires_visual_mcp",
            "screen_reviewer_driver": "registry.tasks[].verification_surface.requires_screen_journey_reviewer",
        },
        "notes": [
            "Replaces the previous architecture-contract.md generated from TECHNICAL_GUIDE.md.",
            "Use resolved_specs in task-packs for slice-specific detail.",
        ],
    }

def _ensure_project_yaml_files() -> None:
    defaults = {
        memory_dir() / "decisions.yaml": {
            "schema_version": SCHEMA_VERSION,
            "kind": "orchestrator.decisions",
            "updated_at": now_iso(),
            "decisions": [],
            "note": "Durable operator/orchestrator decisions. ADRs still live in inputs/BLUEPRINT.md; this file records runtime decisions and waivers.",
        },
        memory_dir() / "risk-register.yaml": {
            "schema_version": SCHEMA_VERSION,
            "kind": "orchestrator.risk_register",
            "updated_at": now_iso(),
            "risks": [],
            "note": "Runtime risks discovered by subagents. Product risks remain in inputs/BLUEPRINT.md auxiliary.risks.",
        },
        tasks_dir() / "handoff-index.yaml": {
            "schema_version": SCHEMA_VERSION,
            "kind": "orchestrator.handoff_index",
            "updated_at": now_iso(),
            "handoffs": [],
        },
        tasks_dir() / "lifecycle-events.yaml": {
            "schema_version": SCHEMA_VERSION,
            "kind": "orchestrator.lifecycle_events",
            "updated_at": now_iso(),
            "events": [],
        },
    }
    for path, default in defaults.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        current = read_yaml(path, None)
        if not isinstance(current, dict) or not current:
            write_yaml(path, default)

def write_memory_snapshot(inp: dict[str, Any] | None = None, registry: dict[str, Any] | None = None, runtime: dict[str, Any] | None = None) -> None:
    ensure_dirs()
    (tasks_dir() / "slices").mkdir(parents=True, exist_ok=True)
    registry = registry or load_registry()
    runtime = runtime or load_runtime_state()
    inp = inp or read_json(state_dir() / "compiled" / "orchestrator-input.json", {})
    _ensure_project_yaml_files()
    mirror_lossless_to_memory()
    write_yaml(memory_dir() / "project-context.yaml", build_project_context(inp, registry))
    source_manifest = build_source_manifest(inp)
    project_brief = build_project_brief(inp, registry)
    architecture_contract = build_architecture_contract(inp)
    write_yaml(memory_dir() / "source-manifest.yaml", source_manifest)
    write_yaml(memory_dir() / "project-brief.yaml", project_brief)
    (memory_dir() / "project-brief.md").write_text(_brief_text(project_brief), encoding="utf-8")
    write_yaml(memory_dir() / "architecture-contract.yaml", architecture_contract)
    (memory_dir() / "architecture-contract.md").write_text(_architecture_text(architecture_contract), encoding="utf-8")
    write_yaml(memory_dir() / "stack-profile.yaml", {"schema_version": SCHEMA_VERSION, "kind": "orchestrator.stack_profile_memory", "updated_at": now_iso(), "stack": (inp or {}).get("stack") or {}})
    progress = build_progress(registry, runtime)
    write_yaml(progress_yaml_path(), progress)
    _write_progress_md(progress)
    dag = (registry or {}).get("task_dag") or read_json(tasks_dir() / "task-dag.json", {})
    write_yaml(memory_dir() / "task-dag.yaml", dag)
    write_yaml(tasks_dir() / "task-dag.yaml", dag)
    execution_graph = {"schema_version": SCHEMA_VERSION, "kind": "orchestrator.execution_graph", "updated_at": now_iso(), "tasks": [{"id": t.get("id"), "title": t.get("title"), "description": t.get("description"), "status": t.get("status"), "phase_id": t.get("phase_id"), "depends_on": t.get("depends_on") or [], "write_set": t.get("write_set") or [], "conflict_groups": t.get("conflict_groups") or []} for t in (registry.get("tasks") or [])]}
    write_yaml(memory_dir() / "execution-graph.yaml", execution_graph)
    write_yaml(tasks_dir() / "registry.yaml", _build_registry_yaml(registry))
    write_yaml(tasks_dir() / "registry-summary.yaml", {"schema_version": SCHEMA_VERSION, "kind": "orchestrator.registry_summary", "updated_at": now_iso(), "tasks": execution_graph["tasks"], "phases": registry.get("phases") or []})
    write_yaml(tasks_dir() / "task-index.yaml", build_task_index(registry))
    write_yaml(runtime_state_yaml_path(), runtime)
    _write_task_yaml_mirrors(registry)
    for agent in _agents():
        ensure_agent_memory(agent)

def append_progress_event(event: dict[str, Any]) -> None:
    ensure_dirs()
    with file_lock(progress_yaml_path()):
        progress = build_progress()
        events = list(progress.get("recent_events") or [])
        events.append({"at": event.get("at") or now_iso(), **event})
        progress["recent_events"] = events[-MAX_GLOBAL_EVENTS:]
        progress["updated_at"] = now_iso()
        write_yaml(progress_yaml_path(), progress)
        _write_progress_md(progress)


def init_memory_from_bootstrap(inp: dict[str, Any], registry: dict[str, Any], runtime: dict[str, Any]) -> None:
    write_memory_snapshot(inp, registry, runtime)
    append_progress_event({"kind": "bootstrap", "task_id": None, "tasks": len(registry.get("tasks", []) or []), "phases": len(registry.get("phases", []) or [])})


def _append_task_lifecycle_event(event: dict[str, Any]) -> None:
    """Write the per-task durable lifecycle event that travels with the PR.

    The DAG runtime does not commit the mutable registry. Instead,
    each slice carried a small lifecycle event artifact in its branch/PR, and
    the canonical checkout rehydrated local runtime state from those events
    after the PR reached main.  preserves that behavior without changing
    the blueprint-first authority chain: registry.json remains local runtime;
    orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json is the durable
    per-slice transport signal.
    """
    task_id = str(event.get("task_id") or "").strip()
    if not task_id:
        return
    path = tasks_dir() / "lifecycle-events" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        data = read_json(path, {})
        if not isinstance(data, dict) or not data:
            data = {
                "schema_version": SCHEMA_VERSION,
                "kind": "orchestrator.task_lifecycle_event",
                "task_id": task_id,
                "events": [],
            }
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("kind", "orchestrator.task_lifecycle_event")
        data.setdefault("task_id", task_id)
        data.setdefault("events", [])
        data["events"].append(event)
        data["events"] = data["events"][-MAX_GLOBAL_EVENTS:]
        if event.get("to_status"):
            data["last_status"] = event.get("to_status")
        elif event.get("next_status"):
            data["last_status"] = event.get("next_status")
        data["last_event"] = event
        data["updated_at"] = event.get("at") or now_iso()
        write_json(path, data)


def append_lifecycle_event(event: dict[str, Any]) -> None:
    ensure_dirs()
    path = tasks_dir() / "lifecycle-events.yaml"
    with file_lock(path):
        data = read_yaml(path, None)
        if not isinstance(data, dict) or not data:
            data = {"schema_version": SCHEMA_VERSION, "kind": "orchestrator.lifecycle_events", "updated_at": now_iso(), "events": []}
        ev = {"at": event.get("at") or now_iso(), **event}
        data.setdefault("events", []).append(ev)
        data["events"] = data["events"][-MAX_GLOBAL_EVENTS:]
        data["updated_at"] = now_iso()
        write_yaml(path, data)
    _append_task_lifecycle_event(ev)


def update_handoff_index(task_id: str, role: str | None = None, event: dict[str, Any] | None = None) -> None:
    ensure_dirs()
    path = tasks_dir() / "handoff-index.yaml"
    with file_lock(path):
        data = read_yaml(path, None)
        if not isinstance(data, dict) or not data:
            data = {"schema_version": SCHEMA_VERSION, "kind": "orchestrator.handoff_index", "updated_at": now_iso(), "handoffs": []}
        handoffs = [h for h in (data.get("handoffs") or []) if str(h.get("task_id")) != str(task_id)]
        md = tasks_dir() / "handoffs" / f"{task_id}.md"
        yml = tasks_dir() / "handoffs" / f"{task_id}.yaml"
        ydata = read_yaml(yml, {}) if yml.exists() else {}
        events = ydata.get("events") if isinstance(ydata, dict) else []
        roles = sorted({str(e.get("agent")) for e in (events or []) if isinstance(e, dict) and e.get("agent")})
        handoffs.append({
            "task_id": task_id,
            "handoff_md": f"orchestrator-state/tasks/handoffs/{task_id}.md",
            "handoff_yaml": f"orchestrator-state/tasks/handoffs/{task_id}.yaml",
            "exists_md": md.exists(),
            "exists_yaml": yml.exists(),
            "roles": roles,
            "last_role": role,
            "events_count": len(events or []),
            "updated_at": now_iso(),
        })
        data["handoffs"] = sorted(handoffs, key=lambda x: str(x.get("task_id")))
        data["updated_at"] = now_iso()
        write_yaml(path, data)


def record_task_transition(task_id: str, actor: str, from_status: str | None, to_status: str | None, reason: str = "") -> None:
    event = {"kind": "task_transition", "task_id": task_id, "agent": actor, "from_status": from_status, "to_status": to_status, "reason": reason}
    append_progress_event(event)
    append_lifecycle_event(event)


def check_memory_yaml() -> dict[str, Any]:
    ensure_dirs()
    errors: list[str] = []
    warnings: list[str] = []
    required = [
        "orchestrator-state/memory/PROGRESS.yaml",
        "orchestrator-state/memory/project-context.yaml",
        "orchestrator-state/memory/source-manifest.yaml",
        "orchestrator-state/memory/blueprint-manifest.yaml",
        "orchestrator-state/memory/blueprint-sections.yaml",
        "orchestrator-state/memory/blueprint-blocks.yaml",
        "orchestrator-state/memory/blueprint-lossless.yaml",
        "orchestrator-state/memory/project-brief.yaml",
        "orchestrator-state/memory/project-brief.md",
        "orchestrator-state/memory/architecture-contract.yaml",
        "orchestrator-state/memory/architecture-contract.md",
        "orchestrator-state/memory/stack-profile.yaml",
        "orchestrator-state/memory/decisions.yaml",
        "orchestrator-state/memory/risk-register.yaml",
        "orchestrator-state/memory/task-dag.yaml",
        "orchestrator-state/memory/execution-graph.yaml",
        "orchestrator-state/tasks/runtime-state.yaml",
        "orchestrator-state/tasks/registry.yaml",
        "orchestrator-state/tasks/registry-summary.yaml",
        "orchestrator-state/tasks/task-index.yaml",
        "orchestrator-state/tasks/task-dag.yaml",
        "orchestrator-state/tasks/handoff-index.yaml",
        "orchestrator-state/tasks/lifecycle-events.yaml",
    ]
    for rel in required:
        p = project_root() / rel
        if not p.exists():
            errors.append(f"missing {rel}")
        elif p.suffix == ".md":
            if p.stat().st_size <= 0:
                errors.append(f"empty {rel}")
        elif read_yaml(p, None) in (None, {}):
            errors.append(f"empty_or_invalid {rel}")
    registry = load_registry()
    tasks = [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]
    for task in tasks:
        tid = str(task.get("id") or task.get("task_id") or "unknown")
        y = tasks_dir() / "slices" / f"{tid}.yaml"
        data = read_yaml(y, None)
        if not isinstance(data, dict) or not data:
            errors.append(f"missing_or_invalid slice memory orchestrator-state/tasks/slices/{tid}.yaml")
        else:
            s = data.get("slice") or {}
            for key in ["id", "title", "description", "status", "depends_on", "write_set", "verification_surface", "resolved_specs"]:
                if key not in s:
                    errors.append(f"slice memory {tid} missing {key}")
    agents = _agents()
    for agent in agents:
        # Refresh generated agent memory before validating it. This mirrors the
        # runtime behavior where memory files are regenerated by
        # runtime hooks, while preserving the new YAML contract.
        ensure_agent_memory(agent)
        prompt = project_root() / ".claude" / "agents" / f"{agent}.md"
        if not prompt.exists():
            errors.append(f"missing agent prompt .claude/agents/{agent}.md")
            continue
        text = prompt.read_text(encoding="utf-8", errors="replace")
        if "memory: project" not in text.split("---", 2)[1]:
            errors.append(f"agent {agent} missing frontmatter memory: project")
        for token in ["MEMORY.yaml", "PROGRESS.yaml", "project-context.yaml", "source-manifest.yaml", "project-brief.yaml", "architecture-contract.yaml", "orchestrator-state/tasks", "BLUEPRINT.snapshot.md", "source_sections", "blueprint_lossless_refs", "evidence_matrix", "minimum_runtime_proof"]:
            if token not in text:
                errors.append(f"agent {agent} prompt missing memory token {token}")
        y = agent_memory_path(agent, "yaml")
        m = agent_memory_path(agent, "md")
        data = read_yaml(y, None)
        if not isinstance(data, dict) or not data:
            errors.append(f"missing_or_invalid agent memory {y.relative_to(project_root())}")
            continue
        if data.get("agent") != agent:
            errors.append(f"agent memory mismatch {agent}: {data.get('agent')}")
        if (data.get("claude_code") or {}).get("memory") != "project":
            errors.append(f"agent memory {agent} missing claude_code.memory=project")
        if "trailer_contract" not in data:
            errors.append(f"agent memory missing trailer_contract {agent}")
        if "verify_slice_memory_contract" not in data:
            errors.append(f"agent memory missing verify_slice_memory_contract {agent}")
        contract = data.get("native_runtime_contract") or {}
        if not isinstance(contract, dict) or not contract.get("runtime_role"):
            errors.append(f"agent memory missing native_runtime_contract {agent}")
        if not isinstance(contract.get("runtime_responsibilities"), list):
            errors.append(f"agent memory native_runtime_contract lacks runtime_responsibilities {agent}")
        wc = data.get("write_contract") or {}
        never = wc.get("never_write") or []
        for rel in ["orchestrator-state/tasks/registry.json", "orchestrator-state/memory/PROGRESS.yaml"]:
            if rel not in never:
                errors.append(f"agent memory {agent} write_contract.never_write missing {rel}")
        if not m.exists():
            warnings.append(f"missing markdown memory index for {agent}")
    # Handoff YAML mirrors and index entries must exist whenever handoff Markdown exists.
    handoff_index = read_yaml(tasks_dir() / "handoff-index.yaml", {}) or {}
    indexed = {str(h.get("task_id")) for h in (handoff_index.get("handoffs") or []) if isinstance(h, dict)}
    for md in sorted((tasks_dir() / "handoffs").glob("*.md")):
        yml = md.with_suffix(".yaml")
        if not yml.exists():
            errors.append(f"handoff markdown missing yaml mirror {md.name}")
        if md.stem not in indexed:
            errors.append(f"handoff index missing task {md.stem}")
    lifecycle = read_yaml(tasks_dir() / "lifecycle-events.yaml", {}) or {}
    if not isinstance(lifecycle.get("events", []), list):
        errors.append("lifecycle-events.yaml events must be a list")
    # Case-sensitivity guard for macOS/Linux: canonical names must not have wrong-case siblings.
    # Do not use Path.exists() for the negative probe: on macOS APFS case-insensitive,
    # memory_dir()/"progress.yaml" resolves to PROGRESS.yaml and becomes a false positive.
    # Inspect actual directory entries instead; Linux/CI still catches real wrong-case files.
    try:
        memory_names = {child.name for child in memory_dir().iterdir()}
    except FileNotFoundError:
        memory_names = set()
    for wrong_name in ["progress.yaml", "Project-Context.yaml"]:
        if wrong_name in memory_names:
            errors.append(f"wrong-case memory file orchestrator-state/memory/{wrong_name}")
    return {"ok": not errors, "agents": len(agents), "tasks": len(tasks), "errors": errors, "warnings": warnings}

def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    if argv and argv[0] == "check":
        result = check_memory_yaml()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 2
    write_memory_snapshot()
    result = check_memory_yaml()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
