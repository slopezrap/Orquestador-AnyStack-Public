#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/scripts/python-safe.sh" -m orchestrator.runtime.check_orchestrator_gaps "$@"
