from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, check=True):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def compile_root():
    run(["bash", "scripts/reset-state.sh"])
    run(["bash", "scripts/compile-blueprint.sh", "inputs/BLUEPRINT.md"])
    run(["bash", "scripts/bootstrap-registry.sh", "orchestrator-state/compiled/orchestrator-input.json"])


def test_next_wave_default_is_operator_markdown_with_terminal_command():
    compile_root()
    out = run(["bash", "scripts/next-wave.sh", "--limit", "1"]).stdout
    assert out.startswith("# DAG wave propuesta")
    assert "unset CLAUDE_ACTIVE_TASK_ID" in out
    assert "scripts/ensure-task-worktree.sh" in out
    assert ".claude/bin/runtime_context.py" in out
    assert ".claude/bin/allocate_slice_ports.py" in out
    assert "claude --agent main-orchestrator --permission-mode bypassPermissions" in out
    assert "| TASK_ID | Título | Depends on | Conflict groups | Write set | Comando terminal |" in out


def test_next_wave_json_mode_remains_available_for_tooling():
    compile_root()
    payload = json.loads(run(["bash", "scripts/next-wave.sh", "--limit", "1", "--json"]).stdout)
    assert payload["ok"] is True
    assert payload["dag_mode"] == "explicit_dag"
    assert payload["ready"][0]["id"] == "SLICE-F0-001"


def test_runtime_context_and_port_allocation_support_native_terminal_contract():
    compile_root()
    env_out = run([
        "python3", "-B", "-S", ".claude/bin/runtime_context.py",
        "--root", str(ROOT), "--workspace-root", str(ROOT), "--task", "SLICE-F0-001", "--print-env",
    ]).stdout
    assert "export COMPOSE_PROJECT_NAME=slice-f0-001" in env_out
    env_file = ROOT / "orchestrator-state" / "dev-ports" / "pytest-next-wave.env"
    run([
        "python3", "-B", "-S", ".claude/bin/allocate_slice_ports.py",
        "--root", str(ROOT), "--task", "SLICE-F0-001", "--env-file", str(env_file),
    ])
    text = env_file.read_text(encoding="utf-8")
    assert "CLAUDE_PORT_ENV_FILE" in text
    assert "CLAUDE_FRONTEND_PORT" in text
    assert "CLAUDE_BACKEND_PORT" in text
    assert "CLAUDE_DB_PORT" in text
