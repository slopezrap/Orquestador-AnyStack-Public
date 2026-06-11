---
name: compact-agent-memory
description: "Compacta la memoria YAML de agentes de orchestrator-AnyStack y archiva eventos antiguos de MEMORY.yaml. Úsala manualmente para mantenimiento de memoria; el runtime también la ejecuta automáticamente antes de /next-wave y mediante hook PreCompact."
argument-hint: "[--all|--agent <agent>] [--apply] [--threshold-lines N]"
user-invocable: true
disable-model-invocation: false
allowed-tools: Bash, Read
---

# /compact-agent-memory

Ejecuta mantenimiento seguro de memoria YAML de agentes. No cambia `registry.json`, `task-dag.json`, `runtime-state.json`, task-packs ni lifecycle.

```bash
./scripts/compact-agent-memory.py $ARGUMENTS
```

Uso recomendado:

```bash
./scripts/compact-agent-memory.py --all --apply --threshold-lines 250
```

La misma compactación se dispara automáticamente:

- antes de `./scripts/next-wave.sh`, salvo `CLAUDE_AUTO_COMPACT_AGENT_MEMORY=0`;
- en el hook `PreCompact` para compactación manual o automática de Claude Code.

Contrato de seguridad:

- entrada humana: `inputs/BLUEPRINT.md`;
- runtime generado leído: `orchestrator-state/compiled/orchestrator-input.json`, `orchestrator-state/tasks/registry.json`, task-pack `resolved_specs` solo como contexto de trazabilidad;
- memoria modificada: `orchestrator-state/agent-memory/<agent>/MEMORY.yaml` y contadores derivados en `orchestrator-state/memory/PROGRESS.yaml` cuando los hooks ya los hayan escrito;
- archivo de respaldo: `orchestrator-state/agent-memory/<agent>/archive/MEMORY.full.<timestamp>.yaml`;
- no toca handoffs/evidence/reports salvo que otro flujo lo haga.
