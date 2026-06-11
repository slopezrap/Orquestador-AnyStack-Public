# Blueprint templates

`docs/templates/` forma parte de la superficie de autoría y validación del orquestador.

| Ruta | Uso |
|---|---|
| `blueprint-gold/BLUEPRINT.template.md` | Forma completa esperada para un blueprint real. Úsalo como referencia cuando generes `inputs/BLUEPRINT.md`. |
| `blueprint-smoke/BLUEPRINT.template.md` | Fixture neutral usado por tests y checkers para probar compile/bootstrap sin depender de una app concreta. |

El runtime compila `inputs/BLUEPRINT.md` por defecto. Las plantillas no se compilan directamente salvo en checks específicos.

