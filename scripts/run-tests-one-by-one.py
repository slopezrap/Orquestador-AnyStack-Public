#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

SELFTEST_GUARD_ENV = "ORCHESTRATOR_ALLOW_SELF_TESTS_DURING_SLICE"
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


def active_slice_context() -> bool:
    if os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID"):
        return True
    cwd = str(Path.cwd())
    return "-worktrees/SLICE-" in cwd or "/worktrees/SLICE-" in cwd


def guard_selftests(tests: list[str]) -> bool:
    if os.environ.get(SELFTEST_GUARD_ENV) == "1" or not active_slice_context():
        return True
    selected = {Path(t).name for t in tests}
    if selected & ORCHESTRATOR_SELFTEST_NAMES:
        task = os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID") or "active slice"
        print(
            f"ERROR: refusing to run orchestrator self-tests during {task}; run slice/product tests only, "
            f"or set {SELFTEST_GUARD_ENV}=1 for maintainer runtime tests.",
            file=sys.stderr,
        )
        return False
    return True


def expand(patterns: list[str]) -> list[str]:
    out: list[str] = []
    for item in patterns:
        matches = sorted(glob.glob(item))
        out.extend(matches or [item])
    seen: set[str] = set()
    unique: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pytest files one by one with a per-file timeout without pkill or GNU timeout.")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--python", default=os.environ.get("PYTHON_BIN", "python3.13"))
    parser.add_argument("tests", nargs="*", default=["tests/test_*.py"])
    args = parser.parse_args(argv)
    tests = [t for t in expand(args.tests) if Path(t).exists()]
    if not tests:
        print("ERROR: no test files found", file=sys.stderr)
        return 2
    if not guard_selftests(tests):
        return 4
    total = 0
    env = os.environ.copy()
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    for test in tests:
        cmd = [args.python, "-m", "pytest", "-q", test]
        print(f"== {test}", flush=True)
        try:
            proc = subprocess.run(cmd, timeout=args.timeout, env=env)
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT: {test} exceeded {args.timeout}s", file=sys.stderr)
            return 124
        if proc.returncode != 0:
            return proc.returncode
        total += 1
    print(f"OK: {total} test files passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
