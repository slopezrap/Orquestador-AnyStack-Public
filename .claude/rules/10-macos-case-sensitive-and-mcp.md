# 10 - macOS, Unix y nombres exact-case

Este orquestador debe funcionar en Ubuntu/Linux, macOS y Windows mediante WSL2 ejecutando Claude Code dentro de la distribución Linux. Trata todos los paths y nombres operativos como **case-sensitive**, aunque el volumen APFS local sea case-insensitive.

## Tools Claude Code

Usa los nombres exactos documentados en frontmatter, permissions, hooks y prompts:

```text
Read
Glob
Grep
Bash
Edit
MultiEdit
Write
Agent
Skill
WebFetch
WebSearch
NotebookEdit
TaskCreate
TaskGet
TaskList
TaskUpdate
```

No uses variantes como `agent`, `skill`, `webfetch`, `web_search`, `multiEdit` o `subagent` en campos de configuración.

## Subagentes

El `name` de frontmatter es la identidad que reciben hooks como `agent_type`. Usa exactamente:

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
developer
debugger
tester
slice-verifier
deployer
closer
```

Los trailers deben usar `AGENT` con el mismo valor. La única normalización tolerada por el hook es `slice_verifier -> slice-verifier`; no dependas de ella.

## MCP

Cuando un hook o skill mencione MCP, el nombre del server y del tool debe escribirse con el case exacto configurado. En macOS case-sensitive, `Chrome`, `chrome`, `chrome-devtools` y `Chrome-DevTools` pueden no resolver al mismo servidor. No inventes nombres: usa `claude mcp list`/`/mcp` o el settings real antes de llamar herramientas.

## Shell portable

- Usa `bash`, `python3`, `pwd -P`, `git`, `sed`, `awk`, `grep`, `find` con opciones POSIX. En Windows usa WSL2 y rutas Linux; no ejecutes estos scripts desde PowerShell/CMD nativo.
- Evita flags GNU-only si no hay fallback.
- No asumas `realpath`, `readlink -f`, `gdate` o GNU `sed -r` en macOS.
- Los locks usan `fcntl.flock` desde Python y son POSIX para Linux/Darwin.

## Skills del orquestador

Los entrypoints humanos son skills exact-case en kebab-case:

```text
/next-wave
/next-slice
/verify-slice
/closer
/verify-journey
/phase-gate
/register-followup
/promote-followup
/revise-slice
/slice-maintain
```

Si un directorio se llama `.claude/skills/next-slice/SKILL.md`, no crees `.claude/skills/Next-Slice/SKILL.md`, un fichero alternativo para next-slice ni referencias mixtas.
