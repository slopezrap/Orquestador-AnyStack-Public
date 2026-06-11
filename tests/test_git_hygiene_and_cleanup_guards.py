from __future__ import annotations

from orchestrator.hooks import hook_bash_command_guard as guard


def test_bash_guard_allows_read_only_registry_inspection(monkeypatch):
    monkeypatch.setenv("CLAUDE_ACTIVE_TASK_ID", "SLICE-F0-001")
    cmd = 'python3 -c "import json; json.load(open(\\"orchestrator-state/tasks/registry.json\\"))"'
    assert guard._reason_for_block(cmd) is None


def test_bash_guard_blocks_core_state_writes_not_reads(monkeypatch):
    monkeypatch.setenv("CLAUDE_ACTIVE_TASK_ID", "SLICE-F0-001")
    cmd = 'python3 -c "open(\\"orchestrator-state/tasks/registry.json\\", \\"w\\").write(\\"{}\\")"'
    reason = guard._reason_for_block(cmd)
    assert reason is not None
    assert "core-state write" in reason


def test_bash_guard_blocks_claude_coauthored_commit(monkeypatch):
    monkeypatch.setenv("CLAUDE_ACTIVE_TASK_ID", "SLICE-F0-001")
    cmd = 'git commit -m "slice work\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"'
    reason = guard._reason_for_block(cmd)
    assert reason is not None
    assert "Co-Authored-By" in reason


def test_bash_guard_blocks_active_worktree_removal(monkeypatch):
    monkeypatch.setenv("CLAUDE_ACTIVE_TASK_ID", "SLICE-F0-001")
    monkeypatch.setenv("CLAUDE_WORKTREE_ROOT", "/tmp/app-worktrees/SLICE-F0-001")
    cmd = "git worktree remove /tmp/app-worktrees/SLICE-F0-001"
    reason = guard._reason_for_block(cmd)
    assert reason is not None
    assert "active task worktree" in reason

import json
import os
import shutil
import subprocess
from pathlib import Path


def _copy_repo_for_cleanup(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    shutil.copytree(root, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"))
    state = repo / "orchestrator-state"
    if state.exists():
        shutil.rmtree(state)
    (state / "tasks" / "cleanup-requests").mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return repo


def test_cleanup_schedule_active_defers_task_worktree_even_from_canonical_root(tmp_path: Path) -> None:
    repo = _copy_repo_for_cleanup(tmp_path)
    wt = tmp_path / "repo-worktrees" / "SLICE-F0-001"
    wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(wt), "-b", "dev/SLICE-F0-001"], check=True)

    env = os.environ.copy()
    env["CLAUDE_WORKTREE_CLEANUP_DELAY_SECONDS"] = "0"
    env["CLAUDE_WORKTREE_CLEANUP_INTERVAL_SECONDS"] = "1"
    env["CLAUDE_WORKTREE_CLEANUP_TIMEOUT_SECONDS"] = "1"
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("CLAUDE_WORKTREE_ROOT", None)
    env.pop("CLAUDE_WORKSPACE_ROOT", None)
    proc = subprocess.run(
        ["bash", "scripts/cleanup-worktrees.sh", "--apply", "--task", "SLICE-F0-001", "--schedule-active"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    assert "active_deferred=1" in proc.stdout
    assert "removed=0" in proc.stdout
    assert wt.exists()
    req = repo / "orchestrator-state" / "tasks" / "cleanup-requests" / "SLICE-F0-001.json"
    assert req.exists()
    data = json.loads(req.read_text(encoding="utf-8"))
    assert data["task_id"] == "SLICE-F0-001"
    assert Path(data["worktree"]) == wt
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
