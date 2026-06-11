from __future__ import annotations
import json, sys
from orchestrator.common import append_jsonl, bash_ledger_path, dag_worker_task_id, ledger_path, log_hook_error, now_iso
from orchestrator.runtime.memory_yaml import append_progress_event

def main():
    try:
        raw=sys.stdin.read().strip()
        if not raw: return 0
        data=json.loads(raw)
        tool=str(data.get("tool_name") or "")
        inp=data.get("tool_input") or {}
        path=bash_ledger_path() if tool == "Bash" else ledger_path()
        rec={"ts":now_iso(),"event":str(data.get("hook_event_name") or "PostToolUse"),"tool_name":tool,"task_id":dag_worker_task_id()}
        if data.get("hook_event_name") == "ConfigChange":
            rec["source"] = data.get("source"); rec["file_path"] = data.get("file_path")
        elif tool in {"Write","Edit","MultiEdit","NotebookEdit"}:
            rec["file_path"] = inp.get("file_path") or inp.get("notebook_path")
        elif tool == "Bash":
            rec["command"] = str(inp.get("command") or "")[:500]
            rec["runtime_only"] = True
        append_jsonl(path, rec)
        try:
            if tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"} or data.get("hook_event_name") == "ConfigChange":
                append_progress_event({"kind": "tool_event", **rec})
        except Exception:
            pass
    except Exception as exc:
        log_hook_error("hook_update_ledger", exc)
    return 0
if __name__ == "__main__": raise SystemExit(main())
