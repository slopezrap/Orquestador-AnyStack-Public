from __future__ import annotations
import argparse, json
from orchestrator.common import file_lock, find_task, load_registry, now_iso, registry_path, save_registry
from orchestrator.runtime.state_machine import allowed_transition, explain_transition
from orchestrator.runtime.memory_yaml import record_task_transition, write_memory_snapshot


def main(argv=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("task_id")
    p.add_argument("to_status")
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", default="manual transition")
    args=p.parse_args(argv)
    with file_lock(registry_path()):
        reg=load_registry()
        task=find_task(reg, args.task_id)
        if not task:
            print(json.dumps({"ok": False, "error": "task not found"}, ensure_ascii=False))
            return 2
        current=str(task.get("status"))
        target=str(args.to_status)
        if not allowed_transition(args.actor, current, target):
            print(json.dumps({"ok": False, "error": explain_transition(args.actor, current, target)}, ensure_ascii=False))
            return 3
        task["status"]=target
        task["last_updated_by"]=args.actor
        task["last_transition_reason"]=args.reason
        task["last_transition_at"]=now_iso()
        save_registry(reg)
    try:
        record_task_transition(args.task_id, args.actor, current, target, args.reason)
        write_memory_snapshot()
    except Exception:
        pass
    print(json.dumps({"ok": True, "task_id": args.task_id, "from": current, "to": target}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
