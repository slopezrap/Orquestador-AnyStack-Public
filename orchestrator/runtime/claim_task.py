from __future__ import annotations
import argparse, json
from orchestrator.common import load_registry, save_registry, find_task, file_lock, registry_path, runtime_state_path, load_runtime_state, save_runtime_state, now_iso, task_pack_path, promote_ready_tasks, task_is_ready, active_conflict_blockers
from orchestrator.runtime.handoff import init_handoff_for_task
from orchestrator.runtime.state_machine import allowed_transition
from orchestrator.runtime.memory_yaml import record_task_transition, write_memory_snapshot
from orchestrator.runtime.next_wave import _blocking_followups


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("task_id"); p.add_argument("--in-progress", action="store_true"); args=p.parse_args(argv)
    with file_lock(registry_path()):
        reg=promote_ready_tasks(load_registry())
        task=find_task(reg, args.task_id)
        if not task:
            print(json.dumps({"ok":False,"error":"task not found"}, ensure_ascii=False)); return 2
        current=str(task.get("status"))
        if current == "ready" and not task_is_ready(reg, task):
            print(json.dumps({"ok":False,"error":f"cannot claim {args.task_id}: dependencies are not done"}, ensure_ascii=False)); return 4
        blocking_followups = _blocking_followups()
        if blocking_followups:
            print(json.dumps({"ok":False,"error":f"cannot claim {args.task_id}: blocking proposed follow-ups require /promote-followup or waiver", "blocking_followups": blocking_followups}, ensure_ascii=False)); return 6
        blockers = active_conflict_blockers(reg, task)
        if blockers:
            print(json.dumps({"ok":False,"error":f"cannot claim {args.task_id}: active conflict blockers", "blockers": blockers}, ensure_ascii=False)); return 5
        target="in_progress" if args.in_progress else "claimed"
        actor="claim_task"
        if current == target:
            # Re-entrant /next-slice is useful after terminal refresh, /clear, or
            # a repeated command. It must not mutate lifecycle, but it should
            # refresh runtime active_task_id and handoff context for the same slice.
            previous = current
            task.setdefault("claimed_at", now_iso())
            task["last_updated_by"] = "claim_task_resume"
            save_registry(reg)
            resumed = True
        else:
            resumed = False
            if current == "ready" and target == "in_progress":
                # two-step virtual claim is fine for CLI ergonomics.
                task["status"]="claimed"; current="claimed"
            if not allowed_transition(actor, current, target):
                print(json.dumps({"ok":False,"error":f"cannot claim {args.task_id}: {current}->{target}"}, ensure_ascii=False)); return 3
            previous = current
            task["status"]=target; task["claimed_at"]=now_iso(); task["last_updated_by"]="claim_task"
            save_registry(reg)
    with file_lock(runtime_state_path()):
        rt=load_runtime_state(); rt["active_task_id"]=args.task_id; rt["last_claim_at"]=now_iso(); save_runtime_state(rt)
    try:
        if not resumed:
            record_task_transition(args.task_id, "claim_task", previous, target, "claim task for slice execution")
        write_memory_snapshot()
    except Exception:
        pass
    handoff = init_handoff_for_task(args.task_id)
    print(json.dumps({"ok":True,"task_id":args.task_id,"status":target,"resumed": bool(resumed),"task_pack":str(task_pack_path(args.task_id)),"handoff":str(handoff)}, ensure_ascii=False))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
