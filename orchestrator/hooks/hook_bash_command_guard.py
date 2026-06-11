from __future__ import annotations

import json
import os
import re
import shlex
import sys
from typing import Any

from orchestrator.common import dag_worker_task_id, log_hook_error

SELFTEST_OVERRIDE = "ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE"
RESET_OVERRIDE = "ORCHESTRATOR_ALLOW_DESTRUCTIVE_STATE_RESET"


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )


def _active_task() -> str:
    return dag_worker_task_id() or os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID") or ""


def _command(payload: dict[str, Any]) -> str:
    inp = payload.get("tool_input") or {}
    if isinstance(inp, dict):
        return str(inp.get("command") or "")
    return ""


def _safe_cwd() -> str:
    try:
        return os.getcwd()
    except FileNotFoundError:
        return os.environ.get("PWD") or ""


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except Exception:
        return command.split()


def _contains_any(command: str, needles: list[str]) -> str | None:
    for needle in needles:
        if needle in command:
            return needle
    return None


def _is_root_or_orchestrator_pytest(command: str) -> bool:
    tokens = _tokens(command)
    if not tokens:
        return False
    joined = " ".join(tokens)
    # Explicit self-test selectors are always runtime self-tests.
    if re.search(r"(^|\s)tests/test_[A-Za-z0-9_.-]*(\s|$)", joined) or re.search(r"(^|\s)tests(/|\s|$)", joined):
        return True
    if "scripts/run-tests-one-by-one.py" in joined and ("tests/test_" in joined or re.search(r"(^|\s)tests(/|\s|$)", joined)):
        return True
    # Broad root pytest commands with no explicit product path are unsafe inside
    # a slice because this package's pytest.ini points at orchestrator self-tests.
    lower = [t.lower() for t in tokens]
    pytest_idx = -1
    for i, tok in enumerate(lower):
        if tok == "pytest" or tok.endswith("/pytest"):
            pytest_idx = i
            break
        if tok in {"python", "python3", "python3.13"} and i + 2 < len(lower) and lower[i + 1] == "-m" and lower[i + 2] == "pytest":
            pytest_idx = i + 2
            break
    if pytest_idx < 0:
        return False
    selectors = [t for t in tokens[pytest_idx + 1 :] if not t.startswith("-") and "=" not in t]
    if not selectors:
        return True
    # Common wrappers: `uv run pytest -q` leaves pytest after run; selectors may
    # be absent or only options. Product paths such as backend/tests are allowed.
    unsafe_selectors = {".", "./", "tests", "./tests"}
    if any(s in unsafe_selectors or s.startswith("tests/") or s.startswith("./tests/") for s in selectors):
        return True
    return False


def _active_slice_context() -> bool:
    if _active_task():
        return True
    cwd = _safe_cwd()
    return "-worktrees/SLICE-" in cwd or "/worktrees/SLICE-" in cwd


def _looks_like_git_commit_with_claude_coauthor(command: str) -> bool:
    lower = command.lower()
    if "git commit" not in lower:
        return False
    return "co-authored-by:" in lower and ("anthropic.com" in lower or "claude" in lower)


def _looks_like_core_state_write(command: str) -> bool:
    """Return True only for manual writes to scheduler core state.

    Read-only inspection of registry/runtime/DAG is common during closer and
    debugging.  The guard must block mutations and symlink hacks, not normal
    JSON/YAML reads such as `python -c json.load(open(...registry.json))`.
    """
    lower = command.lower()
    if "orchestrator-state" not in lower:
        return False
    core_path = (
        "registry.json" in lower
        or "runtime-state.json" in lower
        or "task-dag.json" in lower
        or "orchestrator-state/compiled" in lower
        or "orchestrator-state/tasks/task-packs" in lower
    )
    if not core_path:
        return False
    if "ln -s" in lower or "ln -sf" in lower or "ln -snf" in lower:
        return True
    # Shell redirection into core state, including heredocs and append.
    if re.search(r'(>|>>)\s*[\'\"]?[^;&|]*orchestrator-state/(?:tasks|compiled)/', command):
        return True
    # Python write helpers in command strings may arrive with shell/JSON-escaped
    # quotes; use broad checks before regexes.
    if "orchestrator-state/" in lower and ("write_text(" in lower or "json.dump(" in lower):
        return True
    if "open(" in lower and "orchestrator-state/" in lower:
        if any(re.search(pat, lower) for pat in [r",\s*['\"]w['\"]", r",\s*\\['\"]w\\['\"]", r",\s*['\"]a['\"]", r",\s*\\['\"]a\\['\"]", r",\s*['\"]x['\"]", r",\s*\\['\"]x\\['\"]", r",\s*['\"]r\+['\"]", r",\s*\\['\"]r\+\\['\"]"]):
            return True
    # Common in-place edit or destructive verbs that mention core state.
    write_patterns = [
        r"(^|[;&|]\s*)(rm|mv|cp|install|touch|truncate)\s+[^;&|]*orchestrator-state/",
        r"(^|[;&|]\s*)sed\s+-i[^;&|]*orchestrator-state/",
        r"(^|[;&|]\s*)perl\s+-[^;&|]*i[^;&|]*orchestrator-state/",
        r'(^|[;&|]\s*)python[0-9.]*\s+.*open\([^)]*orchestrator-state/[^)]*[, ][\'\"](?:w|a|x|r\+)' ,
        r"write_text\([^)]*orchestrator-state/",
        r"json.dump\([^;&|]*orchestrator-state/",
    ]
    return any(re.search(pat, lower) for pat in write_patterns)


def _looks_like_active_worktree_removal(command: str) -> bool:
    """Prevent deleting the checkout before SubagentStop records the trailer."""
    lower = command.lower()
    if "worktree" not in lower and "rm -rf" not in lower and "rm -fr" not in lower:
        return False
    task = _active_task()
    candidates = [
        os.environ.get("CLAUDE_WORKTREE_ROOT") or "",
        os.environ.get("CLAUDE_WORKSPACE_ROOT") or "",
        os.environ.get("CLAUDE_PROJECT_DIR") or "",
        _safe_cwd(),
    ]
    candidates = [c for c in candidates if c]
    if "git worktree remove" in lower:
        if task and task.lower() in lower:
            return True
        return any(c and c.lower() in lower for c in candidates)
    if "rm -rf" in lower or "rm -fr" in lower:
        return any(c and c.lower() in lower for c in candidates)
    return False


def _reason_for_block(command: str) -> str | None:
    if not _active_slice_context():
        return None
    destructive_state = _contains_any(
        command,
        [
            "scripts/reset-state.sh",
            "./scripts/reset-state.sh",
            "scripts/compile-blueprint.sh",
            "./scripts/compile-blueprint.sh",
            "scripts/bootstrap-registry.sh",
            "./scripts/bootstrap-registry.sh",
        ],
    )
    if destructive_state and os.environ.get(RESET_OVERRIDE) != "1":
        task = _active_task() or "active slice"
        return (
            f"Blocked destructive orchestrator-state command during {task}: {destructive_state}. "
            f"Use product/task-pack tests only, or set {RESET_OVERRIDE}=1 for maintainer-only runtime cleanup."
        )
    destructive_selftest = _contains_any(
        command,
        [
            "scripts/run-all-tests.sh",
            "./scripts/run-all-tests.sh",
            "scripts/run-golden-e2e.sh",
            "./scripts/run-golden-e2e.sh",
            "scripts/simulate-blueprint-to-claude-flow.sh",
            "./scripts/simulate-blueprint-to-claude-flow.sh",
        ],
    )
    if destructive_selftest and os.environ.get(SELFTEST_OVERRIDE) != "1":
        task = _active_task() or "active slice"
        return (
            f"Blocked orchestrator maintainer self-test during {task}: {destructive_selftest}. "
            f"Use product/task-pack tests only, or set {SELFTEST_OVERRIDE}=1 for maintainer-only runtime tests."
        )
    if _is_root_or_orchestrator_pytest(command) and os.environ.get(SELFTEST_OVERRIDE) != "1":
        task = _active_task() or "active slice"
        return (
            f"Blocked broad/root pytest during {task}; this package's root tests are orchestrator self-tests and may reset scheduler state. "
            f"Run the task-pack/product path explicitly, for example backend/tests/<area>, or set {SELFTEST_OVERRIDE}=1 for maintainer-only runtime tests."
        )
    if _looks_like_git_commit_with_claude_coauthor(command):
        return (
            "Blocked git commit message containing a Claude/Anthropic Co-Authored-By trailer. "
            "Use a clean human/project commit message; if the trailer is already in the last commit, amend it before push."
        )
    if _looks_like_active_worktree_removal(command) and os.environ.get("ORCHESTRATOR_ALLOW_ACTIVE_WORKTREE_REMOVE") != "1":
        task = _active_task() or "active slice"
        return (
            f"Blocked removal of the active task worktree during {task}. "
            "SubagentStop still needs the current session/worktree to record the closer trailer; run scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active and let deferred cleanup remove it after hooks."
        )
    if _looks_like_core_state_write(command):
        task = _active_task() or "active slice"
        return (
            f"Blocked manual orchestrator-state topology/core-state write during {task}. "
            "Read-only inspection is allowed, but do not create symlinks or patch registry/runtime/task-dag by hand; use lifecycle scripts/hooks."
        )
    return None


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return 0
        payload = json.loads(raw)
        if str(payload.get("tool_name") or "") != "Bash":
            return 0
        command = _command(payload)
        reason = _reason_for_block(command)
        if reason:
            _deny(reason)
    except Exception as exc:
        log_hook_error("hook_bash_command_guard", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
