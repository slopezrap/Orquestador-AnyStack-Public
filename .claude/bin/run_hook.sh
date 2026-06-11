#!/usr/bin/env bash
set -euo pipefail
# macOS/Linux: add Rancher Desktop and Homebrew tool locations without requiring GNU timeout.
_hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
_root_for_env="$(cd "$_hook_dir/../.." && pwd -P)"
[ -f "$_root_for_env/scripts/unix-runtime-env.sh" ] && . "$_root_for_env/scripts/unix-runtime-env.sh"
hook="${1:?hook name required}"
shift || true
roots=()
add_root() { if [ -n "${1:-}" ] && [ -d "$1" ]; then roots+=("$1"); fi; return 0; }
probe="${CLAUDE_PROJECT_DIR:-$PWD}"
canonical_probe="${CLAUDE_ORCHESTRATOR_ROOT:-$probe}"
tmp_common="${TMPDIR:-/tmp}/claude_hook_common.$$"
if command -v git >/dev/null 2>&1 && git -C "$canonical_probe" rev-parse --path-format=absolute --git-common-dir >"$tmp_common" 2>/dev/null; then
  common="$(cat "$tmp_common")"
  rm -f "$tmp_common"
  [ "$(basename "$common")" = ".git" ] && add_root "$(dirname "$common")"
fi
rm -f "$tmp_common" 2>/dev/null || true
case "$canonical_probe" in
  *-worktrees/*) add_root "${canonical_probe%%-worktrees/*}" ;;
esac
add_root "${CLAUDE_ORCHESTRATOR_ROOT:-}"
add_root "$probe"
add_root "$PWD"
case "$probe" in
  *-worktrees/*) add_root "${probe%%-worktrees/*}" ;;
esac
cur="$probe"
while [ -n "$cur" ] && [ "$cur" != "/" ]; do
  add_root "$cur"
  cur="$(dirname "$cur")"
done
seen="|"
for root in "${roots[@]}"; do
  case "$seen" in *"|$root|"*) continue;; esac
  seen="$seen$root|"
  if [ -f "$root/.claude/bin/$hook" ]; then
    export CLAUDE_ORCHESTRATOR_ROOT="$root"
    export CLAUDE_WORKSPACE_ROOT="${CLAUDE_WORKSPACE_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}"
    exec python3 -B -S "$root/.claude/bin/$hook" "$@"
  fi
done
echo "HOOK_ROOT_WARN: missing $hook from ${CLAUDE_PROJECT_DIR:-$PWD}; set CLAUDE_ORCHESTRATOR_ROOT to the canonical repo root" >&2
exit 0
