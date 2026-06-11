#!/usr/bin/env bash
set -euo pipefail
# Resolve from the script location, not from a possibly stale Claude task/worktree environment.
# This makes the end-to-end simulation safe after switching terminals or slices.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
# Keep this deterministic smoke flow fast; runtime/user flows still compact through next-wave, PreCompact and /slice-maintain by default.
export CLAUDE_AUTO_COMPACT_AGENT_MEMORY="${CLAUDE_AUTO_COMPACT_AGENT_MEMORY:-0}"
RUN_TMP="$(mktemp -d "${TMPDIR:-/tmp}/orq-sim.XXXXXX")"
trap 'rm -rf "$RUN_TMP"' EXIT

echo "[simulate] reset-state"
./scripts/reset-state.sh >/dev/null
echo "[simulate] compile-blueprint"
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md >"$RUN_TMP/compile.out"
echo "[simulate] bootstrap-registry"
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json >"$RUN_TMP/bootstrap.out"
echo "[simulate] check-gold-blueprint"
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md >"$RUN_TMP/gold.out"
echo "[simulate] check-blueprint-machine-contract"
./scripts/check-blueprint-machine-contract.sh >"$RUN_TMP/machine.out"
echo "[simulate] check-task-dag"
./scripts/check-task-dag.sh >"$RUN_TMP/dag.out"
echo "[simulate] check-parallel-locks"
./scripts/check-parallel-locks.sh >"$RUN_TMP/parallel.out"
echo "[simulate] check-verify-surface"
./scripts/check-verify-surface.sh >"$RUN_TMP/verify_surface.out"
echo "[simulate] check-handoff-contract static"
./scripts/check-handoff-contract.sh >"$RUN_TMP/handoff_static.out"
echo "[simulate] next-slice"
./scripts/next-slice.sh SLICE-F0-001 >"$RUN_TMP/next_slice.out"
echo "[simulate] slice-maintain"
./scripts/slice-maintain.sh SLICE-F0-001 | tee "$RUN_TMP/slice_maintain.out"
echo "[simulate] verify-slice contract prep"
./scripts/init-verify-slice-handoff.sh SLICE-F0-001 >"$RUN_TMP/verify_slice_handoff.out"
echo "[simulate] trailer-smoke"
env -i PATH="$PATH" HOME="${HOME:-}" CLAUDE_ORCHESTRATOR_ROOT="$ROOT" PYTHONPATH="$ROOT" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -S scripts/smoke-trailers-current-state.py >"$RUN_TMP/trailer.out"
echo "[simulate] check-handoff-contract task"
./scripts/check-handoff-contract.sh SLICE-F0-001 --require-developer --require-tester --require-verify-slice --require-closer >"$RUN_TMP/handoff_task.out"
echo "[simulate] verify active blueprint origin"
python3 - <<'PY' >"$RUN_TMP/origin.out"
import json
from pathlib import Path
compiled=json.loads(Path('orchestrator-state/compiled/orchestrator-input.json').read_text())
path=compiled.get('compiler',{}).get('blueprint_path')
ok=path == 'inputs/BLUEPRINT.md'
print(json.dumps({'ok': ok, 'blueprint_path': path, 'project': compiled.get('project',{}).get('name')}))
raise SystemExit(0 if ok else 2)
PY
echo "[simulate] check-claude-adapter"
./scripts/check-claude-adapter.sh >"$RUN_TMP/adapter.out"
echo "[simulate] check-memory-yaml"
./scripts/check-memory-yaml.sh >"$RUN_TMP/memory.out"
echo "[simulate] summarize"
cat <<'JSON'
{
  "ok": true,
  "simulation": "blueprint-to-claude-flow",
  "blueprint": "inputs/BLUEPRINT.md",
  "checks": [
    "check-gold-blueprint",
    "check-blueprint-machine-contract",
    "check-task-dag",
    "check-parallel-locks",
    "check-verify-surface",
    "check-handoff-contract static",
    "next-slice",
    "slice-maintain",
    "verify-slice contract prep",
    "trailer-smoke",
    "check-handoff-contract task",
    "check-claude-adapter",
    "check-memory-yaml"
  ]
}
JSON
