# orchestrator-AnyStack — Blueprint gold del orquestador final

Este documento es el contrato reusable del orquestador. No describe una aplicación de negocio; describe el runtime DAG, skills-only, agentes, hooks, memoria, verificación y cierre que cualquier stack puede adoptar.

## project

```yaml orchestrator
kind: project
id: PROJ-ANYSTACK
name: orchestrator-AnyStack
description: orchestrator-AnyStack es el blueprint gold neutral de un orquestador blueprint-first y skills-only para Claude Code. Su objetivo
  es convertir un BLUEPRINT.md humano y completo en un runtime ejecutable por DAG explícito, con registry, task-dag,
  task-packs, memoria YAML, hooks, subagentes, trailers y cierre por PR. El paquete no representa una aplicación
  de negocio; representa el contrato reusable que cualquier aplicación puede adoptar para ejecutar slices con trazabilidad,
  locks, verificación real y control de lifecycle. La autoridad permanece en el blueprint, los scripts generan el
  runtime y los hooks validan las transiciones solicitadas por los trailers.
goals:
- single blueprint authority
- explicit DAG execution
- skills-only slash runtime
- real evidence gates
- portable Linux and macOS operation
non_goals:
- business application code
- provider-specific product workflows
- untracked lifecycle edits
```

## stack

```yaml orchestrator
kind: stack
id: STACK-ANYSTACK
name: Claude Code orchestrator runtime
description: El stack del blueprint gold de orchestrator-AnyStack usa Python y shell POSIX para compilar el blueprint, generar artefactos,
  validar contratos y gobernar el runtime. Claude Code aporta project skills, subagents, hooks, settings and project
  memory. El runtime evita superficies slash duplicadas y conserva solo skills como entrada slash, mientras los scripts mantienen
  una superficie determinista para CI, operadores humanos y hooks. El contrato incluye locks POSIX, aislamiento
  por TASK_ID, limpieza de worktrees, evidencia real y operativa en Linux y Darwin/macOS.
runtime:
  python: 3.13-compatible
  shell: bash posix-portable
  claude_code: project skills, subagents, hooks, memory rules
orchestrator:
  parallelism:
    max_parallel_slices: 3
    selection_policy: dependency_order_then_non_conflicting
    intra_wave_conflict_check: true
    claim_rechecks_active_conflicts: true
  locks:
    backend: posix_fcntl_file_locks
    platforms:
    - linux
    - darwin
  slash_runtime: project_skills_only
```

## auxiliary.arc42

```yaml orchestrator
kind: auxiliary.arc42
items:
- id: ARC-001
  name: Source and runtime authority
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la arquitectura de autoridad
    entre blueprint, compiled input, registry, DAG y hooks con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: ARC-002
  name: Agent and trailer lifecycle boundary
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la separación entre prompts
    de agentes, trailers y mutación real ejecutada por SubagentStop con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: ARC-003
  name: Verification and closure boundary
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la frontera entre implementación,
    pruebas, verificación real, closer, PR flow y cleanup con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
```

## building_blocks

```yaml orchestrator
kind: building_blocks
items:
- id: BB-compiler
  name: Lossless compiler
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el compilador lossless-by-reference
    que preserva snapshot, secciones, bloques, source map y contrato de máquina con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  type: runtime
  paths:
  - orchestrator/compiler/**
  - orchestrator-state/compiled/**
  - scripts/compile-blueprint.sh
  write_surface:
  - compiler
  - compiled-input
  conflict_group:
  - compiler
  - compiled-input
- id: BB-dag-runtime
  name: DAG runtime
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el registry canónico,
    task-dag, locks, next-wave, next-slice, runtime-state y task-packs con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  type: runtime
  paths:
  - orchestrator/bootstrap/**
  - orchestrator/runtime/**
  - orchestrator/rules/**
  - orchestrator-state/tasks/**
  - orchestrator-state/memory/**
  - scripts/**
  write_surface:
  - registry
  - task-dag
  - runtime-state
  - memory-yaml
  conflict_group:
  - registry
  - task-dag
  - runtime-state
  - memory-yaml
- id: BB-claude-adapter
  name: Claude Code adapter
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define subagentes, skills, settings,
    hooks, rules y memoria de proyecto para Claude Code con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
  type: adapter
  paths:
  - .claude/agents/**
  - .claude/skills/**
  - .claude/rules/**
  - .claude/bin/**
  - .claude/settings.json
  - .claude/orchestrator-contract.json
  - orchestrator/hooks/**
  write_surface:
  - claude-adapter
  - hooks
  - agent-prompts
  conflict_group:
  - claude-adapter
  - hooks
- id: BB-verification
  name: Verification gates
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación UI/backend
    real y la matriz de evidencias aceptada por slice-verifier con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  type: runtime
  paths:
  - orchestrator/runtime/verify_requirements.py
  - orchestrator/runtime/check_verify_surface.py
  - .claude/skills/verify-slice/**
  - .claude/agents/slice-verifier.md
  - scripts/check-verify-surface.sh
  write_surface:
  - verify-slice
  - evidence-contract
  conflict_group:
  - verify-slice
  - evidence-contract
- id: BB-close-flow
  name: Close and PR flow
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el cierre final con report,
    Git workflow, PR, sync de main y limpieza de runtime/worktrees con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  type: runtime
  paths:
  - .claude/agents/closer.md
  - .claude/skills/closer/**
  - scripts/git-*.sh
  - .claude/git-workflows/pr-flow.sh
  - scripts/cleanup-slice-runtime.sh
  - orchestrator-state/tasks/reports/**
  write_surface:
  - closer
  - pr-flow
  - runtime-cleanup
  conflict_group:
  - closer
  - pr-flow
```

## logic.domain

```yaml orchestrator
kind: logic.domain
items:
- id: DR-001
  name: Blueprint is the only human source
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la regla de dominio que
    impide usar estado de chat, archivos derivados o IDs desnudos como autoridad humana con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: DR-002
  name: Lifecycle mutates only through hooks
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la regla que exige que
    los agentes pidan cambios por CLAUDE_TRAILER y que los hooks validen máquina de estados con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
- id: DR-003
  name: Real evidence before close
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la regla que exige evidencia
    real, datos reales o razones not_applicable explícitas antes de verificar y cerrar con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## logic.application

```yaml orchestrator
kind: logic.application
items:
- id: UC-001
  name: Compile blueprint losslessly
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define compilar BLUEPRINT.md
    en orchestrator-input.json, source-map y artefactos lossless sin perder descripciones humanas con intención
    humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  location: BB-dag-runtime
- id: UC-002
  name: Bootstrap registry and DAG
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define generar registry, task-dag,
    task-packs, slices YAML, runtime-state y memoria YAML desde el input compilado con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  location: BB-dag-runtime
- id: UC-003
  name: Select safe DAG wave
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define calcular la siguiente
    wave segura usando dependencias, conflict_groups, write_set, locks y max_parallel_slices con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  location: BB-dag-runtime
- id: UC-004
  name: Claim and execute one slice
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define reclamar una slice lista,
    preparar contexto, activar runtime per-slice y coordinar planner, developer, validator and tester con intención
    humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  location: BB-dag-runtime
- id: UC-005
  name: Inject subagent context
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define inyectar en SubagentStart
    el task-pack, resolved_specs, source_sections, memoria, rutas y plantilla de trailer con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  location: BB-dag-runtime
- id: UC-006
  name: Capture trailers and transitions
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define parsear CLAUDE_TRAILER
    en SubagentStop, validar rol, outcome, next_status, artefactos y transición legal con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  location: BB-dag-runtime
- id: UC-007
  name: Maintain YAML memory
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define actualizar PROGRESS, MEMORY
    por agente, mirrors YAML, handoffs y eventos para continuidad tras clear o sesiones nuevas con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  location: BB-dag-runtime
- id: UC-008
  name: Verify non UI work headlessly
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define verificar backend, DB,
    worker, dependencia, integración o core sin exigir navegador cuando no hay superficie UI real con intención
    humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  location: BB-dag-runtime
- id: UC-009
  name: Verify UI work visually
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define exigir MCP visual/browser/mobile
    cuando la slice toca rutas, pantallas, estados visuales o write_set frontend/mobile con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  location: BB-dag-runtime
- id: UC-010
  name: Register follow-up safely
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define registrar trabajo fuera
    de scope sin expandir la slice activa ni saltarse debugger/retest para defectos in-scope con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  location: BB-dag-runtime
- id: UC-011
  name: Close verified slice
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define generar report, staging
    seguro, PR flow, merge/sync, lifecycle event y cleanup antes de done con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  location: BB-dag-runtime
```

## logic.journey

```yaml orchestrator
kind: logic.journey
items:
- id: J-001
  name: Operator runs backend slice
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el recorrido operativo
    de un usuario que compila, bootstrapea, reclama y verifica una slice sin interfaz visual con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
  entrypoint: /next-slice <TASK_ID>
  expected_result: verified_pending_close before closer
- id: J-002
  name: Operator reviews visual status route
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el recorrido operativo
    de un usuario que valida una pantalla o ruta de estado con MCP visual cuando la slice declara superficie UI
    con intención humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta
    orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en
    cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos específicos.
    Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación para
    que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
  entrypoint: /verify-slice <TASK_ID>
  expected_result: visual evidence recorded
```

## logic.permission

```yaml orchestrator
kind: logic.permission
items:
- id: PERM-001
  name: Static config write guard
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define los permisos que protegen
    .claude, BLUEPRINT activo y estado generado durante una ejecución normal con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: PERM-002
  name: Role scoped writes
  description: 'Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define los permisos de escritura
    por rol: mutadores solo dentro de TASK_ID y info-only solo hallazgos, memoria o handoff permitido con intención
    humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.'
```

## logic.state

```yaml orchestrator
kind: logic.state
items:
- id: SM-001
  name: Task lifecycle
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la máquina todo, ready,
    claimed, in_progress, validator_tester_pending, needs_debug, ready_for_close, verified_pending_close, done and
    blocked con intención humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md
    hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable
    en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos específicos.
    Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación para
    que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
  states:
  - todo
  - ready
  - claimed
  - in_progress
  - validator_tester_pending
  - needs_debug
  - ready_for_close
  - verified_pending_close
  - done
  - blocked
- id: SM-002
  name: Journey verification gate
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el estado de journeys
    pendientes que bloquea solo slices que cierran o dependen de ese journey específico con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
  states:
  - pending
  - verified
  - waived
  - issues_found
```

## logic.error

```yaml orchestrator
kind: logic.error
items:
- id: ERR-001
  name: Illegal transition
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el error producido cuando
    un trailer intenta una transición no permitida por state-machine.yaml con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: ERR-002
  name: Insufficient evidence
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el error producido cuando
    verify-slice no aporta datos reales, comandos reales, evidencia, persistencia o logs limpios con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
```

## logic.integration

```yaml orchestrator
kind: logic.integration
items:
- id: INT-CLAUDE
  name: Claude Code project runtime
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la integración con .claude/skills,
    .claude/agents, settings hooks, project memory and rules con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: INT-GIT
  name: Git and PR workflow
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la integración con ramas
    por TASK_ID, staging seguro, PR, merge, main sync y lifecycle event durable con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: INT-RUNTIME
  name: Local runtime boundary
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la integración genérica
    con Docker/Rancher/compose/ports cuando un stack concreto declara esos artefactos con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## logic.ui

```yaml orchestrator
kind: logic.ui
items:
- id: SCR-001
  name: Operator status route
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la ruta visual genérica
    de estado del orquestador para mostrar DAG, slice activa, logs limpios, memoria y próximos pasos cuando un proyecto
    declara UI con intención humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md
    hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable
    en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos específicos.
    Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación para
    que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
  route: /orchestrator/status
  required_states:
  - loading
  - empty
  - error_network
  - error_validation
  - permission_denied
  - success
```

## auxiliary.data

```yaml orchestrator
kind: auxiliary.data
items:
- id: DATA-registry
  name: Registry data
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el contrato JSON/YAML
    de tasks, statuses, dependencies, locks, source refs, resolved specs and evidence refs con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
- id: DATA-memory
  name: YAML memory data
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el contrato de PROGRESS,
    project-context, task-index, handoff-index y MEMORY por agente con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: DATA-evidence
  name: Evidence data
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el contrato de evidencia
    por TASK_ID, incluyendo comandos reales, logs, artefactos y razones not_applicable con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## auxiliary.config

```yaml orchestrator
kind: auxiliary.config
items:
- id: CFG-001
  name: Claude adapter config
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la configuración .claude
    de agentes, skills, hooks, settings, schemas and rules con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: CFG-002
  name: Runtime environment config
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define variables de entorno,
    root canónico, worktree root, task id, task pack, compose project and Python entrypoint con intención humana
    completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
```

## auxiliary.verification

```yaml orchestrator
kind: auxiliary.verification
items:
- id: VER-F0
  name: Foundation runtime verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    1 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F1A
  name: Compiler verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    2 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F1B
  name: Registry DAG verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    3 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F2
  name: Skills runtime verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    4 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F3
  name: Subagent hook verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    5 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F4
  name: Memory handoff verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    6 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F5
  name: Backend verification contract
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    7 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F6
  name: Follow-up verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    8 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F7
  name: Close flow verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    9 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F8
  name: Visual route verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    10 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: VER-F9
  name: Doctor package verification
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la verificación real número
    11 del runtime DAG, con comandos ejecutados, artefactos observados, logs limpios, datos reales o razón explícita
    y evidencia durable con intención humana completa, límites operativos, evidencia verificable y trazabilidad
    desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs y reports.
    Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores externos
    específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios de aceptación
    para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
```

## auxiliary.adr

```yaml orchestrator
kind: auxiliary.adr
items:
- id: ADR-001
  name: Skills-only slash surface
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la decisión de usar project
    skills como única superficie slash, sin superficie Markdown duplicada con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: ADR-002
  name: Central state machine
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la decisión de mantener
    state-machine.yaml como única autoridad de transiciones con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto.
- id: ADR-003
  name: Lossless references
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la decisión de conservar
    snapshot, sections, blocks and refs para no perder intención humana con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## auxiliary.risks

```yaml orchestrator
kind: auxiliary.risks
items:
- id: RISK-001
  name: Environment drift
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el riesgo de ejecutar
    con variables de entorno antiguas, mitigado por root canónico y scripts que resetean contexto con intención
    humana completa, límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json,
    registry.json, task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender
    de una aplicación de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades,
    invariantes, errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG
    sin inventar contexto.
- id: RISK-002
  name: Evidence inflation
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el riesgo de aceptar texto
    sin prueba real, mitigado por verify-slice UI/backend matrix and hook enforcement con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## auxiliary.glossary

```yaml orchestrator
kind: auxiliary.glossary
items:
- id: TERM-DAG
  name: Explicit DAG
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el grafo dirigido acíclico
    que ordena slices, dependencias, paralelismo seguro y locks con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: TERM-TRAILER
  name: CLAUDE_TRAILER
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define el bloque final emitido
    por un agente para solicitar outcome y NEXT_STATUS bajo contrato con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## auxiliary.external_refs

```yaml orchestrator
kind: auxiliary.external_refs
items:
- id: REF-CLAUDE-SKILLS
  name: Claude Code skills docs
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la referencia oficial
    para project skills con SKILL.md como entrypoint y única superficie slash del proyecto con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
- id: REF-CLAUDE-SUBAGENTS
  name: Claude Code subagent docs
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la referencia oficial
    para subagentes con YAML frontmatter, tools, permissionMode, memory and hooks con intención humana completa,
    límites operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto.
```

## registry.slices

```yaml orchestrator
kind: registry.slices
items:
- id: SLICE-F0-001
  phase: F0
  title: Foundation runtime state, locks and memory
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Foundation runtime
    state, locks and memory como unidad ejecutable del DAG con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto. Incluye criterios
    de aceptación, escritura permitida, superficie de verificación, relación con agentes y prueba real requerida
    antes de permitir cierre.
  dependency_rationale: Foundation runtime state, locks and memory es la raíz del DAG porque crea directorios, locks,
    memoria y autoridad mínima para que las demás slices lean un contrato coherente. Esta dependencia explícita
    evita que una terminal paralela consuma artefactos incompletos y documenta por qué el runtime puede arrancar
    sin esperar trabajo previo.
  depends_on: []
  depends_on_rationale: {}
  implements:
  - UC-001
  - DR-001
  builds:
  - BB-dag-runtime
  verifies:
  - VER-F0
  closes_journeys: []
  arc42_refs:
  - ARC-001
  building_block_refs:
  - BB-dag-runtime
  write_set:
  - orchestrator-state/**
  - orchestrator/rules/**
  - .claude/settings.json
  - .claude/orchestrator-contract.json
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - registry
  - runtime-state
  - memory-yaml
  risk: high
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F1-001
  phase: F1
  title: Lossless blueprint compiler and source maps
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Lossless blueprint
    compiler and source maps como unidad ejecutable del DAG con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto. Incluye criterios
    de aceptación, escritura permitida, superficie de verificación, relación con agentes y prueba real requerida
    antes de permitir cierre.
  dependency_rationale: Lossless blueprint compiler and source maps depende de SLICE-F0-001 porque necesita artefactos
    generados, locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón es parte del
    blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave, planner
    y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F0-001
  depends_on_rationale:
    SLICE-F0-001: Depende de SLICE-F0-001 porque Lossless blueprint compiler and source maps consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-001
  builds:
  - BB-compiler
  verifies:
  - VER-F1A
  closes_journeys: []
  arc42_refs:
  - ARC-001
  building_block_refs:
  - BB-compiler
  write_set:
  - orchestrator/compiler/**
  - orchestrator-state/compiled/**
  - BLUEPRINT.md
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - compiler
  - compiled-input
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F1-002
  phase: F1
  title: Registry, DAG projection and parallel locks
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Registry, DAG
    projection and parallel locks como unidad ejecutable del DAG con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto. Incluye criterios de aceptación, escritura permitida, superficie de verificación, relación con agentes
    y prueba real requerida antes de permitir cierre.
  dependency_rationale: Registry, DAG projection and parallel locks depende de SLICE-F1-001 porque necesita artefactos
    generados, locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón es parte del
    blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave, planner
    y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F1-001
  depends_on_rationale:
    SLICE-F1-001: Depende de SLICE-F1-001 porque Registry, DAG projection and parallel locks consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-002
  - UC-003
  builds:
  - BB-dag-runtime
  verifies:
  - VER-F1B
  closes_journeys: []
  arc42_refs:
  - ARC-001
  building_block_refs:
  - BB-dag-runtime
  write_set:
  - orchestrator/bootstrap/**
  - orchestrator/runtime/**
  - orchestrator-state/tasks/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - registry
  - task-dag
  - locks
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F2-001
  phase: F2
  title: Project skills-only slash runtime
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Project skills-only
    slash runtime como unidad ejecutable del DAG con intención humana completa, límites operativos, evidencia verificable
    y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs, handoffs
    y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta ni de proveedores
    externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables y criterios
    de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto. Incluye criterios de
    aceptación, escritura permitida, superficie de verificación, relación con agentes y prueba real requerida antes
    de permitir cierre.
  dependency_rationale: Project skills-only slash runtime depende de SLICE-F1-002 porque necesita
    artefactos generados, locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón
    es parte del blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave,
    planner y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F1-002
  depends_on_rationale:
    SLICE-F1-002: Depende de SLICE-F1-002 porque Project skills-only slash runtime consume su contrato de runtime,
      sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs, trailers,
      verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para que planner,
      next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-003
  - DR-001
  builds:
  - BB-claude-adapter
  verifies:
  - VER-F2
  closes_journeys: []
  arc42_refs:
  - ADR-001
  building_block_refs:
  - BB-claude-adapter
  write_set:
  - .claude/skills/**
  - .claude/rules/07-skills-runtime.md
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - claude-adapter
  - skills
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F3-001
  phase: F3
  title: Subagent context, hooks and trailer capture
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Subagent context,
    hooks and trailer capture como unidad ejecutable del DAG con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto. Incluye criterios de aceptación, escritura permitida, superficie de verificación, relación con agentes
    y prueba real requerida antes de permitir cierre.
  dependency_rationale: Subagent context, hooks and trailer capture depende de SLICE-F1-002, SLICE-F2-001 porque
    necesita artefactos generados, locks, task-packs, memoria o contratos de agente producidos por esas slices.
    La razón es parte del blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre;
    next-wave, planner y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F1-002
  - SLICE-F2-001
  depends_on_rationale:
    SLICE-F1-002: Depende de SLICE-F1-002 porque Subagent context, hooks and trailer capture consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
    SLICE-F2-001: Depende de SLICE-F2-001 porque Subagent context, hooks and trailer capture consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-005
  - UC-006
  - DR-002
  builds:
  - BB-claude-adapter
  verifies:
  - VER-F3
  closes_journeys: []
  arc42_refs:
  - ARC-002
  building_block_refs:
  - BB-claude-adapter
  write_set:
  - .claude/agents/**
  - orchestrator/hooks/**
  - .claude/bin/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - agents
  - hooks
  - trailers
  risk: high
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F4-001
  phase: F4
  title: Memory YAML and handoff continuity
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Memory YAML and
    handoff continuity como unidad ejecutable del DAG con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto. Incluye criterios
    de aceptación, escritura permitida, superficie de verificación, relación con agentes y prueba real requerida
    antes de permitir cierre.
  dependency_rationale: Memory YAML and handoff continuity depende de SLICE-F3-001 porque necesita artefactos generados,
    locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón es parte del blueprint
    gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave, planner y hooks deben
    respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F3-001
  depends_on_rationale:
    SLICE-F3-001: Depende de SLICE-F3-001 porque Memory YAML and handoff continuity consume su contrato de runtime,
      sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs, trailers,
      verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para que planner,
      next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-007
  - DR-002
  builds:
  - BB-dag-runtime
  - BB-claude-adapter
  verifies:
  - VER-F4
  closes_journeys: []
  arc42_refs:
  - ARC-002
  building_block_refs:
  - BB-dag-runtime
  - BB-claude-adapter
  write_set:
  - orchestrator-state/memory/**
  - orchestrator-state/agent-memory/**
  - orchestrator-state/tasks/handoffs/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - memory-yaml
  - handoffs
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F5-001
  phase: F5
  title: Backend verification contract for non UI journey dependencies
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Backend verification
    contract for non UI journey dependencies como unidad ejecutable del DAG con intención humana completa, límites
    operativos, evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json,
    task-dag.json, task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación
    de negocio concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto. Incluye criterios de aceptación, escritura permitida, superficie de verificación, relación con agentes
    y prueba real requerida antes de permitir cierre.
  dependency_rationale: Backend verification contract for non UI journey dependencies depende de SLICE-F4-001
    porque necesita artefactos generados, locks, task-packs, memoria o contratos de agente producidos por esas slices.
    La razón es parte del blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre;
    next-wave, planner y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F4-001
  depends_on_rationale:
    SLICE-F4-001: Depende de SLICE-F4-001 porque Backend verification contract for non UI journey dependencies consume
      su contrato de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar
      task-packs, trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y
      al DAG para que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-008
  - DR-003
  builds:
  - BB-verification
  verifies:
  - VER-F5
  closes_journeys:
  - J-001
  arc42_refs:
  - ARC-003
  building_block_refs:
  - BB-verification
  write_set:
  - orchestrator/runtime/verify_requirements.py
  - orchestrator-state/tasks/evidence/**
  - api/**
  - db/migrations/**
  - workers/**
  - core/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - verify-backend
  - evidence
  risk: high
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F6-001
  phase: F6
  title: Follow-up registration and scope discipline
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Follow-up registration
    and scope discipline como unidad ejecutable del DAG con intención humana completa, límites operativos, evidencia
    verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json, task-packs,
    handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio concreta
    ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes, errores observables
    y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar contexto. Incluye criterios
    de aceptación, escritura permitida, superficie de verificación, relación con agentes y prueba real requerida
    antes de permitir cierre.
  dependency_rationale: Follow-up registration and scope discipline depende de SLICE-F4-001 porque necesita artefactos
    generados, locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón es parte del
    blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave, planner
    y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F4-001
  depends_on_rationale:
    SLICE-F4-001: Depende de SLICE-F4-001 porque Follow-up registration and scope discipline consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-010
  - DR-001
  builds:
  - BB-dag-runtime
  verifies:
  - VER-F6
  closes_journeys: []
  arc42_refs:
  - ARC-002
  building_block_refs:
  - BB-dag-runtime
  write_set:
  - orchestrator/runtime/runtime_ops.py
  - scripts/register-followup-task.sh
  - scripts/promote-followup-task.sh
  - orchestrator-state/tasks/follow-ups/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - followups
  - scope
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F7-001
  phase: F7
  title: Git workflow, PR close and cleanup gates
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Git workflow,
    PR close and cleanup gates como unidad ejecutable del DAG con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto. Incluye criterios de aceptación, escritura permitida, superficie de verificación, relación con agentes
    y prueba real requerida antes de permitir cierre.
  dependency_rationale: Git workflow, PR close and cleanup gates depende de SLICE-F5-001, SLICE-F6-001 porque necesita
    artefactos generados, locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón
    es parte del blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave,
    planner y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F5-001
  - SLICE-F6-001
  depends_on_rationale:
    SLICE-F5-001: Depende de SLICE-F5-001 porque Git workflow, PR close and cleanup gates consume su contrato de
      runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
    SLICE-F6-001: Depende de SLICE-F6-001 porque Git workflow, PR close and cleanup gates consume su contrato de
      runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-011
  - DR-003
  builds:
  - BB-close-flow
  verifies:
  - VER-F7
  closes_journeys: []
  arc42_refs:
  - ARC-003
  building_block_refs:
  - BB-close-flow
  write_set:
  - scripts/git-*.sh
  - scripts/*workflow*.sh
  - orchestrator-state/tasks/reports/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - git
  - pr-flow
  - cleanup
  risk: high
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F8-001
  phase: F8
  title: Operator visual status route and UI verify path
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Operator visual
    status route and UI verify path como unidad ejecutable del DAG con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto. Incluye criterios de aceptación, escritura permitida, superficie de verificación, relación con agentes
    y prueba real requerida antes de permitir cierre.
  dependency_rationale: Operator visual status route and UI verify path depende de SLICE-F5-001 porque necesita
    artefactos generados, locks, task-packs, memoria o contratos de agente producidos por esas slices. La razón
    es parte del blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre; next-wave,
    planner y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F5-001
  depends_on_rationale:
    SLICE-F5-001: Depende de SLICE-F5-001 porque Operator visual status route and UI verify path consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-009
  builds:
  - BB-verification
  - SCR-001
  verifies:
  - VER-F8
  closes_journeys:
  - J-002
  arc42_refs:
  - ARC-003
  building_block_refs:
  - BB-verification
  write_set:
  - frontend/**
  - ui/**
  - app/routes/orchestrator-status/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - ui
  - verify-visual
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
- id: SLICE-F9-001
  phase: F9
  title: Doctor, audit suite and distributable package
  description: Este elemento pertenece al blueprint gold de orchestrator-AnyStack. Define la slice Doctor, audit
    suite and distributable package como unidad ejecutable del DAG con intención humana completa, límites operativos,
    evidencia verificable y trazabilidad desde BLUEPRINT.md hasta orchestrator-input.json, registry.json, task-dag.json,
    task-packs, handoffs y reports. Debe ser reusable en cualquier stack, sin depender de una aplicación de negocio
    concreta ni de proveedores externos específicos. Explica entradas, salidas, responsabilidades, invariantes,
    errores observables y criterios de aceptación para que agentes, hooks y skills ejecuten por DAG sin inventar
    contexto. Incluye criterios de aceptación, escritura permitida, superficie de verificación, relación con agentes
    y prueba real requerida antes de permitir cierre.
  dependency_rationale: Doctor, audit suite and distributable package depende de SLICE-F7-001, SLICE-F8-001 porque
    necesita artefactos generados, locks, task-packs, memoria o contratos de agente producidos por esas slices.
    La razón es parte del blueprint gold y protege el orden real de compilación, bootstrap, verificación y cierre;
    next-wave, planner y hooks deben respetarla antes de autorizar ejecución concurrente.
  depends_on:
  - SLICE-F7-001
  - SLICE-F8-001
  depends_on_rationale:
    SLICE-F7-001: Depende de SLICE-F7-001 porque Doctor, audit suite and distributable package consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
    SLICE-F8-001: Depende de SLICE-F8-001 porque Doctor, audit suite and distributable package consume su contrato
      de runtime, sus locks, sus índices o sus rutas de evidencia. Sin esa base, la slice podría generar task-packs,
      trailers, verificación o cierre sobre estado incompleto. Esta razón humana viaja al registry y al DAG para
      que planner, next-wave y SubagentStart mantengan la trazabilidad tras clear o sesiones nuevas.
  implements:
  - UC-003
  - UC-011
  builds:
  - BB-close-flow
  - BB-dag-runtime
  verifies:
  - VER-F9
  closes_journeys: []
  arc42_refs:
  - ARC-001
  - ARC-003
  building_block_refs:
  - BB-close-flow
  - BB-dag-runtime
  write_set:
  - scripts/check-*.sh
  - tests/**
  - docs/**
  read_set:
  - BLUEPRINT.md
  - orchestrator-state/compiled/orchestrator-input.json
  - orchestrator-state/tasks/registry.json
  - orchestrator-state/tasks/task-dag.json
  conflict_groups:
  - doctor
  - package
  risk: medium
  verify_mode: human
  acceptance:
  - Task pack preserves description, dependency_rationale, source_sections and resolved_specs.
  - Handoff and evidence are scoped to TASK_ID and contain real command output.
  - Logs are clean or not_applicable is explained with a concrete reason.
  evidence:
    required:
    - handoff
    - evidence_file
    - runtime_command_output
    - logs_clean
    - no_unreal_runtime
```
