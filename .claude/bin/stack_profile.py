#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from orchestrator.common import load_orchestrator_input, project_root, read_json

DEFAULT_PROFILE: dict[str, Any] = {
    "profile_kind": "blueprint-stack-profile",
    "frontend": {"language": "none", "framework": "none", "module_root": "none", "theme_root": "none", "test_cmd": "none", "dev_cmd": "none", "visual_check": "none"},
    "backend": {"language": "none", "framework": "none", "module_root": "none", "test_cmd": "none", "dev_cmd": "none", "health_url": "none"},
    "db": {"engine": "none", "migrate_cmd": "none", "seed_cmd": "none"},
    "commands": {},
    "git_workflow": "pr-flow",
    "git_identity": {"user_name": "", "user_email": "", "github_login": ""},
    "design_tokens_enforcer": "none",
    "runtime": {"port_scan_span": 2000, "port_defaults": {"frontend": 3000, "backend": 8000, "api": 8080, "db": 5432, "worker": 9000}, "port_env": {"frontend": "CLAUDE_FRONTEND_PORT", "backend": "CLAUDE_BACKEND_PORT", "api": "CLAUDE_API_PORT", "db": "CLAUDE_DB_PORT", "worker": "CLAUDE_WORKER_PORT"}},
    "verification": {"real_data_policy": "required", "docker": {"compose_project_template": "{task_slug}", "compose_file": "auto", "compose_files": [], "cleanup_remove_images": "local"}},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def get_path(profile: dict[str, Any], dotted: str, default: Any = None) -> Any:
    current: Any = profile
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def load_stack_profile(root: Path | None = None) -> dict[str, Any]:
    # Blueprint-first: The compiled stack section is the source.
    # Respect --root explicitly. Commands such as pr-flow run from a linked
    # task worktree, while the compiled orchestrator input is anchored in the
    # canonical orchestrator root.
    if root is not None:
        data = read_json(root / "orchestrator-state" / "compiled" / "orchestrator-input.json", {})
    else:
        data = load_orchestrator_input()
    stack = data.get("stack") if isinstance(data.get("stack"), dict) else {}
    profile = deep_merge(DEFAULT_PROFILE, stack or {})
    commands = stack.get("commands") if isinstance(stack, dict) else {}
    if isinstance(commands, dict):
        if commands.get("test") and profile["backend"].get("test_cmd") == "none":
            profile["backend"]["test_cmd"] = commands.get("test")
        if commands.get("dev") and profile["backend"].get("dev_cmd") == "none":
            profile["backend"]["dev_cmd"] = commands.get("dev")
        if commands.get("lint"):
            profile.setdefault("commands", {})["lint"] = commands.get("lint")
    profile["_source"] = "orchestrator-state/compiled/orchestrator-input.json:stack"
    return profile


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=None)
    p.add_argument("--get", dest="get", default=None)
    p.add_argument("--default", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    profile = load_stack_profile(Path(args.root).resolve() if args.root else project_root())
    if args.get:
        value = get_path(profile, args.get, args.default)
        if isinstance(value, (dict, list)):
            print(json.dumps(value, ensure_ascii=False))
        else:
            print(value if value is not None else "")
        return 0
    print(json.dumps(profile, indent=2, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
