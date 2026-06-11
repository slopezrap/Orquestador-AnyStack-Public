#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# Restore executable bits after ZIP extraction or Windows/WSL checkout metadata loss.
chmod +x \
  "$ROOT"/scripts/*.sh \
  "$ROOT"/scripts/*.py \
  "$ROOT"/.claude/bin/*.sh \
  "$ROOT"/.claude/bin/*.py \
  "$ROOT"/.claude/git-workflows/*.sh \
  "$ROOT"/.claude/enforcers/*.sh 2>/dev/null || true
printf 'ok: executable permissions refreshed for orchestrator entrypoints\n'
