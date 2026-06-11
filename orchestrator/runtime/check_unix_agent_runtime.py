from __future__ import annotations
import json, re
from pathlib import Path
from orchestrator.common import project_root, read_json
from orchestrator.runtime.check_claude_adapter import EXPECTED_AGENT_MODELS, _frontmatter

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

def main() -> int:
    root = project_root(); errors=[]; warnings=[]
    for agent in sorted((root / ".claude" / "agents").glob("*.md")):
        fm=_frontmatter(_read(agent))
        try: mt=int(fm.get("maxTurns"))
        except Exception: errors.append(f"{agent.relative_to(root)} has non-integer maxTurns"); continue
        if mt < 230: errors.append(f"{agent.relative_to(root)} maxTurns must be native+200; found {mt}")
        expected_model = EXPECTED_AGENT_MODELS.get(agent.stem)
        if expected_model is None:
            errors.append(f"{agent.relative_to(root)} missing expected model mapping")
        elif fm.get("model") != expected_model:
            errors.append(f"{agent.relative_to(root)} model must be {expected_model}; found {fm.get('model')!r}")
        if fm.get("model") == "inherit":
            errors.append(f"{agent.relative_to(root)} must not use model: inherit")
        if fm.get("permissionMode") != "bypassPermissions": errors.append(f"{agent.relative_to(root)} missing permissionMode: bypassPermissions")
    manual_runtime_skills = {"audit-runtime-surface", "auto-verify-slice", "bootstrap-registry", "check-blueprint-lossless-flow", "check-git-pr-flow", "check-gold-blueprint", "check-memory-yaml", "check-parallel-locks", "check-skills-runtime", "check-unix-agent-runtime", "check-verify-surface", "closer", "compile-blueprint", "doctor", "next-slice", "next-wave", "phase-gate", "promote-followup", "register-followup", "revise-slice", "slice-maintain",
        "compact-agent-memory", "verify-journey", "verify-slice"}
    for skill in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        fm=_frontmatter(_read(skill))
        if "disable-model-invocation" not in fm:
            errors.append(f"{skill.relative_to(root)} missing disable-model-invocation")
        elif skill.parent.name in manual_runtime_skills and fm.get("disable-model-invocation") is not False:
            errors.append(f"{skill.relative_to(root)} must set disable-model-invocation: false for manual skills runtime entrypoint safety")
    settings=read_json(root / ".claude" / "settings.json", {})
    settings_text = _read(root / ".claude" / "settings.json")
    if '[ -x \\\"$root/.claude/bin/run_hook.sh\\\" ]' in settings_text:
        errors.append(".claude/settings.json hook launcher must use -f for run_hook.sh because it executes with bash and must not fail open when executable bits are missing")
    if '[ -f \\\"$root/.claude/bin/run_hook.sh\\\" ]' not in settings_text:
        errors.append(".claude/settings.json hook launcher must resolve run_hook.sh by file existence")
    if ((settings.get("permissions") or {}).get("defaultMode") != "bypassPermissions"): errors.append(".claude/settings.json must set permissions.defaultMode=bypassPermissions")
    if str((settings.get("env") or {}).get("CLAUDE_SPAWN_BUDGET")) != "70": errors.append(".claude/settings.json env.CLAUDE_SPAWN_BUDGET must be 70")
    txt=_read(root / "scripts" / "unix-runtime-env.sh")
    for token in ["$HOME/.rd/bin", "/opt/homebrew/bin", "/usr/local/bin"]:
        if token not in txt: errors.append(f"scripts/unix-runtime-env.sh missing {token}")
    gitattrs = root / ".gitattributes"
    if not gitattrs.exists():
        errors.append("missing .gitattributes to force LF line endings for Linux/macOS/WSL2")
    else:
        ga = _read(gitattrs)
        for token in ["*.sh text eol=lf", "*.py text eol=lf", "*.md text eol=lf", "*.zip binary"]:
            if token not in ga:
                errors.append(f".gitattributes missing {token}")

    entrypoint_bases = [root / "scripts", root / ".claude" / "bin", root / ".claude" / "git-workflows", root / ".claude" / "enforcers"]
    for base in entrypoint_bases:
        for path in base.rglob("*") if base.exists() else []:
            if path.is_file() and path.suffix in {".sh", ".py"}:
                if not path.stat().st_mode & 0o111:
                    errors.append(f"entrypoint is not executable: {path.relative_to(root)}")
                raw = path.read_bytes()
                if b"\r\n" in raw:
                    errors.append(f"CRLF line endings are not portable in Unix entrypoint: {path.relative_to(root)}")
                txtp = raw.decode("utf-8", errors="replace")
                if path.suffix == ".sh" and re.search(r"(^|[;&|]\s*)timeout\s+", txtp):
                    errors.append(f"GNU timeout command is not macOS portable: {path.relative_to(root)}")
                for m in re.finditer(r"(?<![A-Za-z0-9_$\{:-])/tmp/[A-Za-z0-9_.-]+", txtp):
                    line = txtp.count("\n", 0, m.start()) + 1
                    errors.append(f"literal /tmp path without TMPDIR guard: {path.relative_to(root)}:{line}")
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2
if __name__ == "__main__": raise SystemExit(main())
