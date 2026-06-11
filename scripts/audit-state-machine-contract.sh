#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.runtime_ops audit_state_machine_contract "$@"
