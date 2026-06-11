# Smoke Blueprint — Orchestrator Smoke Fixture

This smoke blueprint fixture exercises every required orchestrator dimension with runtime-grade language. The prose is human context; fenced YAML blocks are the only machine contract read by the compiler.

```yaml orchestrator
kind: project
project:
  id: PRJ-orchestrator-smoke
  name: Smoke Orchestrator Smoke Blueprint
  description: Smoke orchestrator smoke blueprint used to validate the blueprint compiler and runtime with a real, coherent runtime
    boundary. It exposes an scoped runtime-status contract, typed configuration, deterministic orchestrator state, error handling
    and operator-visible evidence while avoiding hidden manual state, generated artifacts edited by hand or incomplete runtime
    behavior.
  goals:
  - GOAL-001
  non_goals: []
```

```yaml orchestrator
kind: stack
stack:
  id: STACK-orchestrator-smoke-python
  description: Python runtime profile for the orchestrator smoke fixture. It declares module roots, test command and pr-flow so CI can
    compile, bootstrap, validate trailers and exercise the same generated registry/task-pack contract used by larger projects,
    including runtime-grade handoff and evidence paths.
  language: python
  runtime: '3.13'
  module_roots:
  - orchestrator_smoke
  commands:
    test: python -m pytest
  git_workflow:
    mode: pr-flow
  orchestrator:
    parallelism:
      max_parallel_slices: 3
      selection_policy: dependency_order_then_non_conflicting
      intra_wave_conflict_check: true
    locks:
      backend: posix_fcntl_file_locks
      platforms: [linux, darwin]
```

```yaml orchestrator
kind: auxiliary.arc42
items:
- id: ARC-001
  name: Smoke context and quality contract
  description: Smoke arc42 coverage fixture that proves a single blueprint can carry architecture context, domain vocabulary,
    runtime behavior, verification expectations and registry slices without depending on external application documents.
    It gives downstream agents enough human context to understand why runtime status, permissions and state are built in this order.
  logic_focus: all
```

```yaml orchestrator
kind: building_blocks
items:
- id: BB-core
  name: Core runtime settings and status contract
  description: Owns typed runtime settings, deterministic status state, secret-safe configuration and core orchestrator computation. This block is
    the safe foundation before any runtime entrypoint is exposed because every later runtime behavior depends on deterministic configuration
    loading, explicit degraded state and auditable readiness evidence rather than local assumptions.
  path: orchestrator-smoke/core/**
  write_surface:
  - orchestrator-smoke:core
  - orchestrator-smoke:settings
  conflict_group:
  - orchestrator-smoke:core
- id: BB-api
  name: Runtime invocation and operator status contract
  description: 'Owns the scoped runtime-status path, invocation boundary, authorization failure response and runtime wiring required
    for the operator to verify orchestrator readiness. It is deliberately narrow: the route exposes only structured orchestrator status information
    and never becomes an unguarded debug surface or manual control plane.'
  path: orchestrator-smoke/runtime/**
  write_surface:
  - orchestrator-smoke:runtime
  - orchestrator-smoke:entrypoints
  conflict_group:
  - orchestrator-smoke:runtime
```

```yaml orchestrator
kind: logic.domain
items:
- id: DR-001
  name: Production health invariant
  description: Every runtime request observes a deterministic runtime status contract backed by configured services. The service must
    not report readiness from ad hoc development values, hidden manual state or generated runtime artifacts; readiness is
    a product invariant that allows the operator and verifier to trust downstream runtime behavior.
  location: BB-core
  invariant: Every runtime request observes a deterministic runtime status contract backed by configured services.
```

```yaml orchestrator
kind: logic.application
items:
- id: UC-001
  name: Serve authenticated health information
  description: Handles the operator runtime-status request by reading typed settings, checking orchestrator state and returning a structured
    response through the API only after token validation. The use case connects core configuration, state logic, permission
    behavior and UI/read-model output so verification can prove a complete request path.
  location: BB-api
  rules:
  - DR-001
  produces:
  - SCR-001
  - DATA-health-response
```

```yaml orchestrator
kind: logic.journey
items:
- id: J-001
  name: Operator verifies orchestrator readiness
  description: 'The operator opens the runtime-status gate with the configured context token, receives orchestrator status information and can distinguish
    ready, degraded and unauthorized states without hidden manual setup. This journey is intentionally small but complete:
    it gives the runtime, tester and closer a real user-facing path to verify end to end.'
  screens:
  - SCR-001
  steps:
  - Operator opens the runtime-status gate with the configured context token.
  - Service returns orchestrator status information from configured production state.
```

```yaml orchestrator
kind: logic.permission
items:
- id: PG-001
  name: Operator token required
  description: The health route rejects unauthenticated requests using OPERATOR_API_TOKEN and records the failure without
    exposing secrets or relying on user, role or permission tables. The gate demonstrates the operator-only security model
    and ensures even the smallest route has explicit production authorization behavior.
  location: BB-api
  gate: OPERATOR_API_TOKEN
  failure: ERR-001
```

```yaml orchestrator
kind: logic.state
items:
- id: SM-001
  name: Service orchestrator state
  description: Runtime readiness starts at BOOTING, becomes READY after configured checks pass and moves to DEGRADED when
    dependencies fail while still returning structured health output. The state machine makes degraded behavior visible to
    UI and tests instead of collapsing missing dependencies into a misleading successful response.
  location: BB-core
  states:
  - BOOTING
  - READY
  - DEGRADED
  transitions:
  - BOOTING->READY
  - READY->DEGRADED
  - DEGRADED->READY
```

```yaml orchestrator
kind: logic.error
items:
- id: ERR-001
  name: Unauthorized operator request
  description: An unauthenticated request is rejected with a structured error and audit-safe detail. The response never leaks
    token values, environment data or internal configuration; it gives testers and agents a concrete error contract to verify
    without weakening the single-operator security boundary.
  location: BB-api
  response: Request is rejected and audited without exposing secrets.
```

```yaml orchestrator
kind: logic.integration
items:
- id: INT-001
  name: Settings source
  description: Typed runtime configuration is loaded from process environment and validated before the API starts. Missing
    required settings prevent false readiness, and the integration contract ensures health behavior is derived from explicit
    configuration rather than local defaults that would drift between developer machines and CI.
  location: BB-core
  provider: environment
  contract: Typed runtime configuration loaded from process environment.
```

```yaml orchestrator
kind: logic.ui
items:
- id: SCR-001
  name: Health response
  description: API response surface for readiness with loading, ready, degraded and unauthorized states. It gives the operator
    observable proof of runtime status and gives the verifier a concrete UI/read-model contract to inspect through the generated
    task pack rather than relying on route names alone.
  location: BB-api
  route: /health
  states:
  - loading
  - ready
  - degraded
  - unauthorized
```

```yaml orchestrator
kind: auxiliary.data
items:
- id: DATA-health-response
  name: Health response read model
  description: Structured runtime-status response contract populated from typed settings and orchestrator state. It gives the runtime path and
    tests a concrete production data shape, including mode, readiness, degraded reason and authorization outcome, while avoiding
    manual rows or example-only payloads as a substitute for runtime behavior.
  location: BB-api
  table: none-api-read-model
```

```yaml orchestrator
kind: auxiliary.adr
items:
- id: AD-001
  name: Blueprint-first smoke runtime fixture
  description: The fixture keeps one human source, one compiled machine input and a generated registry. This decision verifies
    that even smoke projects preserve arc42 descriptions, dependency rationale, resolved specs, durable handoffs and lifecycle
    trailers without reviving the removed secondary source input model.
```


```yaml orchestrator
kind: auxiliary.config
items:
  - id: CFG-001
    name: Smoke runtime configuration contract
    description: >-
      Captures the production configuration surface for the orchestrator smoke fixture: operator context token, runtime invocation root, runtime status settings and test command. The description is intentionally explicit so the compiler can carry configuration meaning into task packs and subagents do not treat environment values as local conveniences or invisible defaults.
    owner: BB-core
    settings_refs: [OPERATOR_API_TOKEN, APP_BIND]
```

```yaml orchestrator
kind: auxiliary.external_refs
items:
  - id: EXT-001
    name: No external provider required
    description: >-
      Records that the orchestrator smoke fixture has no network provider dependency beyond process environment and local HTTP behavior. This still matters to the orchestrator because the absence of external providers is a deliberate production boundary, not missing analysis, and verification must prove readiness without pretending that provider data exists.
    freshness:
      verified_at: "2026-06"
      revalidate_before_implementation: false
```

```yaml orchestrator
kind: auxiliary.risks
items:
  - id: RISK-001
    name: False readiness and secret exposure risk
    description: >-
      Captures the two risks that matter in the orchestrator smoke fixture: reporting READY before typed settings are valid, and leaking operator context token or environment values through status or error responses. The slice handoffs and evidence must prove that both risks are addressed by state transitions, authorization checks and safe response bodies.
    mitigations: [DR-001, PG-001, ERR-001, SM-001]
```

```yaml orchestrator
kind: auxiliary.glossary
items:
  - id: GLOSS-001
    name: Orchestrator smoke fixture vocabulary
    description: >-
      Defines the terms used by agents and tests for the fixture: operator context token, runtime-status response, orchestrator state, degraded state, authorization failure, typed settings, durable handoff and evidence path. Keeping this vocabulary structured prevents task packs from reducing the slice to runtime IDs without orchestrator meaning.
    terms: [operator_token, health_response, readiness_state, degraded_state, authorization_failure, typed_settings, handoff, evidence]
```

```yaml orchestrator
kind: auxiliary.verification
items:
- id: VER-001
  name: Health contract verification
  description: Automated verification proves the runtime-status gate requires the operator context token, reads configured orchestrator state
    and returns structured runtime information only. It also checks that unauthorized behavior is explicit, degraded state
    is visible and the task can produce durable evidence for SubagentStop trailer validation.
  mode: automated
  assertion: Health endpoint requires the operator context token and returns only configured production orchestrator status information.
```

```yaml orchestrator
kind: registry.slices
items:
- id: SLICE-F0-001
  title: Core settings and orchestrator state foundation
  description: Implementa el contrato base DR-001, SM-001 e INT-001 para que la aplicación tenga configuración tipada,
    estados de readiness explícitos y una superficie de salud verificable antes de habilitar cualquier endpoint
    funcional. La tarea debe producir código y pruebas que demuestren que la salud se deriva de settings reales,
    estado controlado y comportamiento degradado observable, no de valores implícitos.
  dependency_rationale: No tiene dependencias de slice porque crea la raíz de configuración, estado y contrato de
    salud que las rutas posteriores consumen. Debe ejecutarse primero para que la slice de API pueda leer una fuente
    de settings validada y una máquina de readiness ya definida en lugar de duplicar esa lógica.
  phase: F0
  type: foundation
  arc42_refs:
  - ARC-001
  implements:
  - DR-001
  - SM-001
  - INT-001
  builds:
  - BB-core
  depends_on: []
  verifies:
  - VER-001
  risk: medium
  verify_mode: automated
  depends_on_rationale: {}
- id: SLICE-F1-001
  title: Authenticated health API route
  description: Implementa UC-001, PG-001, ERR-001, J-001, SCR-001 y DATA-health-response creando la ruta productiva
    /health protegida por token, conectada al contrato de readiness y preparada para evidenciar estados reales.
    La task debe entregar una frontera HTTP verificable, respuestas estructuradas y evidencia de autorización sin
    datos sintéticos ni atajos de desarrollo.
  dependency_rationale: Depende de SLICE-F0-001 porque la ruta /health solo puede exponerse después de existir settings,
    estado de readiness y contrato de integración con entorno. Esa dependencia evita que la API duplique lógica
    de configuración o declare readiness antes de que el bloque core pueda sostenerla de forma verificable.
  phase: F1
  type: api
  arc42_refs:
  - ARC-001
  implements:
  - UC-001
  - PG-001
  - ERR-001
  - J-001
  - SCR-001
  - DATA-health-response
  builds:
  - BB-api
  depends_on:
  - SLICE-F0-001
  depends_on_rationale:
    SLICE-F0-001: This slice depends on the foundation slice because the authenticated runtime path and API boundary require
      typed settings, runtime status contract and orchestrator state before runtime behavior can be safely exposed. The dependency
      preserves a single source for readiness logic and keeps authorization tests grounded in the already compiled
      core contract.
  verifies:
  - VER-001
  risk: medium
  verify_mode: automated
```
