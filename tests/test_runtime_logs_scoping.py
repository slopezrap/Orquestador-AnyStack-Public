from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLAUDE_ORCHESTRATOR_ROOT"] = str(tmp_root)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _run_check(tmp_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-B", "-S", "-m", "orchestrator.runtime.runtime_ops", "check_runtime_logs", *args],
        cwd=ROOT,
        env=_env(tmp_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_check_runtime_logs_scopes_hook_errors_to_task(tmp_path: Path) -> None:
    state = tmp_path / "orchestrator-state"
    state.mkdir()
    (state / "hook-errors.log").write_text(
        "[2026-06-10T10:00:00+00:00] hook: blocked task=SLICE-F0-001\n"
        "[2026-06-10T11:00:00+00:00] hook: denied task=SLICE-F1-099\n",
        encoding="utf-8",
    )

    own = _run_check(tmp_path, "--task", "SLICE-F1-099")
    assert own.returncode == 3
    assert '"scoped_task": "SLICE-F1-099"' in own.stdout
    assert "SLICE-F1-099" in own.stdout
    assert "SLICE-F0-001" not in own.stdout

    unrelated = _run_check(tmp_path, "--task", "SLICE-F2-001")
    assert unrelated.returncode == 0
    assert '"scoped_task": "SLICE-F2-001"' in unrelated.stdout
    assert '"hook_errors": []' in unrelated.stdout

    maintainer = _run_check(tmp_path)
    assert maintainer.returncode == 3
    assert '"scoped_task": null' in maintainer.stdout
    assert "SLICE-F0-001" in maintainer.stdout
    assert "SLICE-F1-099" in maintainer.stdout


def test_slice_wrappers_degrade_runtime_log_check_to_warning() -> None:
    maintain = (ROOT / "scripts" / "slice-maintain.sh").read_text(encoding="utf-8")
    verify = (ROOT / "scripts" / "verify-slice.sh").read_text(encoding="utf-8")
    assert 'if ! ./scripts/check-runtime-logs.sh --task "$TASK_ID"; then' in maintain
    assert "continuing maintenance as warning" in maintain
    assert 'if ! ./scripts/check-runtime-logs.sh --task "$TASK_ID" --mode hard-reset; then' in verify
    assert "continuing verify-slice as warning" in verify


def test_run_all_tests_lint_is_read_only() -> None:
    script = (ROOT / "scripts" / "run-all-tests.sh").read_text(encoding="utf-8")
    lint_block = script.split('if [ "$MODE" = "lint" ] || [ "$MODE" = "all" ]; then', 1)[1].split('fi', 1)[0]
    assert "scripts/reset-state.sh" not in lint_block
    assert "scripts/compile-blueprint.sh" not in lint_block
    assert "scripts/bootstrap-registry.sh" not in lint_block
    assert "scripts/run-golden-e2e.sh" not in lint_block
