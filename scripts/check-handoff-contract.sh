#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: check-handoff-contract.sh <TASK_ID> [--require-developer] [--require-debugger] [--require-tester] [--require-ready-for-close] [--require-verify-slice] [--require-slice-verifier] [--require-deployer] [--require-validator] [--require-screen-journey-reviewer] [--require-closer]"
  exit 0
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
exec "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops check_handoff_contract "$@"
