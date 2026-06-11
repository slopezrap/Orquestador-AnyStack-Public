from __future__ import annotations

import argparse
import copy
import json
from typing import Any

from orchestrator.common import (
    active_conflict_blockers,
    load_registry,
    load_runtime_state,
    promote_ready_tasks,
    read_yaml,
    save_registry,
    task_conflict_reasons,
    tasks_dir,
    task_is_ready,
)
from orchestrator.runtime.check_task_dag import check_registry


ACTIVE_FALLBACK = {"claimed", "in_progress", "validator_tester_pending", "needs_debug", "ready_for_close", "verified_pending_close"}




def _blocking_followups() -> list[dict[str, Any]]:
    directory = tasks_dir() / "follow-ups"
    if not directory.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = read_yaml(path, {}) or {}
        except Exception as exc:
            out.append({"id": path.stem, "file": str(path), "severity": "unknown", "status": "unreadable", "reason": str(exc)})
            continue
        if not isinstance(data, dict):
            continue
        status = str(data.get("status") or "").strip()
        severity = str(data.get("severity") or "").strip().lower()
        if status == "proposed" and severity in {"blocker", "critical", "high"}:
            out.append({
                "id": data.get("id") or path.stem,
                "file": str(path),
                "origin_task_id": data.get("origin_task_id"),
                "severity": severity,
                "title": data.get("title"),
                "scope_classification": data.get("scope_classification"),
                "reason": "blocking proposed follow-up requires /promote-followup or waive before opening new waves",
            })
    return out

def _phase_order(registry: dict[str, Any]) -> list[str]:
    explicit = registry.get("phase_order")
    if isinstance(explicit, list) and explicit:
        return [str(x) for x in explicit]
    phases = registry.get("phases") or []
    order: list[str] = []
    for phase in phases:
        if isinstance(phase, dict) and phase.get("id"):
            order.append(str(phase.get("id")))
        elif phase:
            order.append(str(phase))
    if order:
        return order
    seen: list[str] = []
    for task in registry.get("tasks", []) or []:
        pid = str(task.get("phase_id") or "")
        if pid and pid not in seen:
            seen.append(pid)
    return seen


def _phase_tasks(registry: dict[str, Any], phase_id: str | None) -> list[dict[str, Any]]:
    tasks = [t for t in registry.get("tasks", []) or [] if isinstance(t, dict)]
    if not phase_id:
        return tasks
    return [t for t in tasks if str(t.get("phase_id")) == str(phase_id)]


def _earliest_incomplete_phase(registry: dict[str, Any]) -> str | None:
    for phase_id in _phase_order(registry):
        tasks = _phase_tasks(registry, phase_id)
        if tasks and not all(str(t.get("status")) == "done" for t in tasks):
            return phase_id
    return None


def _max_parallel(registry: dict[str, Any], limit: int | None) -> int:
    dag = registry.get("task_dag") or {}
    parallelism = dag.get("parallelism") or {}
    configured_raw = parallelism.get("max_parallel_slices")
    try:
        configured = int(configured_raw or 1)
    except Exception:
        configured = 1
    try:
        requested = int(limit) if limit is not None else configured
    except Exception:
        requested = configured
    return max(1, min(max(1, requested), max(1, configured)))


def _selected_conflict_reasons(task: dict[str, Any], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for other in selected:
        reasons = task_conflict_reasons(task, other)
        if reasons:
            out.append({"task_id": other.get("id"), "reasons": reasons})
    return out


def _safe_sort(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(task: dict[str, Any]) -> tuple[str, int, str]:
        try:
            order = int(task.get("order") or 0)
        except Exception:
            order = 0
        return (str(task.get("phase_id") or ""), order, str(task.get("id") or task.get("task_id") or ""))
    return sorted(tasks, key=key)


def _json_ready(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "task_id": task.get("task_id") or task.get("id"),
        "title": task.get("title"),
        "description": task.get("description"),
        "dependency_rationale": task.get("dependency_rationale"),
        "depends_on_rationale": task.get("depends_on_rationale"),
        "phase_id": task.get("phase_id"),
        "risk": task.get("risk"),
        "verify_mode": task.get("verify_mode"),
        "command": f"/next-slice {task.get('id')}",
        "depends_on": task.get("depends_on") or [],
        "write_set": task.get("write_set") or [],
        "conflict_groups": task.get("conflict_groups") or task.get("conflict_group") or [],
        "locks": task.get("locks") or {},
        "parallel": task.get("parallel") or {},
    }


def compute_wave(registry: dict[str, Any], *, phase_id: str | None = None, limit: int | None = None, mutate_ready: bool = True) -> dict[str, Any]:
    working = promote_ready_tasks(registry if mutate_ready else copy.deepcopy(registry))
    if mutate_ready:
        save_registry(working)

    dag = working.get("task_dag") or {}
    errors: list[str] = []
    warnings: list[str] = []
    blocking_followups = _blocking_followups()
    if blocking_followups:
        errors.append("blocking proposed follow-ups require /promote-followup or waiver before next-wave")
    try:
        dag_result = check_registry(working)
        errors.extend(str(e) for e in (dag_result.get("errors") or []))
        warnings.extend(str(w) for w in (dag_result.get("warnings") or []))
    except Exception as exc:
        warnings.append(f"DAG validation warning: {exc}")
    if dag.get("mode") != "explicit_dag":
        errors.append("task_dag.mode must be explicit_dag")

    selected_phase = phase_id or _earliest_incomplete_phase(working)
    max_parallel = _max_parallel(working, limit)
    ready_total = 0
    selected: list[dict[str, Any]] = []
    deferred_conflicts: list[dict[str, Any]] = []
    deferred_journey_gate: list[dict[str, Any]] = []
    deferred_limit: list[dict[str, Any]] = []

    runtime = load_runtime_state()
    pending_journeys = [str(x).strip() for x in (runtime.get("pending_journey_verifications") or []) if str(x).strip()]

    if selected_phase and not errors:
        for task in _safe_sort(_phase_tasks(working, selected_phase)):
            if str(task.get("status")) != "ready":
                continue
            if not task_is_ready(working, task):
                continue
            ready_total += 1
            task_journeys = {str(x) for x in (task.get("journey_refs") or task.get("closes_journeys") or [])}
            blockers = sorted(task_journeys.intersection(pending_journeys))
            if blockers:
                item = _json_ready(task)
                item["journey_gate_reason"] = "pending journeys: " + ", ".join(blockers)
                item["journey_gate_blockers"] = blockers
                deferred_journey_gate.append(item)
                continue
            active_blockers = active_conflict_blockers(working, task)
            if active_blockers:
                item = _json_ready(task)
                item["conflict_risk"] = "alto"
                item["conflict_reason"] = "; ".join(f"active {b.get('task_id')}: {', '.join(b.get('reasons') or [])}" for b in active_blockers)
                item["blockers"] = active_blockers
                deferred_conflicts.append(item)
                continue
            selected_blockers = _selected_conflict_reasons(task, selected)
            if selected_blockers:
                item = _json_ready(task)
                item["conflict_risk"] = "alto"
                item["conflict_reason"] = "; ".join(f"selected {b.get('task_id')}: {', '.join(b.get('reasons') or [])}" for b in selected_blockers)
                item["blockers"] = selected_blockers
                deferred_conflicts.append(item)
                continue
            if len(selected) >= max_parallel:
                item = _json_ready(task)
                item["reason"] = "max_parallel_slices"
                deferred_limit.append(item)
                continue
            selected.append(task)

    return {
        "ok": not errors,
        "dag_mode": dag.get("mode"),
        "phase": selected_phase,
        "ready_total": ready_total,
        "ready_count": len(selected),
        "recommended_parallel_terminals": len(selected),
        "parallelism": dag.get("parallelism") or {},
        "ready": [_json_ready(t) for t in selected],
        "deferred_due_conflicts": deferred_conflicts,
        "deferred_due_journey_gate": deferred_journey_gate,
        "deferred_due_limit": deferred_limit,
        "warnings": warnings,
        "errors": errors,
        "pending_journey_verifications": pending_journeys,
        "blocking_followups": blocking_followups,
    }


UNIX_PATH_PREFIX = 'export PATH="$HOME/.rd/bin:/opt/homebrew/bin:/usr/local/bin:$PATH" && export CLAUDE_SPAWN_BUDGET="${CLAUDE_SPAWN_BUDGET:-70}" && '

def _terminal_command(task_id: str) -> str:
    pack = f"orchestrator-state/tasks/task-packs/{task_id}.md"
    claude_cmd = f'claude --agent main-orchestrator --permission-mode bypassPermissions "/next-slice {task_id}"'
    return (
        UNIX_PATH_PREFIX + 'unset CLAUDE_ACTIVE_TASK_ID CLAUDE_TASK_PACK CLAUDE_WORKTREE_ROOT CLAUDE_WORKSPACE_ROOT CLAUDE_ORCHESTRATOR_ROOT COMPOSE_PROJECT_NAME CLAUDE_COMPOSE_PROJECT_NAME && '
        'BOOTSTRAP_ROOT="${CLAUDE_ORCHESTRATOR_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}" && '
        'ROOT="$(bash "$BOOTSTRAP_ROOT/scripts/ensure-task-worktree.sh" --print-root)" && '
        f'WT="$(bash "$ROOT/scripts/ensure-task-worktree.sh" {task_id})" && '
        'cd "$WT" && '
        f'PACK="$WT/{pack}" && '
        f'if [ ! -f "$PACK" ]; then PACK="$ROOT/{pack}"; fi && '
        f'eval "$(python3 -B -S "$ROOT/.claude/bin/runtime_context.py" --root "$ROOT" --workspace-root "$WT" --task {task_id} --print-env)" && '
        f'export CLAUDE_ORCHESTRATOR_ROOT="$ROOT" CLAUDE_WORKTREE_ROOT="$WT" CLAUDE_WORKSPACE_ROOT="$WT" CLAUDE_ACTIVE_TASK_ID={task_id} CLAUDE_TASK_PACK="$PACK" CLAUDE_COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME" && '
        'PORT_ENV="$ROOT/orchestrator-state/dev-ports/$COMPOSE_PROJECT_NAME.env" && '
        f'python3 -B -S "$ROOT/.claude/bin/allocate_slice_ports.py" --root "$ROOT" --task {task_id} --env-file "$PORT_ENV" >/dev/null && '
        '. "$PORT_ENV" && '
        'echo "Puertos slice: $CLAUDE_PORT_ENV_FILE frontend=${CLAUDE_FRONTEND_PORT:-n/a} backend=${CLAUDE_BACKEND_PORT:-n/a} db=${CLAUDE_DB_PORT:-n/a}" && '
        f"echo 'Ahora ejecuta en Claude Code: {claude_cmd}'"
    )


def _md_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("\n", "<br>").replace("|", "\\|")


def _join(values: object) -> str:
    if isinstance(values, list):
        return ", ".join(str(v) for v in values if str(v).strip()) or "—"
    text = str(values or "").strip()
    return text or "—"


def print_markdown(result: dict[str, Any]) -> None:
    print("# DAG wave propuesta")
    print()
    print("> **Antes de reclamar una task en este terminal**, limpia las 6")
    print("> variables de scope para no mezclar contextos entre slices ni")
    print("> arrancar un docker-stack paralelo:")
    print(">")
    print("> ```bash")
    print("> unset CLAUDE_ACTIVE_TASK_ID")
    print("> unset CLAUDE_TASK_PACK")
    print("> unset CLAUDE_WORKTREE_ROOT")
    print("> unset CLAUDE_WORKSPACE_ROOT")
    print("> unset CLAUDE_ORCHESTRATOR_ROOT")
    print("> unset COMPOSE_PROJECT_NAME  # se re-deriva del TASK_ID de la slice")
    print("> unset CLAUDE_COMPOSE_PROJECT_NAME")
    print("> ```")
    print()
    print(f"- DAG mode: `{result.get('dag_mode')}`")
    print(f"- Phase: `{result.get('phase') or '—'}`")
    print(f"- Ready nodes total: {result.get('ready_total', result.get('ready_count'))}")
    print(f"- Ready nodes seguros: {result.get('ready_count')}")
    print(f"- Recomendación de paralelo: {result.get('recommended_parallel_terminals')} terminales")
    pending = result.get("pending_journey_verifications") or []
    if pending:
        print()
        print("## Journeys pendientes")
        print("- DAG-only: solo se difieren las tasks que referencian esos journeys; las ramas independientes pueden continuar.")
        for jid in pending:
            print(f"- `{jid}` pendiente: `/verify-journey {jid}`")
    blocking_followups = result.get("blocking_followups") or []
    if blocking_followups:
        print()
        print("## Follow-ups bloqueantes propuestos")
        print("- Promociona o waiver estos follow-ups antes de abrir nuevas waves dependientes del mismo riesgo.")
        for fu in blocking_followups:
            print(f"- `{fu.get('id')}` severity={fu.get('severity')} origin={fu.get('origin_task_id')}: {fu.get('title')}")
    if result.get("warnings"):
        print()
        print("## Warnings")
        for warning in result["warnings"]:
            print(f"- {warning}")
    if result.get("errors"):
        print()
        print("## Errors")
        for error in result["errors"]:
            print(f"- {error}")
    ready = result.get("ready") or []
    if not ready:
        print()
        print("No hay nodos ready ejecutables en esta phase.")
    else:
        print()
        print("| TASK_ID | Título | Depends on | Conflict groups | Write set | Comando terminal |")
        print("|---|---|---|---|---|---|")
        for task in ready:
            tid = str(task.get("id") or task.get("task_id"))
            title = _md_cell(task.get("title") or "")
            deps = _md_cell(_join(task.get("depends_on") or []))
            groups = _md_cell(_join(task.get("conflict_groups") or []))
            writes = _md_cell(_join(task.get("write_set") or []))
            cmd = _md_cell(_terminal_command(tid))
            print(f"| `{tid}` | {title} | {deps} | {groups} | {writes} | `{cmd}` |")
        print()
        print("## Copia y pega por terminal")
        for idx, task in enumerate(ready, start=1):
            tid = str(task.get("id") or task.get("task_id"))
            print()
            print(f"### Terminal {idx} — {tid}")
            print("```bash")
            print(_terminal_command(tid))
            print("```")
            print(f"Después, en ese terminal worker: `claude --agent main-orchestrator --permission-mode bypassPermissions \"/next-slice {tid}\"`")
    deferred_journey = result.get("deferred_due_journey_gate") or []
    if deferred_journey:
        print()
        print("## Diferidos por journey gate")
        print()
        print("| TASK_ID | Título | Journey pendiente |")
        print("|---|---|---|")
        for task in deferred_journey:
            print(f"| `{task.get('id')}` | {_md_cell(task.get('title') or '')} | {_md_cell(task.get('journey_gate_reason') or '')} |")
    deferred = (result.get("deferred_due_conflicts") or []) + (result.get("deferred_due_limit") or [])
    if deferred:
        print()
        print("## Serializados por conflicto o límite paralelo")
        print()
        print("Estos nodos están ready por dependencias, pero no se proponen en la misma wave para evitar corrupción de ficheros/estado:")
        print()
        print("| TASK_ID | Título | Motivo |")
        print("|---|---|---|")
        for task in deferred:
            reason = task.get("conflict_reason") or task.get("reason") or "—"
            print(f"| `{task.get('id')}` | {_md_cell(task.get('title') or '')} | {_md_cell(reason)} |")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List current explicit-DAG wave with copy/paste worker commands.")
    parser.add_argument("--phase", help="Phase ID to inspect. Defaults to earliest incomplete phase.")
    parser.add_argument("--limit", type=int, help="Max safe ready tasks to print.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-promote", action="store_true", help="Do not persist todo->ready promotions while computing the wave.")
    args = parser.parse_args(argv)
    result = compute_wave(load_registry(), phase_id=args.phase, limit=args.limit, mutate_ready=not args.no_promote)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_markdown(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
