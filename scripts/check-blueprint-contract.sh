#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: check-blueprint-contract.sh"
  echo "Alias for check-blueprint-machine-contract.sh."
  exit 0
fi
exec "$ROOT/scripts/check-blueprint-machine-contract.sh" "$@"
