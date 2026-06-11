#!/usr/bin/env bash
# Hard reset a per-slice Docker/Rancher Compose runtime.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091
source "$ROOT/scripts/slice-runtime-lib.sh"

TASK_ID_IN="${CLAUDE_ACTIVE_TASK_ID:-}"
PROJECT_OVERRIDE=""
COMPOSE_FILE_OVERRIDE=""
REQUIRE_COMPOSE=0
DETACH=1
usage(){ cat <<'USAGE'
Usage: scripts/docker-hard-reset.sh --task <TASK_ID> [--project <compose-project>] [--compose-file compose.yml] [--require-compose] [--foreground]

Uses Rancher Desktop/Docker Compose for this slice:
  docker compose -p <project> down -v --remove-orphans
  docker compose -p <project> up -d --build

Ports are allocated per TASK_ID before up, so parallel slices do not collide.
Uses portable POSIX shell loops for macOS/Linux and Rancher PATH.
USAGE
}
while [ $# -gt 0 ]; do
  case "$1" in
   --task|--task-id) TASK_ID_IN="${2:?}"; shift 2 ;;
   --project) PROJECT_OVERRIDE="${2:?}"; shift 2 ;;
   --compose-file|-f) COMPOSE_FILE_OVERRIDE="${2:?}"; shift 2 ;;
   --require-compose) REQUIRE_COMPOSE=1; shift ;;
   --foreground) DETACH=0; shift ;;
   -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown flag $1" >&2; usage >&2; exit 2 ;;
  esac
done
[ -n "$TASK_ID_IN" ] || { echo 'ERROR: provide --task <TASK_ID>' >&2; exit 2; }

orq_resolve_runtime "$TASK_ID_IN" "$PROJECT_OVERRIDE"
orq_load_compose_files "$COMPOSE_FILE_OVERRIDE"
if [ "${#COMPOSE_FILES[@]}" -eq 0 ]; then
  echo "DOCKER_HARD_RESET: skipped_no_compose_file workspace=$CLAUDE_WORKTREE_ROOT task=$TASK_ID configured=${CLAUDE_RUNTIME_COMPOSE_FILES_CONFIGURED:-none}"
  [ "$REQUIRE_COMPOSE" = 1 ] && exit 4 || exit 0
fi
orq_ensure_container_runtime
orq_allocate_ports "$TASK_ID"
orq_build_compose_args

printf 'DOCKER_HARD_RESET: project=%s compose=%s task=%s workspace=%s ports_env=%s\n' "$COMPOSE_PROJECT_NAME" "${COMPOSE_FILES[*]}" "$TASK_ID" "$CLAUDE_WORKTREE_ROOT" "${CLAUDE_PORT_ENV_FILE:-none}"
(
  cd "$CLAUDE_WORKTREE_ROOT"
  "${COMPOSE_ARGS[@]}" down -v --remove-orphans
  if [ "$DETACH" = 1 ]; then
    "${COMPOSE_ARGS[@]}" up -d --build
  else
    "${COMPOSE_ARGS[@]}" up --build
  fi
)
printf 'DOCKER_HARD_RESET_READY: yes\n'
