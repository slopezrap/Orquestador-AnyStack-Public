#!/usr/bin/env bash
# Clean Docker/Rancher runtime resources created for one TASK_ID slice.
# Blueprint-first adaptation: runtime context comes from orchestrator-input.json.
# macOS/Linux: Rancher Desktop utilities are discovered via scripts/unix-runtime-env.sh.
# Clean Docker/Rancher runtime resources created for one TASK_ID slice.
# It must prove cleanup before closer can emit RUNTIME_CLEANED: yes.
set -euo pipefail
ROOT_BOOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091
source "$ROOT_BOOT/scripts/slice-runtime-lib.sh"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_ROOT="${CLAUDE_ORCHESTRATOR_ROOT:-$ROOT_DIR}"
WORKSPACE_ROOT="${CLAUDE_WORKTREE_ROOT:-}"
if [ -z "$WORKSPACE_ROOT" ]; then
  WORKSPACE_ROOT="$(git -C "$ROOT_DIR" rev-parse --show-toplevel 2>/dev/null || pwd -P)"
fi
TASK_ID="${CLAUDE_ACTIVE_TASK_ID:-}"
PROJECT="${COMPOSE_PROJECT_NAME:-${CLAUDE_COMPOSE_PROJECT_NAME:-}}"
COMPOSE_FILE_OVERRIDE=""
REMOVE_IMAGES="${SLICE_RUNTIME_REMOVE_IMAGES:-}"
APPLY=0
STRICT=0
JSON=0
KEEP_PORTS=0
usage(){ cat <<'USAGE'
Usage: scripts/cleanup-slice-runtime.sh --task <TASK_ID> [--project <compose-project>] [--compose-file compose.yml] [--apply] [--strict] [--json] [--keep-ports] [--remove-images local|label|all|none]

Cleans runtime resources for one slice:
 - docker compose project: containers, networks, volumes and orphans
 - docker images created for that compose project (`local` by default; never global prune)
 - leftover Docker objects labelled/named for the compose project
 - optional Rancher cleanup command from orchestrator-input.json stack verification/observability config
 - per-slice contract reservation files under orchestrator-state/dev-ports/

Default is dry-run. /closer must call this with --apply --strict.
USAGE
}
while [ $# -gt 0 ]; do
  case "$1" in
   --task|--task-id) TASK_ID="${2:?}"; shift 2 ;;
   --project) PROJECT="${2:?}"; shift 2 ;;
   --compose-file|-f) COMPOSE_FILE_OVERRIDE="${2:?}"; shift 2 ;;
   --remove-images) REMOVE_IMAGES="${2:?}"; shift 2 ;;
   --apply) APPLY=1; shift ;;
   --dry-run) APPLY=0; shift ;;
   --strict) STRICT=1; shift ;;
   --json) JSON=1; shift ;;
   --keep-ports) KEEP_PORTS=1; shift ;;
   -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown flag $1" >&2; usage >&2; exit 2 ;;
  esac
done
[ -n "$TASK_ID" ] || { echo "ERROR: provide --task <TASK_ID>" >&2; exit 2; }
RUNTIME_ROOT="$ORCHESTRATOR_ROOT"
RUNTIME_SCRIPT="$RUNTIME_ROOT/.claude/bin/runtime_context.py"
if [ ! -f "$RUNTIME_SCRIPT" ]; then
  RUNTIME_ROOT="$ROOT_DIR"
  RUNTIME_SCRIPT="$ROOT_DIR/.claude/bin/runtime_context.py"
fi
RUNTIME_ARGS=(--root "$RUNTIME_ROOT" --workspace-root "$WORKSPACE_ROOT" --task "$TASK_ID" --print-env)
[ -n "$PROJECT" ] && RUNTIME_ARGS+=(--project "$PROJECT")
RUNTIME_ENV="$(python3 -B -S "$RUNTIME_SCRIPT" "${RUNTIME_ARGS[@]}")"
eval "$RUNTIME_ENV"
PROJECT="$COMPOSE_PROJECT_NAME"
if [ -z "$REMOVE_IMAGES" ]; then
  REMOVE_IMAGES="$(python3 -B -S "$RUNTIME_ROOT/.claude/bin/stack_profile.py" --root "$RUNTIME_ROOT" --get verification.docker.cleanup_remove_images --default local 2>/dev/null || printf 'local')"
fi
case "$REMOVE_IMAGES" in local|label|all|none) ;; *) echo "ERROR: --remove-images must be local, label, all or none" >&2; exit 2 ;; esac

profile_get(){ local key="$1" default="${2:-}"; python3 -B -S "$RUNTIME_ROOT/.claude/bin/stack_profile.py" --root "$RUNTIME_ROOT" --get "$key" --default "$default" 2>/dev/null | sed -e 's/^"//' -e 's/"$//' || printf '%s' "$default"; }
is_none_value(){ local v; v="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | xargs)"; [ -z "$v" ] || [ "$v" = "none" ] || [ "$v" = "null" ] || [ "$v" = "[]" ] || [ "$v" = "auto" ] || [ "$v" = "false" ]; }
render_runtime_template(){ local text="$1"; text="${text//\{\{ task_slug \}\}/$TASK_SLUG}"; text="${text//\{\{task_slug\}\}/$TASK_SLUG}"; text="${text//\{task_slug\}/$TASK_SLUG}"; text="${text//\$\{TASK_SLUG\}/$TASK_SLUG}"; text="${text//\$TASK_SLUG/$TASK_SLUG}"; text="${text//\{\{ task_id \}\}/$TASK_ID}"; text="${text//\{\{task_id\}\}/$TASK_ID}"; text="${text//\{task_id\}/$TASK_ID}"; text="${text//\$\{TASK_ID\}/$TASK_ID}"; text="${text//\$TASK_ID/$TASK_ID}"; printf '%s' "$text"; }
dry_run_echo(){
  if [ "$JSON" = 1 ]; then
    { printf 'DRY_RUN:'; printf ' %q' "$@"; printf '\n'; } >&2
  else
    printf 'DRY_RUN:'; printf ' %q' "$@"; printf '\n'
  fi
}
run_or_echo(){ if [ "$APPLY" = 1 ]; then "$@"; else dry_run_echo "$@"; fi; }
collect_ids(){ bash -lc "$1" 2>/dev/null || true; }
remove_ids(){
  local kind="$1" remove_cmd="$2" ids="$3"
  [ -n "$ids" ] || return 0
  if [ "$APPLY" = 1 ]; then
    # shellcheck disable=SC2086
    $remove_cmd $ids >/dev/null 2>&1 || true
  else
    if [ "$JSON" = 1 ]; then printf 'DRY_RUN: remove %s %s\n' "$kind" "$(printf '%s' "$ids" | tr '\n' ' ')" >&2; else printf 'DRY_RUN: remove %s %s\n' "$kind" "$(printf '%s' "$ids" | tr '\n' ' ')"; fi
  fi
}
json_string(){ local s="${1:-}"; s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/\\n}"; printf '"%s"' "$s"; }

EVIDENCE_DIR="$WORKSPACE_ROOT/orchestrator-state/tasks/evidence/$TASK_ID/runtime-cleanup"
[ "$APPLY" = 1 ] && mkdir -p "$EVIDENCE_DIR"
status="yes"
docker_status="not_applicable:no_docker_runtime_declared"
rancher_status="not_applicable:no_rancher_cleanup_cmd"
ports_status="not_applicable:no_port_files"
compose_status="not_applicable:no_compose_file"
verification_status="not_checked"
containers_inactive="0"; networks_inactive="0"; volumes_inactive="0"; images_inactive="0"; remaining_count="0"

COMPOSE_FILES=()
if [ -n "$COMPOSE_FILE_OVERRIDE" ]; then
  COMPOSE_FILES=("$COMPOSE_FILE_OVERRIDE")
elif [ -n "${CLAUDE_RUNTIME_COMPOSE_FILES:-}" ]; then
  OLD_IFS="$IFS"; IFS=':'; for item in $CLAUDE_RUNTIME_COMPOSE_FILES; do [ -n "$item" ] && COMPOSE_FILES+=("$item"); done; IFS="$OLD_IFS"
fi

if [ "${#COMPOSE_FILES[@]}" -gt 0 ] || [ "${CLAUDE_RUNTIME_COMPOSE_FILES_EXPLICIT:-no}" = "yes" ]; then
  orq_ensure_container_runtime
fi

if command -v docker >/dev/null 2>&1; then
  if [ "${#COMPOSE_FILES[@]}" -gt 0 ]; then
    compose_args=(docker compose -p "$PROJECT")
    for f in "${COMPOSE_FILES[@]}"; do compose_args+=(-f "$f"); done
    down_args=("${compose_args[@]}" down -v --remove-orphans)
    case "$REMOVE_IMAGES" in
      local|all) down_args+=(--rmi "$REMOVE_IMAGES") ;;
      none|label) ;;
    esac
    compose_status="applied"
    if [ "$APPLY" = 1 ]; then
      (cd "$WORKSPACE_ROOT" && "${down_args[@]}") >"$EVIDENCE_DIR/docker-compose-down.log" 2>&1 || { status="no"; docker_status="failed:compose_down"; }
    else
      dry_run_echo "${down_args[@]}"
    fi
    [ "$docker_status" = "not_applicable:no_docker_runtime_declared" ] && docker_status="yes"
  elif [ "$STRICT" = 1 ] && [ "${CLAUDE_RUNTIME_COMPOSE_FILES_EXPLICIT:-no}" = "yes" ]; then
    status="no"; docker_status="failed:compose_file_missing"; compose_status="failed:compose_file_missing"
  fi

  label="com.docker.compose.project=$PROJECT"
  container_ids="$(collect_ids "docker ps -aq --filter label=$label")"
  network_ids="$(collect_ids "docker network ls -q --filter label=$label")"
  volume_ids="$(collect_ids "docker volume ls -q --filter label=$label")"
  image_ids="$(collect_ids "docker images -q --filter label=$label")"
  name_container_ids="$(collect_ids "docker ps -aq --filter name=^/${PROJECT}[_-]")"
  name_network_ids="$(collect_ids "docker network ls --format '{{.Name}}' | grep -E '^${PROJECT}[_-]' || true")"
  name_volume_ids="$(collect_ids "docker volume ls --format '{{.Name}}' | grep -E '^${PROJECT}[_-]' || true")"
  all_container_ids="$(printf '%s\n%s\n' "$container_ids" "$name_container_ids" | awk 'NF && !seen[$0]++')"
  all_network_ids="$(printf '%s\n%s\n' "$network_ids" "$name_network_ids" | awk 'NF && !seen[$0]++')"
  all_volume_ids="$(printf '%s\n%s\n' "$volume_ids" "$name_volume_ids" | awk 'NF && !seen[$0]++')"
  containers_inactive="$(printf '%s\n' "$all_container_ids" | awk 'NF{c++} END{print c+0}')"
  networks_inactive="$(printf '%s\n' "$all_network_ids" | awk 'NF{c++} END{print c+0}')"
  volumes_inactive="$(printf '%s\n' "$all_volume_ids" | awk 'NF{c++} END{print c+0}')"
  images_inactive="$(printf '%s\n' "$image_ids" | awk 'NF{c++} END{print c+0}')"
  remove_ids containers "docker rm -f" "$all_container_ids"
  remove_ids networks "docker network rm" "$all_network_ids"
  remove_ids volumes "docker volume rm -f" "$all_volume_ids"
  if [ "$REMOVE_IMAGES" = "label" ] || [ "$REMOVE_IMAGES" = "local" ]; then
    remove_ids images "docker rmi -f" "$image_ids"
  fi
  if [ "$containers_inactive$networks_inactive$volumes_inactive$images_inactive" != "0000" ] && [ "$docker_status" = "not_applicable:no_docker_runtime_declared" ]; then
    docker_status="yes"
  fi
  if [ "$APPLY" = 1 ]; then
    left_c="$(collect_ids "docker ps -aq --filter label=$label; docker ps -aq --filter name=^/${PROJECT}[_-]")"
    left_n="$(collect_ids "docker network ls -q --filter label=$label; docker network ls --format '{{.Name}}' | grep -E '^${PROJECT}[_-]' || true")"
    left_v="$(collect_ids "docker volume ls -q --filter label=$label; docker volume ls --format '{{.Name}}' | grep -E '^${PROJECT}[_-]' || true")"
    remaining_count="$(printf '%s\n%s\n%s\n' "$left_c" "$left_n" "$left_v" | awk 'NF && !seen[$0]++{c++} END{print c+0}')"
    verification_status="yes"
    if [ "$remaining_count" != "0" ]; then
      status="no"; docker_status="failed:docker_objects_remaining"; verification_status="failed:docker_objects_remaining"
      printf 'Remaining Docker resources for project %s:\ncontainers:\n%s\nnetworks:\n%s\nvolumes:\n%s\n' "$PROJECT" "$left_c" "$left_n" "$left_v" > "$EVIDENCE_DIR/docker-cleanup-remaining.log" 2>/dev/null || true
    fi
  fi
else
  if [ "$STRICT" = 1 ] && { [ "${#COMPOSE_FILES[@]}" -gt 0 ] || [ "${CLAUDE_RUNTIME_COMPOSE_FILES_EXPLICIT:-no}" = "yes" ]; }; then
    status="no"; docker_status="failed:docker_command_not_found"
  fi
fi

rancher_cmd="$(profile_get verification.rancher.cleanup_cmd none)"
is_none_value "$rancher_cmd" && rancher_cmd="$(profile_get observability.rancher_cleanup_cmd none)"
rancher_cmd="$(render_runtime_template "$rancher_cmd")"
if ! is_none_value "$rancher_cmd"; then
  rancher_status="yes"
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$EVIDENCE_DIR"
    { printf 'COMMAND: %s\n' "$rancher_cmd"; printf 'TASK_ID: %s\n' "$TASK_ID"; printf 'TASK_SLUG: %s\n' "$TASK_SLUG"; printf 'COMPOSE_PROJECT_NAME: %s\n--- output ---\n' "$PROJECT"; } > "$EVIDENCE_DIR/rancher-cleanup.log"
    set +e
    bash -lc "$rancher_cmd" >> "$EVIDENCE_DIR/rancher-cleanup.log" 2>&1
    rc=$?
    set -e
    printf 'COMMAND_EXIT: %s\n' "$rc" >> "$EVIDENCE_DIR/rancher-cleanup.log"
    if [ "$rc" -ne 0 ]; then status="no"; rancher_status="failed:$rc"; fi
  else
    if [ "$JSON" = 1 ]; then printf 'DRY_RUN: bash -lc %q\n' "$rancher_cmd" >&2; else printf 'DRY_RUN: bash -lc %q\n' "$rancher_cmd"; fi
  fi
fi

if [ "$KEEP_PORTS" = 0 ]; then
  port_dir="$ORCHESTRATOR_ROOT/orchestrator-state/dev-ports"
  released=0
  if [ -d "$port_dir" ]; then
    for suffix in env json; do
      for p in "$port_dir/$PROJECT.$suffix" "$port_dir/$TASK_SLUG.$suffix"; do
        if [ -e "$p" ]; then released=1; run_or_echo rm -f "$p"; fi
      done
    done
    for envfile in "$port_dir"/*.env; do
      [ -e "$envfile" ] || continue
      if grep -Eq "(COMPOSE_PROJECT_NAME|CLAUDE_COMPOSE_PROJECT_NAME)=['\"]?${PROJECT}['\"]?" "$envfile" 2>/dev/null || grep -Eq "CLAUDE_ACTIVE_TASK_ID=['\"]?${TASK_ID}['\"]?" "$envfile" 2>/dev/null; then
        released=1
        jsonfile="${envfile%.env}.json"
        run_or_echo rm -f "$envfile"
        [ -e "$jsonfile" ] && run_or_echo rm -f "$jsonfile"
      fi
    done
  fi
  if [ "$released" = 1 ]; then ports_status="yes"; fi
fi

if [ "$JSON" = 1 ]; then
  printf '{"task_id":%s,"task_slug":%s,"compose_project":%s,"workspace_root":%s,"applied":%s,"runtime_cleaned":%s,"docker_runtime_cleaned":%s,"docker_compose_status":%s,"docker_cleanup_verified":%s,"docker_objects_remaining":%s,"containers_inactive":%s,"networks_inactive":%s,"volumes_inactive":%s,"images_inactive":%s,"rancher_runtime_cleaned":%s,"dev_ports_released":%s,"remove_images":%s}\n' \
    "$(json_string "$TASK_ID")" "$(json_string "$TASK_SLUG")" "$(json_string "$PROJECT")" "$(json_string "$WORKSPACE_ROOT")" "$([ "$APPLY" = 1 ] && echo true || echo false)" \
    "$(json_string "$status")" "$(json_string "$docker_status")" "$(json_string "$compose_status")" "$(json_string "$verification_status")" "$remaining_count" \
    "$containers_inactive" "$networks_inactive" "$volumes_inactive" "$images_inactive" "$(json_string "$rancher_status")" "$(json_string "$ports_status")" "$(json_string "$REMOVE_IMAGES")"
else
  printf 'TASK_ID: %s\n' "$TASK_ID"
  printf 'TASK_SLUG: %s\n' "$TASK_SLUG"
  printf 'COMPOSE_PROJECT_NAME: %s\n' "$PROJECT"
  printf 'WORKSPACE_ROOT: %s\n' "$WORKSPACE_ROOT"
  printf 'COMPOSE_FILES: %s\n' "${CLAUDE_RUNTIME_COMPOSE_FILES:-none}"
  printf 'RUNTIME_CLEANUP_APPLIED: %s\n' "$([ "$APPLY" = 1 ] && echo yes || echo dry_run)"
  printf 'DOCKER_RUNTIME_CLEANED: %s\n' "$docker_status"
  printf 'DOCKER_COMPOSE_STATUS: %s\n' "$compose_status"
  printf 'DOCKER_CLEANUP_VERIFIED: %s\n' "$verification_status"
  printf 'DOCKER_OBJECTS_REMAINING: %s\n' "$remaining_count"
  printf 'RANCHER_RUNTIME_CLEANED: %s\n' "$rancher_status"
  printf 'DEV_PORTS_RELEASED: %s\n' "$ports_status"
  printf 'DOCKER_IMAGES_REMOVED: %s\n' "$REMOVE_IMAGES"
  printf 'RUNTIME_CLEANED: %s\n' "$status"
fi
[ "$status" = "yes" ] || exit 5
