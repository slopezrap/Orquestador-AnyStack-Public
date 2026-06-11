# 01 - Non-negotiables

## Production quality

- Build production-grade code, not demos.
- Do not use fake product data as acceptance evidence.
- No runtime `TODO`, `TBD`, bare `pass`, `NotImplementedError`, incomplete placeholders or stubbed production branches.
- No hardcoded demo responses.
- No secrets in source, blueprint, compiled JSON, task packs, ledgers, reports or evidence.

## Scope discipline

- Work only on the active `TASK_ID`.
- The task title and description are authoritative human scope.
- Implement only IDs in `implements`, `builds`, `verification_refs` and required support code.
- Respect `write_set` and `conflict_groups`.
- Use `/register-followup` only after repair triage proves the work cannot be fixed in the active slice. Small/in-scope fixes go to developer/debugger/retest, not FU.

## Architecture discipline

- Honor `building_blocks` and logic locations.
- Keep domain/application/core logic separate from delivery adapters.
- Shared code belongs in shared modules only after two real users.
- DRY, KISS and YAGNI apply; do not prebuild future slices.

## Evidence discipline

- Tests must prove the task acceptance and verification refs.
- Integration/E2E tests should fail when the owned backend/DB/runtime is down.
- Provider-boundary isolation must be explicit and not confused with product proof.
- Evidence lives under `orchestrator-state/tasks/evidence/<TASK_ID>/` unless the trailer points elsewhere.

## Security discipline

- Validate inputs at boundaries.
- Return structured errors.
- Never log secrets or private data.
- Permission gates declared in `logic.permission` are mandatory.


## Runtime quality defaults

- Keep one responsibility per file. Large files are a signal to split by concern, not by arbitrary line count.
- Public endpoints, use cases, workers and durable scripts must document purpose, inputs, outputs, side effects and error behavior when the target stack expects comments/docstrings.
- Logging must be useful for verify-slice: log operation start/end, correlation IDs, state transitions and typed errors; never log secrets, tokens or private payloads.
- Security basics are always active: environment-based secrets, parameterized persistence calls, explicit CORS/origin policy when web-facing, structured errors, permission gates from `logic.permission`, and no raw stack traces to users.
- Design-token or UI consistency checks are stack-declared. If the blueprint stack declares a design-token enforcer, run it; if not applicable, record why.

## Chain discipline (per slice)

The `/next-slice` chain is non-negotiable:

1. `planner` runs first and blocks implementation until context is ready, including `CONTEXT_READY: yes` and `NEEDS_OFFICIAL_DOCS: yes|no`.
2. `developer ∥ official-docs-researcher?` run in the same assistant message when official documentation is needed. The researcher is conditional and info-only.
3. `validator ∥ tester` run together in one assistant message after developer. Validator is info-only; tester is lifecycle.
4. `debugger` runs only for in-scope defects, then the chain returns to `validator ∥ tester`.
5. Maximum 4 debugger cycles; then block with evidence.
6. `slice-maintain` and full `verify-slice` run automatically after tester reaches `ready_for_close`; `/closer` remains manual after `verified_pending_close`.


## Active-slice test safety

During `/next-slice`, do not run the orchestrator maintainer self-tests or any command that resets/compiles/bootstraps scheduler state as test evidence. Use task-pack/product tests only. Full runtime self-tests belong to maintainer mode outside an active `TASK_ID` and require explicit override env vars.
