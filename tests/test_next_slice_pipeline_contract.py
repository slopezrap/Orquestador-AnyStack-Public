from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_TERMS = ["planner", "developer", "official-docs-researcher", "validator", "tester", "debugger"]
SURFACES = [
    ".claude/agents/main-orchestrator.md",
    ".claude/rules/01-non-negotiables.md",
    ".claude/rules/02-phase-execution.md",
    ".claude/CLAUDE.md",
    ".claude/skills/next-slice/SKILL.md",
]


def test_next_slice_pipeline_is_declared_on_all_operator_surfaces() -> None:
    for rel in SURFACES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        missing = [term for term in PIPELINE_TERMS if term not in text]
        assert not missing, f"{rel} missing pipeline terms {missing}"
    next_slice = (ROOT / ".claude/skills/next-slice/SKILL.md").read_text(encoding="utf-8")
    assert "developer ∥ official-docs-researcher?" in next_slice
    assert "validator ∥ tester" in next_slice
    assert "obligatorio" in next_slice.lower() or "mandatory" in next_slice.lower()


def test_contract_makes_parallel_pair_machine_safe() -> None:
    contract = json.loads((ROOT / ".claude/orchestrator-contract.json").read_text(encoding="utf-8"))
    roles = contract["trailer_schema"]["roles"]
    assert roles["validator"].get("info_only") is True
    assert roles["official-docs-researcher"].get("info_only") is True
    assert roles["tester"].get("mutates_registry_lifecycle") is True
    pipeline = contract.get("runtime_contract", {}).get("next_slice_pipeline", {})
    assert "developer" in pipeline.get("chain", "")
    assert "official-docs-researcher" in pipeline.get("chain", "")
    assert "validator" in pipeline.get("chain", "")
    assert "tester" in pipeline.get("chain", "")
    assert pipeline.get("debugger_max_cycles") == 4
    assert "4 cycles" in pipeline.get("debugger_loop", "") or "maximum 4" in pipeline.get("debugger_loop", "")
    assert "70" in contract.get("runtime_contract", {}).get("spawn_budget", "")
