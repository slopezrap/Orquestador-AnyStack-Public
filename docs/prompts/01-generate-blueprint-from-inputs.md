# Prompt 01 — Generar `inputs/BLUEPRINT.md` desde blueprint + diseño + template

```text
Actúa como arquitecto principal de producto, AI engineer senior, technical lead y planificador DAG para orchestrator-AnyStack.

Voy a darte tres materiales:

1. Un blueprint inicial, PRD, notas o especificación de la aplicación. Úsalo como fuente principal de producto, alcance, reglas, módulos, entidades, lógica, roles, permisos, estados, errores, datos, integraciones, auditoría, requisitos no funcionales y criterios de verificación.

2. Un ZIP de diseño/prototipo si existe. Úsalo como apoyo visual para pantallas, rutas, layouts, navegación, componentes, formularios, copy visible, estados loading/empty/error/permission/success, responsive y discrepancias visuales. No copies el ZIP como implementación.

3. Un template de blueprint, normalmente `docs/templates/blueprint-gold/BLUEPRINT.template.md`. Úsalo como contrato de forma: conserva los kinds requeridos, la estructura de bloques, la granularidad de slices, los campos de trazabilidad y el nivel de detalle. No copies ejemplos del template como producto real; rellénalos con la aplicación recibida.

Objetivo: entregar un único archivo completo llamado `inputs/BLUEPRINT.md`, listo para guardarse en `inputs/BLUEPRINT.md` y compilarse con:

./scripts/compile-blueprint.sh
./scripts/bootstrap-registry.sh orchestrator-state/compiled/orchestrator-input.json
./scripts/check-gold-blueprint.sh inputs/BLUEPRINT.md
./scripts/check-blueprint-machine-contract.sh
./scripts/check-task-dag.sh
./scripts/check-verify-surface.sh

No generes documentos paralelos. No generes runtime bajo `orchestrator-state/`. No escribas código de la app.

PASO 1 — Inventario de entradas
- Identifica nombre de app, objetivo, alcance, no alcance, actores, roles, módulos y restricciones.
- Lee el template y úsalo como checklist de forma: todos los kinds requeridos deben aparecer en el resultado.
- Si hay ZIP de diseño, inventaría pantallas, rutas, navegación, formularios, componentes, tablas, dashboards, modales, menús, estados visuales, copy visible y diferencias por rol.
- Si hay conflicto, prioriza el blueprint para comportamiento y el diseño para representación visual. Registra la decisión en `auxiliary.adr`.

PASO 2 — Familias de IDs
Usa A42-*, BB-*, DR-*, AL-*, CORE-*, J-*, AUTH-*, STATE-*, ERR-*, DATA-*, INT-*, UI-*, OBS-*, EVAL-*, VER-* y SLICE-*.
Cada ID debe estar declarado y referenciado. No uses IDs decorativos.

PASO 3 — Bloques obligatorios
Incluye prosa humana suficiente y bloques fenced exactamente como ```yaml orchestrator.
Kinds obligatorios: project, stack, auxiliary.arc42, building_blocks, logic.domain, logic.application, logic.journey, logic.permission, logic.state, logic.error, logic.integration, logic.ui, auxiliary.data, auxiliary.config, auxiliary.verification, auxiliary.adr, auxiliary.risks, auxiliary.glossary, auxiliary.external_refs, registry.slices.
Cada item debe tener `id`, `name` o `title`, y `description` detallada.

PASO 4 — Contratos lógicos
Completa cada DR, AL, CORE, J, AUTH, STATE, ERR, DATA, INT, UI, OBS y EVAL con inputs, outputs, reglas, errores, datos, auditoría, verificación y evidencia real.

PASO 5 — Stack
Declara frontend si existe, backend, DB, package manager, comandos reales de dev/test/verify, puertos, Docker/Compose si aplica, `git_workflow: pr-flow`, MCP visual cuando haya UI, MCP mobile cuando haya mobile, observabilidad y contrato de datos reales.

PASO 6 — `registry.slices` sin límite artificial
No limites el plan a phases, tareas o slices predefinidas. Crea todas las slices necesarias y solo las necesarias. Las phases son etiquetas opcionales de agrupación; el orden real lo define `depends_on` y el DAG.
Cada slice debe tener id, title, description, dependency_rationale, depends_on, dependency_edges, phase, type, implements, builds, verifies, risk, verify_mode, write_set, conflict_group, refs lógicos, acceptance y verify.

PASO 7 — Verificación real
UI/web/mobile: hard reset si aplica, datos reales/proporcionados, MCP visual/mobile, interacción humana, persistencia front->back->DB, logs limpios y evidencia.
Backend/no-UI: MCP_BROWSER not_applicable:no_ui_surface, VISUAL_CHECK_METHOD backend, servidor/comando real, migraciones/worker/dependency proof si aplica, persisted data observed o not_applicable:<razón>, logs limpios.

PASO 8 — Revisión antes de entregar
Corrige placeholders, IDs duplicados, refs huérfanas, journeys sin AL/UI/verify, pantallas sin estados, permisos sin deny, estados sin transiciones prohibidas, errores sin recovery, core sin evaluación, slices sin depends_on/write_set/conflict_group/verify real y contradicciones con el diseño sin ADR.

SALIDA: entrega el `inputs/BLUEPRINT.md` completo, sin explicación externa.

Materiales:
<PEGA AQUÍ EL BLUEPRINT INICIAL O NOTAS>
<ADJUNTA O REFERENCIA EL ZIP DE DISEÑO SI EXISTE>
<PEGA O REFERENCIA EL TEMPLATE docs/templates/blueprint-gold/BLUEPRINT.template.md>
```

