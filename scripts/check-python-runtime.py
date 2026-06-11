#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

DEFAULT_DIRS = ["orchestrator", ".claude/bin", "scripts", "tests"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def iter_py(root: Path, dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for rel in dirs:
        base = root / rel
        if not base.exists():
            continue
        if base.is_file() and base.suffix == ".py":
            files.append(base)
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse Python files with a target grammar to catch syntax that would fail in CI.")
    parser.add_argument("--min-version", default="3.13", help="Minimum Python grammar version, e.g. 3.13")
    parser.add_argument("paths", nargs="*", help="Files or directories to scan; defaults to orchestrator, .claude/bin, scripts and tests")
    args = parser.parse_args()
    major, minor = (int(x) for x in args.min_version.split(".", 1))
    root = Path.cwd()
    targets = iter_py(root, args.paths or DEFAULT_DIRS)
    errors: list[dict[str, str]] = []
    if sys.version_info[:2] < (major, minor):
        errors.append({
            "path": "<python-runtime>",
            "line": "0",
            "error": f"active interpreter is {sys.version_info.major}.{sys.version_info.minor}, requires >= {major}.{minor}",
        })
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path), feature_version=(major, minor))
        except SyntaxError as exc:
            errors.append({"path": str(path.relative_to(root)), "line": str(exc.lineno), "error": exc.msg})
    print(json.dumps({"ok": not errors, "min_version": args.min_version, "active_python": f"{sys.version_info.major}.{sys.version_info.minor}", "files": len(targets), "errors": errors}, indent=2, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
