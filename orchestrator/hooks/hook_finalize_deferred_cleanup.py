from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
from orchestrator.common import append_jsonl, ledger_path, now_iso, log_hook_error, project_root


def _compact_on_stop() -> dict:
    if os.environ.get("CLAUDE_AUTO_COMPACT_AGENT_MEMORY_ON_STOP", "1") == "0":
        return {"enabled": False}
    threshold = os.environ.get("CLAUDE_AGENT_MEMORY_COMPACT_THRESHOLD", "250")
    script = project_root() / "scripts" / "compact-agent-memory.py"
    if not script.exists():
        return {"enabled": True, "skipped": "missing_script"}
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--all", "--apply", "--threshold-lines", threshold, "--quiet"],
            cwd=str(project_root()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        return {"enabled": True, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"enabled": True, "timeout": True}
    except Exception as exc:
        log_hook_error("hook_finalize_deferred_cleanup.compact", exc)
        return {"enabled": True, "error": str(exc)}


def _schedule_deferred_worktree_cleanup() -> dict:
    script = project_root() / "scripts" / "cleanup-deferred-worktrees-loop.sh"
    req_dir = project_root() / "orchestrator-state" / "tasks" / "cleanup-requests"
    if not script.exists() or not req_dir.exists() or not any(req_dir.glob("*.json")):
        return {"scheduled": False, "reason": "no_requests"}
    log = project_root() / "orchestrator-state" / "tasks" / "cleanup-deferred-hook.log"
    try:
        proc = subprocess.Popen(
            ["bash", str(script), "--initial-delay", os.environ.get("CLAUDE_WORKTREE_CLEANUP_STOP_DELAY_SECONDS", "10"), "--quiet"],
            cwd=str(project_root()),
            stdout=log.open("ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return {"scheduled": True, "pid": proc.pid, "log": str(log)}
    except Exception as exc:
        log_hook_error("hook_finalize_deferred_cleanup.worktrees", exc)
        return {"scheduled": False, "error": str(exc)}


def main() -> int:
    try:
        payload = {"ts": now_iso(), "event": "session_stop", "memory_compaction": _compact_on_stop(), "deferred_worktree_cleanup": _schedule_deferred_worktree_cleanup()}
        append_jsonl(ledger_path(), payload)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop"}, "memory_compaction": payload["memory_compaction"], "deferred_worktree_cleanup": payload["deferred_worktree_cleanup"]}, ensure_ascii=False))
    except Exception as exc:
        log_hook_error("hook_finalize_deferred_cleanup", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
