# Rule 11 — pr-flow, Rancher runtime and per-slice cleanup

- `pr-flow` is transport plus integration proof. A PR that is only open, queued or waiting for CI is not a closed DAG slice.
- Under `pr-flow`, closer must use `./scripts/git-workflow.sh <TASK_ID>` and may close only after `PR_READY: yes`, `MERGED: yes` and `CANONICAL_MAIN_SYNCED: yes`.
- Do not use `git stash`; do not fallback to `git push origin main`; do not switch workflow unless the compiled stack declares it.
- At slice start, if the compiled stack exposes Docker Compose files, use `./scripts/dev-restart.sh --task <TASK_ID> --soft` before implementation agents need runtime.
- For verification hard reset, use `./scripts/docker-hard-reset.sh --task <TASK_ID>`.
- At close, use `./scripts/cleanup-slice-runtime.sh --task <TASK_ID> --apply --strict` before the closer trailer.
- Cleanup must remove the slice Docker Compose project containers/networks/volumes/images, release `orchestrator-state/dev-ports/<compose_project>.*`, and run Rancher cleanup commands if declared.
- Host ports are global on macOS/Linux. `docker compose -p` isolates object names, not host ports. Always use the contract allocator output.
- Rancher Desktop is the expected local desktop container runtime when present on macOS/Linux/WSL2, but Docker Engine/Compose also works if `docker` is available. Scripts include `~/.rd/bin`, `/opt/homebrew/bin` and `/usr/local/bin` on PATH and must not depend on GNU `timeout` for normal runtime operation.

- Windows support is through WSL2: install/run Claude Code, git, Python and Docker/Rancher integration inside the WSL distribution. Native PowerShell/CMD is not the target shell for orchestrator scripts.
