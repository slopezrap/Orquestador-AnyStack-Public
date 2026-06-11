#!/usr/bin/env bash
# Stack-agnostic design-token enforcer for blueprint-first 
set -euo pipefail

TOOL_ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$TOOL_ROOT}"

if [ "${1:-}" = "--project-root" ]; then
  PROJECT_ROOT="$2"
  shift 2
fi

get_profile() {
  python3 -B -S "$TOOL_ROOT/.claude/bin/stack_profile.py" --root "$PROJECT_ROOT" --get "$1" --default "$2"
}

FRAMEWORK="$(get_profile frontend.framework none)"
MODULE_ROOT="$(get_profile frontend.module_root none)"
THEME_ROOT="$(get_profile frontend.theme_root none)"

case "$FRAMEWORK" in
  flutter|dart)
    if [ "$MODULE_ROOT" = "none" ] || [ ! -d "$PROJECT_ROOT/$MODULE_ROOT" ]; then
      echo "i ${MODULE_ROOT} does not exist yet - skip."
      exit 0
    fi
    if [ "$THEME_ROOT" = "none" ]; then
      echo "X design_tokens: stack.frontend.theme_root must be declared for Flutter/Dart projects." >&2
      exit 2
    fi
    exec python3 -B -S "$TOOL_ROOT/scripts/check_design_tokens.py" --root "$PROJECT_ROOT" --app-lib "$PROJECT_ROOT/$MODULE_ROOT" --theme-root "$PROJECT_ROOT/$THEME_ROOT" "$@"
    ;;
  react|nextjs|vite|web|typescript|javascript)
    TARGET="$PROJECT_ROOT/$MODULE_ROOT"
    if [ "$MODULE_ROOT" = "none" ] || [ ! -d "$TARGET" ]; then
      echo "i ${MODULE_ROOT} does not exist yet - skip."
      exit 0
    fi
    if [ "$THEME_ROOT" != "none" ] && [ -n "$THEME_ROOT" ]; then
      exec python3 -B -S "$TOOL_ROOT/scripts/check_web_design_tokens.py" --root "$PROJECT_ROOT" --target "$TARGET" --theme-root "$PROJECT_ROOT/$THEME_ROOT" "$@"
    fi
    exec python3 -B -S "$TOOL_ROOT/scripts/check_web_design_tokens.py" --root "$PROJECT_ROOT" --target "$TARGET" "$@"
    ;;
  swiftui|swift)
    echo "i design_tokens SwiftUI extension point: configure a project-specific plugin if strict Swift scanning is required."
    ;;
  none|"")
    echo "OK Design tokens - no frontend framework declared."
    ;;
  *)
    echo "i design_tokens has no built-in scanner for frontend.framework=${FRAMEWORK}. Use enforcer none or a project plugin for strict checks."
    ;;
esac
