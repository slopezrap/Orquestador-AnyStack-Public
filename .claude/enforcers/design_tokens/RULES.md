# design tokens — blueprint-first visual-token enforcer

The public enforcer name is capability-based, not framework-based.

The framework/theme contract comes from compiled stack config:

```text
orchestrator-state/compiled/orchestrator-input.json -> stack.frontend.framework
orchestrator-state/compiled/orchestrator-input.json -> stack.frontend.module_root
orchestrator-state/compiled/orchestrator-input.json -> stack.frontend.theme_root
orchestrator-state/compiled/orchestrator-input.json -> stack.design_tokens_enforcer | stack.enforcer
```

The dispatcher reads those values through `.claude/bin/stack_profile.py`.

- Flutter/Dart: uses `scripts/check_design_tokens.py`.
- React/Next/Vite/TypeScript: uses `scripts/check_web_design_tokens.py`.
- SwiftUI: extension point; use a project-specific plugin for strict enforcement.
- `none`: explicit no-op.

The orchestrator core must not depend on a Flutter-, React- or SwiftUI-named plugin.
