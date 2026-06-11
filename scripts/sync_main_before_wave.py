#!/usr/bin/env python3
"""Fast-forward the canonical main branch before computing a DAG wave.

Blueprint-first contract of the orchestrator-AnyStack helper. It is conservative:
fetch/prune remote, fast-forward main only when safe, and use runtime-git-guard
so generated orchestrator-state files do not hide real dirty product changes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)


def say(message: str, quiet: bool = False, err: bool = False) -> None:
    if quiet:
        return
    print(message, file=sys.stderr if err else sys.stdout)


def git_output(root: Path, *args: str) -> str:
    proc = run(["git", *args], cwd=root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def resolve_root(start: Path) -> Path:
    top = Path(git_output(start, "rev-parse", "--show-toplevel"))
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=top)
    if common.returncode == 0:
        common_path = Path(common.stdout.strip())
        if common_path.name == ".git" and common_path.parent.exists():
            return common_path.parent.resolve()
    return top.resolve()


def ref_exists(root: Path, ref: str) -> bool:
    return run(["git", "show-ref", "--verify", "--quiet", ref], cwd=root).returncode == 0


def rev_parse(root: Path, ref: str) -> str:
    return git_output(root, "rev-parse", "--verify", ref)


def current_branch(root: Path) -> str:
    proc = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def call_runtime_guard(root: Path, command: str, backup_dir: str = "") -> dict[str, Any]:
    script = root / "scripts" / "runtime-git-guard.sh"
    if not script.exists():
        return {"ok": True, "reason": "runtime_guard_missing"}
    args = ["bash", str(script), command, "--root", str(root), "--json"]
    if command == "restore":
        args.extend(["--backup-dir", backup_dir])
    proc = run(args, cwd=root)
    text = (proc.stdout or "").strip()
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        payload = {"ok": False, "reason": "runtime_guard_invalid_json", "stdout": proc.stdout, "stderr": proc.stderr}
    if proc.returncode != 0 and payload.get("ok", False):
        payload["ok"] = False
    return payload


def sync(root: Path, remote: str, main_branch: str, *, apply: bool, quiet: bool, strict: bool = False) -> int:
    if run(["git", "remote", "get-url", remote], cwd=root).returncode != 0:
        say(f"sync-main-before-wave: remote={remote} not_configured; skipped", quiet)
        return 0
    fetch = run(["git", "fetch", remote, "--prune"], cwd=root, timeout=120)
    if fetch.returncode != 0:
        say(f"sync-main-before-wave: fetch failed; {fetch.stderr.strip() or fetch.stdout.strip()}", quiet, err=True)
        return 3
    local_ref = f"refs/heads/{main_branch}"
    remote_ref = f"refs/remotes/{remote}/{main_branch}"
    if not ref_exists(root, local_ref) or not ref_exists(root, remote_ref):
        say(f"sync-main-before-wave: main_ref_missing local={main_branch} remote={remote}/{main_branch}; skipped", quiet)
        return 0
    branch = current_branch(root)
    if branch != main_branch:
        guard = call_runtime_guard(root, "backup")
        backup = str(guard.get("backup_dir") or "")
        if not guard.get("ok", False):
            say("sync-main-before-wave: cannot switch canonical root to main; non-runtime dirty files would be hidden", quiet, err=True)
            for item in guard.get("non_runtime", []) or []:
                if isinstance(item, dict):
                    say(f"DIRTY_NON_RUNTIME: {item.get('code','')} {item.get('path','')}", quiet, err=True)
            return 3
        if not apply:
            say(f"sync-main-before-wave: would switch canonical root from '{branch or 'DETACHED'}' to '{main_branch}'", quiet)
            return 0
        switch = run(["git", "switch", main_branch], cwd=root, timeout=120)
        if switch.returncode != 0:
            checkout = run(["git", "checkout", main_branch], cwd=root, timeout=120)
            if checkout.returncode != 0:
                if backup:
                    call_runtime_guard(root, "restore", backup)
                say(f"sync-main-before-wave: failed to switch to {main_branch}; {checkout.stderr.strip() or switch.stderr.strip() or checkout.stdout.strip() or switch.stdout.strip()}", quiet, err=True)
                return 3
        if backup:
            restore = call_runtime_guard(root, "restore", backup)
            if not restore.get("ok", False):
                say(f"sync-main-before-wave: runtime restore incomplete after branch switch backup={backup}", quiet, err=True)
                return 3
        say(f"sync-main-before-wave: switched canonical root from '{branch or 'DETACHED'}' to '{main_branch}'", quiet)
    guard = call_runtime_guard(root, "backup")
    backup_dir = str(guard.get("backup_dir") or "")
    if not guard.get("ok", False):
        say("sync-main-before-wave: blocked by non-runtime dirty files", quiet, err=True)
        for item in guard.get("non_runtime", []) or []:
            if isinstance(item, dict):
                say(f"DIRTY_NON_RUNTIME: {item.get('code','')} {item.get('path','')}", quiet, err=True)
        return 3
    try:
        local_sha = rev_parse(root, main_branch)
        remote_sha = rev_parse(root, f"{remote}/{main_branch}")
        if local_sha == remote_sha:
            say(f"sync-main-before-wave: {main_branch} already at {remote}/{main_branch}", quiet)
            return 0
        base = git_output(root, "merge-base", main_branch, f"{remote}/{main_branch}")
        if local_sha == base:
            if not apply:
                say(f"sync-main-before-wave: would fast-forward {main_branch} to {remote}/{main_branch}", quiet)
                return 0
            ff = run(["git", "merge", "--ff-only", f"{remote}/{main_branch}"], cwd=root, timeout=120)
            if ff.returncode != 0:
                say(f"sync-main-before-wave: ff-only failed; {ff.stderr.strip() or ff.stdout.strip()}", quiet, err=True)
                return 3
            say(f"sync-main-before-wave: fast-forwarded {main_branch} to {remote}/{main_branch}", quiet)
            return 0
        if remote_sha == base:
            say(f"sync-main-before-wave: local {main_branch} is ahead of {remote}/{main_branch}; using local main for DAG wave.", quiet, err=bool(strict))
            return 0
        say(f"sync-main-before-wave: divergence detected between {main_branch} and {remote}/{main_branch}; manual reconciliation required.", quiet, err=True)
        return 3
    finally:
        if backup_dir:
            restore = call_runtime_guard(root, "restore", backup_dir)
            if not restore.get("ok", False):
                say(f"sync-main-before-wave: runtime restore incomplete backup={backup_dir}", quiet, err=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fast-forward canonical main before DAG next-wave")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remote", default=os.environ.get("CLAUDE_GIT_REMOTE", "origin"))
    parser.add_argument("--main", default=os.environ.get("CLAUDE_GIT_MAIN_BRANCH") or os.environ.get("GIT_DEFAULT_BRANCH", "main"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        args.apply = False
    try:
        root = resolve_root(Path.cwd())
    except Exception as exc:
        say(f"sync-main-before-wave: git_repository=no reason={exc}", args.quiet)
        return 0
    return sync(root, args.remote, args.main, apply=bool(args.apply), quiet=bool(args.quiet), strict=bool(args.strict))


if __name__ == "__main__":
    raise SystemExit(main())
