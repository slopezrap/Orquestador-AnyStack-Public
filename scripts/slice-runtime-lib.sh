#!/usr/bin/env bash
# Shared Unix/Rancher/Docker helpers for per-slice runtime scripts.
# Source from scripts/dev-restart.sh, docker-hard-reset.sh and cleanup-slice-runtime.sh.
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ORQ_CANONICAL_ROOT="$SCRIPT_ROOT"
if [ -x "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" ]; then
  ORQ_CANONICAL_ROOT="$(bash "$SCRIPT_ROOT/scripts/resolve-orchestrator-root.sh" "$SCRIPT_ROOT")"
fi
# shellcheck disable=SC1091
source "$ORQ_CANONICAL_ROOT/scripts/unix-runtime-env.sh"

orq_log(){ printf '%s\n' "$*"; }
orq_warn(){ printf 'WARN: %s\n' "$*" >&2; }
orq_fail(){ printf 'ERROR: %s\n' "$*" >&2; exit "${2:-1}"; }

orq_workspace_root(){
  local root_candidate="${CLAUDE_WORKTREE_ROOT:-}"
  if [ -n "$root_candidate" ] && [ -d "$root_candidate" ]; then (cd "$root_candidate" && pwd -P); return 0; fi
  root_candidate="${CLAUDE_PROJECT_DIR:-$PWD}"
  if [ -n "$root_candidate" ] && [ -d "$root_candidate" ] && git -C "$root_candidate" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$root_candidate" rev-parse --show-toplevel
    return 0
  fi
  git -C "$SCRIPT_ROOT" rev-parse --show-toplevel 2>/dev/null || pwd -P
}

orq_resolve_runtime(){
  # orq_resolve_runtime <task_id> [project_override]
  local task_id="${1:-}" project_override="${2:-}" runtime_root workspace_root
  [ -n "$task_id" ] || orq_fail 'provide --task <TASK_ID>' 2
  runtime_root="${CLAUDE_ORCHESTRATOR_ROOT:-$ORQ_CANONICAL_ROOT}"
  workspace_root="$(orq_workspace_root)"
  [ -f "$runtime_root/.claude/bin/runtime_context.py" ] || runtime_root="$ORQ_CANONICAL_ROOT"
  local args=(--root "$runtime_root" --workspace-root "$workspace_root" --task "$task_id" --print-env)
  [ -n "$project_override" ] && args+=(--project "$project_override")
  eval "$(python3 -B -S "$runtime_root/.claude/bin/runtime_context.py" "${args[@]}")"
  export CLAUDE_ORCHESTRATOR_ROOT="$runtime_root" CLAUDE_WORKTREE_ROOT="$workspace_root"
  export CLAUDE_ACTIVE_TASK_ID="$task_id" TASK_ID="$task_id"
}

orq_load_compose_files(){
  COMPOSE_FILES=()
  local override="${1:-}"
  if [ -n "$override" ]; then
    COMPOSE_FILES=("$override")
  elif [ -n "${CLAUDE_RUNTIME_COMPOSE_FILES:-}" ]; then
    local old_ifs="$IFS" item
    IFS=':'
    for item in $CLAUDE_RUNTIME_COMPOSE_FILES; do
      [ -n "$item" ] && COMPOSE_FILES+=("$item")
    done
    IFS="$old_ifs"
  fi
}

orq_allocate_ports(){
  local task_id="${1:-}" runtime_root="${CLAUDE_ORCHESTRATOR_ROOT:-$ORQ_CANONICAL_ROOT}" env_file
  [ -n "$task_id" ] || orq_fail 'missing task for contract allocation' 2
  env_file="$runtime_root/orchestrator-state/dev-ports/${COMPOSE_PROJECT_NAME}.env"
  python3 -B -S "$runtime_root/.claude/bin/allocate_slice_ports.py" --root "$runtime_root" --task "$task_id" --env-file "$env_file" >/dev/null
  # shellcheck disable=SC1090
  source "$env_file"
  export CLAUDE_PORT_ENV_FILE="$env_file"
}

orq_ensure_container_runtime(){
  # Rancher Desktop is the expected local container runtime. On macOS/Linux its
  # CLI utilities live in ~/.rd/bin; unix-runtime-env.sh already prepends it.
  if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
    return 0
  fi
  if command -v rdctl >/dev/null 2>&1; then
    orq_warn 'docker is not ready; attempting Rancher Desktop start via rdctl start'
    rdctl start >/dev/null 2>&1 || true
  fi
  local i
  for i in $(seq 1 60); do
    if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  orq_fail 'docker is not available after Rancher Desktop/PATH check. Ensure Rancher Desktop is running and ~/.rd/bin is on PATH.' 4
}

orq_build_compose_args(){
  COMPOSE_ARGS=(docker compose -p "$COMPOSE_PROJECT_NAME")
  local f
  for f in "${COMPOSE_FILES[@]:-}"; do COMPOSE_ARGS+=(-f "$f"); done
}

orq_print_runtime_summary(){
  printf 'TASK_ID: %s\n' "${TASK_ID:-}"
  printf 'TASK_SLUG: %s\n' "${TASK_SLUG:-}"
  printf 'COMPOSE_PROJECT_NAME: %s\n' "${COMPOSE_PROJECT_NAME:-}"
  printf 'WORKSPACE_ROOT: %s\n' "${CLAUDE_WORKTREE_ROOT:-}"
  printf 'COMPOSE_FILES: %s\n' "${CLAUDE_RUNTIME_COMPOSE_FILES:-none}"
  printf 'PORT_ENV: %s\n' "${CLAUDE_PORT_ENV_FILE:-none}"
}
