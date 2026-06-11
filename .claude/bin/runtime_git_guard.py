#!/usr/bin/env python3
"""Protect local blueprint orchestrator runtime files around Git transport.

Defined from the orchestrator-AnyStack runtime-git-guard, adapted to 
YAML memory and blueprint-first generated artifacts. The guard allows pr-flow
and next-wave main sync to proceed when the only dirty paths are local runtime
state; non-runtime dirty product files still block.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

RUNTIME_EXACT = {
    # Core scheduler/runtime state.
    "orchestrator-state/tasks/registry.json",
    "orchestrator-state/tasks/registry.yaml",
    "orchestrator-state/tasks/registry-summary.yaml",
    "orchestrator-state/tasks/runtime-state.json",
    "orchestrator-state/tasks/runtime-state.yaml",
    "orchestrator-state/tasks/task-dag.json",
    "orchestrator-state/tasks/task-dag.yaml",
    "orchestrator-state/tasks/task-index.yaml",
    "orchestrator-state/tasks/handoff-index.yaml",
    "orchestrator-state/tasks/lifecycle-events.yaml",
    "orchestrator-state/tasks/ledger.jsonl",
    "orchestrator-state/tasks/bash-ledger.jsonl",
    # Global memory mirrors.
    "orchestrator-state/memory/PROGRESS.yaml",
    "orchestrator-state/memory/PROGRESS.md",
    "orchestrator-state/memory/project-context.yaml",
    "orchestrator-state/memory/source-manifest.yaml",
    "orchestrator-state/memory/blueprint-manifest.yaml",
    "orchestrator-state/memory/blueprint-manifest.json",
    "orchestrator-state/memory/blueprint-sections.yaml",
    "orchestrator-state/memory/blueprint-sections.json",
    "orchestrator-state/memory/blueprint-blocks.yaml",
    "orchestrator-state/memory/blueprint-blocks.json",
    "orchestrator-state/memory/blueprint-lossless.yaml",
    "orchestrator-state/memory/blueprint-lossless.json",
    "orchestrator-state/memory/project-brief.yaml",
    "orchestrator-state/memory/project-brief.md",
    "orchestrator-state/memory/architecture-contract.yaml",
    "orchestrator-state/memory/architecture-contract.md",
    "orchestrator-state/memory/stack-profile.yaml",
    "orchestrator-state/memory/task-dag.yaml",
    "orchestrator-state/memory/execution-graph.yaml",
    "orchestrator-state/memory/decisions.yaml",
    "orchestrator-state/memory/risk-register.yaml",
    "orchestrator-state/hook-errors.log",
    "orchestrator-state/hook-info.log",
}

RUNTIME_GLOBS = {
    "orchestrator-state/**/*.lock",
    "orchestrator-state/**/*.tmp",
    "orchestrator-state/agent-memory/*/MEMORY.yaml",
    "orchestrator-state/agent-memory/*/MEMORY.md",
    "orchestrator-state/agent-memory/*/archive/**",
    "orchestrator-state/tasks/slices/*.yaml",
    "orchestrator-state/tasks/task-packs/*.json",
    "orchestrator-state/tasks/task-packs/*.md",
    "orchestrator-state/tasks/handoffs/*.yaml",
    "orchestrator-state/tasks/handoffs/*.tmp",
    "orchestrator-state/tasks/follow-ups/*.yaml",
    "orchestrator-state/tasks/source-doc-patches/**",
    "orchestrator-state/tasks/work-items/**",
    "orchestrator-state/tasks/cleanup-requests/**",
    "orchestrator-state/tasks/worktree-cleanup-*.log",
    "orchestrator-state/tasks/cleanup-deferred-hook.log",
    "orchestrator-state/memory/archive/**",
    "orchestrator-state/memory/official-doc-notes/**",
    "orchestrator-state/dev-logs/**",
    "orchestrator-state/dev-ports/**",
    "orchestrator-state/archive/**",
    "orchestrator-state/tasks/runtime-snapshots/**/*.lock",
}

LOCAL_EXCLUDE_LINES = sorted(RUNTIME_EXACT | RUNTIME_GLOBS)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)


def _norm(path: str) -> str:
    return path.strip().replace("\\", "/")


def _is_runtime(path: str) -> bool:
    p = _norm(path)
    if p in RUNTIME_EXACT:
        return True
    return any(fnmatch.fnmatch(p, pat) for pat in RUNTIME_GLOBS)


def _status_entries(root: Path) -> list[dict[str, str]]:
    proc = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if proc.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.append({"code": code, "path": _norm(path)})
    return out


def ensure_local_excludes(root: Path) -> None:
    git_dir = _git(root, "rev-parse", "--git-dir")
    if git_dir.returncode != 0:
        return
    exclude = (root / git_dir.stdout.strip() / "info" / "exclude").resolve()
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8", errors="replace") if exclude.exists() else ""
    marker = "# orchestrator-AnyStack local runtime excludes"
    lines = [line for line in existing.splitlines() if line.strip()]
    to_add = [marker, *LOCAL_EXCLUDE_LINES]
    changed = False
    for line in to_add:
        if line not in lines:
            lines.append(line)
            changed = True
    if changed:
        exclude.write_text("\n".join(lines) + "\n", encoding="utf-8")


def protect(root: Path, paths: list[str] | None = None) -> list[str]:
    ensure_local_excludes(root)
    protected: list[str] = []
    candidates = paths or sorted(RUNTIME_EXACT)
    for rel in candidates:
        if not _is_runtime(rel):
            continue
        if _git(root, "ls-files", "--error-unmatch", rel).returncode == 0:
            _git(root, "update-index", "--skip-worktree", rel)
            protected.append(rel)
    return protected


def _copy_path(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=True)
    elif src.exists() or src.is_symlink():
        shutil.copy2(src, dst, follow_symlinks=False)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def backup(root: Path) -> dict[str, Any]:
    ensure_local_excludes(root)
    entries = _status_entries(root)
    non_runtime = [e for e in entries if not _is_runtime(e["path"])]
    runtime = [e for e in entries if _is_runtime(e["path"])]
    if non_runtime:
        return {"ok": False, "reason": "non_runtime_dirty", "non_runtime": non_runtime, "runtime": runtime}
    if not runtime:
        return {"ok": True, "backup_dir": "", "paths": [], "protected": protect(root)}
    ts = subprocess.run(["date", "-u", "+%Y%m%dT%H%M%SZ"], text=True, capture_output=True).stdout.strip() or "runtime"
    backup_dir = root / "orchestrator-state" / "archive" / f"runtime-git-sync-{ts}-{os.getpid()}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "orchestrator-blueprint.runtime-git-guard.v1", "paths": [], "root": str(root)}
    protected = protect(root, [e["path"] for e in runtime])
    for entry in runtime:
        rel = entry["path"]
        src = root / rel
        dst = backup_dir / rel
        if src.exists() or src.is_symlink():
            _copy_path(src, dst)
            manifest["paths"].append({"path": rel, "code": entry["code"], "existed": True})
        else:
            manifest["paths"].append({"path": rel, "code": entry["code"], "existed": False})
        if _git(root, "ls-files", "--error-unmatch", rel).returncode == 0:
            _git(root, "restore", "--staged", "--worktree", "--", rel)
        else:
            _remove_path(src)
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "backup_dir": str(backup_dir), "paths": [e["path"] for e in runtime], "protected": protected}


def restore(root: Path, backup_dir: Path) -> dict[str, Any]:
    ensure_local_excludes(root)
    manifest_path = backup_dir / "manifest.json"
    if not backup_dir or not manifest_path.exists():
        return {"ok": True, "restored": [], "reason": "no_backup"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for item in manifest.get("paths", []) or []:
        rel = str(item.get("path") or "")
        if not rel or not _is_runtime(rel) or not item.get("existed"):
            continue
        src = backup_dir / rel
        dst = root / rel
        if src.exists() or src.is_symlink():
            _copy_path(src, dst)
            restored.append(rel)
    return {"ok": True, "backup_dir": str(backup_dir), "restored": restored, "protected": protect(root, restored)}


def _print_lines(result: dict[str, Any]) -> None:
    print("RUNTIME_GIT_GUARD_READY: yes" if result.get("ok") else "RUNTIME_GIT_GUARD_READY: no")
    if result.get("backup_dir"):
        print(f"RUNTIME_BACKUP_DIR: {result['backup_dir']}")
    if result.get("paths"):
        print(f"RUNTIME_PATHS_BACKED_UP: {len(result['paths'])}")
    if result.get("restored"):
        print(f"RUNTIME_PATHS_RESTORED: {len(result['restored'])}")
    if result.get("protected"):
        print(f"RUNTIME_PATHS_PROTECTED: {len(result['protected'])}")
    if result.get("non_runtime"):
        for entry in result["non_runtime"]:
            print(f"DIRTY_NON_RUNTIME: {entry['code']} {entry['path']}")
    if result.get("reason"):
        print(f"Reason: {result['reason']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup/restore local blueprint runtime files around Git transport.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("backup", "protect"):
        sp = sub.add_parser(name)
        sp.add_argument("--root", default=".")
        sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("restore")
    sp.add_argument("--root", default=".")
    sp.add_argument("--backup-dir", required=True)
    sp.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "backup":
        result = backup(root)
    elif args.cmd == "restore":
        result = restore(root, Path(args.backup_dir).resolve())
    else:
        result = {"ok": True, "protected": protect(root)}
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_lines(result)
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
