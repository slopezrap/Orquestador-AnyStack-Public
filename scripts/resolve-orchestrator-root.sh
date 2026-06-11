#!/usr/bin/env bash
set -euo pipefail

# Print the canonical orchestrator root. In a git linked worktree this is the
# main repository root that owns .git and the shared scheduler state, not the
# per-task worktree. Without git, fall back to the supplied script root/current
# directory.

candidate="${1:-}"
if [ -z "$candidate" ]; then
  if [ -n "${CLAUDE_ORCHESTRATOR_ROOT:-}" ] && [ -d "$CLAUDE_ORCHESTRATOR_ROOT" ]; then
    candidate="$CLAUDE_ORCHESTRATOR_ROOT"
  else
    candidate="$(pwd -P)"
  fi
fi

has_markers() {
  [ -n "${1:-}" ] \
    && [ -d "$1" ] \
    && [ -f "$1/orchestrator/rules/state-machine.yaml" ] \
    && [ -f "$1/.claude/orchestrator-contract.json" ]
}

abs_dir() {
  [ -n "${1:-}" ] && [ -d "$1" ] || return 1
  (cd "$1" && pwd -P)
}

canonical_git_root() {
  local context="${1:-}" common_dir top root
  [ -n "$context" ] && [ -d "$context" ] || return 1
  command -v git >/dev/null 2>&1 || return 1
  git -C "$context" rev-parse --git-dir >/dev/null 2>&1 || return 1
  common_dir="$(git -C "$context" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [ -n "$common_dir" ] && [ "$(basename "$common_dir")" = ".git" ] && [ -d "$(dirname "$common_dir")" ]; then
    root="$(dirname "$common_dir")"
    if has_markers "$root"; then
      abs_dir "$root"
      return 0
    fi
  fi
  top="$(git -C "$context" rev-parse --show-toplevel 2>/dev/null || true)"
  if has_markers "$top"; then
    abs_dir "$top"
    return 0
  fi
  return 1
}

if root="$(canonical_git_root "$candidate")"; then
  printf '%s\n' "$root"
  exit 0
fi

if [ -n "${CLAUDE_ORCHESTRATOR_ROOT:-}" ] && has_markers "$CLAUDE_ORCHESTRATOR_ROOT"; then
  abs_dir "$CLAUDE_ORCHESTRATOR_ROOT"
  exit 0
fi

cur="$(abs_dir "$candidate" || pwd -P)"
while [ -n "$cur" ] && [ "$cur" != "/" ]; do
  if root="$(canonical_git_root "$cur")"; then
    printf '%s\n' "$root"
    exit 0
  fi
  if has_markers "$cur"; then
    abs_dir "$cur"
    exit 0
  fi
  cur="$(dirname "$cur")"
done

abs_dir "$candidate" || pwd -P
