from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator.common import project_root
from orchestrator.runtime.check_claude_adapter import _frontmatter

MANUAL_RUNTIME_SKILLS = {
    "audit-runtime-surface": ["./scripts/audit-runtime-surface.sh"],
    "auto-verify-slice": ["./scripts/auto-verify-slice.sh", "resolved_specs"],
    "bootstrap-registry": ["./scripts/bootstrap-registry.sh", "orchestrator-input.json"],
    "check-blueprint-lossless-flow": ["./scripts/check-blueprint-lossless-flow.sh"],
    "check-git-pr-flow": ["./scripts/check-git-pr-flow.sh", "pr-flow", "Docker/Rancher"],
    "check-gold-blueprint": ["./scripts/check-gold-blueprint.sh"],
    "check-memory-yaml": ["./scripts/check-memory-yaml.sh"],
    "check-parallel-locks": ["./scripts/check-parallel-locks.sh"],
    "check-skills-runtime": ["./scripts/check-skills-runtime.sh"],
    "check-unix-agent-runtime": ["./scripts/check-unix-agent-runtime.sh"],
    "check-verify-surface": ["./scripts/check-verify-surface.sh"],
    "closer": ["./scripts/closer.sh", "verified_pending_close", "PR_READY", "MERGED", "CANONICAL_MAIN_SYNCED", "NEXT_STATUS: done"],
    "compile-blueprint": ["./scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"],
    "compact-agent-memory": ["./scripts/compact-agent-memory.py", "MEMORY.yaml", "PROGRESS.yaml"],
    "doctor": ["./scripts/orchestrator-doctor.sh"],
    "next-slice": ["./scripts/next-slice.sh", "./scripts/slice-maintain.sh", "verify-slice", "init obligatorio", "MODO DAG ACTIVO", "planner", "developer", "official-docs-researcher", "NEEDS_OFFICIAL_DOCS", "validator ∥ tester", "debugger", "4 ciclos", "CLAUDE_TRAILER", "ready_for_close", "verified_pending_close"],
    "next-wave": ["./scripts/next-wave.sh", "DAG wave", "Ready nodes", "ensure-task-worktree.sh", "explicit_dag"],
    "phase-gate": ["./scripts/phase-gate.sh"],
    "promote-followup": ["./scripts/promote-followup.sh"],
    "register-followup": ["./scripts/register-followup-task.sh"],
    "revise-slice": ["inputs/BLUEPRINT.md", "compile-blueprint", "bootstrap"],
    "slice-maintain": ["./scripts/slice-maintain.sh", "inspect-task-state", "check-handoff-contract", "compact-agent-memory"],
    "verify-journey": ["./scripts/verify-journey.sh", "--verified", "--waived", "--issues-found"],
    "verify-slice": ["./scripts/verify-slice.sh", "./scripts/init-verify-slice-handoff.sh", "## verify-slice", "slice-verifier", "verified_pending_close", "NO_STUB_DATA_USED", "RUNTIME_LOGS_CHECKED"],
}

SOURCE_TOKENS = ["inputs/BLUEPRINT.md", "orchestrator-input.json", "registry.json", "resolved_specs"]
MCP_RE = re.compile(r"mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_.-]+")
BAD_MCP_RE = re.compile(r"\bMCP__[A-Za-z0-9_-]+__[A-Za-z0-9_.-]+|mcp__[A-Z][A-Za-z0-9_-]*__|mcp__[A-Za-z0-9_-]+__[A-Z]")

PIPELINE_CONTRACT_FILES = {
    ".claude/agents/main-orchestrator.md": ["Intra-slice pipeline `/next-slice`", "official-docs-researcher", "NEEDS_OFFICIAL_DOCS", "validator ∥ tester", "debugger"],
    ".claude/rules/01-non-negotiables.md": ["Chain discipline (per slice)", "official-docs-researcher", "official documentation is needed", "validator ∥ tester"],
    ".claude/rules/02-phase-execution.md": ["Pipeline per slice", "official-docs-researcher", "NEEDS_OFFICIAL_DOCS", "validator ∥ tester"],
    ".claude/CLAUDE.md": ["Per-slice chain", "official-docs-researcher", "NEEDS_OFFICIAL_DOCS", "validator ∥ tester"],
    ".claude/skills/next-slice/SKILL.md": ["pipeline paralelo obligatorio", "official-docs-researcher", "NEEDS_OFFICIAL_DOCS", "validator ∥ tester", "Máximo 4 ciclos"],
    ".claude/agents/planner.md": ["CONTEXT_READY", "NEEDS_OFFICIAL_DOCS"],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        return path.as_posix()


def _script_refs(text: str) -> set[str]:
    refs = set(re.findall(r"\./scripts/[A-Za-z0-9_.-]+", text))
    refs.update(re.findall(r"scripts/[A-Za-z0-9_.-]+", text))
    return refs


def _check_case(path: Path, root: Path, errors: list[str]) -> None:
    rel = _rel(root, path)
    if rel.startswith(".claude/skills/"):
        parts = rel.split("/")
        if len(parts) >= 3:
            skill_name = parts[2]
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", skill_name):
                errors.append(f"skill directory is not lower-hyphen case-safe: {rel}")


def main(argv: list[str] | None = None) -> int:
    root = project_root()
    errors: list[str] = []
    warnings: list[str] = []

    command_dir = root / ".claude" / ("com" + "mands")
    if command_dir.exists():
        command_files = sorted(command_dir.glob("*.md"))
        if command_files:
            errors.append("project command directory must not contain Markdown slash files; project skills are the only slash entrypoints")
        else:
            warnings.append("empty project command directory is unnecessary")

    rule_dir = root / ".claude" / "rules"
    for rule in sorted(rule_dir.glob("*.md")):
        lowered = rule.name.lower()
        if any(token in lowered for token in ["dual-runtime-rule", "noncanonical-runtime-rule", "archived-runtime-rule"]):
            errors.append(f"non-canonical rule name is not allowed in final runtime: {_rel(root, rule)}")
        if re.search(r"v\d", lowered):
            errors.append(f"release-tagged rule name is not allowed in final runtime: {_rel(root, rule)}")

    skill_dir = root / ".claude" / "skills"
    for name, tokens in MANUAL_RUNTIME_SKILLS.items():
        path = skill_dir / name / "SKILL.md"
        text = _read(path)
        if not path.exists():
            errors.append(f"missing skill .claude/skills/{name}/SKILL.md")
            continue
        fm = _frontmatter(text)
        if not fm or fm.get("__frontmatter_error__"):
            errors.append(f"skill {name} invalid/missing YAML frontmatter")
            continue
        if not fm.get("description"):
            errors.append(f"skill {name} missing description")
        if fm.get("user-invocable") is not True:
            errors.append(f"skill {name} must set user-invocable: true")
        if fm.get("disable-model-invocation") is not False:
            errors.append(f"manual runtime skill {name} must set disable-model-invocation: false so Skill tool invocation works")
        for token in SOURCE_TOKENS:
            if token not in text:
                errors.append(f"skill {name} missing source-chain token {token}")
        for token in tokens:
            if token not in text:
                errors.append(f"skill {name} missing operational token: {token}")
        if (".claude/" + "commands") in text:
            errors.append(f"skill {name} must not reference project command directory")
        _check_case(path, root, errors)

    for rel, tokens in PIPELINE_CONTRACT_FILES.items():
        pipeline_text = _read(root / rel)
        if not pipeline_text:
            errors.append(f"pipeline contract file missing: {rel}")
            continue
        for token in tokens:
            if token not in pipeline_text:
                errors.append(f"{rel} missing next-slice pipeline token: {token}")

    for skill in sorted(skill_dir.glob("*/SKILL.md")):
        text = _read(skill)
        fm = _frontmatter(text)
        name = skill.parent.name
        if not fm or fm.get("__frontmatter_error__"):
            errors.append(f"{_rel(root, skill)} invalid/missing YAML frontmatter")
            continue
        if fm.get("name") and str(fm.get("name")) != name:
            errors.append(f"{_rel(root, skill)} frontmatter name must equal directory name for exact-case clarity")
        if not fm.get("description"):
            errors.append(f"{_rel(root, skill)} missing description")
        for ref in _script_refs(text):
            if not (root / ref.lstrip("./")).exists():
                errors.append(f"{_rel(root, skill)} references missing {ref}")

    for base in [root / ".claude", root / "docs", root / "scripts", root / "orchestrator", root / "tests"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".json", ".py", ".sh", ".yaml", ".yml"}:
                rel = _rel(root, path)
                text = _read(path)
                if rel.startswith(".claude/schemas/"):
                    continue
                if BAD_MCP_RE.search(text):
                    errors.append(f"case-unsafe MCP reference in {rel}")
                for m in MCP_RE.findall(text):
                    if m.lower() != m:
                        errors.append(f"MCP reference must be lowercase in {rel}: {m}")

    required_scripts = [
        "scripts/next-wave.sh", "scripts/next-slice.sh", "scripts/verify-slice.sh", "scripts/closer.sh",
        "scripts/ensure-task-worktree.sh", "scripts/check-handoff-contract.sh", "scripts/check-runtime-logs.sh",
        "scripts/dev-restart.sh", "scripts/docker-hard-reset.sh", "scripts/cleanup-slice-runtime.sh",
        "scripts/check-git-pr-flow.sh", "scripts/check-skills-runtime.sh", "scripts/slice-maintain.sh",
    ]
    for rel in required_scripts:
        if not (root / rel).exists():
            errors.append(f"missing required script {rel}")

    result: dict[str, Any] = {
        "ok": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "manual_runtime_skills": sorted(MANUAL_RUNTIME_SKILLS),
        "skills_total": len(list(skill_dir.glob("*/SKILL.md"))),
        "commands_total": len(list(command_dir.glob("*.md"))) if command_dir.exists() else 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
