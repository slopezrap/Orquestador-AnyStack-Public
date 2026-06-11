#!/usr/bin/env bash
set -euo pipefail
STRICT=0
[ "${1:-}" = "--strict" ] && STRICT=1
name="$(git config user.name 2>/dev/null || true)"
email="$(git config user.email 2>/dev/null || true)"
if [ -z "$name" ] || [ -z "$email" ]; then
  echo "GIT_IDENTITY_READY: no"
  echo "Reason: git user.name/user.email not configured."
  [ "$STRICT" -eq 1 ] && exit 2 || exit 0
fi
echo "GIT_IDENTITY_READY: yes"
echo "GIT_USER_NAME: $name"
echo "GIT_USER_EMAIL: $email"
