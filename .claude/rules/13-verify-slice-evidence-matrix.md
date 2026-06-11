# Verify-slice evidence matrix

`/verify-slice` verifies the slice, not just a UI route. The compiled field `verification_surface` in `registry.json`, `task-dag.json`, `task-packs/<TASK_ID>.json` and `tasks/slices/<TASK_ID>.yaml` is authoritative.

## UI slices

If `verification_surface.requires_visual_mcp=true`, run real visual verification:

- hard reset or runtime restart when the stack declares it;
- real/provided data;
- browser/mobile MCP evidence using exact-case MCP/tool names;
- loading/empty/error/permission/success states when declared;
- front -> back -> DB persistence and logs;
- `screen-journey-reviewer` when `requires_screen_journey_reviewer=true`.

## Non-UI slices

If `requires_visual_mcp=false`, never invent browser/mobile MCP just because `journey_refs` exists. Use `verification_surface.evidence_matrix`:

| Evidence kind | Real proof |
|---|---|
| `endpoint_service` | hard reset, live server, real HTTP/API/service call, response contract, DB side effect, clean backend logs |
| `migration_ddl_data` | up to head, schema/introspection, indexes/constraints, idempotence, reversible down when applicable |
| `pipeline_worker_queue` | real worker/pipeline/queue run with real/provided input, observed durable output, worker/Rancher/Docker logs |
| `dependency_runtime` | real install/sync, import proof from real venv/runtime, lockfile version/path proof, anti-imposter check |
| `integration_provider` | adapter probe/contract call or explicit not-applicable with reason, provider-health/degradation evidence |
| `core_logic` | real calculation/use-case with real/provided fixtures, DR/UC invariants, boundary/error tests, anti-stub grep |
| `permission_state_error` | allowed/denied gates, legal/illegal transitions, error/degraded payloads, audit evidence |

Every non-UI verification must satisfy `minimum_runtime_proof` and write evidence under `orchestrator-state/tasks/evidence/<TASK_ID>/`.

## Journey references

`journey_refs` and `closes_journeys` are journey-gate metadata. They are not UI ownership. Backend/API/worker/database slices can support a journey without owning a screen. Visual journey closure belongs to `/verify-journey` or to a later UI slice with explicit `logic.ui`/route specs.


## Acceptance contract for backend/no-UI verification

A non-UI slice may not be blocked merely because no browser exists, but it also may not pass with only tests or prose. The `## verify-slice` handoff and durable evidence must include:

```text
MCP_BROWSER: not_applicable:no_ui_surface
VISUAL_CHECK_METHOD: backend
REAL_OR_PROVIDED_DATA_USED: yes
REAL_DATA_SOURCE: <real data/migration/wheel/command source>
NO_STUB_DATA: yes
FLOWS_TESTED: <real commands executed>
DATA_SETUP: <reset/migrations/data/dependency setup>
DATA_CONTRACT_ROWS: <row-count|not_applicable:<reason>>
PERSISTED_DATA_OBSERVED: yes|not_applicable:<reason>
RUNTIME_LOGS_CHECKED: yes
ERROR_LOGS_STATUS: clean
RUNTIME_LOG_ERRORS: 0
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/slice-verifier.json
```

For each `verification_surface.required_evidence_categories[]`, include a matching `EVIDENCE_<CATEGORY>` proof or a concrete `not_applicable:<reason>`. A UI slice cannot use `not_applicable:no_ui_surface`; if `requires_visual_mcp=true`, browser/mobile MCP remains mandatory.
