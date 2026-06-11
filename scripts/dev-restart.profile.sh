#!/usr/bin/env bash
# Neutral blueprint-first dev profile.
# The active runtime normally uses Docker Compose files resolved from
# orchestrator-input.json via scripts/dev-restart.sh. A generated product app may
# still source this profile for stack-specific health/log helpers, but it is not
# the source of truth.

back_health() { return 2; }
front_health() { return 2; }
db_health() { return 2; }
back_url() { printf 'not_applicable'; }
front_url() { printf 'not_applicable'; }
back_start() { echo 'DEV_PROFILE_BACK_START: not_applicable'; return 0; }
front_start() { echo 'DEV_PROFILE_FRONT_START: not_applicable'; return 0; }
db_reset() { echo 'DEV_PROFILE_DB_RESET: not_applicable'; return 0; }
runtime_logs_collect() { return 0; }
rancher_worker_logs() { return 0; }
