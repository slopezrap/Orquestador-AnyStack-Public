#!/usr/bin/env bash
# Start/check/reset the per-slice development runtime.
# Blueprint-first adaptation of the orchestrator dispatcher.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091
source "$ROOT/scripts/slice-runtime-lib.sh"

MODE="soft"
TASK_ID_IN="${CLAUDE_ACTIVE_TASK_ID:-}"
PROJECT_OVERRIDE=""
COMPOSE_FILE_OVERRIDE=""
REQUIRE_COMPOSE=0
usage(){ cat <<'USAGE'
Usage: scripts/dev-restart.sh [--task <TASK_ID>] [--project <compose-project>] [--compose-file compose.yml] [--soft|--check|--reset] [--require-compose]

Starts the per-slice local runtime when the compiled blueprint/stack exposes a
Docker Compose file. Rancher Desktop is the expected local container runtime on
macOS/Linux; ~/.rd/bin is prepended automatically. If no compose file exists,
the command exits successfully with DEV_RESTART: skipped_no_compose_file unless
--require-compose is supplied.

The command always derives COMPOSE_PROJECT_NAME from TASK_ID and allocates free
host ports before compose starts, so parallel slices do not collide on macOS or Linux.
USAGE
}
while [ $# -gt 0 ]; do
  case "$1" in
   --soft) MODE="soft"; shift ;;
   --check) MODE="check"; shift ;;
   --reset) MODE="reset"; shift ;;
   --task|--task-id) TASK_ID_IN="${2:?}"; shift 2 ;;
   --project) PROJECT_OVERRIDE="${2:?}"; shift 2 ;;
   --compose-file|-f) COMPOSE_FILE_OVERRIDE="${2:?}"; shift 2 ;;
   --require-compose) REQUIRE_COMPOSE=1; shift ;;
   -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown flag $1" >&2; usage >&2; exit 2 ;;
  esac
done
[ -n "$TASK_ID_IN" ] || { echo 'ERROR: provide --task <TASK_ID> or export CLAUDE_ACTIVE_TASK_ID' >&2; exit 2; }

orq_resolve_runtime "$TASK_ID_IN" "$PROJECT_OVERRIDE"
orq_load_compose_files "$COMPOSE_FILE_OVERRIDE"
if [ "${#COMPOSE_FILES[@]}" -eq 0 ]; then
  echo "DEV_RESTART: skipped_no_compose_file task=$TASK_ID project=$COMPOSE_PROJECT_NAME configured=${CLAUDE_RUNTIME_COMPOSE_FILES_CONFIGURED:-none}"
  [ "$REQUIRE_COMPOSE" = 1 ] && exit 4 || exit 0
fi
orq_ensure_container_runtime
orq_allocate_ports "$TASK_ID"
orq_build_compose_args

if [ "$MODE" = "check" ]; then
  if (cd "$CLAUDE_WORKTREE_ROOT" && "${COMPOSE_ARGS[@]}" ps --status running >/dev/null 2>&1); then
    echo "DEV_RESTART: running task=$TASK_ID project=$COMPOSE_PROJECT_NAME"
    orq_print_runtime_summary
    exit 0
  fi
  echo "DEV_RESTART: not_running task=$TASK_ID project=$COMPOSE_PROJECT_NAME"
  orq_print_runtime_summary
  exit 1
fi

if [ "$MODE" = "reset" ]; then
  args=(--task "$TASK_ID")
  [ -n "$PROJECT_OVERRIDE" ] && args+=(--project "$PROJECT_OVERRIDE")
  [ -n "$COMPOSE_FILE_OVERRIDE" ] && args+=(--compose-file "$COMPOSE_FILE_OVERRIDE")
  exec "$ROOT/scripts/docker-hard-reset.sh" "${args[@]}"
fi

printf 'DEV_RESTART: starting task=%s project=%s compose=%s ports_env=%s\n' "$TASK_ID" "$COMPOSE_PROJECT_NAME" "${COMPOSE_FILES[*]}" "${CLAUDE_PORT_ENV_FILE:-none}"
(
  cd "$CLAUDE_WORKTREE_ROOT"
  "${COMPOSE_ARGS[@]}" up -d --build
)
orq_print_runtime_summary
printf 'DEV_RESTART_READY: yes\n'
