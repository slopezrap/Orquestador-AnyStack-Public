from __future__ import annotations
import json, os, sys
from pathlib import Path
from orchestrator.common import dag_worker_task_id, project_root, workspace_root, load_registry, find_task, task_write_set, write_patterns_conflict, append_jsonl, ledger_path, now_iso, log_hook_error

WRITE_TOOLS={"Write","Edit","MultiEdit","NotebookEdit"}
CORE_STATE={"orchestrator-state/tasks/registry.json","orchestrator-state/tasks/runtime-state.json","orchestrator-state/tasks/ledger.jsonl","orchestrator-state/tasks/task-dag.json","orchestrator-state/compiled/orchestrator-input.json","orchestrator-state/compiled/orchestrator-input.lock.json"}

def deny(reason):
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":reason}}, ensure_ascii=False))

def target_path(data):
    inp=data.get("tool_input") or {}
    return str(inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or "")

def resolved_target(text):
    if not text: return None
    raw=Path(text).expanduser()
    base=workspace_root()
    if not raw.is_absolute(): raw=base/raw
    return raw.resolve()

def relpath(text):
    resolved=resolved_target(text)
    if resolved is None: return ""
    # Prefer the canonical scheduler root for generated runtime state.  A linked
    # worktree may not carry its own orchestrator-state during an active slice.
    pr=project_root().resolve()
    wr=workspace_root().resolve()
    for root in [pr, wr]:
        try: return resolved.relative_to(root).as_posix()
        except Exception: pass
    s=text.replace('\\','/')
    return s[2:] if s.startswith('./') else s

def is_local_worktree_state_write(text):
    resolved=resolved_target(text)
    if resolved is None: return False
    pr=project_root().resolve()
    wr=workspace_root().resolve()
    if pr == wr: return False
    try:
        resolved.relative_to(wr / "orchestrator-state")
    except Exception:
        return False
    try:
        resolved.relative_to(pr / "orchestrator-state")
        return False
    except Exception:
        return True

def main():
    try:
        raw=sys.stdin.read().strip()
        if not raw: return 0
        data=json.loads(raw)
        if str(data.get("tool_name") or "") not in WRITE_TOOLS: return 0
        target=target_path(data)
        rel=relpath(target)
        if not rel: return 0
        tid=dag_worker_task_id()
        if is_local_worktree_state_write(target) and os.environ.get("CLAUDE_ALLOW_WORKTREE_LOCAL_STATE_WRITES") != "1":
            deny(f"Blocked write to local worktree orchestrator-state: {rel}. The scheduler truth lives at {project_root()}/orchestrator-state; use the canonical absolute handoff/evidence path or run scripts/repair-worktree-state.sh before resuming."); return 0
        if rel.startswith(".claude/") and os.environ.get("CLAUDE_ALLOW_STATIC_CONFIG_WRITES") != "1":
            deny(f"Blocked write to static Claude adapter config during app execution: {rel}"); return 0
        if tid and rel in {"BLUEPRINT.md", "inputs/BLUEPRINT.md"} and os.environ.get("CLAUDE_ALLOW_BLUEPRINT_WRITES") != "1":
            deny(f"Blocked blueprint edit ({rel}) while TASK_ID {tid} is active. Compile/bootstrap after changing the blueprint, not mid-slice."); return 0
        if rel in CORE_STATE and os.environ.get("CLAUDE_ALLOW_CORE_STATE_WRITES") != "1":
            deny(f"Blocked direct edit to generated orchestrator state: {rel}. Use compiler/bootstrap/runtime scripts."); return 0
        if tid:
            task=find_task(load_registry(), tid)
            if task and not rel.startswith("orchestrator-state/") and not rel.startswith("docs/") and not rel.startswith(".claude/"):
                ws=task_write_set(task)
                if ws and not any(write_patterns_conflict(rel, pat) for pat in ws):
                    append_jsonl(ledger_path(), {"ts":now_iso(),"event":"write_set_warning","task_id":tid,"file_path":rel,"write_set":ws})
    except Exception as exc:
        log_hook_error("hook_write_scope_guard", exc)
    return 0
if __name__ == "__main__": raise SystemExit(main())
