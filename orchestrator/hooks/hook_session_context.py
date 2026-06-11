from __future__ import annotations
import json
from orchestrator.common import hook_errors_path, load_registry, load_runtime_state, project_root, progress_yaml_path, memory_dir, read_yaml
from orchestrator.runtime.memory_yaml import write_memory_snapshot


def main():
    try:
        write_memory_snapshot()
    except Exception:
        pass
    reg = load_registry(); rt = load_runtime_state(); errors = ""
    p = hook_errors_path()
    if p.exists():
        errors = "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-10:])
    ready = [t for t in reg.get("tasks", []) if t.get("status") == "ready"]
    active = [t for t in reg.get("tasks", []) if t.get("status") in {"claimed", "in_progress", "validator_tester_pending", "needs_debug", "ready_for_close", "verified_pending_close"}]
    progress = read_yaml(progress_yaml_path(), {}) or {}
    ctx = [
        "## Orchestrator session context",
        f"- Root: `{project_root()}`",
        f"- Active task: `{rt.get('active_task_id') or 'none'}`",
        f"- Ready tasks: {len(ready)}",
        f"- Active lifecycle tasks: {len(active)}",
        "- Input: `inputs/BLUEPRINT.md` → `orchestrator-state/compiled/orchestrator-input.json` → `orchestrator-state/tasks/registry.json`",
        f"- Global progress YAML: `{progress_yaml_path().relative_to(project_root())}`",
        f"- Project context YAML: `{(memory_dir() / 'project-context.yaml').relative_to(project_root())}`",
    ]
    counts = (progress.get("task_counts") or {}).get("by_status") or {}
    if counts:
        ctx.append("- Status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if ready[:5]:
        ctx.append("\n### Ready preview\n" + "\n".join(f"- `{t['id']}` {t.get('title')} — {str(t.get('description') or '')[:180]}" for t in ready[:5]))
    if errors:
        ctx.append("\n### Recent hook errors\n```text\n" + errors + "\n```")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(ctx)}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
