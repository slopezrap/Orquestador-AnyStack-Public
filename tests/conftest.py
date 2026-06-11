from __future__ import annotations

import os
from pathlib import Path

import pytest

ORCHESTRATOR_SELFTEST_NAMES = {
    "test_agent_runtime.py",
    "test_authored_slice_fields.py",
    "test_blueprint_trailers.py",
    "test_compile_and_bootstrap.py",
    "test_final_cleanliness.py",
    "test_followups.py",
    "test_gold_blueprint.py",
    "test_handoff.py",
    "test_handoff_trailers.py",
    "test_hooks_runtime.py",
    "test_lossless.py",
    "test_memory_yaml_agents.py",
    "test_memory_yaml_contract.py",
    "test_next_slice_pipeline_contract.py",
    "test_next_wave_dag.py",
    "test_parallel_locks.py",
    "test_skills_runtime.py",
    "test_state_machine.py",
    "test_verify_acceptance.py",
    "test_verify_surface.py",
    "test_worktree_state_topology.py",
}


def _active_slice_context() -> bool:
    if os.environ.get("ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE") == "1":
        return False
    if os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID"):
        return True
    cwd = Path.cwd().as_posix()
    return "-worktrees/SLICE-" in cwd or "/worktrees/SLICE-" in cwd


def _selects_orchestrator_selftests(args: list[str]) -> bool:
    if not args:
        return True
    for raw in args:
        path = Path(str(raw))
        if path.name in ORCHESTRATOR_SELFTEST_NAMES:
            return True
        # pytest default/testpath selectors such as `tests` or `tests/` include
        # the runtime self-tests in this package and are destructive to
        # orchestrator-state.
        if path.as_posix().rstrip("/") == "tests":
            return True
    return False


def pytest_sessionstart(session: pytest.Session) -> None:
    if not _active_slice_context():
        return
    args = [str(a) for a in getattr(session.config, "args", [])]
    if _selects_orchestrator_selftests(args):
        task = os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID") or "active slice"
        raise pytest.UsageError(
            "refusing to run orchestrator self-tests during "
            f"{task}; run slice/product tests only, or set "
            "ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE=1 for maintainer runtime tests"
        )
