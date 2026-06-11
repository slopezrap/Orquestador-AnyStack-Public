from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _copy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "app"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc")
    shutil.copytree(ROOT, repo, ignore=ignore)
    state = repo / "orchestrator-state"
    if state.exists():
        shutil.rmtree(state)
    for d in [
        state / "compiled",
        state / "tasks" / "task-packs",
        state / "tasks" / "slices",
        state / "tasks" / "handoffs",
        state / "tasks" / "evidence",
        state / "tasks" / "reports",
        state / "tasks" / "lifecycle-events",
        state / "memory",
        state / "agent-memory",
        state / "dev-ports",
        state / "dev-logs",
        state / "runs",
    ]:
        d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


def _env(repo: Path, worktree: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if worktree is not None:
        env["CLAUDE_PROJECT_DIR"] = str(worktree)
    env.pop("CLAUDE_ORCHESTRATOR_ROOT", None)
    return env


def _minimal_canonical_state(repo: Path) -> None:
    tasks = repo / "orchestrator-state" / "tasks"
    (tasks / "task-packs").mkdir(parents=True, exist_ok=True)
    task_id = "SLICE-F0-001"
    (tasks / "registry.json").write_text(json.dumps({
        "tasks": [{
            "id": task_id,
            "task_id": task_id,
            "status": "in_progress",
            "title": "Worktree topology fixture",
            "description": "Fixture used to verify linked worktree runtime-state topology.",
            "write_set": ["src/**"],
            "conflict_groups": ["src"],
        }],
        "phases": [],
        "task_dag": {"nodes": [], "edges": []},
    }), encoding="utf-8")
    (tasks / "runtime-state.json").write_text(json.dumps({"active_task_id": task_id, "spawn_counts": {}}), encoding="utf-8")
    (tasks / "task-packs" / f"{task_id}.json").write_text("{}\n", encoding="utf-8")
    (tasks / "task-packs" / f"{task_id}.md").write_text("# pack\n", encoding="utf-8")


def _remove_worktree(repo: Path, wt: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "worktree", "prune"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_ensure_task_worktree_refuses_local_core_state_and_repair_archives_it(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _minimal_canonical_state(repo)
    proc = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    wt = Path(proc.stdout.strip().splitlines()[-1])
    assert wt.exists()
    assert not (wt / "orchestrator-state").exists()

    local_registry = wt / "orchestrator-state" / "tasks" / "registry.json"
    local_registry.parent.mkdir(parents=True, exist_ok=True)
    local_registry.write_text('{"tasks": []}\n', encoding="utf-8")

    check = subprocess.run(["bash", str(repo / "scripts" / "ensure-task-worktree.sh"), "--check-current", "SLICE-F0-001"], cwd=wt, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert check.returncode == 4
    assert "SPLIT" in check.stdout or "split" in check.stdout

    repair = subprocess.run(["bash", str(repo / "scripts" / "repair-worktree-state.sh"), "--apply", str(wt)], cwd=repo, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    assert "WORKTREE_STATE_ARCHIVED" in repair.stdout
    assert not (wt / "orchestrator-state").exists()
    assert list(wt.glob("orchestrator-state.split-brain.*"))
    _remove_worktree(repo, wt)


def test_subagent_context_uses_canonical_absolute_paths_from_linked_worktree(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _minimal_canonical_state(repo)
    proc = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    wt = Path(proc.stdout.strip().splitlines()[-1])
    payload = {"agent_type": "developer", "task_id": "SLICE-F0-001"}
    out = subprocess.run(["bash", str(repo / ".claude" / "bin" / "run_hook.sh"), "hook_subagent_start_context.py"], cwd=wt, env=_env(repo, wt), input=json.dumps(payload), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout
    assert f"Canonical orchestrator root: `{repo}`" in out
    assert str(repo / "orchestrator-state" / "tasks" / "handoffs" / "SLICE-F0-001.md") in out
    assert "Linked worktree state rule" in out
    _remove_worktree(repo, wt)


def test_write_guard_blocks_relative_local_worktree_orchestrator_state(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _minimal_canonical_state(repo)
    proc = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    wt = Path(proc.stdout.strip().splitlines()[-1])
    payload = {"tool_name": "Write", "tool_input": {"file_path": "orchestrator-state/tasks/evidence/SLICE-F0-001/developer.json"}}
    out = subprocess.run(["python3", "-m", "orchestrator.hooks.hook_write_scope_guard"], cwd=wt, env=_env(repo, wt), input=json.dumps(payload), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout
    assert "permissionDecision" in out
    assert "local worktree orchestrator-state" in out
    _remove_worktree(repo, wt)


def test_resolver_recovers_from_invalid_env_and_argument(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    env = _env(repo)
    env["CLAUDE_ORCHESTRATOR_ROOT"] = "/definitely/missing/root"
    out = subprocess.run(["bash", "scripts/resolve-orchestrator-root.sh", "/definitely/missing/root"], cwd=repo, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True).stdout.strip()
    assert out == str(repo)


def test_generated_memory_json_is_gitignored(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    check = subprocess.run(["git", "check-ignore", "-q", "orchestrator-state/memory/blueprint-blocks.json"], cwd=repo)
    assert check.returncode == 0


def test_workspace_root_prefers_claude_worktree_root_over_project_dir(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    wt_parent = tmp_path / "external-worktrees"
    wt_parent.mkdir()
    wt = wt_parent / "SLICE-F0-001"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(wt), "-b", "dev/SLICE-F0-001"], check=True)
    env = _env(repo)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    env["CLAUDE_WORKTREE_ROOT"] = str(wt)
    out = subprocess.run(
        ["python3", "-c", "from orchestrator.common import workspace_root; print(workspace_root())"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.strip()
    assert out == str(wt)
    _remove_worktree(repo, wt)


def test_repair_worktree_state_rejects_orchestrator_state_symlink(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _minimal_canonical_state(repo)
    proc = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    wt = Path(proc.stdout.strip().splitlines()[-1])
    os.symlink(repo / "orchestrator-state", wt / "orchestrator-state")
    check = subprocess.run(["bash", str(repo / "scripts" / "repair-worktree-state.sh"), "--check", str(wt)], cwd=repo, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert check.returncode == 4
    assert "symlink" in check.stdout.lower()
    repair = subprocess.run(["bash", str(repo / "scripts" / "repair-worktree-state.sh"), "--apply", str(wt)], cwd=repo, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    assert "WORKTREE_STATE_ARCHIVED" in repair.stdout
    assert not (wt / "orchestrator-state").exists()
    assert list(wt.glob("orchestrator-state.symlink.*"))
    _remove_worktree(repo, wt)


def test_tracked_blueprint_memory_json_mirrors_do_not_block_worktree_provision(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _minimal_canonical_state(repo)
    proc = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    wt = Path(proc.stdout.strip().splitlines()[-1])
    memory = wt / "orchestrator-state" / "memory"
    memory.mkdir(parents=True, exist_ok=True)
    for name in [
        "blueprint-blocks.json",
        "blueprint-lossless.json",
        "blueprint-manifest.json",
        "blueprint-sections.json",
        "execution-graph.json",
    ]:
        (memory / name).write_text("{}\n", encoding="utf-8")

    check = subprocess.run(["bash", str(repo / "scripts" / "repair-worktree-state.sh"), "--check", str(wt)], cwd=repo, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    assert "WORKTREE_STATE_READY: yes" in check.stdout
    assert "Topology: local_commit_artifacts_only" in check.stdout

    again = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    assert str(wt) in again.stdout
    assert "SPLIT_BRAIN" not in again.stdout

    repair = subprocess.run(["bash", str(repo / "scripts" / "repair-worktree-state.sh"), "--apply", str(wt)], cwd=repo, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    assert "Topology: local_commit_artifacts_only" in repair.stdout
    assert (memory / "blueprint-blocks.json").exists()
    assert not list(wt.glob("orchestrator-state.split-brain.*"))
    _remove_worktree(repo, wt)


def test_non_core_non_allowlisted_orchestrator_state_still_blocks_provision(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _minimal_canonical_state(repo)
    proc = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    wt = Path(proc.stdout.strip().splitlines()[-1])
    local = wt / "orchestrator-state" / "tasks" / "evidence" / "SLICE-F0-001" / "developer.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("{}\n", encoding="utf-8")

    check = subprocess.run(["bash", str(repo / "scripts" / "repair-worktree-state.sh"), "--check", str(wt)], cwd=repo, env=_env(repo, wt), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert check.returncode == 4
    assert "outside the allowed tracked compatibility blueprint memory JSON mirrors" in check.stdout

    again = subprocess.run(["bash", "scripts/ensure-task-worktree.sh", "SLICE-F0-001"], cwd=repo, env=_env(repo), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert again.returncode == 4
    assert "SPLIT_BRAIN" in again.stdout
    _remove_worktree(repo, wt)
