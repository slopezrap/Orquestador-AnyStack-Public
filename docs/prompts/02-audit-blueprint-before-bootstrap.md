# Prompt 02 — Auditar `inputs/BLUEPRINT.md` antes de bootstrap

```text
Actúa como blueprint-reviewer, validator, project-architect y auditor DAG de orchestrator-AnyStack.

Te voy a dar `inputs/BLUEPRINT.md`, el ZIP de diseño/prototipo si existe y salidas de checkers si ya las tengo.

Objetivo: comprobar que el blueprint alimenta correctamente: inputs/BLUEPRINT.md -> compile-blueprint -> orchestrator-input.json -> bootstrap-registry -> registry.json -> task-dag.json -> task-packs -> SubagentStart -> subagentes -> CLAUDE_TRAILER -> SubagentStop -> verify-slice -> closer.

Debes hacer la revisión punto por punto y corregir el blueprint completo. No entregues solo un diff.

PASO 1 — Valida estructura
Comprueba que existen estos kinds: project, stack, auxiliary.arc42, building_blocks, logic.domain, logic.application, logic.journey, logic.permission, logic.state, logic.error, logic.integration, logic.ui, auxiliary.data, auxiliary.config, auxiliary.verification, auxiliary.adr, auxiliary.risks, auxiliary.glossary, auxiliary.external_refs, registry.slices.
Cada item debe tener `id`, `name` o `title`, y `description` suficiente.

PASO 2 — Valida trazabilidad
Para cada slice responde: qué journey cubre, qué AL implementa, qué CORE toca, qué DR protege, qué AUTH exige, qué STATE cambia, qué ERR maneja, qué DATA crea/modifica/borra, qué INT dispara, qué UI/backend cambia, qué OBS deja, cómo se verifica y qué evidencia queda. Si alguna respuesta no sale del blueprint, corrígelo.

PASO 3 — Valida DAG abierto
Comprueba que no hay límite artificial de phases, tareas o slices; que `depends_on` define el orden real; que no hay ciclos; que `write_set`, `conflict_group`, risk y verify_mode son correctos; y que no hay mega-slices innecesarias.

PASO 4 — Valida diseño/prototipo
Si hay ZIP de diseño, comprueba pantallas, rutas, navegación, formularios, componentes, copy y estados visuales; cada pantalla relevante debe estar en logic.ui, logic.journey y alguna slice; las contradicciones deben quedar en auxiliary.adr.

PASO 5 — Valida verify-slice
UI/web/mobile exige MCP visual/mobile e interacción humana real. Backend/no-UI no fuerza navegador por journey_refs y exige MCP_BROWSER not_applicable:no_ui_surface, VISUAL_CHECK_METHOD backend, datos reales/proporcionados, comando/servidor/worker real, persisted data observed o not_applicable:<razón>, logs limpios.

PASO 6 — Valida checkers
El blueprint corregido debe estar preparado para compile-blueprint, bootstrap-registry, check-gold-blueprint, check-blueprint-lossless-flow, check-blueprint-machine-contract, check-task-dag, check-verify-surface y check-orchestrator-gaps.

SALIDA: devuelve un resumen breve de bloqueantes corregidos y el `inputs/BLUEPRINT.md` completo corregido, listo para guardar en `inputs/BLUEPRINT.md`.

BLUEPRINT actual:
<PEGA AQUÍ inputs/BLUEPRINT.md>

Diseño/prototipo si existe:
<ADJUNTA O REFERENCIA EL ZIP DE DISEÑO>

Errores de checkers si existen:
<PEGA AQUÍ SALIDAS>
```

