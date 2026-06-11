#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/repair-worktree-state.sh [--check|--provision|--apply] [WORKTREE]

Ensures a linked task worktree does not carry a second mutable orchestrator-state.

Modes:
  --check      report topology only; non-zero on split-brain risk (default)
  --provision create no local state; fail if a divergent local state exists
  --apply      archive a local divergent orchestrator-state and leave the worktree
               without local scheduler state

The scheduler truth is the canonical repository root returned by git's
shared .git directory. Handoffs/evidence should be written to that canonical
root while a slice is active; git-add-slice mirrors the selected evidence into
the task branch only during closer/transport.
USAGE
}

MODE="check"
case "${1:-}" in
  --check) MODE="check"; shift ;;
  --provision) MODE="provision"; shift ;;
  --apply) MODE="apply"; shift ;;
  --help|-h) usage; exit 0 ;;
esac

WORKTREE="${1:-$(pwd -P)}"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
RESOLVER="$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh"
if [ -x "$RESOLVER" ]; then
  ROOT="$(bash "$RESOLVER" "$WORKTREE")"
else
  ROOT="$SCRIPT_ROOT"
fi

realpath_py() {
  python3 - "$1" <<'PY'
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}

is_allowed_local_commit_artifact() {
  case "$1" in
    memory/blueprint-blocks.json|\
    memory/blueprint-lossless.json|\
    memory/blueprint-manifest.json|\
    memory/blueprint-sections.json|\
    memory/execution-graph.json|\
    .gitkeep|*/.gitkeep)
      return 0
      ;;
  esac
  return 1
}

abs_dir() {
  if [ -d "$1" ]; then (cd "$1" && pwd -P); else printf '%s\n' "$1"; fi
}

WORKTREE="$(abs_dir "$WORKTREE")"
ROOT="$(abs_dir "$ROOT")"
CANON_STATE="$ROOT/orchestrator-state"
LOCAL_STATE="$WORKTREE/orchestrator-state"
mkdir -p "$CANON_STATE"

if [ "$WORKTREE" = "$ROOT" ]; then
  echo "WORKTREE_STATE_READY: yes"
  echo "Reason: canonical root; no linked worktree state repair needed"
  echo "CanonicalRoot: $ROOT"
  exit 0
fi

if [ -L "$LOCAL_STATE" ]; then
  target="$(realpath_py "$LOCAL_STATE")"
  if [ "$MODE" = "apply" ]; then
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    archive="$WORKTREE/orchestrator-state.symlink.$ts"
    rm "$LOCAL_STATE"
    mkdir -p "$archive"
    cat > "$archive/README.symlink.txt" <<EOF_SYMLINK
This worktree contained an orchestrator-state symlink.

Symlink target:
$target

Linked task worktrees must not contain local orchestrator-state symlinks because
Git staging, hooks and relative writes can diverge or traverse scheduler state.
The canonical scheduler state is:
$CANON_STATE
EOF_SYMLINK
    echo "WORKTREE_STATE_ARCHIVED: $archive"
  else
    echo "WORKTREE_STATE_READY: no"
    echo "SPLIT_BRAIN_RISK: linked worktree must not contain orchestrator-state symlinks (target: $target)"
    echo "Repair: bash $ROOT/scripts/repair-worktree-state.sh --apply $WORKTREE"
    exit 4
  fi
fi

if [ ! -e "$LOCAL_STATE" ]; then
  echo "WORKTREE_STATE_READY: yes"
  echo "Topology: no_local_orchestrator_state"
  echo "CanonicalRoot: $ROOT"
  echo "Worktree: $WORKTREE"
  exit 0
fi

if [ -d "$LOCAL_STATE" ]; then
  file_list="$(mktemp "${TMPDIR:-/tmp}/orchestrator-worktree-state.XXXXXX")"
  find "$LOCAL_STATE" -type f ! -name '.DS_Store' ! -name '*.lock' ! -name '*.tmp' > "$file_list"
  file_count="$(wc -l < "$file_list" | tr -d ' ')"
  core_count="$({ grep -E '/(compiled/|tasks/(registry|runtime-state|task-dag)\.(json|yaml)$|tasks/(task-index|handoff-index|lifecycle-events)\.yaml$|tasks/task-packs/|tasks/slices/)' "$file_list" || true; } | wc -l | tr -d ' ')"
  disallowed_count=0
  disallowed_examples=""
  while IFS= read -r local_file; do
    rel="${local_file#$LOCAL_STATE/}"
    if ! is_allowed_local_commit_artifact "$rel"; then
      disallowed_count=$((disallowed_count + 1))
      if [ -z "$disallowed_examples" ]; then
        disallowed_examples="$rel"
      elif [ "$disallowed_count" -le 5 ]; then
        disallowed_examples="$disallowed_examples, $rel"
      fi
    fi
  done < "$file_list"
  rm -f "$file_list"
  if [ "${file_count:-0}" = "0" ]; then
    if [ "$MODE" = "provision" ] || [ "$MODE" = "apply" ]; then
      rm -rf "$LOCAL_STATE"
      echo "WORKTREE_STATE_READY: yes"
      echo "Topology: removed_empty_local_orchestrator_state"
      echo "CanonicalRoot: $ROOT"
      echo "Worktree: $WORKTREE"
      exit 0
    fi
    echo "WORKTREE_STATE_READY: yes"
    echo "Topology: empty_local_orchestrator_state_scaffold"
    echo "CanonicalRoot: $ROOT"
    echo "Worktree: $WORKTREE"
    exit 0
  fi
  if [ "${core_count:-0}" = "0" ] && [ "${disallowed_count:-0}" = "0" ]; then
    echo "WORKTREE_STATE_READY: yes"
    echo "Topology: local_commit_artifacts_only"
    echo "LocalAllowedArtifacts: $file_count"
    echo "AllowedClass: tracked_blueprint_memory_json_mirrors"
    echo "CanonicalRoot: $ROOT"
    echo "Worktree: $WORKTREE"
    exit 0
  fi
  if [ "$MODE" = "apply" ]; then
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    archive="$WORKTREE/orchestrator-state.split-brain.$ts"
    mv "$LOCAL_STATE" "$archive"
    cat > "$archive/README.split-brain.txt" <<EOF_ARCHIVE
This directory was archived by repair-worktree-state.sh because a linked task
worktree carried local generated orchestrator state outside the allowed tracked compatibility
blueprint memory JSON mirrors. The canonical scheduler state is:

$CANON_STATE

Review this archive manually if you need to recover local evidence/handoff prose.
Do not restore registry.json, runtime-state.json, task-dag.json, task-packs,
handoffs, evidence, reports, compiled output or other generated runtime state
into the worktree while a slice is active.
EOF_ARCHIVE
    echo "WORKTREE_STATE_READY: yes"
    echo "WORKTREE_STATE_ARCHIVED: $archive"
    echo "Topology: local_split_brain_state_archived"
    echo "CanonicalRoot: $ROOT"
    echo "Worktree: $WORKTREE"
    exit 0
  fi
  if [ "${core_count:-0}" = "0" ]; then
    echo "WORKTREE_STATE_READY: no"
    echo "SPLIT_BRAIN_RISK: linked worktree has local orchestrator-state files outside the allowed tracked compatibility blueprint memory JSON mirrors"
    echo "LocalFiles: $file_count"
    echo "DisallowedFiles: $disallowed_count"
    [ -z "$disallowed_examples" ] || echo "Examples: $disallowed_examples"
    echo "LocalState: $LOCAL_STATE"
    echo "CanonicalState: $CANON_STATE"
    echo "Repair: bash $ROOT/scripts/repair-worktree-state.sh --apply $WORKTREE"
    exit 4
  fi
  echo "WORKTREE_STATE_READY: no"
  echo "SPLIT_BRAIN_DETECTED: local worktree has $core_count core scheduler state file(s) and $file_count local orchestrator-state file(s)"
  echo "LocalState: $LOCAL_STATE"
  echo "CanonicalState: $CANON_STATE"
  echo "Repair: bash $ROOT/scripts/repair-worktree-state.sh --apply $WORKTREE"
  exit 4
fi

echo "WORKTREE_STATE_READY: no"
echo "SPLIT_BRAIN_RISK: unexpected orchestrator-state path type at $LOCAL_STATE"
echo "Repair: bash $ROOT/scripts/repair-worktree-state.sh --apply $WORKTREE"
exit 4
