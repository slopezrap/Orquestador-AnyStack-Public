from __future__ import annotations
import json, sys
from orchestrator.common import dag_worker_task_id, get_spawn_budget, get_spawn_count, log_hook_error


def _agent_name(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return "unknown"
    for key in ("subagent_type", "agent_type", "name", "teammate_name"):
        val = tool_input.get(key)
        if val:
            return str(val)
    return "unknown"


def deny(reason: str):
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":reason}}, ensure_ascii=False))


def main():
    try:
        raw=sys.stdin.read().strip()
        if not raw: return 0
        payload=json.loads(raw)
        if str(payload.get("tool_name") or "") != "Agent": return 0
        tid=dag_worker_task_id()
        if not tid: return 0
        count=get_spawn_count(tid); budget=get_spawn_budget()
        if count >= budget:
            agent = _agent_name(payload)
            deny(
                f"Spawn budget reached for slice {tid}: {count}/{budget}. "
                f"Do not spawn agent '{agent}'. Finish the current lifecycle, run /clear and inspect runtime-state, or split/waive the slice explicitly."
            )
    except Exception as exc:
        log_hook_error("hook_spawn_budget", exc)
    return 0
if __name__ == "__main__": raise SystemExit(main())
