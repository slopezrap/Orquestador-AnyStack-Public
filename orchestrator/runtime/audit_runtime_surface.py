from __future__ import annotations
import json
import py_compile
import subprocess
from pathlib import Path
from orchestrator.common import project_root


def main() -> int:
    root = project_root()
    errors: list[str] = []
    shell_files = list((root / "scripts").glob("*.sh")) + list((root / ".claude" / "git-workflows").glob("*.sh")) + list((root / ".claude" / "enforcers").glob("*.sh")) + [root / ".claude" / "bin" / "run_hook.sh"]
    for path in shell_files:
        if not path.exists():
            continue
        proc = subprocess.run(["bash", "-n", str(path)], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            errors.append(f"bash -n failed for {path.relative_to(root)}: {proc.stderr.strip()}")
        if path.read_text(encoding="utf-8", errors="replace").startswith("#!") is False:
            errors.append(f"{path.relative_to(root)} missing shebang")
    python_files: list[Path] = []
    for base in [root / "orchestrator", root / ".claude" / "bin", root / "scripts"]:
        if base.exists():
            python_files.extend(base.rglob("*.py"))
    for path in python_files:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append(f"py_compile failed for {path.relative_to(root)}: {exc}")
    for hook in (root / "orchestrator" / "hooks").glob("*.py"):
        mirror = root / ".claude" / "bin" / hook.name
        if hook.name.startswith("__"):
            continue
        if not mirror.exists():
            errors.append(f"hook {hook.relative_to(root)} has no .claude/bin mirror")
    for wrapper in (root / ".claude" / "bin").glob("*.py"):
        if wrapper.name.startswith("__"):
            continue
        text = wrapper.read_text(encoding="utf-8", errors="replace")
        if "main" not in text and "orchestrator" not in text:
            errors.append(f"bin wrapper {wrapper.relative_to(root)} does not appear to delegate to orchestrator runtime")
    result = {"ok": not errors, "errors": errors, "shell_files": len(shell_files), "python_files": len(python_files)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
