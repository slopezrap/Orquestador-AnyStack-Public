#!/usr/bin/env bash
# push-to-main.sh -- Closer's Git workflow for git_workflow: push-to-main / direct-main
#
# Use case: single-branch repos, personal projects, or local-only setups where
# there is no PR review step. The orchestrator's /verify-slice is the
# verification gate; this script only handles the transport layer.
#
# Steps:
#   1. Verify we are on main (or the configured default branch).
#   2. Resolve the push remote (branch tracking config → 'origin' fallback).
#   3. Fetch the remote to detect divergence BEFORE pushing.
#   4. Reject if remote is ahead of local (someone else pushed; pull + rebase first).
#   5. Push with --force-with-lease for safety (never bare --force).
#
# Outputs (closer parses these from stdout):
#   GIT_WORKFLOW_READY: yes|no|blocked
#   PUSH_READY:         yes|no
#   REMOTE_AHEAD:       yes  (only when blocked by divergence)
#   LOCAL_AHEAD:        <n> commits (informational)
#
# Exit codes:
#   0   push succeeded
#   2   not on main / not a git repo (wrong workflow)
#   3   push failed (network, auth, divergence)

set -euo pipefail

# ── Branch guard ─────────────────────────────────────────────────────────────
BRANCH="$(git branch --show-current)"
DEFAULT_BRANCH="${GIT_DEFAULT_BRANCH:-main}"

if [ "$BRANCH" != "$DEFAULT_BRANCH" ]; then
  echo "GIT_WORKFLOW_READY: no"
  echo "Reason: push-to-main requires branch '$DEFAULT_BRANCH', current='$BRANCH'."
  echo "  If this is a feature branch, set git_workflow: pr-flow in orchestrator-input.json stack.git_workflow."
  echo "  If '$BRANCH' is your default branch, set GIT_DEFAULT_BRANCH=$BRANCH."
  exit 2
fi

# ── Remote resolution ─────────────────────────────────────────────────────────
# Honour the branch's configured upstream remote; fall back to 'origin'.
REMOTE="$(git config "branch.${BRANCH}.remote" 2>/dev/null || echo origin)"

# Verify the remote actually exists in this repo.
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: no"
  echo "Reason: remote '$REMOTE' not found. Add it with: git remote add $REMOTE <url>"
  exit 3
fi

# ── Fetch (detect divergence before touching remote) ─────────────────────────
# Parallel Claude Code workers can run Git workflows concurrently, so never use
# fixed /tmp filenames. Keep logs when something fails so the closer can print a
# stable path in its evidence report.
LOG_DIR="${TMPDIR:-/tmp}/claude-git-workflows"
mkdir -p "$LOG_DIR"
RUN_ID="push-to-main-$$-$(date +%s)"
FETCH_LOG="$LOG_DIR/${RUN_ID}-fetch.log"
PUSH_LOG="$LOG_DIR/${RUN_ID}-push.log"

REMOTE_REF_EXISTS=0
if git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >"$FETCH_LOG" 2>&1; then
  REMOTE_REF_EXISTS=1
else
  rc=$?
  # git ls-remote --exit-code returns 2 when the remote is reachable but the ref
  # does not exist. That is a valid first-push case, not a transport failure.
  if [ "$rc" -ne 2 ]; then
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: no"
    echo "Reason: could not inspect $REMOTE/$BRANCH (network or auth). See $FETCH_LOG"
    sed 's/^/  /' "$FETCH_LOG" >&2 || true
    exit 3
  fi
fi

if [ "$REMOTE_REF_EXISTS" -eq 1 ]; then
  if ! git fetch "$REMOTE" "$BRANCH" >>"$FETCH_LOG" 2>&1; then
    echo "GIT_WORKFLOW_READY: blocked"
    echo "PUSH_READY: no"
    echo "Reason: git fetch $REMOTE $BRANCH failed (network or auth). See $FETCH_LOG"
    sed 's/^/  /' "$FETCH_LOG" >&2 || true
    exit 3
  fi
  REMOTE_AHEAD="$(git rev-list --count "HEAD..${REMOTE}/${BRANCH}" 2>/dev/null || echo 0)"
  LOCAL_AHEAD="$(git rev-list --count "${REMOTE}/${BRANCH}..HEAD" 2>/dev/null || echo 0)"
else
  REMOTE_AHEAD=0
  LOCAL_AHEAD="$(git rev-list --count HEAD 2>/dev/null || echo 0)"
  echo "REMOTE_REF: absent (${REMOTE}/${BRANCH}); treating as first push"
fi

echo "LOCAL_AHEAD: ${LOCAL_AHEAD} commit(s) ahead of ${REMOTE}/${BRANCH}"

if [ "$REMOTE_AHEAD" -gt 0 ]; then
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: no"
  echo "REMOTE_AHEAD: yes (${REMOTE_AHEAD} commit(s) on remote not in local)"
  echo "Reason: ${REMOTE}/${BRANCH} is ${REMOTE_AHEAD} commit(s) ahead. Pull and rebase before pushing:"
  echo "  git fetch ${REMOTE} ${BRANCH}"
  echo "  git rebase ${REMOTE}/${BRANCH}"
  echo "  ./scripts/git-workflow.sh   # retry"
  exit 3
fi

if [ "$LOCAL_AHEAD" -eq 0 ]; then
  # Nothing to push — remote already has our commit (e.g. re-run after success).
  echo "GIT_WORKFLOW_READY: yes"
  echo "PUSH_READY: yes"
  echo "Reason: nothing to push — ${REMOTE}/${BRANCH} is already up to date."
  exit 0
fi

# ── Push ─────────────────────────────────────────────────────────────────────
# --force-with-lease: safe against concurrent pushes; refuses if the remote
# ref moved since our last fetch. Never bare --force.
if ! git push --force-with-lease "$REMOTE" "$BRANCH" >"$PUSH_LOG" 2>&1; then
  echo "GIT_WORKFLOW_READY: blocked"
  echo "PUSH_READY: no"
  echo "Reason: git push failed. See $PUSH_LOG"
  sed 's/^/  /' "$PUSH_LOG" >&2 || true
  exit 3
fi

PUSHED_SHA="$(git rev-parse HEAD)"
echo "GIT_WORKFLOW_READY: yes"
echo "PUSH_READY: yes"
echo "PUSHED_SHA: ${PUSHED_SHA}"
echo "REMOTE: ${REMOTE}/${BRANCH}"
