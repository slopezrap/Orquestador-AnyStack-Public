#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: check-blueprint-machine-contract.sh"
  exit 0
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
exec "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.check_blueprint_machine_contract "$@"
