from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "SLICE-F0-001"
BLUEPRINT = ROOT / "examples/gold/BLUEPRINT.md"
EXPECTED_WRITE_SET = [
    "orchestrator-state/**",
    "orchestrator/rules/**",
    ".claude/settings.json",
    ".claude/orchestrator-contract.json",
]
EXPECTED_CONFLICT_GROUPS = ["registry", "runtime-state", "memory-yaml"]
EXPECTED_CLOSES: list[str] = []


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _load() -> tuple[dict, dict, dict]:
    _run(["bash", "scripts/reset-state.sh"])
    _run(["bash", "scripts/compile-blueprint.sh", str(BLUEPRINT)])
    _run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])

    compiled = json.loads((ROOT / "orchestrator-state/compiled/orchestrator-input.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "orchestrator-state/tasks/registry.json").read_text(encoding="utf-8"))
    pack = json.loads((ROOT / "orchestrator-state/tasks/task-packs" / f"{TASK_ID}.json").read_text(encoding="utf-8"))
    compiled_slice = {s["id"]: s for s in compiled["slices"]}[TASK_ID]
    registry_task = {t["id"]: t for t in registry["tasks"]}[TASK_ID]
    return compiled_slice, registry_task, pack


def test_authored_scope_and_closure_fields_survive_compile_bootstrap() -> None:
    for obj in _load():
        assert obj.get("write_set") == EXPECTED_WRITE_SET
        assert (obj.get("conflict_groups") or obj.get("conflict_group")) == EXPECTED_CONFLICT_GROUPS
        assert obj.get("closes_journeys") == EXPECTED_CLOSES
        locks = obj.get("locks") or {}
        if locks:
            assert locks.get("write_set") == EXPECTED_WRITE_SET
            assert locks.get("conflict_groups") == EXPECTED_CONFLICT_GROUPS
