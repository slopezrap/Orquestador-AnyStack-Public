from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


def test_skills_runtime_checker_passes() -> None:
    proc = run(["bash", "scripts/check-skills-runtime.sh"])
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["commands_total"] == 0


def test_single_skill_surface_and_core_skills_are_rich() -> None:
    command_dir = ROOT / ".claude" / "commands"
    assert not command_dir.exists() or not list(command_dir.glob("*.md"))
    for name in ["next-wave", "next-slice", "verify-slice", "closer", "compile-blueprint", "bootstrap-registry"]:
        text = (ROOT / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "user-invocable: true" in text
        assert "disable-model-invocation: false" in text
        assert "inputs/BLUEPRINT.md" in text
        assert "orchestrator-input.json" in text
        assert "registry.json" in text
        assert (".claude/" + "commands") not in text
    assert "chrome-devtools" in (ROOT / ".claude" / "skills" / "verify-slice" / "SKILL.md").read_text(encoding="utf-8")
    assert "CANONICAL_MAIN_SYNCED" in (ROOT / ".claude" / "skills" / "closer" / "SKILL.md").read_text(encoding="utf-8")


def test_final_runtime_rule_names_are_canonical() -> None:
    rule_names = {path.name for path in (ROOT / ".claude" / "rules").glob("*.md")}
    assert "07-skills-runtime.md" in rule_names
    assert not any(re.search(r"v\d", name.lower()) for name in rule_names)
    assert not any(token in name.lower() for name in rule_names for token in ["dual-runtime-rule", "noncanonical-runtime-rule", "archived-runtime-rule"])
