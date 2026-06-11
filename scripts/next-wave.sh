#!/usr/bin/env bash
set -euo pipefail
# Blueprint-first next-wave wrapper, preserving DAG housekeeping semantics.
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
resolve_canonical_root() {
  local common_dir
  if git -C "$SCRIPT_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    common_dir="$(git -C "$SCRIPT_ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
      (cd "$(dirname "$common_dir")" && pwd -P)
      return 0
    fi
  fi
  printf '%s\n' "$SCRIPT_ROOT"
}
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: next-wave.sh [--phase PHASE] [--limit N] [--json] [--no-promote]"
  exit 0
fi
ROOT="$(resolve_canonical_root)"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"
export CLAUDE_ORCHESTRATOR_ROOT="$ROOT"

# 1) Compact per-agent runtime memory before computing a new frontier. This is
# local runtime housekeeping; archives stay under gitignored orchestrator-state.
if [ "${CLAUDE_AUTO_COMPACT_AGENT_MEMORY:-1}" != "0" ] && [ -f "$ROOT/scripts/compact-agent-memory.py" ]; then
  threshold="${CLAUDE_AGENT_MEMORY_COMPACT_THRESHOLD_LINES:-250}"
  if ! python3 -B -S "$ROOT/scripts/compact-agent-memory.py" --all --apply --threshold-lines "$threshold" --quiet >/dev/null 2>&1; then
    echo "WARN: agent memory auto-compaction incomplete; run: python3 -B -S scripts/compact-agent-memory.py --all --apply --threshold-lines $threshold" >&2
  fi
fi

# 2) Keep canonical main aligned before listing work, unless explicitly skipped.
if [ "${CLAUDE_SKIP_MAIN_SYNC_BEFORE_WAVE:-0}" != "1" ] && [ -f "$ROOT/scripts/sync-main-before-wave.sh" ]; then
  sync_log="${TMPDIR:-/tmp}/orq-next-wave-sync.$$"
  sync_args=(--apply)
  [ "${CLAUDE_STRICT_MAIN_SYNC_BEFORE_WAVE:-0}" = "1" ] && sync_args+=(--strict)
  if ! bash "$ROOT/scripts/sync-main-before-wave.sh" "${sync_args[@]}" >"$sync_log" 2>&1; then
    if [ "${CLAUDE_STRICT_MAIN_SYNC_BEFORE_WAVE:-0}" = "1" ]; then
      cat "$sync_log" >&2 || true
      rm -f "$sync_log"
      echo "ERROR: canonical main sync failed before next-wave in strict mode; run: bash scripts/sync-main-before-wave.sh --apply --strict" >&2
      exit 3
    fi
    echo "WARN: canonical main sync did not complete before next-wave; continuing with current checkout." >&2
    sed 's/^/WARN_SYNC_MAIN: /' "$sync_log" >&2 || true
    echo "WARN: set CLAUDE_STRICT_MAIN_SYNC_BEFORE_WAVE=1 to make this fatal." >&2
  fi
  rm -f "$sync_log"
fi

# 3) Safe local cleanup/sync before frontier computation. These helpers are
# intentionally non-destructive; dirty/active worktrees are never discarded.
if [ -f "$ROOT/scripts/cleanup-deferred-worktrees.sh" ]; then
  bash "$ROOT/scripts/cleanup-deferred-worktrees.sh" --apply --quiet >/dev/null 2>&1 || echo "WARN: deferred worktree cleanup incomplete; run: bash scripts/cleanup-deferred-worktrees.sh --apply" >&2
fi
if [ -f "$ROOT/scripts/sync-lifecycle-events.sh" ]; then
  bash "$ROOT/scripts/sync-lifecycle-events.sh" --apply >/dev/null 2>&1 || true
fi
if [ -f "$ROOT/scripts/cleanup-closed-task-worktrees.sh" ]; then
  bash "$ROOT/scripts/cleanup-closed-task-worktrees.sh" --apply --quiet >/dev/null 2>&1 || echo "WARN: closed task worktree cleanup incomplete; run: bash scripts/cleanup-closed-task-worktrees.sh --apply --verbose" >&2
fi
if [ "${CLAUDE_DISABLE_ZOMBIE_WORKTREE_CLEANUP:-0}" != "1" ] && [ -f "$ROOT/scripts/cleanup-zombie-task-worktrees.sh" ]; then
  bash "$ROOT/scripts/cleanup-zombie-task-worktrees.sh" --apply --quiet >/dev/null 2>&1 || echo "WARN: zombie task worktree cleanup incomplete; run: bash scripts/cleanup-zombie-task-worktrees.sh --apply --verbose" >&2
fi
if [ "${CLAUDE_CLEAN_MERGED_PR_BRANCHES:-1}" != "0" ] && [ "${CLAUDE_DISABLE_REMOTE_BRANCH_CLEANUP:-0}" != "1" ] && [ "${CLAUDE_DISABLE_REMOTE_PR_BRANCH_CLEANUP:-0}" != "1" ] && [ -f "$ROOT/scripts/cleanup-merged-pr-branches.sh" ]; then
  bash "$ROOT/scripts/cleanup-merged-pr-branches.sh" --apply --quiet >/dev/null 2>&1 || echo "WARN: merged PR remote branch cleanup incomplete; run: bash scripts/cleanup-merged-pr-branches.sh --apply --verbose" >&2
fi

exec "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.next_wave "$@"
