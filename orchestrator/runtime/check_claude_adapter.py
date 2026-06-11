from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator.common import project_root, read_json, read_yaml

EXACT_TOOL_NAMES = {
    "Read", "Glob", "Grep", "Bash", "Edit", "MultiEdit", "Write", "Agent", "Skill", "WebFetch", "WebSearch", "NotebookEdit",
    "TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "ToolSearch", "WaitForMcpServers", "Workflow",
}


EXPECTED_AGENT_MODELS = {
    "developer": "fable[1m]",
    "main-orchestrator": "opus[1m]",
    "planner": "opus",
    "blueprint-reviewer": "opus",
    "project-architect": "opus",
    "validator": "opus",
    "debugger": "opus",
    "slice-verifier": "opus",
    "tester": "sonnet",
    "deployer": "sonnet",
    "closer": "sonnet",
    "task-planner": "sonnet",
    "document-analyzer": "sonnet",
    "official-docs-researcher": "sonnet",
    "screen-journey-reviewer": "sonnet",
}

SUPPORTED_HOOK_EVENTS = {
    "SessionStart",
    "Setup",
    "InstructionsLoaded",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "MessageDisplay",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "PermissionDenied",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "Elicitation",
    "ElicitationResult",
}


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1].strip()
    try:
        import yaml  # type: ignore
        parsed = yaml.safe_load(raw) if raw else {}
        if parsed is None:
            return {}
        if not isinstance(parsed, dict):
            return {"__frontmatter_error__": "frontmatter must be a mapping"}
        return {str(k): v for k, v in parsed.items()}
    except Exception as exc:
        # Surface invalid YAML instead of silently accepting line-split approximations.
        return {"__frontmatter_error__": str(exc)}



def _split_tools(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw or "")
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                out.append(item)
            buf = []
        else:
            buf.append(ch)
    item = "".join(buf).strip()
    if item:
        out.append(item)
    return out


def _tool_bases(tools: set[str]) -> set[str]:
    return {tool.split("(", 1)[0].strip() for tool in tools if tool.strip()}

def _rel(path: Path) -> str:
    try:
        return path.relative_to(project_root()).as_posix()
    except Exception:
        return path.as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _script_refs(text: str) -> set[str]:
    refs = set(re.findall(r"\.\/scripts\/[A-Za-z0-9_.-]+", text))
    refs.update(re.findall(r"scripts\/[A-Za-z0-9_.-]+", text))
    return refs


def _has_bypass_project_default(settings: dict[str, Any]) -> bool:
    return ((settings.get("permissions") or {}).get("defaultMode") == "bypassPermissions")



TRAILER_BODY_RE = re.compile(r"CLAUDE_TRAILER:\s*\n(?P<body>.*?)(?:\n```|\Z)", re.S)
TRAILER_KV_RE = re.compile(r"^\s*(?:[-*]\s*)?(?P<key>[A-Z][A-Z0-9_]*):\s*(?P<value>.*?)\s*$", re.M)


def _effective_required_keys(role: str, spec: dict[str, Any], trailer: dict[str, str]) -> list[str]:
    keys = [str(k) for k in (spec.get("required_keys") or [])]
    outcome = trailer.get("outcome", "").lower()
    next_status = trailer.get("next_status", "").lower()
    if outcome == "blocked" or next_status == "blocked":
        if role == "closer":
            return ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "BLOCKER_REASON"]
        if role == "slice-verifier":
            return ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "EVIDENCE", "VERIFY_OUTCOME", "BLOCKER_REASON"]
        if spec.get("mutates_registry_lifecycle"):
            base = ["AGENT", "TASK_ID", "OUTCOME", "NEXT_STATUS", "HANDOFF", "EVIDENCE", "BLOCKER_REASON"]
            return [k for k in base if k in set(keys) | {"BLOCKER_REASON"}]
        return [k for k in ["AGENT", "TASK_ID", "OUTCOME", "HANDOFF", "BLOCKER_REASON"] if k in set(keys) | {"BLOCKER_REASON"}]
    return keys


def _parse_trailer_body(body: str) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    seen: set[str] = set()
    duplicates: list[str] = []
    for match in TRAILER_KV_RE.finditer(body or ""):
        key_raw = match.group("key")
        key = key_raw.lower()
        if key in seen:
            duplicates.append(key_raw)
        seen.add(key)
        values[key] = match.group("value").strip()
    return values, duplicates


def _check_agent_trailer_examples(rel: str, expected: str, text: str, roles: dict[str, Any], errors: list[str]) -> None:
    spec = roles.get(expected) or {}
    if not spec:
        return
    blocks = list(TRAILER_BODY_RE.finditer(text))
    if not blocks:
        errors.append(f"{rel} missing CLAUDE_TRAILER example")
        return
    allowed_outcomes = {str(x).lower() for x in spec.get("outcome_values") or []}
    allowed_status = {str(x).lower() for x in spec.get("next_status_values") or []}
    has_non_blocked_valid = False
    for idx, block in enumerate(blocks, start=1):
        trailer, duplicates = _parse_trailer_body(block.group("body"))
        block_errors: list[str] = []
        for dup in sorted(set(duplicates)):
            block_errors.append(f"duplicates key {dup}")
        if not trailer:
            errors.append(f"{rel} trailer block {idx} has no parseable KEY: value lines")
            continue
        agent_value = trailer.get("agent", "").lower().replace("_", "-")
        if agent_value != expected:
            block_errors.append(f"AGENT={agent_value or 'missing'} must equal {expected}")
        missing = [key for key in _effective_required_keys(expected, spec, trailer) if not trailer.get(str(key).lower())]
        for key in missing:
            block_errors.append(f"missing required key {key}")
        outcome = trailer.get("outcome", "").lower()
        if outcome and allowed_outcomes and outcome not in allowed_outcomes:
            block_errors.append(f"OUTCOME={outcome} not allowed")
        next_status = trailer.get("next_status", "").lower()
        if next_status:
            if allowed_status and next_status not in allowed_status:
                block_errors.append(f"NEXT_STATUS={next_status} not allowed")
            elif not allowed_status:
                block_errors.append("should not emit NEXT_STATUS for this info-only role")
        if outcome != "blocked" and next_status != "blocked" and not block_errors:
            has_non_blocked_valid = True
        for err in block_errors:
            errors.append(f"{rel} trailer block {idx} {err}")
    if not has_non_blocked_valid:
        errors.append(f"{rel} must include at least one non-blocked trailer example satisfying the role contract")


def _check_workflows(root: Path, errors: list[str], warnings: list[str]) -> None:
    ci = root / ".github" / "workflows" / "ci.yml"
    if not ci.exists():
        errors.append("missing .github/workflows/ci.yml")
    else:
        ci_text = _read(ci)
        for token in ["name: CI", "name: Lint", "name: Bootstrap", "name: Unit tests 3.13", "actions/setup-python@v5"]:
            if token not in ci_text:
                errors.append(f".github/workflows/ci.yml missing {token}")
        for cmd in ["./scripts/check-claude-adapter.sh", "./scripts/check-blueprint-machine-contract.sh", "./scripts/check-orchestrator-gaps.sh", "./scripts/run-golden-e2e.sh"]:
            if cmd not in ci_text:
                errors.append(f".github/workflows/ci.yml missing runtime command {cmd}")
        if "pytest -q" not in ci_text and "scripts/run-tests-one-by-one.py --timeout 180" not in ci_text:
            errors.append(".github/workflows/ci.yml missing runtime test command: pytest -q or run-tests-one-by-one.py --timeout 180")
        if "python-version: '3.13'" not in ci_text:
            errors.append(".github/workflows/ci.yml must test Python 3.13 explicitly")
    pr = root / ".github" / "workflows" / "claude-code-pr-flow.yml"
    if not pr.exists():
        errors.append("missing .github/workflows/claude-code-pr-flow.yml")
    else:
        pr_text = _read(pr)
        for forbidden in ["anthropics/claude-code-action@beta", "direct_prompt:", "override_prompt:", "custom_instructions:", "mode:"]:
            if forbidden in pr_text:
                errors.append(f"claude-code-pr-flow.yml uses deprecated Claude Code Action input {forbidden}")
        for token in ["anthropics/claude-code-action@v1", "prompt:", "claude_args:", "--agent main-orchestrator"]:
            if token not in pr_text:
                errors.append(f"claude-code-pr-flow.yml missing {token}")
        if "permissions:" not in pr_text or "contents: write" not in pr_text or "pull-requests: write" not in pr_text:
            warnings.append("claude-code-pr-flow.yml should declare least write permissions for PR workflow")


def _check_settings(root: Path, errors: list[str], warnings: list[str]) -> None:
    path = root / ".claude" / "settings.json"
    try:
        settings = json.loads(_read(path))
    except Exception as exc:
        errors.append(f"invalid .claude/settings.json: {exc}")
        return
    if not _has_bypass_project_default(settings):
        errors.append("project .claude/settings.json must set permissions.defaultMode=bypassPermissions for this orchestrator profile")
    if "agent" in settings:
        errors.append("project .claude/settings.json must not set top-level agent; launch with claude --agent main-orchestrator or use documented subagent definitions")
    for secret_rule in ["Read(./.env)", "Read(./.env.*)"]:
        if secret_rule not in ((settings.get("permissions") or {}).get("deny") or []):
            errors.append(f".claude/settings.json missing secret deny rule {secret_rule}")
    hooks = settings.get("hooks") or {}
    if not isinstance(hooks, dict):
        errors.append(".claude/settings.json hooks must be an object")
        return
    for event, groups in hooks.items():
        if event not in SUPPORTED_HOOK_EVENTS:
            errors.append(f"unknown hook event in settings.json: {event}")
        if not isinstance(groups, list):
            errors.append(f"hook event {event} must be a list")
            continue
        for idx, group in enumerate(groups):
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                cmd = str(hook.get("command") or "")
                for rel in re.findall(r'"\$root/([^"\s]+\.py)"', cmd):
                    if not (root / rel).exists():
                        errors.append(f"settings hook {event}[{idx}] references missing {rel}")
                if "python3 -B -S" not in cmd and "run_hook.sh" not in cmd:
                    warnings.append(f"settings hook {event}[{idx}] does not use python3 -B -S or run_hook.sh")


def main() -> int:
    root = project_root()
    errors: list[str] = []
    warnings: list[str] = []

    contract = read_json(root / ".claude" / "orchestrator-contract.json", {})
    roles: dict[str, Any] = ((contract.get("trailer_schema") or {}).get("roles") or {})
    sm = read_yaml(root / "orchestrator" / "rules" / "state-machine.yaml", {})
    mutating = {r for r, spec in roles.items() if spec.get("mutates_registry_lifecycle")}
    info = {r for r, spec in roles.items() if spec.get("info_only") or not spec.get("mutates_registry_lifecycle")}

    root_claude = root / "CLAUDE.md"
    if not root_claude.exists():
        errors.append("missing root CLAUDE.md")
    elif "@.claude/CLAUDE.md" not in _read(root_claude):
        errors.append("root CLAUDE.md must import @.claude/CLAUDE.md")

    inner = root / ".claude" / "CLAUDE.md"
    if not inner.exists():
        errors.append("missing .claude/CLAUDE.md")
    else:
        txt = _read(inner)
        for token in ["BLUEPRINT.md", "orchestrator-input.json", "registry.json", "CLAUDE_TRAILER", "state-machine.yaml", "dependency_edges", "resolved_dependencies", "PROGRESS.yaml", "MEMORY.yaml", "CI", "10-macos-case-sensitive-and-mcp.md"]:
            if token not in txt:
                errors.append(f".claude/CLAUDE.md missing {token}")
        for rule in sorted((root / ".claude" / "rules").glob("*.md")):
            if rule.name not in txt:
                warnings.append(f".claude/CLAUDE.md rule index does not mention {rule.name}")

    required_blueprint_kinds = [
        "kind: project",
        "kind: stack",
        "kind: auxiliary.arc42",
        "kind: building_blocks",
        "kind: logic.domain",
        "kind: logic.application",
        "kind: logic.journey",
        "kind: logic.permission",
        "kind: logic.state",
        "kind: logic.error",
        "kind: logic.integration",
        "kind: logic.ui",
        "kind: auxiliary.data",
        "kind: auxiliary.config",
        "kind: auxiliary.verification",
        "kind: auxiliary.adr",
        "kind: auxiliary.risks",
        "kind: auxiliary.glossary",
        "kind: auxiliary.external_refs",
        "kind: registry.slices",
    ]
    for rel in [".claude/rules/00-blueprint-runtime-authority.md"]:
        txt = _read(root / rel)
        for token in required_blueprint_kinds:
            if token not in txt:
                errors.append(f"{rel} missing required blueprint kind {token}")
    desc_rule = _read(root / ".claude" / "rules" / "08-blueprint-descriptions-and-resolved-specs.md")
    for token in [
        "auxiliary.data[]",
        "auxiliary.config[]",
        "auxiliary.verification[]",
        "auxiliary.adr[]",
        "auxiliary.risks[]",
        "auxiliary.glossary[]",
        "auxiliary.external_refs[]",
        "registry.slices[]",
    ]:
        if token not in desc_rule:
            errors.append(f".claude/rules/08-blueprint-descriptions-and-resolved-specs.md missing {token}")


    skills_rule = root / ".claude" / "rules" / "07-skills-runtime.md"
    if not skills_rule.exists():
        errors.append(".claude/rules/07-skills-runtime.md missing")
    else:
        skills_rule_text = _read(skills_rule)
        for token in [".claude/skills/<name>/SKILL.md", "disable-model-invocation: false", "Single skill layer", "orchestrator-input.json"]:
            if token not in skills_rule_text:
                errors.append(f".claude/rules/07-skills-runtime.md missing {token}")
    for rule in sorted((root / ".claude" / "rules").glob("*.md")):
        lowered = rule.name.lower()
        if any(token in lowered for token in ["dual-runtime-rule", "noncanonical-runtime-rule", "archived-runtime-rule"]):
            errors.append(f"non-canonical rule name is not allowed in final runtime: .claude/rules/{rule.name}")
        if re.search(r"v\d", lowered):
            errors.append(f"release-tagged rule name is not allowed in final runtime: .claude/rules/{rule.name}")
    mem_rule = root / ".claude" / "rules" / "12-memory-yaml-contract.md"
    if not mem_rule.exists():
        errors.append(".claude/rules/12-memory-yaml-contract.md missing")
    else:
        mem_text = _read(mem_rule)
        for token in ["MEMORY.yaml", "PROGRESS.yaml", "project-context.yaml", "SubagentStop"]:
            if token not in mem_text:
                errors.append(f".claude/rules/12-memory-yaml-contract.md missing {token}")

    agent_dir = root / ".claude" / "agents"
    for agent in sorted(agent_dir.glob("*.md")):
        text = _read(agent)
        fm = _frontmatter(text)
        expected = agent.stem
        if not fm:
            errors.append(f"{_rel(agent)} missing YAML frontmatter")
            continue
        if fm.get("__frontmatter_error__"):
            errors.append(f"{_rel(agent)} invalid YAML frontmatter: {fm.get('__frontmatter_error__')}")
            continue
        name = fm.get("name")
        if name != expected:
            errors.append(f"{_rel(agent)} frontmatter name {name!r} != filename stem {expected!r}")
        if not fm.get("description"):
            errors.append(f"{_rel(agent)} missing description")
        expected_model = EXPECTED_AGENT_MODELS.get(expected)
        if expected_model is None:
            errors.append(f"{_rel(agent)} has no expected model mapping in check_claude_adapter.py")
        elif fm.get("model") != expected_model:
            errors.append(f"{_rel(agent)} model must be {expected_model}; found {fm.get('model')!r}")
        if fm.get("model") == "inherit":
            errors.append(f"{_rel(agent)} must not use model: inherit; keep role-optimized explicit aliases")
        if not fm.get("tools"):
            errors.append(f"{_rel(agent)} missing tools")
        tool_set = set(_split_tools(fm.get("tools")))
        tool_bases = _tool_bases(tool_set)
        for tool in sorted(tool_set):
            base_tool = tool.split("(", 1)[0].strip()
            if base_tool and base_tool not in EXACT_TOOL_NAMES:
                errors.append(f"{_rel(agent)} uses non-official or wrong-case tool name {tool!r}")
        if not fm.get("maxTurns"):
            errors.append(f"{_rel(agent)} missing maxTurns contract from subagent config")
        else:
            try:
                if int(fm.get("maxTurns")) < 230:
                    errors.append(f"{_rel(agent)} maxTurns must be + 200, minimum active value is 230")
            except Exception:
                errors.append(f"{_rel(agent)} maxTurns must be an integer")
        if not fm.get("effort"):
            errors.append(f"{_rel(agent)} missing effort contract from subagent config")
        if fm.get("permissionMode") != "bypassPermissions":
            errors.append(f"{_rel(agent)} must force permissionMode=bypassPermissions for this orchestrator profile")
        if fm.get("memory") != "project":
            errors.append(f"{_rel(agent)} must declare memory: project so Claude Code project-scoped subagent memory is enabled")
        for required_memory_token in ["MEMORY.yaml", "PROGRESS.yaml", "project-context.yaml", "source-manifest.yaml", "project-brief.yaml", "architecture-contract.yaml"]:
            if required_memory_token not in text:
                errors.append(f"{_rel(agent)} missing structured YAML memory instruction {required_memory_token}")
        if "Skill" not in tool_bases:
            errors.append(f"{_rel(agent)} must include Skill so blueprint-first skills remain available despite restrictive tools allowlists")
        if expected == "main-orchestrator":
            for required_tool in ["Agent", "Skill"]:
                if required_tool not in tool_bases:
                    errors.append(f"{_rel(agent)} must include {required_tool} in tools because it delegates/uses skills when launched via --agent")
        elif "Agent" in tool_bases:
            errors.append(f"{_rel(agent)} must not include Agent; only main-orchestrator may spawn subagents")
        if expected == "official-docs-researcher":
            for required_tool in ["WebFetch", "WebSearch"]:
                if required_tool not in tool_bases:
                    errors.append(f"{_rel(agent)} must include {required_tool} in tools to verify official documentation")
        if "orchestrator-state/agent-memory/" not in text or "MEMORY.yaml" not in text:
            errors.append(f"{_rel(agent)} missing manual YAML agent-memory contract")
        if expected not in roles:
            errors.append(f"{_rel(agent)} role missing from orchestrator-contract.json")
        _check_agent_trailer_examples(_rel(agent), expected, text, roles, errors)
        if expected in info:
            lowered = text.lower()
            for phrase in ["mark `done`", "mark done", "moves the slice to", "moves ready_for_close"]:
                loc = lowered.find(phrase)
                if loc >= 0 and "do not" not in lowered[max(0, loc - 60): loc + 80] and "never" not in lowered[max(0, loc - 60): loc + 80]:
                    warnings.append(f"{_rel(agent)} may imply lifecycle mutation: {phrase}")
        if expected in info and expected in (sm.get("transitions") or {}):
            errors.append(f"{_rel(agent)} is info-only but has state-machine transitions")
        if expected in mutating and expected not in (sm.get("transitions") or {}):
            errors.append(f"{_rel(agent)} mutates lifecycle but has no state-machine transition set")

    agent_names = {p.stem for p in agent_dir.glob("*.md")}
    for role in roles:
        if role not in agent_names:
            errors.append(f"orchestrator-contract role {role} has no .claude/agents/{role}.md")

    manual_runtime_skill_names = {"audit-runtime-surface", "auto-verify-slice", "bootstrap-registry", "check-blueprint-lossless-flow", "check-git-pr-flow", "check-gold-blueprint", "check-memory-yaml", "check-parallel-locks", "check-skills-runtime", "check-unix-agent-runtime", "check-verify-surface", "closer", "compile-blueprint", "doctor", "next-slice", "next-wave", "phase-gate", "promote-followup", "register-followup", "revise-slice", "slice-maintain",
        "compact-agent-memory", "verify-journey", "verify-slice"}
    skill_dir = root / ".claude" / "skills"
    for skill in sorted(skill_dir.glob("*/SKILL.md")):
        text = _read(skill)
        fm = _frontmatter(text)
        if not fm:
            errors.append(f"{_rel(skill)} missing YAML frontmatter")
        elif fm.get("__frontmatter_error__"):
            errors.append(f"{_rel(skill)} invalid YAML frontmatter: {fm.get('__frontmatter_error__')}")
        else:
            if not fm.get("description"):
                errors.append(f"{_rel(skill)} missing description frontmatter")
            if "disable-model-invocation" not in fm:
                errors.append(f"{_rel(skill)} missing disable-model-invocation frontmatter")
            elif skill.parent.name in manual_runtime_skill_names and fm.get("disable-model-invocation") is not False:
                errors.append(f"{_rel(skill)} must set disable-model-invocation: false for user-timed manual workflow safety")
            if fm.get("user-invocable") is not True and skill.parent.name in manual_runtime_skill_names:
                errors.append(f"{_rel(skill)} must set user-invocable: true")
        for token in ["BLUEPRINT.md", "orchestrator-input.json", "registry.json", "resolved_specs"]:
            if token not in text:
                errors.append(f"{_rel(skill)} missing source-chain token {token}")

    command_dir = root / ".claude" / ("com" + "mands")
    if command_dir.exists() and list(command_dir.glob("*.md")):
        errors.append("project command directory must be empty or absent; project slash entrypoints are skills runtime")

    # Skills and docs should not reference missing scripts.
    for base in [root / ".claude" / "skills", root / ".claude"]:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            text = _read(path)
            for ref in _script_refs(text):
                script = root / ref.lstrip("./")
                if not script.exists():
                    errors.append(f"{_rel(path)} references missing {ref}")

    # Scripts and bin wrappers are part of the public surface: keep them executable/readable and syntactically discoverable.
    for script in sorted((root / "scripts").glob("*.sh")):
        head = _read(script).splitlines()[:1]
        if not head or not head[0].startswith("#!"):
            errors.append(f"{_rel(script)} missing shebang")
    for py in sorted((root / ".claude" / "bin").glob("*.py")):
        if not _read(py).strip():
            errors.append(f"{_rel(py)} is empty")


    # Skills runtime runtime and macOS exact-case guard.
    skills_runtime_script = root / "scripts" / "check-skills-runtime.sh"
    if not skills_runtime_script.exists():
        errors.append("missing scripts/check-skills-runtime.sh")
    else:
        for rel in [
            ".claude/skills/next-wave/SKILL.md",
            ".claude/skills/next-slice/SKILL.md",
            ".claude/skills/verify-slice/SKILL.md",
            ".claude/skills/closer/SKILL.md",
            ".claude/rules/10-macos-case-sensitive-and-mcp.md",
        ]:
            txt2 = _read(root / rel)
            for token in ["macOS", "MCP", "case"]:
                if token not in txt2:
                    errors.append(f"{rel} missing {token} exact-case portability guidance")

    unix_env = root / "scripts" / "unix-runtime-env.sh"
    if not unix_env.exists():
        errors.append("missing scripts/unix-runtime-env.sh for macOS/Linux PATH bootstrap")
    else:
        unix_text = _read(unix_env)
        for token in ["$HOME/.rd/bin", "/opt/homebrew/bin", "/usr/local/bin", "CLAUDE_SPAWN_BUDGET"]:
            if token not in unix_text:
                errors.append(f"scripts/unix-runtime-env.sh missing {token}")
    for scan_base in [root / "scripts", root / ".claude" / "bin", root / "orchestrator"]:
        for scan_path in scan_base.rglob("*") if scan_base.exists() else []:
            if scan_path.is_file() and scan_path.suffix == ".sh":
                txt_scan = _read(scan_path)
                if re.search(r"(^|[^A-Za-z0-9_])timeout\\s+", txt_scan):
                    errors.append(f"GNU timeout command is not macOS portable in {_rel(scan_path)}")
    _check_settings(root, errors, warnings)
    _check_workflows(root, errors, warnings)

    result = {
        "ok": not errors,
        "agents": len(agent_names),
        "contract_roles": len(roles),
        "skills": len(list(skill_dir.glob("*/SKILL.md"))),
        "commands": len(list(command_dir.glob("*.md"))),
        "ci_workflow": (root / ".github" / "workflows" / "ci.yml").exists(),
        "mutating_roles": sorted(mutating),
        "info_only_roles": sorted(info),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
