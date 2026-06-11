#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  cat <<'HELP'
Usage: scripts/run-golden-e2e.sh

Compiles inputs/BLUEPRINT.md, bootstraps registry, checks the DAG and prints the first ready wave.
HELP
  exit 0
fi
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/orq-golden.XXXXXX")"
RUN_TMP="$(mktemp -d "${TMPDIR:-/tmp}/orq-golden-out.XXXXXX")"
trap 'rm -rf "$TMP_DIR" "$RUN_TMP"' EXIT
./scripts/reset-state.sh >/dev/null
./scripts/python-safe.sh -m orchestrator.compiler.compile_blueprint inputs/BLUEPRINT.md \
 --out "$TMP_DIR/orchestrator-input.json" \
 --source-map "$TMP_DIR/source-map.json" \
 --lock "$TMP_DIR/orchestrator-input.lock.json" \
 --report "$TMP_DIR/compile-report.md" >"$RUN_TMP/compile.out"
./scripts/python-safe.sh -m orchestrator.bootstrap.bootstrap_registry "$TMP_DIR/orchestrator-input.json" >"$RUN_TMP/bootstrap.out"
mkdir -p orchestrator-state/compiled
cp "$TMP_DIR/orchestrator-input.json" orchestrator-state/compiled/orchestrator-input.json
cp "$TMP_DIR/source-map.json" orchestrator-state/compiled/source-map.json
cp "$TMP_DIR/orchestrator-input.lock.json" orchestrator-state/compiled/orchestrator-input.lock.json
cp "$TMP_DIR/compile-report.md" orchestrator-state/compiled/compile-report.md
./scripts/check-task-dag.sh >"$RUN_TMP/dag.out"
./scripts/check-parallel-locks.sh >"$RUN_TMP/parallel.out"
CLAUDE_AUTO_COMPACT_AGENT_MEMORY=0 CLAUDE_SKIP_MAIN_SYNC_BEFORE_WAVE=1 CLAUDE_DISABLE_ZOMBIE_WORKTREE_CLEANUP=1 CLAUDE_CLEAN_MERGED_PR_BRANCHES=0 ./scripts/next-wave.sh --limit 5 --json >"$RUN_TMP/wave.json"
WAVE_JSON="$RUN_TMP/wave.json" python3 - <<'PY'
import json, os
from pathlib import Path
compiled=json.loads(Path('orchestrator-state/compiled/orchestrator-input.json').read_text())
registry=json.loads(Path('orchestrator-state/tasks/registry.json').read_text())
wave=json.loads(Path(os.environ['WAVE_JSON']).read_text())
print(json.dumps({
  'ok': True,
  'compiled_project': compiled.get('project', {}).get('name'),
  'compiled_slices': len(compiled.get('slices', [])),
  'registry_tasks': len(registry.get('tasks', [])),
  'ready': [x['id'] for x in wave.get('ready', [])],
  'parallelism': wave.get('parallelism', {})
}, indent=2, ensure_ascii=False))
PY
