#!/usr/bin/env bash
# git-flow.sh -- Closer's Git workflow for git_workflow: git-flow
#
# /verify-slice is the verification gate. This script is transport-only.
# It is designed for Claude task worktrees: the closer runs in feature/<TASK_ID>,
# while develop/main may be checked out elsewhere. Integration merges therefore
# happen in short-lived detached worktrees and are pushed as HEAD:<target>.

set -euo pipefail

log() { echo "$*"; }
warn() { echo "WARN: $*" >&2; }

LOG_DIR="${TMPDIR:-/tmp}/claude-git-workflows"
mkdir -p "$LOG_DIR"
RUN_ID="git-flow-$$-$(date +%s)"
TMP_WT_DIR="$LOG_DIR/${RUN_ID}-worktrees"
LOCK_DIR=""
TMP_WTS_FILE="$LOG_DIR/${RUN_ID}-tmp-worktrees.txt"
: >"$TMP_WTS_FILE"
NEW_DETACHED_WORKTREE=""
MERGE_RESULT_WT=""

cleanup_all() {
  local wt
  if [ -f "$TMP_WTS_FILE" ]; then
    while IFS= read -r wt; do
      [ -n "$wt" ] || continue
      git worktree remove --force "$wt" >/dev/null 2>&1 || rm -rf "$wt" 2>/dev/null || true
    done <"$TMP_WTS_FILE"
  fi
  rmdir "$TMP_WT_DIR" >/dev/null 2>&1 || true
  if [ -n "${LOCK_DIR:-}" ] && [ -d "$LOCK_DIR" ]; then
    rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup_all EXIT

abort() {
  local code=3
  if [ "$#" -gt 0 ] && [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    code="$1"
    shift || true
  fi
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: no"
  if [ "$#" -eq 0 ]; then
    echo "Reason: git-flow workflow blocked."
  else
    printf '%s\n' "$@"
  fi
  exit "$code"
}

BRANCH="$(git branch --show-current 2>/dev/null || true)"
DEVELOP_BRANCH="${GIT_FLOW_DEVELOP:-develop}"
MAIN_BRANCH="${GIT_FLOW_MAIN:-main}"

if [ -z "$BRANCH" ]; then
  echo "GIT_WORKFLOW_READY: no"
  echo "PUSH_READY: no"
  echo "BRANCH_TYPE: unknown"
  echo "Reason: git-flow requires a named branch; current checkout is detached."
  exit 2
fi

detect_branch_type() {
  case "$BRANCH" in
    feature/*) echo "feature" ;;
    release/*) echo "release" ;;
    hotfix/*) echo "hotfix" ;;
    "$DEVELOP_BRANCH") echo "develop" ;;
    "$MAIN_BRANCH") echo "main" ;;
    *) echo "unknown" ;;
  esac
}

BRANCH_TYPE="$(detect_branch_type)"
log "BRANCH_TYPE: ${BRANCH_TYPE}"

# Report workflow mismatch before remote checks, so diagnostics are stable in
# freshly initialized repos with no origin yet.
if [ "$BRANCH_TYPE" = "unknown" ]; then
  echo "GIT_WORKFLOW_READY: no"
  echo "PUSH_READY: no"
  echo "Reason: branch '$BRANCH' does not match git-flow conventions."
  echo "  Expected: feature/<TASK_ID>, release/<version>, hotfix/<version>, or '$DEVELOP_BRANCH'."
  exit 2
fi

if [ "$BRANCH_TYPE" = "main" ]; then
  echo "GIT_WORKFLOW_READY: no"
  echo "PUSH_READY: no"
  echo "Reason: direct push to '$MAIN_BRANCH' is not allowed in git-flow."
  echo "  Use a release/* or hotfix/* branch to reach $MAIN_BRANCH."
  exit 2
fi

REMOTE="$(git config "branch.${BRANCH}.remote" 2>/dev/null || true)"
REMOTE="${REMOTE:-origin}"
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  REMOTE="origin"
fi
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  abort 3 "Reason: remote '$REMOTE' not found. Add it with: git remote add $REMOTE <url>"
fi

acquire_lock() {
  local common_dir pid_file owner_pid
  common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  [ -n "$common_dir" ] || abort 3 "Reason: cannot resolve git common dir for git-flow lock."
  LOCK_DIR="$common_dir/claude-git-flow.lock"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    pid_file="$LOCK_DIR/pid"
    owner_pid=""
    if [ -f "$pid_file" ]; then
      owner_pid="$(cat "$pid_file" 2>/dev/null || true)"
    fi
    if [ -n "$owner_pid" ] && ! kill -0 "$owner_pid" 2>/dev/null; then
      rm -rf "$LOCK_DIR" 2>/dev/null || true
      if mkdir "$LOCK_DIR" 2>/dev/null; then
        printf '%s\n' "$$" >"$LOCK_DIR/pid"
        printf '%s\n' "$BRANCH" >"$LOCK_DIR/branch"
        return 0
      fi
    fi
    abort 3 \
      "Reason: another git-flow integration is already running for this repository." \
      "Lock: $LOCK_DIR" \
      "Owner PID: ${owner_pid:-unknown}" \
      "Retry after that closer finishes, or remove the lock only after verifying no git-flow process is running."
  fi
  printf '%s\n' "$$" >"$LOCK_DIR/pid"
  printf '%s\n' "$BRANCH" >"$LOCK_DIR/branch"
}

acquire_lock

FETCH_LOG="$LOG_DIR/${RUN_ID}-fetch.log"
log "Fetching ${REMOTE}..."
if ! git fetch "$REMOTE" --prune --tags >"$FETCH_LOG" 2>&1; then
  abort 3 "Reason: git fetch $REMOTE failed. See $FETCH_LOG"
fi

local_branch_exists() { git show-ref --verify --quiet "refs/heads/$1"; }
remote_branch_exists() { git show-ref --verify --quiet "refs/remotes/${REMOTE}/$1"; }

ensure_branch_ref() {
  local branch="$1"
  local hint_base="${2:-}"
  if local_branch_exists "$branch" || remote_branch_exists "$branch"; then
    return 0
  fi
  if [ -n "$hint_base" ]; then
    abort 3 \
      "Reason: branch '$branch' not found locally or on '$REMOTE'." \
      "Create it explicitly from '$hint_base' and push it before using git-flow:" \
      "  git checkout -b $branch $hint_base" \
      "  git push -u $REMOTE $branch"
  fi
  abort 3 "Reason: branch '$branch' not found locally or on '$REMOTE'."
}

best_ref() {
  local branch="$1"
  if remote_branch_exists "$branch"; then
    printf '%s\n' "${REMOTE}/${branch}"
  elif local_branch_exists "$branch"; then
    printf '%s\n' "$branch"
  else
    return 1
  fi
}

safe_name() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '-'; }

ensure_clean_repo() {
  local repo_path="$1"
  local label="$2"
  local status
  status="$(git -C "$repo_path" status --porcelain --untracked-files=all 2>/dev/null || true)"
  if [ -n "$status" ]; then
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: no"
    echo "Reason: $label worktree is dirty; git-flow refuses to hide changes."
    printf '%s\n' "$status" | sed 's/^/DIRTY: /'
    exit 3
  fi
}

new_detached_worktree() {
  local label="$1"
  local ref="$2"
  local sha wt
  mkdir -p "$TMP_WT_DIR"
  sha="$(git rev-parse "${ref}^{commit}")"
  wt="$TMP_WT_DIR/$(safe_name "$label")"
  if ! git worktree add --detach "$wt" "$sha" >/dev/null 2>&1; then
    abort 3 "Reason: could not create detached integration worktree for '$label' at '$ref'." \
      "Run: git worktree list"
  fi
  printf '%s\n' "$wt" >>"$TMP_WTS_FILE"
  NEW_DETACHED_WORKTREE="$wt"
}

rebase_onto_develop() {
  ensure_branch_ref "$DEVELOP_BRANCH" "$MAIN_BRANCH"
  local base_ref base base_sha rebase_log
  base_ref="$(best_ref "$DEVELOP_BRANCH")"
  base="$(git merge-base "$base_ref" HEAD 2>/dev/null || echo)"
  base_sha="$(git rev-parse "$base_ref" 2>/dev/null || echo)"
  if [ -n "$base" ] && [ -n "$base_sha" ] && [ "$base" = "$base_sha" ]; then
    log "REBASED_ON_DEVELOP: no (already up to date with $base_ref)"
    return 0
  fi

  rebase_log="$LOG_DIR/${RUN_ID}-rebase.log"
  if git rebase "$base_ref" >"$rebase_log" 2>&1; then
    log "REBASED_ON_DEVELOP: yes (rebased onto $base_ref)"
  else
    git rebase --abort >/dev/null 2>&1 || true
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: no"
    echo "REBASE_CONFLICT: yes"
    echo "Reason: rebase onto $base_ref had conflicts. Resolve manually:"
    printf '  cd %q\n' "$(pwd)"
    echo "  git rebase $base_ref"
    echo "  # fix conflicts, git add <files>, git rebase --continue"
    echo "  ./scripts/git-workflow.sh"
    echo "Conflict log: $rebase_log"
    sed 's/^/  /' "$rebase_log" >&2 || true
    exit 4
  fi
}

push_current_branch() {
  local push_log
  push_log="$LOG_DIR/${RUN_ID}-push-$(safe_name "$BRANCH").log"
  if ! git push --force-with-lease -u "$REMOTE" "$BRANCH" >"$push_log" 2>&1; then
    abort 3 "Reason: push of '$BRANCH' to '$REMOTE' failed. See $push_log"
  fi
}

push_repo_head_to_branch() {
  local repo_path="$1"
  local branch="$2"
  local push_log
  push_log="$LOG_DIR/${RUN_ID}-push-$(safe_name "$branch").log"
  if ! git -C "$repo_path" push "$REMOTE" "HEAD:refs/heads/${branch}" >"$push_log" 2>&1; then
    abort 3 "Reason: push of '$branch' to '$REMOTE' failed. See $push_log"
  fi
}

push_develop_only() {
  ensure_clean_repo "." "develop"
  if remote_branch_exists "$DEVELOP_BRANCH"; then
    local remote_ahead
    remote_ahead="$(git rev-list --count "HEAD..${REMOTE}/${DEVELOP_BRANCH}" 2>/dev/null || echo 0)"
    if [ "$remote_ahead" -gt 0 ]; then
      abort 3 \
        "Reason: ${REMOTE}/${DEVELOP_BRANCH} is ${remote_ahead} commit(s) ahead of local. Rebase first:" \
        "  git fetch ${REMOTE} ${DEVELOP_BRANCH}" \
        "  git rebase ${REMOTE}/${DEVELOP_BRANCH}" \
        "  ./scripts/git-workflow.sh"
    fi
  fi
  local push_log
  push_log="$LOG_DIR/${RUN_ID}-push-$(safe_name "$DEVELOP_BRANCH").log"
  if ! git push "$REMOTE" "$DEVELOP_BRANCH" >"$push_log" 2>&1; then
    abort 3 "Reason: push of '$DEVELOP_BRANCH' to '$REMOTE' failed. See $push_log"
  fi
}

merge_into_detached_and_push() {
  local target="$1"
  local source="$2"
  ensure_branch_ref "$target"
  local target_ref wt merge_log
  target_ref="$(best_ref "$target")"
  new_detached_worktree "merge-$target" "$target_ref"
  wt="$NEW_DETACHED_WORKTREE"
  MERGE_RESULT_WT="$wt"
  ensure_clean_repo "$wt" "target '$target'"
  merge_log="$LOG_DIR/${RUN_ID}-merge-$(safe_name "$target").log"
  if ! git -C "$wt" merge --no-ff "$source" \
     -m "chore(git-flow): merge $source into $target" \
      >"$merge_log" 2>&1; then
    git -C "$wt" merge --abort >/dev/null 2>&1 || true
    abort 3 "Reason: merge of '$source' into '$target' failed. See $merge_log"
  fi
  push_repo_head_to_branch "$wt" "$target"
}

create_tag_from_worktree() {
  local wt="$1"
  local tag="$2"
  local message="$3"
  local head_sha tag_sha
  head_sha="$(git -C "$wt" rev-parse HEAD)"
  if git rev-parse --verify "refs/tags/${tag}" >/dev/null 2>&1; then
    tag_sha="$(git rev-parse "refs/tags/${tag}^{commit}" 2>/dev/null || true)"
    if [ "$tag_sha" = "$head_sha" ]; then
      warn "Tag '${tag}' already exists at the intended commit; skipping tag creation."
      log "TAGGED: ${tag} (pre-existing)"
      return 0
    fi
    abort 3 \
      "Reason: tag '$tag' already exists but does not point at the release merge commit." \
      "Existing tag commit: ${tag_sha:-unknown}" \
      "Expected commit: $head_sha" \
      "Pick a new release/hotfix branch name or delete the incorrect tag manually."
  fi
  git -C "$wt" tag -a "$tag" -m "$message"
  local tag_log="$LOG_DIR/${RUN_ID}-tag.log"
  if ! git -C "$wt" push "$REMOTE" "$tag" >"$tag_log" 2>&1; then
    abort 3 "Reason: push of tag '$tag' failed. See $tag_log"
  fi
  log "TAGGED: ${tag}"
}

delete_source_branch() {
  local branch="$1"
  local remote_ok=0
  if git ls-remote --exit-code --heads "$REMOTE" "$branch" >/dev/null 2>&1; then
    if git push "$REMOTE" --delete "$branch" >/dev/null 2>&1; then
      log "REMOTE_BRANCH_DELETED: yes"
    else
      remote_ok=1
      warn "Could not delete remote branch '$REMOTE/$branch'."
      log "REMOTE_BRANCH_DELETED: no"
    fi
  else
    log "REMOTE_BRANCH_DELETED: yes (already absent)"
  fi

  if [ "$(git branch --show-current 2>/dev/null || true)" = "$branch" ]; then
    git checkout --detach HEAD >/dev/null 2>&1 || true
  fi
  if local_branch_exists "$branch"; then
    git branch -d "$branch" >/dev/null 2>&1 || git branch -D "$branch" >/dev/null 2>&1 || true
  fi

  if local_branch_exists "$branch" || [ "$remote_ok" -ne 0 ]; then
    log "BRANCH_DELETED: no"
  else
    log "BRANCH_DELETED: yes"
  fi
}

if [ "$BRANCH_TYPE" = "feature" ]; then
  rebase_onto_develop
  push_current_branch
  log "PUSH_READY: yes"
  merge_into_detached_and_push "$DEVELOP_BRANCH" "$BRANCH"
  log "MERGED_TO_DEVELOP: yes"
  log "MERGED_TO_MAIN: no"
  log "TAGGED: no"
  delete_source_branch "$BRANCH"
  log "GIT_WORKFLOW_READY: yes"
  exit 0
fi

if [ "$BRANCH_TYPE" = "develop" ]; then
  push_develop_only
  log "GIT_WORKFLOW_READY: yes"
  log "PUSH_READY: yes"
  log "MERGED_TO_DEVELOP: no"
  log "MERGED_TO_MAIN: no"
  log "TAGGED: no"
  log "BRANCH_DELETED: no"
  exit 0
fi

if [ "$BRANCH_TYPE" = "release" ] || [ "$BRANCH_TYPE" = "hotfix" ]; then
  ensure_branch_ref "$MAIN_BRANCH"
  ensure_branch_ref "$DEVELOP_BRANCH" "$MAIN_BRANCH"
  VERSION="${BRANCH#*/}"
  if [ "$BRANCH_TYPE" = "hotfix" ]; then
    TAG="v${VERSION}-hotfix"
  else
    TAG="v${VERSION}"
  fi

  push_current_branch
  log "PUSH_READY: yes"
  merge_into_detached_and_push "$MAIN_BRANCH" "$BRANCH"
  main_wt="$MERGE_RESULT_WT"
  log "MERGED_TO_MAIN: yes"
  create_tag_from_worktree "$main_wt" "$TAG" "Release ${TAG} - merged from ${BRANCH}"
  merge_into_detached_and_push "$DEVELOP_BRANCH" "$BRANCH"
  log "MERGED_TO_DEVELOP: yes"
  delete_source_branch "$BRANCH"
  log "GIT_WORKFLOW_READY: yes"
  exit 0
fi
