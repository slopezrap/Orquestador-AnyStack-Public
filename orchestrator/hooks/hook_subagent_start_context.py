from __future__ import annotations
import contextlib
import io
import json, sys
from typing import Any

from orchestrator.common import (
    dag_worker_task_id,
    find_task,
    get_spawn_budget,
    get_spawn_count,
    handoff_path,
    evidence_dir,
    reports_dir,
    load_registry,
    log_hook_error,
    project_root,
    read_json,
    read_yaml,
    task_pack_path,
    workspace_relpath,
    agent_memory_path,
    progress_yaml_path,
    memory_dir,
)
from orchestrator.runtime.memory_yaml import record_agent_start, ensure_agent_memory
from orchestrator.runtime.verify_requirements import classify_task_verification


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _init_verify_slice_handoff_if_needed(agent_type: str, task_id: str | None) -> tuple[bool, str]:
    if agent_type != "slice-verifier" or not task_id:
        return False, "not_applicable"
    try:
        from orchestrator.runtime.runtime_ops import init_verify_slice_handoff

        with contextlib.redirect_stdout(io.StringIO()):
            code = init_verify_slice_handoff([task_id])
        if code == 0:
            return True, "initialized"
        return False, f"init_verify_slice_handoff_exit_{code}"
    except Exception as exc:
        log_hook_error("hook_subagent_start_context.init_verify_slice_handoff", exc)
        return False, f"error:{exc}"


def _trailer_template(role: str, role_spec: dict[str, Any], task_id: str | None) -> list[str]:
    required = [str(x) for x in _as_list(role_spec.get("required_keys"))]
    allowed_status = [str(x) for x in _as_list(role_spec.get("next_status_values"))]
    allowed_outcome = [str(x) for x in _as_list(role_spec.get("outcome_values"))]
    tid = task_id or "<TASK_ID>"
    lines = [
        "",
        "### Trailer contract",
        f"- Required keys: {', '.join(required) if required else 'none'}",
        f"- Allowed OUTCOME: {', '.join(allowed_outcome) if allowed_outcome else 'n/a'}",
        f"- Allowed NEXT_STATUS: {', '.join(allowed_status)}" if allowed_status else "- Lifecycle status changes: none (info-only role)",
        "- The final trailer must be the last machine-readable block in the subagent answer.",
        "- AGENT must match the Claude Code `agent_type`; TASK_ID must match the active task.",
        "",
        "Emit at the end:",
        "```text",
        "CLAUDE_TRAILER:",
        f"AGENT: {role or '<agent-name>'}",
        f"TASK_ID: {tid}",
        "OUTCOME: <allowed outcome>",
    ]
    if "NEXT_STATUS" in required or allowed_status:
        lines.append("NEXT_STATUS: <allowed status>")
    if "HANDOFF" in required:
        lines.append(f"HANDOFF: {workspace_relpath(handoff_path(task_id)) if task_id else 'orchestrator-state/tasks/handoffs/<TASK_ID>.md'}")
    if "EVIDENCE" in required:
        lines.append(f"EVIDENCE: {workspace_relpath(evidence_dir(task_id)) if task_id else 'orchestrator-state/tasks/evidence/<TASK_ID>'}")
    if "VERIFY_OUTCOME" in required:
        lines.append("VERIFY_OUTCOME: verified|issues_found|blocked")
    if "REAL_DATA_OR_USER_PROVIDED" in required:
        lines.append("REAL_DATA_OR_USER_PROVIDED: yes|no")
    if "NO_STUB_DATA_USED" in required:
        lines.append("NO_STUB_DATA_USED: yes|no")
    if "RUNTIME_LOGS_CHECKED" in required:
        lines.append("RUNTIME_LOGS_CHECKED: yes|no")
    if "REPORT" in required:
        report = reports_dir() / f"{tid}.md" if task_id else reports_dir() / "<TASK_ID>.md"
        lines.append(f"REPORT: {workspace_relpath(report)}")
    for key in [
        "REPORT_READY",
        "BASELINE_SYNC_READY",
        "GIT_READY",
        "PUSH_READY",
        "GIT_WORKFLOW_READY",
        "RUNTIME_CLEANED",
        "DOCKER_RUNTIME_CLEANED",
        "RANCHER_RUNTIME_CLEANED",
        "DEV_PORTS_RELEASED",
        "WORKTREES_CLEANED",
    ]:
        if key in required:
            lines.append(f"{key}: yes")
    if role == "closer":
        lines.extend([
            "# Under pr-flow, done also requires:",
            "PR_READY: yes",
            "MERGED: yes",
            "CANONICAL_MAIN_SYNCED: yes",
            "DOCKER_RUNTIME_CLEANED: yes|not_applicable:no_compose_file",
            "RANCHER_RUNTIME_CLEANED: yes|not_applicable:no_rancher_cleanup_cmd",
            "DEV_PORTS_RELEASED: yes",
        ])
    if role == "deployer":
        lines.extend([
            "DEPLOY_READY: yes",
            "DEPLOY_URL: <deployment or verification URL>",
        ])
    if "BLOCKER_REASON" in required:
        lines.append("BLOCKER_REASON: <reason when blocked>")
    emitted_keys = {line.split(":", 1)[0] for line in lines if ":" in line and line.split(":", 1)[0].isupper()}
    special_required_values = {
        "CONTEXT_READY": "yes|no",
        "NEEDS_OFFICIAL_DOCS": "yes|no",
    }
    for key in required:
        if key in emitted_keys or key == "CLAUDE_TRAILER":
            continue
        lines.append(f"{key}: {special_required_values.get(key, '<value>')}")
    lines.append("```")
    return lines


def build_context(payload: dict[str, Any]) -> str:
    agent_type = str((payload.get("agent_type") or payload.get("subagent_type") or payload.get("name") or "unknown")).strip()
    tid = dag_worker_task_id() or str((payload.get("task_id") or "")).strip() or None
    reg = load_registry()
    task = find_task(reg, tid) if tid else None
    verify_init_done, verify_init_status = _init_verify_slice_handoff_if_needed(agent_type, tid)
    canonical_root = project_root()
    current_workspace = __import__("orchestrator.common", fromlist=["workspace_root"]).workspace_root()
    linked_worktree = canonical_root.resolve() != current_workspace.resolve()
    contract = read_json(canonical_root / ".claude" / "orchestrator-contract.json", {})
    role_spec = ((contract.get("trailer_schema") or {}).get("roles") or {}).get(agent_type, {})
    lines = [
        "## Subagent runtime context",
        f"- Agent type: `{agent_type}`",
        f"- Active TASK_ID: `{tid or 'not_set'}`",
        f"- Canonical orchestrator root: `{canonical_root}`",
        f"- Current workspace root: `{current_workspace}`",
        f"- Task pack JSON: `{workspace_relpath(task_pack_path(tid, 'json')) if tid else 'not_applicable'}`",
        f"- Task pack Markdown: `{workspace_relpath(task_pack_path(tid, 'md')) if tid else 'not_applicable'}`",
        f"- Handoff: `{workspace_relpath(handoff_path(tid)) if tid else 'not_applicable'}`",
        f"- Evidence dir: `{workspace_relpath(evidence_dir(tid)) if tid else 'not_applicable'}`",
        f"- Spawn count: {get_spawn_count(tid)}/{get_spawn_budget()}",
        "- Human source of truth: `inputs/BLUEPRINT.md` fenced `yaml orchestrator` blocks.",
        "- Machine input: `orchestrator-state/compiled/orchestrator-input.json`.",
        "- Lossless blueprint snapshot: `orchestrator-state/compiled/BLUEPRINT.snapshot.md`.",
        "- Lossless blueprint sections: `orchestrator-state/compiled/blueprint-sections.json` and `orchestrator-state/memory/blueprint-sections.yaml`.",
        "- Runtime task field: `source_sections` gives exact section line ranges for the active slice.",
        "- Runtime task field: `blueprint_lossless_refs` points to the snapshot, manifest, sections index and blocks index.",
        "- Lossless blueprint blocks: `orchestrator-state/compiled/blueprint-blocks.json` and `orchestrator-state/memory/blueprint-blocks.yaml`.",
        "- Runtime state: `orchestrator-state/tasks/registry.json` plus generated task packs.",
        f"- Global memory YAML: `{workspace_relpath(progress_yaml_path())}`",
        f"- Project context YAML: `{workspace_relpath(memory_dir() / 'project-context.yaml')}`",
        f"- Blueprint manifest YAML: `{workspace_relpath(memory_dir() / 'blueprint-manifest.yaml')}`",
        f"- Blueprint sections YAML: `{workspace_relpath(memory_dir() / 'blueprint-sections.yaml')}`",
        f"- Agent memory YAML: `{workspace_relpath(agent_memory_path(agent_type, 'yaml'))}`",
        f"- Task slice YAML: `{workspace_relpath(project_root() / 'orchestrator-state' / 'tasks' / 'slices' / ((tid or '<TASK_ID>') + '.yaml')) if tid else 'not_applicable'}`",
        f"- Handoff YAML: `{workspace_relpath(project_root() / 'orchestrator-state' / 'tasks' / 'handoffs' / ((tid or '<TASK_ID>') + '.yaml')) if tid else 'not_applicable'}`",
        "- Agent memory rule: read MEMORY.yaml at start; append only stable, reusable observations. Per-run facts belong in handoff/evidence/ledger.",
    ]
    if linked_worktree:
        lines.extend([
            "",
            "### Linked worktree state rule",
            "- The scheduler truth is the canonical root above, not the local worktree.",
            "- Write handoff/evidence using the exact paths printed in this context; if they are absolute, keep them absolute.",
            "- Do not create symlinks for registry.json, runtime-state.json, task-dag.json or task-packs.",
            "- A local `orchestrator-state/` that contains only tracked compatibility blueprint memory JSON mirrors is harmless (`local_commit_artifacts_only`); if it contains scheduler state, handoffs/evidence, task-packs, compiled output or other generated runtime files, stop and run `scripts/repair-worktree-state.sh --apply <WORKTREE>` from the canonical root.",
        ])
    if agent_type == "slice-verifier":
        lines += [
            "",
            "### verify-slice bootstrap",
            f"- Init handoff skeleton before verifier start: `{'yes' if verify_init_done else 'no'}`",
            f"- Init status: `{verify_init_status}`",
            f"- Expected section: `## verify-slice` in `{workspace_relpath(handoff_path(tid)) if tid else 'not_applicable'}`",
            "- Do not emit `verified_pending_close` unless the filled `## verify-slice` section and durable evidence JSON both satisfy the acceptance contract.",
        ]
    try:
        mem = record_agent_start(agent_type, tid)
        recent = mem.get("recent_events") or []
        stable = mem.get("stable_lessons") or []
        contract = mem.get("native_runtime_contract") or {}
        write_contract = mem.get("write_contract") or {}
        lines += [
            "",
            "### Durable agent memory YAML",
            f"- Path: `{workspace_relpath(agent_memory_path(agent_type, 'yaml'))}`",
            f"- Recent event count: {len(recent)}",
            f"- Stable lessons count: {len(stable)}",
            f"- Runtime role: {contract.get('runtime_role') or 'not_declared'}",
            f"- Canonical memory write target: `{write_contract.get('canonical_memory_file') or workspace_relpath(agent_memory_path(agent_type, 'yaml'))}`",
            "- Agents may update only their own MEMORY.yaml with stable cross-slice lessons; task facts go to handoff/evidence/report, and shared progress/task YAML is updated by hooks/bootstrap.",
        ]
        for item in (contract.get("runtime_responsibilities") or [])[:6]:
            lines.append(f"- responsibility: {item}")
        for item in (contract.get("writes") or [])[:6]:
            lines.append(f"- allowed write surface: {item}")
        for item in stable[:8]:
            if isinstance(item, dict):
                lines.append(f"- lesson: {item.get('text') or item.get('lesson') or item}")
            else:
                lines.append(f"- lesson: {item}")
        wc = mem.get("write_contract") or {}
        lines += ["", "### Runtime YAML memory write contract", f"- Canonical agent memory: `{wc.get('canonical_memory_file')}`", f"- Markdown index: `{wc.get('markdown_index')}`"]
        for dest in (wc.get("runtime_writes_go_to") or [])[:12]:
            lines.append(f"- Runtime write destination: `{dest}`")
        for never in (wc.get("never_write") or [])[:8]:
            lines.append(f"- Never write directly: `{never}`")
    except Exception as exc:
        log_hook_error("hook_subagent_start_context.memory_yaml", exc)
    try:
        progress = read_yaml(progress_yaml_path(), {})
        if isinstance(progress, dict) and progress:
            counts = ((progress.get("task_counts") or {}).get("by_status") or {})
            lines += ["", "### Project memory snapshot", f"- PROGRESS.yaml updated_at: `{progress.get('updated_at')}`", f"- Active task in progress memory: `{progress.get('active_task_id') or 'none'}`", f"- Task counts by status: `{counts}`"]
            for event in (progress.get("recent_events") or [])[-5:]:
                lines.append(f"- recent: `{event.get('at')}` {event.get('kind') or event.get('event')} task=`{event.get('task_id')}` agent=`{event.get('agent')}` outcome=`{event.get('outcome')}`")
    except Exception as exc:
        log_hook_error("hook_subagent_start_context.progress_yaml", exc)

    if role_spec:
        lines.extend(_trailer_template(agent_type, role_spec, tid))

    if task:
        lines += [
            "",
            "### Active slice",
            f"- Title: {task.get('title')}",
            f"- Description: {task.get('description')}",
            f"- Dependency rationale: {task.get('dependency_rationale')}",
            f"- Status: `{task.get('status')}`",
            f"- Depends on: {', '.join(task.get('depends_on') or []) or 'none'}",
            f"- Implements: {', '.join(task.get('implements') or []) or 'none'}",
            f"- Builds: {', '.join(task.get('builds') or []) or 'none'}",
            f"- Arc42 refs: {', '.join(task.get('arc42_refs') or []) or 'none'}",
            f"- Write set: {', '.join(task.get('write_set') or []) or 'not_derived'}",
            f"- Conflict groups: {', '.join(task.get('conflict_groups') or task.get('conflict_group') or []) or 'not_derived'}",
            f"- Parallel group: {(task.get('parallel') or {}).get('safe_group') or 'not_derived'}",
            f"- Lock files: {', '.join((task.get('locks') or {}).get('lock_files') or []) or 'not_derived'}",
            f"- Verification refs: {', '.join(task.get('verification_refs') or []) or 'missing'}",
            f"- Verification surface: `{(task.get('verification_surface') or {}).get('kind', 'not_derived')}` / method=`{(task.get('verification_surface') or {}).get('method', 'not_derived')}`",
            f"- Visual MCP required: `{(task.get('verification_surface') or {}).get('requires_visual_mcp', False)}`; screen reviewer required: `{(task.get('verification_surface') or {}).get('requires_screen_journey_reviewer', False)}`",
            f"- Verification surface rationale: {(task.get('verification_surface') or {}).get('rationale', '')}",
            f"- Blueprint lossless refs: `{json.dumps(task.get('blueprint_lossless_refs') or {}, ensure_ascii=False)[:900]}`",
        ]
        try:
            routing = classify_task_verification(task)
            lines += ["", "### Verify routing ", f"- Evidence route: `{routing.get('evidence_route')}`", f"- Visual required: `{routing.get('visual_required')}`", f"- Visual mode: `{routing.get('visual_mode')}`", f"- Screen/journey reviewer required: `{routing.get('screen_journey_reviewer_required')}`", f"- Journey participation only: `{routing.get('journey_participation_only')}`", f"- Explanation: {routing.get('explanation')}"]
        except Exception as exc:
            log_hook_error("hook_subagent_start_context.verify_routing", exc)
        if task.get("source_sections"):
            lines += ["", "### Blueprint source sections"]
            for sec in (task.get("source_sections") or [])[:24]:
                lines.append(f"- `{sec.get('section_id')}` lines `{sec.get('line_start')}-{sec.get('line_end')}` — {sec.get('title')} via `{sec.get('id')}`")
        if task.get("dependency_edges"):
            lines += ["", "### Dependency edges"]
            for edge in task.get("dependency_edges") or []:
                lines.append(f"- `{edge.get('from')}` -> `{edge.get('to')}`: {edge.get('reason')}")
        if task.get("resolved_dependencies"):
            lines += ["", "### Resolved dependency tasks"]
            for dep in (task.get("resolved_dependencies") or [])[:8]:
                lines.append(f"- {dep.get('id')}: {dep.get('title')} — {dep.get('description')}")
        specs = task.get("resolved_specs") or []
        if specs:
            lines += ["", "### Resolved blueprint specs"]
            for spec in specs[:18]:
                sec_hint = ""
                if spec.get("source_sections"):
                    first = (spec.get("source_sections") or [{}])[0]
                    sec_hint = f" [source `{first.get('section_id')}` lines `{first.get('line_start')}-{first.get('line_end')}`]"
                lines.append(f"- {spec.get('id')} ({spec.get('kind')}): {spec.get('name')} — {spec.get('description')}{sec_hint}")
    return "\n".join(lines)[:12000]


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": build_context(payload)}}, ensure_ascii=False))
    except Exception as exc:
        log_hook_error("hook_subagent_start_context", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
