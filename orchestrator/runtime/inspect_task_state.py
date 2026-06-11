from __future__ import annotations
import argparse, json
from orchestrator.common import load_registry, find_task

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("task_id", nargs="?"); args=p.parse_args(argv)
    reg=load_registry()
    if args.task_id:
        print(json.dumps(find_task(reg,args.task_id) or {}, ensure_ascii=False, indent=2)); return 0
    print(json.dumps({"tasks":[{"id":t.get("id"),"title":t.get("title"),"description":t.get("description"),"status":t.get("status"),"phase_id":t.get("phase_id")} for t in reg.get("tasks",[])]}, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
