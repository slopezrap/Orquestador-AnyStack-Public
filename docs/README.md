# Documentación de orchestrator-AnyStack

Esta carpeta contiene la documentación operativa del orquestador final. El estado generado vive en `orchestrator-state/` y la entrada humana canónica vive en `inputs/BLUEPRINT.md`.

| Ruta | Uso |
|---|---|
| `CHEATSHEET.md` | Guía diaria: qué sustituir, dónde poner el blueprint y el ZIP de diseño, qué skills usar y qué checks ejecutar. |
| `ORCHESTRATOR.md` | Manual breve del runtime DAG: autoridad, compilación, bootstrap, agentes, hooks, trailers, memoria YAML, locks, verify-slice y closer. |
| `ORCHESTRATOR_ANYSTACK_GUIDE.md` | Guía interna detallada: explica cada superficie, cada bloque del blueprint, arc42, lógicas, registry slices, agentes, hooks, memoria, verify-slice, PR-flow y adopción. |
| `CALL_MATRIX.md` | Matriz de cableado entre skills, scripts, hooks, agentes, contrato, estado y memoria. Úsala antes de borrar o mover ficheros. |
| `prompts/` | Prompts para generar y auditar `inputs/BLUEPRINT.md` desde un blueprint base, un ZIP/prototipo de diseño y el template de blueprint. |
| `templates/` | Plantillas neutrales de `inputs/BLUEPRINT.md`. Deben permanecer porque los prompts las usan y los checkers validan el template smoke. |

No guardes aquí runtime generado, handoffs, evidencia ni reports. La descripción del producto se concentra en `inputs/BLUEPRINT.md`.

