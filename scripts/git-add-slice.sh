#!/usr/bin/env bash
set -euo pipefail
# ORQ_HELP_GUARD
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: git-add-slice.sh [--dry-run] <TASK_ID>"
  exit 0
fi
DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi
TASK_ID="${1:-}"
if [ -z "$TASK_ID" ]; then echo "ERROR: missing TASK_ID" >&2; exit 2; fi
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORKSPACE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
resolve_canonical_root() {
  local common_dir
  if git -C "$WORKSPACE_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    common_dir="$(git -C "$WORKSPACE_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
      (cd "$(dirname "$common_dir")" && pwd -P)
      return 0
    fi
  fi
  printf '%s\n' "$SCRIPT_ROOT"
}
ROOT_CANDIDATE="${CLAUDE_ORCHESTRATOR_ROOT:-$(resolve_canonical_root)}"
ROOT="$ROOT_CANDIDATE"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$ROOT_CANDIDATE")"
fi
REG="$ROOT/orchestrator-state/tasks/registry.json"
cd "$WORKSPACE_ROOT"
if [ ! -f "$REG" ]; then echo "ERROR: registry not found: $REG" >&2; exit 2; fi
paths="$(python3 - "$REG" "$TASK_ID" "$DRY_RUN" <<'PY'
import json, sys, datetime
from pathlib import Path
reg=Path(sys.argv[1]); tid=sys.argv[2]; dry_run=(sys.argv[3] == "1")
data=json.load(open(reg));
task=next((t for t in data.get('tasks',[]) if str(t.get('id'))==tid), None)
if not task: raise SystemExit(3)
state_root=reg.parents[1]
# Canonical DAG/pr-flow behavior: a slice PR carries a durable lifecycle event
# scoped to TASK_ID. The mutable registry remains runtime-local, but after
# squash/merge/reset the canonical checkout can rehydrate task state from
# orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json. For a closer from
# verified_pending_close, target_status=done is safe because the event reaches
# main only if the PR is actually merged.
status=str(task.get('status') or '')
target='done' if status == 'verified_pending_close' else status
event={
  'schema_version':'current',
  'kind':'orchestrator.lifecycle_event',
  'task_id':tid,
  'source':'git-add-slice',
  'event_type':'durable_close_signal' if target == 'done' else 'durable_task_state',
  'current_status':status,
  'target_status':target,
  'phase_id':task.get('phase_id'),
  'title':task.get('title'),
  'git_workflow_safe_to_apply_after_merge': True,
  'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
lf=state_root/'tasks'/'lifecycle-events'/f'{tid}.json'
lf.parent.mkdir(parents=True, exist_ok=True)
if not dry_run:
    lf.write_text(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
for p in task.get('write_set') or []: print(str(p))
for p in [f'orchestrator-state/tasks/handoffs/{tid}.md', f'orchestrator-state/tasks/handoffs/{tid}.yaml', f'orchestrator-state/tasks/evidence/{tid}', f'orchestrator-state/tasks/reports/{tid}.md', f'orchestrator-state/tasks/task-packs/{tid}.md', f'orchestrator-state/tasks/task-packs/{tid}.json', f'orchestrator-state/tasks/lifecycle-events/{tid}.json']:
    print(p)
PY
)" || { echo "ERROR: task not found in registry: $TASK_ID" >&2; exit 3; }
prepare_runtime_artifact_for_stage() {
  local rel="$1" src dst parent
  case "$rel" in
    orchestrator-state/*) ;;
    *) return 0 ;;
  esac
  [ "$WORKSPACE_ROOT" = "$ROOT" ] && return 0
  if [ -L "$WORKSPACE_ROOT/orchestrator-state" ]; then
    echo "ERROR: $WORKSPACE_ROOT/orchestrator-state is a symlink; Git cannot stage files through it." >&2
    echo "Run: bash $ROOT/scripts/repair-worktree-state.sh --apply $WORKSPACE_ROOT" >&2
    return 4
  fi
  src="$ROOT/$rel"
  dst="$WORKSPACE_ROOT/$rel"
  [ -e "$src" ] || return 0
  parent="$(dirname "$dst")"
  mkdir -p "$parent"
  rm -rf "$dst"
  if [ -d "$src" ]; then
    cp -R "$src" "$dst"
  else
    cp -p "$src" "$dst"
  fi
}

added=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$p" in db:*|api:*|config:*|core:*|worker:*|integration:*|security:*|broker:*|ui:*) continue ;; esac
  prepare_runtime_artifact_for_stage "$p"
  if compgen -G "$p" >/dev/null 2>&1; then
    for m in $p; do
      [ -e "$m" ] || continue
      if [ "$DRY_RUN" -eq 1 ]; then echo "WOULD_STAGE: $m"; else git add -f -- "$m"; echo "STAGED: $m"; fi
      added=$((added+1))
    done
  elif [ -e "$p" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then echo "WOULD_STAGE: $p"; else git add -f -- "$p"; echo "STAGED: $p"; fi
    added=$((added+1))
  fi
done <<EOF_PATHS
$paths
EOF_PATHS
echo "GIT_ADD_SLICE_READY: yes"
echo "STAGED_COUNT: $added"
