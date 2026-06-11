# Guía interna de orchestrator-AnyStack

## 1. Propósito

`orchestrator-AnyStack` es un runtime DAG para Claude Code que convierte una especificación humana única en una ejecución controlada por slices, agentes, hooks, memoria YAML y checks. La entrada humana canónica vive en:

```text
inputs/BLUEPRINT.md
```

El diseño visual de apoyo, cuando existe, vive en:

```text
inputs/design/<app-design>.zip
```

El template de formato vive en:

```text
docs/templates/blueprint-gold/BLUEPRINT.template.md
```

El ZIP de diseño y el template no son runtime. Sirven para que el modelo complete un `inputs/BLUEPRINT.md` suficientemente rico. El bootstrap solo consume el JSON compilado desde `inputs/BLUEPRINT.md`.

## 2. Cadena operativa completa

El flujo normal del orquestador es:

```text
inputs/BLUEPRINT.md
  -> ./scripts/compile-blueprint.sh
  -> orchestrator-state/compiled/orchestrator-input.json
  -> ./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
  -> orchestrator-state/tasks/registry.json
  -> orchestrator-state/tasks/task-dag.json
  -> orchestrator-state/tasks/task-packs/<TASK_ID>.json|md
  -> /next-wave
  -> /next-slice <TASK_ID>
  -> SubagentStart
  -> subagentes
  -> CLAUDE_TRAILER
  -> SubagentStop
  -> debugger si tester falla o validator pide cambios in-scope
  -> validator ∥ tester hasta converger o bloquear
  -> slice-maintain cuando tester deja ready_for_close
  -> verify-slice automático
  -> /closer <TASK_ID>
  -> done
```

El operador humano debería usar normalmente solo:

```text
/next-wave
/next-slice <TASK_ID>
/closer <TASK_ID>
```

`verify-slice`, `slice-maintain`, `compact-agent-memory`, `register-followup` y `promote-followup` siguen existiendo como skills manuales, pero el flujo diario intenta automatizar mantenimiento y verificación cuando la slice llega al estado adecuado.

## 3. Mapa de autoridad

| Superficie | Ruta | Autoridad | Quién escribe |
|---|---|---|---|
| Blueprint humano | `inputs/BLUEPRINT.md` | Producto, arquitectura y DAG humano | operador/modelo antes de compilar |
| Diseño de apoyo | `inputs/design/*.zip` | Pantallas, rutas, copy y UX observable | operador |
| Template de blueprint | `docs/templates/blueprint-gold/BLUEPRINT.template.md` | Forma esperada del blueprint gold | mantenedor del orquestador |
| Compiled input | `orchestrator-state/compiled/orchestrator-input.json` | Contrato de máquina para bootstrap | compiler |
| Registry | `orchestrator-state/tasks/registry.json` | Estado canónico de tasks | bootstrap, claim y hooks bajo lock |
| DAG | `orchestrator-state/tasks/task-dag.json` | Topología, dependencias, paralelo y locks | bootstrap |
| Task-pack | `orchestrator-state/tasks/task-packs/<TASK_ID>.json|md` | Contexto operativo de una slice | bootstrap/claim |
| State machine | `orchestrator/rules/state-machine.yaml` | Transiciones legales | configuración estática |
| Contract | `.claude/orchestrator-contract.json` | Roles, trailers y permisos de transición | configuración estática |
| Agentes | `.claude/agents/*.md` | Comportamiento de subagentes | configuración estática |
| Skills | `.claude/skills/<skill>/SKILL.md` | Entradas slash del runtime | configuración estática |
| Hooks | `orchestrator/hooks/*.py` y `.claude/bin/hook_*.py` | Validación y mutación segura | runtime |
| Memoria global | `orchestrator-state/memory/**` | Continuidad compacta del proyecto | hooks/scripts |
| Memoria por agente | `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` | Continuidad del rol | hooks/scripts y agente en su scope |
| Handoff/evidence | `orchestrator-state/tasks/handoffs/**`, `orchestrator-state/tasks/evidence/**` | Comunicación durable por slice | agentes según rol |

Regla central:

```text
Los agentes no editan registry, DAG ni runtime-state directamente.
Los agentes piden transición con CLAUDE_TRAILER.
SubagentStop valida el trailer y muta lifecycle si la transición es legal.
```

## 4. Entrada humana: los tres materiales que recibe el modelo

Para crear un proyecto nuevo se entregan tres materiales al modelo:

1. **Blueprint base, PRD o notas de producto.** Fuente principal para alcance, reglas, roles, datos, lógica, permisos, errores, integraciones, objetivos y verificación.
2. **ZIP de diseño/prototipo.** Fuente auxiliar para pantallas, rutas, layout, componentes, copy visible, navegación, estados visuales y comportamiento UX observable. No se copia como implementación.
3. **Template de blueprint.** Fuente de forma. Normalmente `docs/templates/blueprint-gold/BLUEPRINT.template.md`. El modelo debe respetar su estructura y rellenar todos los bloques necesarios.

El resultado esperado de esa interacción es un único archivo:

```text
inputs/BLUEPRINT.md
```

No se generan documentos paralelos de producto. No se genera estado en `orchestrator-state/` desde el modelo conversacional. El estado se genera con scripts.

## 5. Qué es arc42 dentro del blueprint

arc42 es una forma de describir arquitectura de software de manera estructurada. En este orquestador aparece como `auxiliary.arc42` y usa IDs `A42-*`. Su objetivo es que las decisiones técnicas no queden escondidas en texto libre.

| ID recomendado | Sección | Qué debe explicar |
|---|---|---|
| `A42-01` | Introduction and Goals | Objetivos, stakeholders, drivers y metas de calidad. |
| `A42-02` | Constraints | Restricciones técnicas, legales, de datos, UX, operación y organización. |
| `A42-03` | Context and Scope | Límites del sistema, actores externos, sistemas vecinos e interfaces. |
| `A42-04` | Solution Strategy | Estrategia de solución, trade-offs y patrón arquitectónico principal. |
| `A42-05` | Building Block View | Módulos, capas, servicios, componentes y ownership. |
| `A42-06` | Runtime View | Escenarios dinámicos, jobs, eventos, secuencias y flujos críticos. |
| `A42-07` | Deployment View | Entornos, contenedores, workers, DB, puertos y runtime local/remoto. |
| `A42-08` | Crosscutting Concepts | Auth, seguridad, errores, logging, idempotencia, caching, i18n y observabilidad. |
| `A42-09` | Architecture Decisions | ADRs, alternativas descartadas, consecuencias y estado. |
| `A42-10` | Quality Requirements | Escenarios medibles de performance, resiliencia, seguridad y usabilidad. |
| `A42-11` | Risks and Technical Debt | Riesgos, deuda aceptada, mitigación y slices/follow-ups cuando haga falta. |
| `A42-12` | Glossary | Glosario técnico y de dominio para evitar ambigüedad. |

Cada `A42-*` debe tener impacto en alguna slice mediante `arc42_refs`, `building_block_refs`, `resolved_specs` o `acceptance`. Si una decisión arquitectónica no afecta a ninguna slice ni a ninguna verificación, probablemente está incompleta.

## 6. Bloques obligatorios de `inputs/BLUEPRINT.md`

El blueprint mezcla prosa humana con bloques fenced:

```text
```yaml orchestrator
kind: <kind>
items:
  - ...
```
```

Los kinds que el blueprint gold debe cubrir son:

```text
project
stack
auxiliary.arc42
building_blocks
logic.domain
logic.application
logic.journey
logic.permission
logic.state
logic.error
logic.integration
logic.ui
auxiliary.data
auxiliary.config
auxiliary.verification
auxiliary.adr
auxiliary.risks
auxiliary.glossary
auxiliary.external_refs
registry.slices
```

El compiler extrae esos bloques, crea índices lossless y produce el `orchestrator-input.json` que usa bootstrap.

## 7. `project`

`project` identifica el producto que se va a construir. Debe incluir:

```text
id
name
description
goals
non_goals
stakeholders
success_criteria
constraints
```

Uso dentro del orquestador:

- alimenta `project-context.yaml`;
- aparece en task-packs;
- sirve para que los agentes no pierdan el objetivo global;
- ayuda a detectar que el blueprint no es una plantilla vacía.

## 8. `stack`

`stack` define la tecnología esperada y los comandos reales que el runtime puede invocar o verificar.

Debe incluir, cuando aplique:

```text
frontend framework
backend framework
database
package manager
runtime commands
test commands
verify commands
docker/compose
ports
git_workflow
browser/mobile MCP requirements
observability/log commands
cleanup commands
```

No debe declarar herramientas por costumbre. Cada comando declarado debe ser realista y verificable para la app. Para UI, debe declarar cómo se verifica visualmente. Para no-UI, debe dejar claro cómo se comprueba servicio, DB, worker, pipeline o lógica core.

## 9. `building_blocks`

`building_blocks` define los bloques técnicos o funcionales que después construyen las slices.

Un bloque suele tener:

```text
id: BB-...
name
description
responsibility
owned_paths
interfaces
data
risks
verification
```

Ejemplos de building blocks genéricos:

```text
BB-frontend-shell
BB-api
BB-domain-services
BB-persistence
BB-worker-runtime
BB-observability
BB-auth
BB-integration-adapters
```

Cada slice debe referenciar los bloques que construye o modifica mediante `builds` o `building_block_refs`.

## 10. Domain Logic — `logic.domain`

La Domain Logic contiene reglas de negocio con IDs `DR-*`. Una regla de dominio no depende de la UI ni del framework.

Cada `DR-*` debe explicar:

```text
id
name
description
applies_to
valid_examples
invalid_examples
enforcement_surface
failure_behavior
verification
related_data
related_errors
related_slices
```

Una buena `DR-*` es verificable. Si dice “el sistema debe ser seguro” no es una regla de dominio; si dice “un usuario solo puede modificar recursos de su organización activa y debe recibir permiso denegado cuando la organización no coincide”, sí es una regla verificable.

## 11. Application Logic — `logic.application`

Application Logic usa IDs `AL-*`. Describe casos de uso internos: qué hace el sistema para cumplir un journey o una operación.

Cada `AL-*` debe incluir:

```text
id
name
description
trigger
actor
preconditions
steps
inputs
outputs
permissions
state_changes
data_changes
integrations
failure_paths
observability
verification
related_slices
```

Diferencia importante:

```text
Journey = qué hace y ve el usuario.
Application Logic = qué hace internamente el sistema.
Core Logic = motor especializado o cálculo central.
```

## 12. Core Logic — `CORE-*`

Core Logic no tiene un bloque separado obligatorio en el runtime actual; puede aparecer dentro de `logic.application`, `logic.domain`, `auxiliary.verification` y `registry.slices` como IDs `CORE-*`. Se usa para describir la lógica central especializada del producto.

Cada `CORE-*` debería explicar:

```text
purpose
inputs
outputs
parameters
algorithm_or_steps
edge_cases
domain_rules
errors
data
state
observability
evaluation
slices
```

Si el producto no tiene algoritmo numérico, puede tener core logic de workflow, matching, approval, ranking, generación de informes, consolidación, scheduling, permisos avanzados o reglas de asignación.

## 13. Journey Logic — `logic.journey`

Journey usa IDs `J-*`. Representa recorridos end-to-end de usuarios o actores.

Cada journey debe incluir:

```text
id
actor
objective
preconditions
screens_or_routes
user_actions
system_actions
endpoints_or_jobs
data_read_written
state_transitions
visible_errors
ui_states
application_logic_refs
core_logic_refs
domain_rule_refs
permission_refs
verification
slices
```

`journey_refs` no implica automáticamente UI. Un journey puede ser backend, worker, admin, webhook, batch o API. La superficie real la decide `verification_surface` durante bootstrap.

## 14. Permission Logic — `logic.permission`

Permission Logic usa IDs `AUTH-*`. Define quién puede hacer qué, sobre qué recurso y bajo qué condición.

Cada `AUTH-*` debe tener:

```text
actor_or_role
resource
action
allowed_when
denied_when
enforcement_surface
ui_behavior_when_denied
error_ref
data_needed
observability
verification
```

Todo permiso debe tener allow y deny. Un permiso sin caso denegado no es suficiente para verificar auth.

## 15. State Logic — `logic.state`

State Logic usa IDs `STATE-*`. Describe estados de entidades o procesos de la aplicación, no el lifecycle interno del orquestador.

Cada `STATE-*` debe incluir:

```text
entity_or_process
valid_states
initial_state
terminal_states
allowed_transitions
forbidden_transitions
triggers
permissions
domain_rules
errors
audit_events
verification
```

La máquina de estados del orquestador vive aparte en `orchestrator/rules/state-machine.yaml`. `STATE-*` describe la app que se construirá.

## 16. Error Logic — `logic.error`

Error Logic usa IDs `ERR-*`. Cubre fallos, recuperación y comportamiento visible o técnico.

Cada `ERR-*` debe incluir:

```text
scenario
cause
expected_behavior
visible_message
status_code_if_applicable
state_change
rollback_or_compensation
retry_policy
idempotency_key_if_applicable
observability
verification
```

Debe cubrir camino feliz y casos borde: permiso denegado, datos vacíos, validación fallida, timeout, integración caída, duplicados, estado inválido, conflicto de concurrencia y datos insuficientes para verificar.

## 17. Integration Logic — `logic.integration`

Integration Logic usa IDs `INT-*`. Describe APIs externas, side effects internos, colas, emails, pagos, webhooks, almacenamiento externo, jobs, workers o proveedores.

Cada `INT-*` debe incluir:

```text
trigger
system_or_service
action
payload
response
idempotency
retry_policy
timeout
failure_behavior
data_persisted
audit_event
verification
```

Una integración sin política de fallo no está completa. Si no se puede llamar a un proveedor real en verificación, debe quedar documentada la razón y la evidencia alternativa aceptada.

## 18. UI Logic — `logic.ui`

UI Logic usa IDs `UI-*`. Describe pantallas, rutas y estados visibles.

Cada `UI-*` debe incluir:

```text
screen_or_route
condition
visible_behavior
copy
available_actions
disabled_actions
loading_state
empty_state
error_state
permission_denied_state
success_state
data_required
permission_refs
failure_refs
visual_verification
```

Toda pantalla del ZIP/prototipo relevante debe quedar reflejada aquí si afecta al producto. Si una pantalla necesita backend, debe enlazar con `AL-*`, `DATA-*`, endpoints/jobs y slices.

## 19. Data Logic — `auxiliary.data`

Data Logic usa IDs `DATA-*`. Describe el ciclo de vida de datos, no solo tablas.

Cada `DATA-*` debe explicar:

```text
entity_or_dataset
owner
creation
mutable_fields
immutable_fields
validations
relationships
storage
retention
privacy
audit
indexes_or_constraints
fixtures_or_real_data_for_verify
slices
```

El verificador necesita saber qué filas, documentos, archivos o registros deben existir para considerar real la evidencia.

## 20. Config — `auxiliary.config`

Config define settings, flags, variables de entorno, secretos, puertos, límites, timeouts y cualquier parámetro operativo.

Debe aclarar:

```text
name
purpose
required_or_optional
safe_default
secret_or_non_secret
source
override_policy
validation
verification
```

Nunca debe incluir secretos reales.

## 21. Verification — `auxiliary.verification`

Verification usa IDs `VER-*`, `EVAL-*` y contratos de evidencia. Define cómo se prueba lo construido.

Debe cubrir:

```text
verification_data
commands
browser_or_mobile_mcp
backend proof
DB proof
worker proof
integration proof
logs
screenshots when UI
acceptance evidence
cleanup
blocking criteria
```

En slices UI, el verificador exige MCP visual real. En slices no-UI, exige prueba real headless con evidencia de servicio, DB, worker, pipeline, dependencia, integración o lógica core según lo que tocó la slice.

## 22. ADR — `auxiliary.adr`

ADR registra decisiones relevantes.

Cada ADR debe incluir:

```text
id
decision
context
options_considered
chosen_option
consequences
affected_slices
verification
```

También se usa para resolver discrepancias entre blueprint base y ZIP de diseño.

## 23. Risks — `auxiliary.risks`

Risks describe riesgos técnicos, producto, datos, operación o UX.

Cada riesgo debe incluir:

```text
id
description
impact
likelihood
mitigation
owner
slice_or_followup
verification
```

Un riesgo alto sin mitigación o sin slice relacionada suele ser un gap.

## 24. Glossary — `auxiliary.glossary`

Glossary evita ambigüedad.

Debe definir términos del dominio, abreviaturas, nombres de estados, actores, entidades, métricas y conceptos técnicos usados por las slices.

## 25. External refs — `auxiliary.external_refs`

External refs apunta a documentación oficial, APIs, SDKs, reglamentos, librerías y referencias relevantes.

Cada referencia debe explicar:

```text
id
name
url_or_source
why_needed
used_by
verification_need
```

Para facts volátiles, el agente `official-docs-researcher` puede verificar documentación oficial antes de implementar.

## 26. Registry slices — `registry.slices`

`registry.slices` es la sección que el bootstrap convierte en tasks.

Cada slice debe tener, como mínimo:

```text
id
title
description
dependency_rationale
depends_on
depends_on_rationale
dependency_edges
phase
type
implements
builds
verifies
risk
verify_mode
write_set
read_set
conflict_group
building_block_refs
arc42_refs
journey_refs
permission_refs
state_refs
error_refs
integration_refs
ui_refs
data_refs
observability_refs
evaluation_refs
acceptance
verify
evidence_contract
```

No hay límite artificial de phases, tasks o slices. El modelo debe crear todas las slices necesarias y solo las necesarias. `phase` es una etiqueta de agrupación; el orden real lo define `depends_on`.

## 27. De blueprint a compiled input

`compile-blueprint.sh` crea:

```text
orchestrator-state/compiled/BLUEPRINT.snapshot.md
orchestrator-state/compiled/blueprint-lossless.json|yaml
orchestrator-state/compiled/blueprint-sections.json|yaml
orchestrator-state/compiled/blueprint-blocks.json|yaml
orchestrator-state/compiled/blueprint-manifest.json|yaml
orchestrator-state/compiled/source-map.json
orchestrator-state/compiled/orchestrator-input.json
```

Qué significa cada uno:

| Fichero | Uso |
|---|---|
| `BLUEPRINT.snapshot.md` | Copia exacta del blueprint compilado. |
| `blueprint-sections.*` | Índice de secciones Markdown, líneas, anchors e IDs. |
| `blueprint-blocks.*` | Índice de bloques `yaml orchestrator`, kind, hash e IDs. |
| `blueprint-lossless.*` | Mapa para recuperar contexto humano por referencia. |
| `blueprint-manifest.*` | Manifiesto de compilación y preservación. |
| `source-map.json` | ID a fichero/línea/bloque/kind. |
| `orchestrator-input.json` | Contrato de máquina para bootstrap. |

Invariante:

```text
Cada task y cada resolved_spec deben conservar source_sections y blueprint_lossless_refs.
```

## 28. Bootstrap y artefactos generados

`bootstrap-registry.sh` lee `orchestrator-input.json` y genera:

```text
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/registry.yaml
orchestrator-state/tasks/task-dag.json
orchestrator-state/tasks/task-dag.yaml
orchestrator-state/tasks/runtime-state.json
orchestrator-state/tasks/runtime-state.yaml
orchestrator-state/tasks/task-packs/<TASK_ID>.json
orchestrator-state/tasks/task-packs/<TASK_ID>.md
orchestrator-state/tasks/slices/<TASK_ID>.yaml
orchestrator-state/tasks/task-index.yaml
orchestrator-state/tasks/handoff-index.yaml
orchestrator-state/tasks/lifecycle-events.yaml
orchestrator-state/memory/*.yaml|md
orchestrator-state/agent-memory/<agent>/MEMORY.yaml|md
```

El DAG generado mantiene nodos ligeros de scheduling/paralelismo; el contexto lossless completo permanece en `registry.json`, `task-packs/<TASK_ID>.json|md` y `slices/<TASK_ID>.yaml` para evitar duplicación masiva de blueprint en el ZIP.

El operador no edita esos ficheros a mano. Si hay que cambiar scope, se modifica `inputs/BLUEPRINT.md`, se recompila y se vuelve a bootstrappear.

`bootstrap-registry` rehidrata automáticamente los estados de lifecycle desde `orchestrator-state/tasks/lifecycle-events/<TASK_ID>.json`. Esa carpeta es la señal durable que viaja por PR-flow; `registry.json` y `runtime-state.json` son runtime local regenerable. Si bootstrap detecta estados ya avanzados sin evento durable que pueda restaurarlos, aborta con instrucción de reparación en vez de resetear silenciosamente.

## 29. DAG y paralelismo

El DAG usa `mode: explicit_dag`. Cada nodo representa una slice. Las edges salen de `depends_on`. `next-wave` selecciona tareas listas cuando:

```text
1. todas sus dependencias están done;
2. no hay follow-ups bloqueantes sin triage;
3. no hay journeys pendientes que bloqueen esa rama;
4. no hay conflicto con tasks activas;
5. no hay conflicto intra-wave;
6. se respeta max_parallel_slices.
```

La seguridad paralela depende de:

```text
write_set
read_set
conflict_group
locks
parallel.safe_group
```

## 30. Locks

El backend de locks es:

```text
posix_fcntl_file_locks
```

Se usa en Linux, macOS y WSL2. El runtime protege:

```text
registry.json
runtime-state.json
handoff por TASK_ID
spawn count
lifecycle events
write_set lógico
conflict_group lógico
```

El timeout por defecto de lock está pensado para subagentes paralelos. El hook de `SubagentStop` tiene timeout mayor que el lock timeout para no morir durante una espera válida.

## 31. Máquina de estados del orquestador

La máquina canónica vive en:

```text
orchestrator/rules/state-machine.yaml
```

Flujo normal:

```text
todo -> ready -> claimed -> in_progress -> validator_tester_pending -> ready_for_close -> verified_pending_close -> done
```

Ramas:

```text
validator_tester_pending -> needs_debug
needs_debug -> validator_tester_pending
cualquier estado permitido -> blocked según rol y contrato
```

Solo roles mutadores pueden solicitar transición de lifecycle:

```text
developer
debugger
tester
slice-verifier
deployer
closer
```

Roles informativos pueden producir análisis, handoff o evidencia, pero no deben emitir `NEXT_STATUS` de lifecycle:

```text
main-orchestrator
planner
task-planner
blueprint-reviewer
document-analyzer
project-architect
official-docs-researcher
validator
screen-journey-reviewer
```

## 32. CLAUDE_TRAILER

`CLAUDE_TRAILER` es el contrato por el que un subagente solicita transición o deja resultado formal.

Ejemplo base mutador:

```text
CLAUDE_TRAILER:
AGENT: developer
TASK_ID: <TASK_ID>
OUTCOME: success
NEXT_STATUS: validator_tester_pending
HANDOFF: orchestrator-state/tasks/handoffs/<TASK_ID>.md
EVIDENCE: orchestrator-state/tasks/evidence/<TASK_ID>/developer.json
```

`SubagentStop` valida:

```text
AGENT == agent_type
TASK_ID == CLAUDE_ACTIVE_TASK_ID
required_keys por rol
OUTCOME permitido
NEXT_STATUS permitido
transición legal en state-machine.yaml
artefactos requeridos
verify-slice evidence contract
closer/pr-flow requirements
anti-replay accepted_by_hook
accepted markdown block preserves all contract/global trailer keys; structured handoff YAML is used as compatibility source for older accepted blocks
```

Si algo no cuadra, bloquea o reescribe a `blocked` según el caso.

## 33. Subagentes

Hay 15 agentes:

| Agente | Tipo | Responsabilidad |
|---|---|---|
| `main-orchestrator` | info-only/coordinador | Coordina skills y delegación. Es el único con `Agent`. |
| `planner` | info-only | Prepara contexto de slice, dependencias, locks y plan. |
| `task-planner` | info-only | Descompone trabajo y detecta follow-ups o gaps de planificación. |
| `blueprint-reviewer` | info-only | Revisa calidad del blueprint, bloques, IDs y trazabilidad. |
| `document-analyzer` | info-only | Analiza documentación, source maps y coherencia textual. |
| `project-architect` | info-only | Revisa arquitectura, building blocks, límites y decisiones. |
| `official-docs-researcher` | info-only | Verifica facts volátiles en documentación oficial. |
| `validator` | info-only | Revisa scope, seguridad, arquitectura y contratos. |
| `screen-journey-reviewer` | info-only | Revisa pantallas, rutas, UX y journeys visuales. |
| `developer` | mutating | Implementa una slice dentro de `write_set`. |
| `tester` | mutating | Ejecuta pruebas y decide `ready_for_close`, `needs_debug` o `blocked`. |
| `debugger` | mutating | Corrige el mínimo defecto in-scope y vuelve a test. |
| `slice-verifier` | mutating | Verifica comportamiento real UI/backend antes del cierre. |
| `deployer` | mutating | Aporta evidencia de deploy cuando el stack lo requiere. |
| `closer` | mutating | Cierra en `done` con report, PR-flow y cleanup. |

Todos deben leer task-pack, memoria YAML, state machine y contrato antes de actuar.


### Agent model allocation

Agent frontmatter must use explicit role-optimized aliases; do not use `model: inherit` for project agents.

```text
fable[1m]: developer
opus[1m]: main-orchestrator
opus: planner, blueprint-reviewer, project-architect, validator, debugger, slice-verifier
sonnet: tester, deployer, closer, task-planner, document-analyzer, official-docs-researcher, screen-journey-reviewer
```

`check-claude-adapter` and `check-unix-agent-runtime` enforce this matrix so model drift is caught before execution.


## 34. Skills

Las skills viven en:

```text
.claude/skills/<skill-name>/SKILL.md
```

No hay una carpeta separada de comandos. Las skills son la superficie slash. Las skills deben tener `disable-model-invocation: false` para poder usarse con el Skill tool desde main y subagentes; las skills con efectos laterales delegan en scripts y los hooks conservan la seguridad de lifecycle.

Skills principales:

```text
/compile-blueprint
/bootstrap-registry
/next-wave
/next-slice <TASK_ID>
/closer <TASK_ID>
/verify-slice <TASK_ID>
/slice-maintain <TASK_ID>
/compact-agent-memory
/register-followup
/promote-followup
/revise-slice <TASK_ID>
/check-orchestrator-gaps
/doctor
```

`/verify-slice` sigue existiendo como skill completa, pero `/next-slice` la invoca automáticamente cuando la slice queda lista para verificación formal.

## 35. Hooks

Los hooks están cableados en `.claude/settings.json` y delegan a `.claude/bin/run_hook.sh`, que a su vez lanza wrappers Python en `.claude/bin/`.

| Hook | Propósito |
|---|---|
| `SessionStart` | Inyecta snapshot de estado, ready tasks, contexto y últimos eventos. |
| `SubagentStart` | Inyecta task-pack, memoria, resolved_specs, source_sections y trailer template. |
| `SubagentStop` | Captura trailer, valida contrato y muta lifecycle si procede. |
| `PreToolUse Agent` | Aplica spawn budget. |
| `PreToolUse Write/Edit` | Protege config estática, runtime generado y write_set. |
| `PostToolUse` | Registra ledger y eventos recientes. |
| `PreCompact` | Compacta memoria de agentes antes de compactación manual o automática. |
| `Stop` | Snapshot de sesión y mantenimiento seguro. |
| `ConfigChange` | Ledger de cambios de configuración cuando aplica. |

El launcher de hooks usa `bash` explícito para evitar depender del bit ejecutable del dispatcher. Aun así, el ZIP conserva permisos ejecutables para scripts y wrappers.

## 36. Memoria YAML

La memoria global vive en:

```text
orchestrator-state/memory/
```

Ficheros clave:

| Fichero | Uso |
|---|---|
| `PROGRESS.yaml` | Counts por estado, eventos recientes y spawn budget. |
| `project-context.yaml` | Resumen compacto del proyecto compilado. |
| `source-manifest.yaml` | Fuente activa y artefactos compilados. |
| `blueprint-manifest.yaml` | Manifest lossless. |
| `blueprint-sections.yaml` | Secciones Markdown indexadas. |
| `blueprint-blocks.yaml` | Bloques `yaml orchestrator` indexados. |
| `blueprint-lossless.yaml` | Recuperación de contexto humano por referencia. |
| `project-brief.yaml|md` | Briefing de producto para agentes. |
| `architecture-contract.yaml|md` | Contrato arquitectónico resumido. |
| `stack-profile.yaml` | Stack compilado. |
| `task-dag.yaml` | Espejo YAML del DAG. |
| `execution-graph.yaml` | Vista compacta de ejecución. |
| `decisions.yaml` | Decisiones durables. |
| `risk-register.yaml` | Riesgos durables. |

La memoria por agente vive en:

```text
orchestrator-state/agent-memory/<agent>/MEMORY.yaml
```

Incluye rol, tools, contrato, read order, write contract, trailer contract, native runtime contract, counters, recent events y last trailer.

## 37. Handoff y evidence

Handoff humano:

```text
orchestrator-state/tasks/handoffs/<TASK_ID>.md
```

Handoff estructurado:

```text
orchestrator-state/tasks/handoffs/<TASK_ID>.yaml
```

Evidencia:

```text
orchestrator-state/tasks/evidence/<TASK_ID>/<agent>.json
```

Report de cierre:

```text
orchestrator-state/tasks/reports/<TASK_ID>.md
```

El handoff debe contener secciones por rol. `verify-slice` debe añadir tabla de áreas verificadas, evidencia, esperado, observado, estado y follow-up.

## 38. Verify-slice UI

Una slice UI requiere verificación visual real. Debe probar:

```text
hard reset cuando aplique
datos reales/proporcionados
MCP visual/browser o Dart/Flutter MCP
navegación real
botones y formularios
loading
empty
error
permission denied
success
persistencia front -> back -> DB
logs limpios
capturas/evidencia
```

No puede pasar como backend declarando `not_applicable:no_ui_surface` si `verification_surface.requires_visual_mcp=true`.

## 39. Verify-slice backend/no-UI

Una slice no-UI no necesita navegador, pero debe ser real. Debe declarar:

```text
MCP_BROWSER: not_applicable:no_ui_surface
VISUAL_CHECK_METHOD: backend
NO_STUB_DATA: yes
REAL_DATA_SOURCE: <datos/migraciones/comandos/wheels reales o proporcionados>
FLOWS_TESTED: <comandos reales>
DATA_SETUP: <setup real>
DATA_CONTRACT_ROWS: <real> | not_applicable:<razón>
PERSISTED_DATA_OBSERVED: <real> | not_applicable:<razón>
RUNTIME_LOGS_CHECKED: yes
ERROR_LOGS_STATUS: clean
RUNTIME_LOG_ERRORS: 0
```

La matriz backend cubre:

| Superficie tocada | Prueba real esperada |
|---|---|
| Endpoint/servicio | server vivo, httpx/curl/CLI real, respuesta, DB y logs. |
| Migración/DDL | migración up, esquema real, índices, constraints, idempotencia y down si aplica. |
| Pipeline/worker/cola | worker real con input real/proporcionado, output persistido y logs. |
| Dependencia | sync/install real, import desde venv real, path/version/lockfile y anti-imposter. |
| Integración | probe/adapter real o not_applicable razonado, provider-health y degradación. |
| Core logic | fixtures reales/proporcionados, resultado esperado y reglas DR aplicadas. |
| Permiso/estado/error | allow/deny, transición válida/prohibida, payloads y audit logs. |

## 40. Follow-ups

Un follow-up formal solo existe para trabajo que no cabe razonablemente en la slice activa: fuera de scope, cobertura ausente que exige blueprint nuevo, datos reales ausentes, dependencia externa, scope expansion, write_set externo o decisión humana. No se usa para defectos in-scope ni para arreglos pequeños que caben en el `write_set` actual. Esos se solucionan en la misma slice vía developer/debugger/retest.

Estados típicos:

```text
proposed
waived
promoted_to_blueprint
```

Comandos:

```bash
./scripts/register-followup-task.sh propose --origin-task <TASK_ID> --scope-classification <classification> --repair-decision <followup_required|human_decision_required> --why-not-debugger "<reason>" --files-estimate <n|unknown> --fits-current-write-set <yes|no|unknown> --requires-blueprint-change <yes|no|unknown> --title "<title>" --severity <severity>
./scripts/register-followup-task.sh waive <FOLLOWUP_ID> --reason "<human decision>"
/promote-followup <FOLLOWUP_ID>
```

Promover un follow-up no edita directamente registry ni DAG. Genera patch request para `inputs/BLUEPRINT.md`; después se recompila y bootstrappea.

El runtime rechaza propuestas con `repair_decision=fix_in_current_slice|debugger_retest|mechanical_retry`, sin trigger duro de fuera de slice, o que parezcan un arreglo pequeño dentro del write_set actual.

## 41. PR-flow y closer

`closer` solo opera cuando la task está en:

```text
verified_pending_close
```

En `pr-flow`, `done` exige:

```text
REPORT_READY: yes
GIT_READY: yes
PUSH_READY: yes
GIT_WORKFLOW_READY: yes
PR_READY: yes
MERGED: yes
CANONICAL_MAIN_SYNCED: yes
RUNTIME_CLEANED: yes
WORKTREES_CLEANED: yes
```

El closer no debe cerrar sin report, evidencia, merge, sync de main y cleanup.

## 42. Docker, Rancher y puertos

El runtime no asume un stack concreto. Si el blueprint declara Docker/Compose o runtime local, los scripts pueden gestionar:

```text
COMPOSE_PROJECT_NAME
CLAUDE_COMPOSE_PROJECT_NAME
CLAUDE_FRONTEND_PORT
CLAUDE_BACKEND_PORT
CLAUDE_API_PORT
CLAUDE_DB_PORT
CLAUDE_WORKER_PORT
orchestrator-state/dev-ports/<compose-project>.env
```

Rancher Desktop se detecta por herramientas disponibles en PATH. El runtime también puede operar con Docker Engine o Docker Desktop si `docker compose` funciona.

## 43. Compatibilidad de plataforma

Objetivos soportados:

```text
linux
darwin
wsl2
```

No se soporta PowerShell/CMD como shell objetivo. En Windows se ejecuta dentro de WSL2 con Bash, Python y locks POSIX.

Reglas de portabilidad:

```text
usar LF
conservar +x en entrypoints
usar /usr/bin/env bash o /usr/bin/env python3
no depender de GNU-only cuando macOS no lo trae
usar ${TMPDIR:-/tmp} o mktemp para temporales
no usar rutas de usuario hardcodeadas
mantener nombres exact-case
```

## 44. Checks de salud

Checks esenciales:

```bash
./scripts/check-python-runtime.sh --min-version 3.13
./scripts/check-claude-adapter.sh
./scripts/check-skills-runtime.sh
./scripts/check-task-dag.sh
./scripts/check-parallel-locks.sh
./scripts/check-memory-yaml.sh
./scripts/check-blueprint-lossless-flow.sh
./scripts/check-blueprint-machine-contract.sh
./scripts/check-blueprint-contract.sh
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-verify-surface.sh
./scripts/check-handoff-contract.sh
./scripts/check-git-pr-flow.sh
./scripts/check-unix-agent-runtime.sh
./scripts/check-orchestrator-gaps.sh
./scripts/orchestrator-doctor.sh
```

Smokes:

```bash
./scripts/run-golden-e2e.sh
./scripts/simulate-blueprint-to-claude-flow.sh
```

Tests con timeout portable:

```bash
python3.13 scripts/run-tests-one-by-one.py --timeout 180 tests/test_*.py
```

## 45. Cómo adoptar el orquestador en una app nueva

1. Coloca el ZIP de diseño en `inputs/design/` si existe.
2. Usa `docs/prompts/01-generate-blueprint-from-inputs.md` con blueprint base, ZIP de diseño y template.
3. Guarda la salida como `inputs/BLUEPRINT.md`.
4. Usa `docs/prompts/02-audit-blueprint-before-bootstrap.md` para corregirlo.
5. Ejecuta:

```bash
./scripts/reset-state.sh
./scripts/compile-blueprint.sh inputs/BLUEPRINT.md
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-task-dag.sh
./scripts/check-orchestrator-gaps.sh
```

6. Usa `/next-wave`, `/next-slice <TASK_ID>` y `/closer <TASK_ID>`.

## 46. Cómo auditar un agente

Para revisar un agente:

```bash
sed -n '1,220p' .claude/agents/developer.md
cat orchestrator-state/agent-memory/developer/MEMORY.yaml
python3 - <<'PY'
import json
c=json.load(open('.claude/orchestrator-contract.json'))
print(c['trailer_schema']['roles']['developer'])
PY
```

Comprueba:

```text
name coincide con fichero
tools exact-case
memory: project
permissionMode: bypassPermissions
Skill disponible
Agent solo en main-orchestrator
read order incluye memoria y task-pack
no promete cerrar si no es closer
trailer coincide con contrato
write scope no toca runtime generado a mano
```

## 47. Cómo auditar un hook

Para `SubagentStop`:

```bash
sed -n '1,260p' orchestrator/hooks/hook_capture_subagent_stop.py
sed -n '260,620p' orchestrator/hooks/hook_capture_subagent_stop.py
```

Comprueba:

```text
parsea CLAUDE_TRAILER explícito
usa last_assistant_message como fuente primaria
usa fallback solo si falta mensaje final
valida AGENT y TASK_ID
valida required keys
valida OUTCOME y NEXT_STATUS
valida artefactos
aplica verify-slice guardrails
aplica closer guardrails
consulta state-machine.yaml
escribe bajo lock
actualiza memoria y lifecycle events
```

## 48. Cómo auditar memoria

Ejecuta:

```bash
./scripts/check-memory-yaml.sh
```

Inspecciona:

```bash
cat orchestrator-state/memory/PROGRESS.yaml
cat orchestrator-state/memory/project-context.yaml
cat orchestrator-state/tasks/slices/<TASK_ID>.yaml
cat orchestrator-state/agent-memory/<agent>/MEMORY.yaml
cat orchestrator-state/tasks/handoffs/<TASK_ID>.yaml
```

Busca:

```text
schema_version
kind
updated_at
canonical references
source_sections
blueprint_lossless_refs
read_order
write_contract
trailer_contract
verify_slice_memory_contract
native_runtime_contract
recent_events
last_trailer
```

## 49. Qué no debes hacer

No edites a mano:

```text
orchestrator-state/compiled/**
orchestrator-state/tasks/registry.json
orchestrator-state/tasks/task-dag.json
orchestrator-state/tasks/runtime-state.json
orchestrator-state/tasks/task-packs/**
```

No cierres una task sin:

```text
verify-slice real
handoff actualizado
evidence
report
PR-flow si aplica
cleanup
trailer de closer validado
```

No uses follow-up para evitar arreglar un defecto de la slice activa.


## Active-slice test safety

During an active `/next-slice <TASK_ID>`, tester and verifier must run product/task-pack tests only. The orchestrator maintainer self-tests (`tests/test_*.py`, `scripts/run-all-tests.sh` in full/no-argument mode, `scripts/run-golden-e2e.sh`, `scripts/simulate-blueprint-to-claude-flow.sh`) can reset/compile/bootstrap scheduler state and therefore are blocked when `CLAUDE_ACTIVE_TASK_ID`, `CLAUDE_TASK_ID` or a `SLICE-*` worktree is detected, unless a maintainer sets the explicit override env vars. `scripts/run-all-tests.sh lint` is read-only/static and does not reset, compile or bootstrap state; it is still a maintainer/runtime check, not a substitute for product task-pack tests.

## 50. Conclusión

La forma correcta de entender orchestrator-AnyStack es:

```text
El blueprint conserva intención humana.
El compiler conserva trazabilidad.
El bootstrap genera runtime.
El DAG decide orden y paralelo.
Los task-packs dan contexto a agentes.
Los hooks gobiernan lifecycle.
Los trailers son contrato de transición.
La memoria YAML conserva continuidad.
verify-slice prueba comportamiento real.
closer cierra con evidencia, PR-flow y cleanup.
```

El chat ayuda a razonar e implementar, pero no sustituye a los contratos de máquina ni a los hooks que protegen el lifecycle.

## Root-split / linked worktree guard

When a slice runs in a linked worktree, the worktree is only the code workspace. The scheduler truth remains in the canonical root returned by `scripts/ensure-task-worktree.sh --print-root`. Tracked compatibility blueprint memory JSON mirrors under `orchestrator-state/memory/` are classified as `local_commit_artifacts_only`, not split-brain. Do not inspect, mutate or symlink a local worktree `orchestrator-state/` as authority.

Before resuming a suspicious worktree, run:

```bash
ROOT="$(bash scripts/ensure-task-worktree.sh --print-root)"
bash "$ROOT/scripts/repair-worktree-state.sh" --check "$PWD"
```

If it reports split-brain, archive the local state and resume from canonical:

```bash
bash "$ROOT/scripts/repair-worktree-state.sh" --apply "$PWD"
```

Never create per-file symlinks for `registry.json`, `runtime-state.json`, `task-dag.json` or task-packs. Use the canonical handoff/evidence paths injected by `SubagentStart`; if they are absolute, keep them absolute.

### Git hygiene and hook-safe cleanup

Do not include `Co-Authored-By: Claude ...` or Anthropic noreply trailers in commits. If the last local commit has one, amend the message before push. During `/closer`, do not remove the active task worktree directly; run `scripts/cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active  # task worktrees are deferred even when cleanup runs from canonical root; Stop/next-wave removes after done`. `active_deferred=1` is the safe path because `SubagentStop` still needs the checkout/session alive to record `done`; Stop/next-wave retries deferred cleanup from the canonical root.
