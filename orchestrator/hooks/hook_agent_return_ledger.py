from __future__ import annotations
import json, sys
from orchestrator.common import append_jsonl, ledger_path, now_iso, dag_worker_task_id, log_hook_error


def _short(value, limit=1200):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text[:limit] + ("..." if len(text) > limit else "")


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return 0
        data = json.loads(raw)
        if str(data.get("tool_name") or "") != "Agent":
            return 0
        ti = data.get("tool_input") or {}
        tr = data.get("tool_response") or {}
        append_jsonl(ledger_path(), {
            "ts": now_iso(),
            "event": "agent_tool_return",
            "task_id": dag_worker_task_id(),
            "description": ti.get("description") or ti.get("agent_type") or ti.get("subagent_type"),
            "response": _short(tr),
        })
    except Exception as exc:
        log_hook_error("hook_agent_return_ledger", exc)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
