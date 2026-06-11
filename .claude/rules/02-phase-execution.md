# 02 - Phase and slice execution

Phases are compiled from `registry.slices[].phase` into runtime state. Do not assume a fixed number of phases.

## Pipeline per slice

The executable `/next-slice` pipeline is:

```text
planner -> developer ∥ official-docs-researcher? -> validator ∥ tester -> debugger? -> validator ∥ tester -> slice-maintain -> verify-slice automático
```

1. `/compile-blueprint` after any blueprint edit. This is valid even when generated state is empty.
2. `/bootstrap-registry` after compilation. This is valid when registry/DAG/task-packs do not yet exist, as long as compiled input exists.
3. `/next-wave` lists ready slices using DAG dependencies, active blockers, intra-wave conflicts and `max_parallel_slices`.
4. `/next-slice <TASK_ID>` claims exactly one DAG node under lock.
5. `planner` is blocking and prepares context, locks, resolved specs, acceptance, verification surface and `NEEDS_OFFICIAL_DOCS`.
6. `developer ∥ official-docs-researcher?` run in the same message when docs are required by the planner or by external/version-sensitive scope.
7. `developer` emits `validator_tester_pending`.
8. `validator ∥ tester` run in one message as mandatory parallel review/test. Validator is info-only; tester emits `ready_for_close`, `needs_debug` or `blocked`.
9. If tester leaves `ready_for_close`, `/next-slice` runs `slice-maintain` and invokes the complete `verify-slice` skill automatically.
10. `slice-verifier` emits `verified_pending_close`, `needs_debug` or `blocked`.
11. `/closer <TASK_ID>` remains manual; it reports, commits, runs Git workflow, cleans runtime and emits `done` or `blocked`.

During an active slice, tester/verifier must run product or task-pack tests only. The orchestrator maintainer self-tests (`tests/test_*.py`, `scripts/run-all-tests.sh`, `scripts/run-golden-e2e.sh`, `scripts/simulate-blueprint-to-claude-flow.sh`) are destructive because they reset/compile/bootstrap scheduler state; they are blocked unless explicitly enabled with maintainer-only override env vars.

## Debug loop

Defects covered by the active task pack go to `debugger`. Debugger fixes the smallest safe scope and returns to `validator_tester_pending`; the next cycle must run `validator ∥ tester` together again.

Register a follow-up only when the work cannot reasonably be solved inside the active slice: new IDs/building blocks/routes/tables/journeys, new external dependencies, missing real verification data, scope expansion, work outside the current write_set, or a human decision. Before opening a FU, perform repair triage: if it fits the current write_set, touches only a few files and needs no blueprint/dependency/data/human decision, fix it in the current slice through developer/debugger/retest. Use `./scripts/register-followup-task.sh propose --origin-task <TASK_ID> --scope-classification <classification> --repair-decision <followup_required|human_decision_required> --why-not-debugger <reason> --files-estimate <n|unknown> --fits-current-write-set <yes|no|unknown> --requires-blueprint-change <yes|no|unknown> --title <title> --severity <severity>`; never use follow-ups for `in_scope_defect`, `fix_in_current_slice`, `debugger_retest` or mechanical runtime retries.

## Phase gate

A phase passes only when every task in that phase is `done` or explicitly waived by a human process:

```bash
./scripts/phase-gate.sh <PHASE_ID>
```

A phase gate never edits the blueprint or generated input.

## Parallel wave safety

`/next-wave` may return more than one ready slice, but only after applying the compiled parallel model:

```text
dependencies done
active blockers absent
no intra-wave conflict_group overlap
no intra-wave write_set overlap
within task-dag.parallelism.max_parallel_slices
```

Before starting parallel work, run:

```bash
./scripts/check-parallel-locks.sh
```

Every `next-slice`/`claim_task` still rechecks conflicts under the registry lock. A task that is listed in the same topological layer is not automatically safe to run in parallel unless it is also in a generated safe parallel group.

## Worker checkout and session scope

`next-wave` proposes safe DAG workers; `next-slice` claims exactly one task and prepares the task pack, runtime context and active checkout. Agents must not infer a slice from global phase state, open files or chat history. The active identity is the explicit `TASK_ID` plus `CLAUDE_TASK_PACK`. If task pack, handoff and environment disagree, block and ask the operator to repair runtime state with the scripts rather than proceeding.

Workers run in the checkout prepared for the task. Subagents must not create nested worktrees or switch to another task branch; that would split evidence, runtime logs and lifecycle updates.

