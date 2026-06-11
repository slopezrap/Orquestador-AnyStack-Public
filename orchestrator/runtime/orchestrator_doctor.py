from __future__ import annotations
import argparse, json, py_compile
from pathlib import Path
from orchestrator.common import project_root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = project_root()
    required = [
        "inputs/BLUEPRINT.md",
        "orchestrator/compiler/compile_blueprint.py",
        "orchestrator/bootstrap/bootstrap_registry.py",
        "orchestrator/runtime/state_machine.py",
        "orchestrator/rules/state-machine.yaml",
        ".claude/settings.json",
        ".claude/orchestrator-contract.json",
    ]
    checks=[]
    ok=True
    for rel in required:
        exists=(root/rel).exists()
        checks.append({"path": rel, "exists": exists})
        ok = ok and exists
    compile_targets = [
        "orchestrator/compiler/compile_blueprint.py",
        "orchestrator/bootstrap/bootstrap_registry.py",
        "orchestrator/runtime/state_machine.py",
        "orchestrator/hooks/hook_capture_subagent_stop.py",
    ]
    py_errors=[]
    for rel in compile_targets:
        try:
            py_compile.compile(str(root/rel), doraise=True)
        except Exception as exc:
            py_errors.append({"path": rel, "error": str(exc)})
    ok = ok and not py_errors
    result={"ok": ok, "checks": checks, "py_compile_errors": py_errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if ok else 2

if __name__ == "__main__":
    raise SystemExit(main())
