from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(ROOT)
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return env


def test_root_blueprint_is_gold_contract():
    subprocess.run(["bash", "scripts/check-gold-blueprint.sh", "inputs/BLUEPRINT.md"], cwd=ROOT, env=_env(), check=True)


def test_example_gold_blueprint_is_gold_contract():
    subprocess.run(["bash", "scripts/check-gold-blueprint.sh", "examples/gold/BLUEPRINT.md"], cwd=ROOT, env=_env(), check=True)


def test_smoke_template_contains_required_logic_kinds():
    text = (ROOT / "docs/templates/blueprint-smoke/BLUEPRINT.template.md").read_text(encoding="utf-8")
    for token in [
        "kind: auxiliary.arc42",
        "kind: logic.domain",
        "kind: logic.application",
        "kind: logic.journey",
        "kind: logic.permission",
        "kind: logic.state",
        "kind: logic.error",
        "kind: logic.integration",
        "kind: logic.ui",
        "kind: registry.slices",
    ]:
        assert token in text
    assert "dependency_rationale" in text
    assert "depends_on_rationale" in text
    assert "smoke blueprint" in text.lower() or "production contract fixture" in text.lower()
