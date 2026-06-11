#!/usr/bin/env bash
# POSIX/Unix bootstrap for macOS and Linux command/hook execution.
# Rancher Desktop on macOS/Linux exposes docker/nerdctl/kubectl/helm under ~/.rd/bin.
# Homebrew lives under /opt/homebrew/bin on Apple Silicon and /usr/local/bin on Intel/macOS/Linux.
set -euo pipefail
prepend_path() {
  case ":$PATH:" in
    *":$1:"*) ;;
    *) if [ -d "$1" ]; then PATH="$1:$PATH"; fi ;;
  esac
}
prepend_path "$HOME/.rd/bin"
prepend_path "/opt/homebrew/bin"
prepend_path "/usr/local/bin"
export PATH
export CLAUDE_SPAWN_BUDGET="${CLAUDE_SPAWN_BUDGET:-70}"
