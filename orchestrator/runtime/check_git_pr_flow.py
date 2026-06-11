from __future__ import annotations
import json, re
from pathlib import Path
from orchestrator.common import project_root


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def has_all(text: str, tokens: list[str]) -> list[str]:
    return [tok for tok in tokens if tok not in text]


def main() -> int:
    root = project_root()
    errors: list[str] = []
    checks: dict[str, str] = {}
    files = {
        "pr_flow": root / ".claude/git-workflows/pr-flow.sh",
        "git_workflow": root / "scripts/git-workflow.sh",
        "closer_skill": root / ".claude/skills/closer/SKILL.md",
        "closer_agent": root / ".claude/agents/closer.md",
        "cleanup": root / "scripts/cleanup-slice-runtime.sh",
        "cleanup_worktrees": root / "scripts/cleanup-worktrees.sh",
        "cleanup_deferred_worktrees": root / "scripts/cleanup-deferred-worktrees.sh",
        "dev_restart": root / "scripts/dev-restart.sh",
        "docker_reset": root / "scripts/docker-hard-reset.sh",
        "runtime_lib": root / "scripts/slice-runtime-lib.sh",
        "unix_env": root / "scripts/unix-runtime-env.sh",
        "github_action": root / ".github/workflows/claude-code-pr-flow.yml",
        "contract": root / ".claude/orchestrator-contract.json",
        "hook": root / "orchestrator/hooks/hook_capture_subagent_stop.py",
        "runtime_git_guard": root / ".claude/bin/runtime_git_guard.py",
        "next_wave": root / "scripts/next-wave.sh",
        "sync_main_before_wave": root / "scripts/sync_main_before_wave.py",
        "git_add_slice": root / "scripts/git-add-slice.sh",
        "sync_lifecycle_events": root / "scripts/sync-lifecycle-events.sh",
        "ensure_task_worktree": root / "scripts/ensure-task-worktree.sh",
        "git_add_slice": root / "scripts/git-add-slice.sh",
        "runtime_ops": root / "orchestrator/runtime/runtime_ops.py",
    }
    for name, path in files.items():
        if not path.exists():
            errors.append(f"missing {path.relative_to(root)}")
        else:
            checks[name] = "present"
    pr = read(files["pr_flow"])
    missing = has_all(pr, ["gh pr create", "gh pr merge", "--force-with-lease", "PR_READY: yes", "MERGED: yes", "CANONICAL_MAIN_SYNCED: yes", "git fetch", "git rebase", "REMOTE_BRANCH_CLEANED", "git switch", "Single-checkout repositories are supported", "TARGET_REMOTE=\"${GIT_TARGET_REMOTE:-${CLAUDE_GIT_REMOTE:-origin}}\"", "origin/main"])
    errors.extend(f"pr-flow missing token: {m}" for m in missing)
    if re.search(r"(^|[^A-Za-z0-9_])git\s+stash(\s|$)", pr):
        errors.append("pr-flow must not use git stash")
    if "CANONICAL_MAIN_SYNCED: skipped" in pr:
        errors.append("pr-flow must not report skipped canonical main sync; it must sync or block")
    git_workflow = read(files["git_workflow"])
    missing = has_all(git_workflow, ["amend_late_trace_files", "runtime-git-guard.sh", "git stash", "GIT_WORKFLOW_TRACE_AMENDED", "stack_profile.py", "--root \"$CONFIG_ROOT\"", "linked task worktree", "resolve_canonical_root", "CONFIG_ROOT_CANDIDATE=\"${CLAUDE_ORCHESTRATOR_ROOT:-$(resolve_canonical_root)}\""])
    errors.extend(f"git-workflow missing transport guard token: {m}" for m in missing)
    next_wave = read(files["next_wave"])
    missing = has_all(next_wave, ["compact-agent-memory.py", "sync-main-before-wave.sh", "cleanup-deferred-worktrees.sh", "sync-lifecycle-events.sh", "cleanup-closed-task-worktrees.sh", "cleanup-zombie-task-worktrees.sh", "cleanup-merged-pr-branches.sh"])
    errors.extend(f"next-wave wrapper missing housekeeping token: {m}" for m in missing)
    ensure_wt = read(files["ensure_task_worktree"])
    missing = has_all(ensure_wt, ["pr-flow  -> dev/<TASK_ID>", "git-flow -> feature/<TASK_ID>", "current branch ${CURRENT_BRANCH:-detached} is not the exact task branch", "Do not fall back to canonical root in $WORKFLOW"])
    errors.extend(f"ensure-task-worktree missing branch isolation token: {m}" for m in missing)
    ensure_task_worktree = read(files["ensure_task_worktree"])
    for tok in ["CALL_DIR=", "GIT_PROBE_DIR", "MODE\" = \"check", "git -C \"$CALL_DIR\" rev-parse --show-toplevel"]:
        if tok not in ensure_task_worktree:
            errors.append(f"ensure-task-worktree missing linked-worktree check token: {tok}")
    runtime_guard = read(files["runtime_git_guard"])
    missing = has_all(runtime_guard, ["RUNTIME_EXACT", "RUNTIME_GLOBS", "backup", "restore", "protect", "non_runtime_dirty", "orchestrator-state/memory/PROGRESS.yaml", "orchestrator-state/memory/blueprint-lossless.json", "orchestrator-state/agent-memory/*/MEMORY.yaml"])
    errors.extend(f"runtime git guard missing blueprint runtime token: {m}" for m in missing)
    stack_profile = read(root / ".claude/bin/stack_profile.py")
    for tok in ["Respect --root explicitly", "read_json(root / \"orchestrator-state\"", "compiled orchestrator input is anchored"]:
        if tok not in stack_profile:
            errors.append(f"stack_profile.py missing root-aware workflow support token: {tok}")
    sync_main = read(files["sync_main_before_wave"])
    missing = has_all(sync_main, ["fetch", "--ff-only", "runtime-git-guard", "non-runtime dirty", "divergence detected"])
    errors.extend(f"sync-main-before-wave missing token: {m}" for m in missing)
    sync_lifecycle = read(files["sync_lifecycle_events"])
    missing = has_all(sync_lifecycle, ["lifecycle-events/<TASK_ID>.json", "LIFECYCLE_EVENTS_APPLIED", "target_status", "last_status", "promote_ready_tasks", "registry.json is local runtime"])
    errors.extend(f"sync-lifecycle-events missing DAG rehydration token: {m}" for m in missing)
    git_add_slice = read(files["git_add_slice"])
    missing = has_all(git_add_slice, ["orchestrator-state/tasks/lifecycle-events/{tid}.json", "orchestrator-state/tasks/handoffs/{tid}.yaml", "git add -f", "write_set"])
    errors.extend(f"git-add-slice missing per-task transport token: {m}" for m in missing)

    git_add = read(files["git_add_slice"])
    missing = has_all(git_add, ["lifecycle-events/{tid}.json", "target_status", "durable_close_signal", "verified_pending_close", "git_workflow_safe_to_apply_after_merge"])
    errors.extend(f"git-add-slice missing durable lifecycle token: {m}" for m in missing)
    runtime_ops = read(files["runtime_ops"])
    missing = has_all(runtime_ops, ["def sync_lifecycle_events", "lifecycle-events", "target_status", "promote_ready_tasks", "write_memory_snapshot", "applied_count"])
    errors.extend(f"sync_lifecycle_events missing durable lifecycle token: {m}" for m in missing)
    closer = read(files["closer_skill"]) + "\n" + read(files["closer_agent"])
    missing = has_all(closer, ["./scripts/git-workflow.sh", "./scripts/cleanup-slice-runtime.sh --task <TASK_ID> --apply --strict", "cleanup-worktrees.sh --apply --task <TASK_ID> --schedule-active", "Co-Authored-By: Claude", "PR_READY: yes", "MERGED: yes", "CANONICAL_MAIN_SYNCED: yes", "DOCKER_RUNTIME_CLEANED", "RANCHER_RUNTIME_CLEANED", "DEV_PORTS_RELEASED"])
    errors.extend(f"closer skill/agent missing token: {m}" for m in missing)
    cleanup = read(files["cleanup"])
    missing = has_all(cleanup, ["docker compose", "down -v --remove-orphans", "orchestrator-state/dev-ports", "RUNTIME_CLEANED", "DOCKER_RUNTIME_CLEANED", "RANCHER_RUNTIME_CLEANED", "DEV_PORTS_RELEASED"])
    errors.extend(f"cleanup missing token: {m}" for m in missing)
    cleanup_wt = read(files["cleanup_worktrees"]) + "\n" + read(files["cleanup_deferred_worktrees"])
    missing = has_all(cleanup_wt, ["--schedule-active", "active_deferred", "cleanup-requests", "DEFERRED_CLEANUP_COMMAND", "active_worktree_deferred_until_after_claude_hooks", "SubagentStop/Stop hooks"])
    errors.extend(f"worktree cleanup missing hook-safe token: {m}" for m in missing)
    if "docker system prune" in cleanup or "docker volume prune" in cleanup:
        errors.append("cleanup must not use global docker prune")
    dev = read(files["dev_restart"]) + "\n" + read(files["docker_reset"]) + "\n" + read(files["runtime_lib"])
    missing = has_all(dev, ["allocate_slice_ports.py", "runtime_context.py", "rdctl start", "~/.rd/bin", "COMPOSE_PROJECT_NAME", "docker compose -p", "--task <TASK_ID>"])
    errors.extend(f"dev/runtime scripts missing token: {m}" for m in missing)
    action = read(files["github_action"])
    missing = has_all(action, ["anthropics/claude-code-action@v1", "prompt:", "claude_args:", "--agent main-orchestrator", "--permission-mode bypassPermissions", "GH_TOKEN", "pull-requests: write", "contents: write"])
    errors.extend(f"claude-code-pr-flow workflow missing token: {m}" for m in missing)
    unix_env = read(files["unix_env"])
    for token in ["$HOME/.rd/bin", "/opt/homebrew/bin", "/usr/local/bin"]:
        if token not in unix_env:
            errors.append(f"unix env missing PATH token: {token}")
    hook = read(files["hook"])
    missing = has_all(hook, ["DOCKER_RUNTIME_CLEANED".lower(), "RANCHER_RUNTIME_CLEANED".lower(), "DEV_PORTS_RELEASED".lower(), "pr_ready", "merged", "canonical_main_synced"])
    errors.extend(f"SubagentStop closer guard missing token: {m}" for m in missing)
    result = {"ok": not errors, "errors": errors, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 2

if __name__ == "__main__":
    raise SystemExit(main())
