# orchestrator-AnyStack call matrix

Matriz de cableado para revisar borrados, renombres o movimientos. Si un fichero aparece como caller/callee, cambia también sus checks y tests.

## Skills -> scripts

| Skill | Delegación |
| --- | --- |
| audit-runtime-surface | ./scripts/audit-runtime-surface.sh |
| auto-verify-slice | ./scripts/auto-verify-slice.sh |
| bootstrap-registry | ./scripts/bootstrap-registry.sh, ./scripts/check-orchestrator-gaps.sh, ./scripts/check-task-dag.sh, ./scripts/check-task-descriptions.sh |
| build-task-pack | ./scripts/bootstrap-registry.sh |
| check-blueprint-lossless-flow | ./scripts/check-blueprint-lossless-flow.sh |
| check-git-pr-flow | ./scripts/check-git-pr-flow.sh |
| check-gold-blueprint | ./scripts/check-gold-blueprint.sh |
| check-memory-yaml | ./scripts/check-memory-yaml.sh |
| check-orchestrator-gaps | ./scripts/audit-state-machine-contract.sh, ./scripts/check-claude-adapter.sh, ./scripts/check-orchestrator-gaps.sh |
| check-parallel-locks | ./scripts/check-parallel-locks.sh |
| check-skills-runtime | ./scripts/check-skills-runtime.sh |
| check-unix-agent-runtime | ./scripts/check-unix-agent-runtime.sh |
| check-verify-surface | ./scripts/check-verify-surface.sh |
| closer | ./scripts/check-handoff-contract.sh, ./scripts/check-task-dag.sh, ./scripts/cleanup-slice-runtime.sh, ./scripts/closer.sh, ./scripts/git-workflow.sh, scripts/git-workflow.sh |
| compact-agent-memory | ./scripts/compact-agent-memory.py, ./scripts/next-wave.sh |
| compile-blueprint | ./scripts/compile-blueprint.sh |
| dev-loop | sin script directo |
| dev-verify | ./scripts/check-orchestrator-gaps.sh, ./scripts/check-task-dag.sh, ./scripts/check-task-descriptions.sh |
| doctor | ./scripts/check-claude-adapter.sh, ./scripts/orchestrator-doctor.sh |
| next-slice | ./scripts/dev-restart.sh, ./scripts/next-slice.sh, ./scripts/slice-maintain.sh, ./scripts/verify-slice.sh, ./scripts/next-wave.sh, scripts/check-worktree-deps-visible.sh, scripts/ensure-task-worktree.sh, scripts/inspect-task-state.sh, scripts/unix-runtime-env.sh |
| next-wave | ./scripts/next-wave.sh, scripts/ensure-task-worktree.sh, scripts/next-wave.sh |
| official-docs-check | sin script directo |
| phase-execution | ./scripts/next-slice.sh, ./scripts/next-wave.sh |
| phase-gate | ./scripts/phase-gate.sh |
| promote-followup | ./scripts/promote-followup.sh |
| register-followup | ./scripts/register-followup-task.sh |
| revise-slice | ./scripts/bootstrap-registry.sh, ./scripts/check-orchestrator-gaps.sh, ./scripts/compile-blueprint.sh |
| slice-maintain | ./scripts/slice-maintain.sh, ./scripts/check-handoff-contract.sh, ./scripts/check-runtime-logs.sh, ./scripts/inspect-task-state.sh, ./scripts/compact-agent-memory.py |
| verify-journey | ./scripts/verify-journey.sh |
| verify-slice | ./scripts/check-handoff-contract.sh, ./scripts/check-runtime-logs.sh, ./scripts/check-verify-routing.sh, ./scripts/docker-hard-reset.sh, ./scripts/init-verify-slice-handoff.sh, ./scripts/verify-slice-state.sh, ./scripts/verify-slice.sh, scripts/ensure-task-worktree.sh |
| write-handoff | sin script directo |

## Hooks declarados en `.claude/settings.json`

| Evento | Matcher | Hook | Timeout |
| --- | --- | --- | --- |
| PreToolUse | Agent | hook_spawn_budget.py | 15 |
| PreToolUse | Write|Edit|MultiEdit|NotebookEdit | hook_write_scope_guard.py | 15 |
| PostToolUse | Agent | hook_agent_return_ledger.py | 15 |
| PostToolUse | Write|Edit|MultiEdit|Bash|NotebookEdit | hook_update_ledger.py | 15 |
| SubagentStart | - | hook_subagent_start_context.py | 20 |
| SubagentStop | - | hook_capture_subagent_stop.py | 90 |
| SessionStart | - | hook_session_context.py | 20 |
| Stop | - | hook_finalize_deferred_cleanup.py | 15 |
| ConfigChange | - | hook_update_ledger.py | 15 |
| PreCompact | manual|auto | hook_compact_agent_memory.py | 20 |

## Agentes -> contrato/memoria

| Agente | Tipo | Tools | Memoria estructurada | NEXT_STATUS permitido |
| --- | --- | --- | --- | --- |
| blueprint-reviewer | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/blueprint-reviewer/MEMORY.yaml | none |
| closer | mutating | Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/closer/MEMORY.yaml | done, blocked |
| debugger | mutating | Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/debugger/MEMORY.yaml | validator_tester_pending, blocked |
| deployer | mutating | Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/deployer/MEMORY.yaml | ready_for_close, blocked |
| developer | mutating | Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/developer/MEMORY.yaml | validator_tester_pending, blocked |
| document-analyzer | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/document-analyzer/MEMORY.yaml | none |
| main-orchestrator | info-only | Agent(planner, task-planner, developer, validator, tester, debugger, slice-verifier, deployer, closer, blueprint-reviewer, document-analyzer, project-architect, official-docs-researcher, screen-journey-reviewer), Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/main-orchestrator/MEMORY.yaml | none |
| official-docs-researcher | info-only | Read, Glob, Grep, Bash, WebFetch, WebSearch, Skill | orchestrator-state/agent-memory/official-docs-researcher/MEMORY.yaml | none |
| planner | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/planner/MEMORY.yaml | none |
| project-architect | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/project-architect/MEMORY.yaml | none |
| screen-journey-reviewer | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/screen-journey-reviewer/MEMORY.yaml | none |
| slice-verifier | mutating | Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/slice-verifier/MEMORY.yaml | verified_pending_close, needs_debug, blocked |
| task-planner | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/task-planner/MEMORY.yaml | none |
| tester | mutating | Read, Glob, Grep, Bash, Edit, MultiEdit, Write, Skill | orchestrator-state/agent-memory/tester/MEMORY.yaml | ready_for_close, needs_debug, blocked |
| validator | info-only | Read, Glob, Grep, Bash, Skill | orchestrator-state/agent-memory/validator/MEMORY.yaml | none |

## Scripts -> módulos/scripts llamados

| Script | Módulos Python | Scripts referenciados |
| --- | --- | --- |
| allocate-slice-ports.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| audit-agent-reality.py | orchestrator.runtime.runtime_ops | - |
| audit-agent-trailer-vocabulary.py | orchestrator.runtime.runtime_ops | - |
| audit-orchestrator-consistency.py | orchestrator.runtime.runtime_ops | - |
| audit-runtime-surface.sh | orchestrator.runtime.audit_runtime_surface | scripts/python-safe.sh, scripts/unix-runtime-env.sh |
| audit-state-machine-contract.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| audit-template-screen-journey-redactor.py | orchestrator.runtime.runtime_ops | - |
| auto-verify-slice.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| bootstrap-registry.sh | orchestrator.bootstrap.bootstrap_registry | scripts/python-safe.sh |
| check-blueprint-contract.sh | - | scripts/check-blueprint-machine-contract.sh |
| check-blueprint-lossless-flow.sh | orchestrator.runtime.check_blueprint_lossless_flow | scripts/python-safe.sh |
| check-blueprint-machine-contract.sh | orchestrator.runtime.check_blueprint_machine_contract | scripts/python-safe.sh |
| check-claude-adapter.sh | orchestrator.runtime.check_claude_adapter | scripts/python-safe.sh |
| check-design-tokens.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-git-identity.sh | - | - |
| check-git-pr-flow.sh | orchestrator.runtime.check_git_pr_flow | scripts/python-safe.sh |
| check-gold-blueprint.sh | orchestrator.runtime.check_gold_blueprint | scripts/python-safe.sh |
| check-handoff-contract.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-journey-matrix.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-memory-contract.sh | - | scripts/check-memory-yaml.sh |
| check-memory-yaml.sh | - | scripts/unix-runtime-env.sh |
| check-orchestrator-gaps.sh | orchestrator.runtime.check_orchestrator_gaps | scripts/python-safe.sh |
| check-parallel-locks.sh | orchestrator.runtime.check_parallel_locks | scripts/python-safe.sh |
| check-progress-updated.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-python-runtime.py | - | - |
| check-python-runtime.sh | - | scripts/check-python-runtime.py |
| check-runtime-logs.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-skills-runtime.sh | orchestrator.runtime.check_skills_runtime | scripts/python-safe.sh |
| check-staged-deletions.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-task-dag.sh | orchestrator.runtime.check_task_dag | scripts/python-safe.sh |
| check-task-descriptions.sh | orchestrator.runtime.check_task_descriptions | scripts/python-safe.sh |
| check-unix-agent-runtime.sh | orchestrator.runtime.check_unix_agent_runtime | scripts/python-safe.sh, scripts/unix-runtime-env.sh |
| check-verify-routing.sh | - | - |
| check-verify-surface.sh | orchestrator.runtime.check_verify_surface | scripts/python-safe.sh |
| check-wiring-contract.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check-worktree-deps-visible.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| check_design_tokens.py | orchestrator.runtime.runtime_ops | - |
| check_staged_deletions.py | orchestrator.runtime.runtime_ops | - |
| check_web_design_tokens.py | orchestrator.runtime.runtime_ops | - |
| chrome-devtools-isolated-session.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| chrome-mcp-doctor.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup-closed-task-worktrees.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup-deferred-worktrees-loop.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup-deferred-worktrees.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup-merged-pr-branches.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup-slice-runtime.sh | - | scripts/cleanup-slice-runtime.sh, scripts/slice-runtime-lib.sh, scripts/unix-runtime-env.sh. |
| cleanup-worktrees.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup-zombie-task-worktrees.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| cleanup_closed_task_worktrees.py | orchestrator.runtime.runtime_ops | - |
| cleanup_merged_pr_branches.py | orchestrator.runtime.runtime_ops | - |
| cleanup_zombie_task_worktrees.py | orchestrator.runtime.runtime_ops | - |
| closer.sh | orchestrator.runtime.runtime_ops | scripts/cleanup-slice-runtime.sh, scripts/closer.sh, scripts/git-workflow.sh, scripts/python-safe.sh |
| compact-agent-memory.py | orchestrator.runtime.agent_memory_compaction | - |
| compile-blueprint.sh | orchestrator.compiler.compile_blueprint | scripts/python-safe.sh |
| configure-github-pr-cleanup.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| dev-restart.profile.sh | - | scripts/dev-restart.sh. |
| dev-restart.sh | - | scripts/dev-restart.sh, scripts/docker-hard-reset.sh, scripts/slice-runtime-lib.sh |
| docker-hard-reset.sh | - | scripts/docker-hard-reset.sh, scripts/slice-runtime-lib.sh |
| doctor.sh | - | scripts/orchestrator-doctor.sh |
| ensure-task-worktree.sh | - | scripts/ensure-task-worktree.sh, scripts/sync-lifecycle-events.sh |
| generate-api-contracts.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| git-add-slice.sh | orchestrator.lifecycle_event | - |
| git-workflow.sh | - | scripts/check-git-identity.sh, scripts/ensure-task-worktree.sh, scripts/runtime-git-guard.sh |
| init-verify-slice-handoff.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| inspect-task-state.sh | orchestrator.runtime.inspect_task_state | scripts/python-safe.sh |
| journey-closures.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| next-slice.sh | orchestrator.runtime.claim_task | scripts/dev-restart.sh, scripts/python-safe.sh, scripts/unix-runtime-env.sh |
| next-wave.sh | orchestrator.runtime.next_wave | scripts/cleanup-closed-task-worktrees.sh, scripts/cleanup-deferred-worktrees.sh, scripts/cleanup-merged-pr-branches.sh, scripts/cleanup-zombie-task-worktrees.sh |
| orchestrator-doctor.sh | orchestrator.runtime.orchestrator_doctor | scripts/python-safe.sh |
| phase-gate.sh | orchestrator.common | - |
| promote-followup-task.sh | .claude/bin/register_followup_task.py promote | creates blueprint patch request, no direct DAG mutation |
| promote-followup.sh | - | scripts/promote-followup-task.sh |
| python-safe.sh | - | scripts/unix-runtime-env.sh |
| register-followup-task.sh | .claude/bin/register_followup_task.py | follow-up propose/waive/promote contract |
| reset-for-new-project.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| reset-state.sh | - | - |
| run-all-tests.sh | - | scripts/audit-runtime-surface.sh, scripts/bootstrap-registry.sh, scripts/check-blueprint-contract.sh, scripts/check-blueprint-machine-contract.sh |
| run-tests-one-by-one.py | pytest | portable per-file timeout runner for macOS/Linux/WSL2 |
| run-golden-e2e.sh | orchestrator.bootstrap.bootstrap_registry, orchestrator.compiler.compile_blueprint | scripts/check-parallel-locks.sh, scripts/check-task-dag.sh, scripts/next-wave.sh, scripts/python-safe.sh |
| runtime-git-guard.sh | - | - |
| setup-from-scratch.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| simulate-blueprint-to-claude-flow.sh | - | scripts/bootstrap-registry.sh, scripts/check-blueprint-machine-contract.sh, scripts/check-claude-adapter.sh, scripts/check-gold-blueprint.sh |
| slice-maintain.sh | orchestrator.runtime.runtime_ops | scripts/check-handoff-contract.sh, scripts/check-runtime-logs.sh, scripts/compact-agent-memory.py, scripts/inspect-task-state.sh |
| slice-clean.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| slice-runtime-lib.sh | - | scripts/dev-restart.sh, scripts/unix-runtime-env.sh |
| smoke-template-profiles.py | orchestrator.runtime.runtime_ops | - |
| smoke-trailers-current-state.py | orchestrator.hooks | scripts/smoke-trailers-current-state.py |
| sync-lifecycle-events.sh | orchestrator.common, orchestrator.runtime.memory_yaml | scripts/sync-lifecycle-events.sh |
| sync-main-before-wave.sh | - | scripts/sync_main_before_wave.py |
| sync-runtime-snapshot.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| sync_main_before_wave.py | - | - |
| transition-task.sh | orchestrator.runtime.transition_task | scripts/python-safe.sh |
| unix-runtime-env.sh | - | - |
| update-journey-verification.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| validate-orchestrator-schemas.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh |
| verify-journey.sh | orchestrator.runtime.runtime_ops | scripts/python-safe.sh, scripts/verify-journey.sh |
| verify-slice-state.sh | - | - |
| verify-slice.sh | orchestrator.runtime.runtime_ops | scripts/docker-hard-reset.sh, scripts/init-verify-slice-handoff.sh, scripts/inspect-task-state.sh, scripts/python-safe.sh |

## Docs -> referencias internas

| Documento | Uso | Caller directo |
| --- | --- | --- |
| `docs/README.md` | Índice humano de documentación. | humano |
| `docs/CHEATSHEET.md` | Operación diaria: inputs, prompts, compile/bootstrap, skills y checks. | humano |
| `docs/ORCHESTRATOR.md` | Manual canónico del runtime DAG final. | `README.md`, `.claude/CLAUDE.md`, humano |
| `docs/CALL_MATRIX.md` | Matriz de cableado antes de borrar/mover ficheros. | humano |
| `docs/prompts/README.md` | Índice de prompts para preparar `inputs/BLUEPRINT.md`. | humano |
| `docs/prompts/01-generate-blueprint-from-inputs.md` | Prompt para generar `inputs/BLUEPRINT.md` desde blueprint base + ZIP/prototipo. | humano/modelo |
| `docs/prompts/02-audit-blueprint-before-bootstrap.md` | Prompt para auditar/corregir `inputs/BLUEPRINT.md` antes de compile/bootstrap. | humano/modelo |
| `docs/templates/README.md` | Índice de plantillas neutrales de blueprint. | prompts, humano |
| `docs/templates/blueprint-gold/BLUEPRINT.template.md` | Forma gold esperada para un blueprint real. | prompts, checks, tests |
| `docs/templates/blueprint-smoke/BLUEPRINT.template.md` | Fixture mínimo de compilación/bootstrap. | checks, tests |

Regla de limpieza: si un `.md` no aparece aquí y no está referenciado por `README.md`, `.claude/CLAUDE.md`, una skill, un test o un checker, puede considerarse candidato a borrado. No borres prompts, templates ni esta matriz sin actualizar los callers.
