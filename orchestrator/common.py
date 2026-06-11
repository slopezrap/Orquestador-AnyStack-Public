from __future__ import annotations
import contextlib, datetime as dt, fcntl, json, os, sys, tempfile, time
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

NONE_VALUES = {"", "none", "null", "n/a", "na", "-", "--", "---", "_", "—"}
_PROJECT_ROOT_CACHE: Path | None = None


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_cwd() -> str:
    try:
        return os.getcwd()
    except FileNotFoundError:
        return os.environ.get("PWD") or "."


def _has_root_markers(p: Path) -> bool:
    return (p / "orchestrator" / "rules" / "state-machine.yaml").exists() and (p / ".claude" / "orchestrator-contract.json").exists()


def _git_canonical_root(p: Path) -> Path | None:
    """Return the shared scheduler root for a git worktree, when knowable.

    In branch-per-task mode a slice runs inside a linked worktree whose local
    `orchestrator-state/` can legitimately be empty. The registry, DAG, task
    packs and compiled input live at the canonical repository root that owns the
    shared `.git` directory.
    """
    try:
        import subprocess

        context = str(p)
        common = subprocess.check_output(
            ["git", "-C", context, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if common:
            common_path = Path(common)
            if common_path.name == ".git":
                root = common_path.parent.resolve()
                if _has_root_markers(root):
                    return root
        top = subprocess.check_output(
            ["git", "-C", context, "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if top:
            root = Path(top).resolve()
            if _has_root_markers(root):
                return root
    except Exception:
        return None
    return None


def _canonical_orchestrator_root(p: Path) -> Path | None:
    root = _git_canonical_root(p)
    if root is not None:
        return root
    if _has_root_markers(p):
        return p.resolve()
    return None


def project_root() -> Path:
    global _PROJECT_ROOT_CACHE
    if _PROJECT_ROOT_CACHE is not None:
        return _PROJECT_ROOT_CACHE
    env = os.environ.get("CLAUDE_ORCHESTRATOR_ROOT")
    if env:
        explicit = Path(env).resolve()
        root = _canonical_orchestrator_root(explicit)
        if root is not None:
            _PROJECT_ROOT_CACHE = root
            return root
        # Maintainer checks and unit tests sometimes run against a temporary
        # state-only root that deliberately contains no .claude/orchestrator
        # markers. Trust an explicit existing CLAUDE_ORCHESTRATOR_ROOT when it
        # has an orchestrator-state directory, but continue ignoring missing or
        # markerless non-state paths so stale env vars cannot create split brain.
        if explicit.is_dir() and (explicit / "orchestrator-state").is_dir():
            _PROJECT_ROOT_CACHE = explicit
            return explicit
    start = Path(os.environ.get("CLAUDE_PROJECT_DIR") or _safe_cwd()).resolve()
    for cur in [start, *start.parents]:
        if _has_root_markers(cur):
            root = _canonical_orchestrator_root(cur) or cur.resolve()
            _PROJECT_ROOT_CACHE = root
            return root
    _PROJECT_ROOT_CACHE = start
    return start


def workspace_root() -> Path:
    """Return the active product checkout/worktree, not scheduler root.

    v1 treated CLAUDE_WORKTREE_ROOT as the explicit task workspace. Keep that
    precedence so hooks and guards stay correct even if Claude Code reports
    CLAUDE_PROJECT_DIR as the canonical repo or an outer folder.
    """
    return Path(
        os.environ.get("CLAUDE_WORKTREE_ROOT")
        or os.environ.get("CLAUDE_WORKSPACE_ROOT")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or _safe_cwd()
    ).resolve()


def state_dir() -> Path:
    return project_root() / "orchestrator-state"


def compiled_dir() -> Path:
    return state_dir() / "compiled"


def tasks_dir() -> Path:
    return state_dir() / "tasks"


def registry_path() -> Path:
    return tasks_dir() / "registry.json"


def runtime_state_path() -> Path:
    return tasks_dir() / "runtime-state.json"


def runtime_state_yaml_path() -> Path:
    return tasks_dir() / "runtime-state.yaml"


def memory_dir() -> Path:
    return state_dir() / "memory"


def agent_memory_dir() -> Path:
    return state_dir() / "agent-memory"


def agent_memory_path(agent: str | None, suffix: str = "yaml") -> Path:
    safe = str(agent or "unknown").strip().replace("_", "-") or "unknown"
    return agent_memory_dir() / safe / f"MEMORY.{suffix}"


def progress_yaml_path() -> Path:
    return memory_dir() / "PROGRESS.yaml"


def progress_md_path() -> Path:
    return memory_dir() / "PROGRESS.md"


def ledger_path() -> Path:
    return tasks_dir() / "ledger.jsonl"


def bash_ledger_path() -> Path:
    return tasks_dir() / "bash-ledger.jsonl"


def hook_errors_path() -> Path:
    return state_dir() / "hook-errors.log"


def task_pack_path(task_id: str | None, suffix: str = "md") -> Path:
    return tasks_dir() / "task-packs" / f"{task_id or 'unknown'}.{suffix}"


def handoff_path(task_id: str | None) -> Path:
    return tasks_dir() / "handoffs" / f"{task_id or 'unknown'}.md"


def evidence_dir(task_id: str | None) -> Path:
    return tasks_dir() / "evidence" / f"{task_id or 'unknown'}"


def reports_dir() -> Path:
    return tasks_dir() / "reports"


def ensure_dirs() -> None:
    for p in [compiled_dir(), tasks_dir(), tasks_dir()/"task-packs", tasks_dir()/"handoffs", tasks_dir()/"slices", tasks_dir()/"evidence", tasks_dir()/"lifecycle-events", reports_dir(), memory_dir(), memory_dir()/"official-doc-notes", memory_dir()/"archive", state_dir()/"runs", agent_memory_dir(), state_dir()/"dev-logs"]:
        p.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    fallback = {} if default is None else default
    # Hooks and scripts frequently read files immediately after another process
    # atomically replaces them.  Retry briefly so callers do not observe a
    # transient missing/empty/partial file as an empty registry.
    last_error: Exception | None = None
    for _ in range(20):
        try:
            if not path.exists() or path.stat().st_size <= 0:
                time.sleep(0.025)
                continue
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.025)
    return fallback


def write_json(path: Path, data: Any) -> None:
    """Atomically write JSON and make the new file immediately visible to readers.

    Several orchestrator hooks read registry.json immediately after a writer exits.  The
    explicit fsyncs keep the write/rename boundary deterministic on overlay filesystems
    and network-mounted workspaces.  On macOS/Linux networked or overlaid filesystems,
    transient temporary-file races can surface as FileNotFoundError at rename time; retry
    the full write with a fresh temporary file instead of leaving a partial artifact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(3):
        fd, name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
            try:
                dir_fd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
            return
        except FileNotFoundError as exc:
            last_error = exc
            time.sleep(0.025 * (attempt + 1))
        finally:
            try:
                if Path(name).exists():
                    Path(name).unlink()
            except Exception:
                pass
    if last_error is not None:
        raise last_error


def _parse_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"'} and value.endswith(value[0]):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        return [_parse_yaml_scalar(part.strip()) for part in body.split(",")]
    try:
        return int(value)
    except Exception:
        return value


def _parse_simple_yaml(text: str) -> Any:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() == "---":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if " #" in line:
            line = line.split(" #", 1)[0].rstrip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            item_text = line[2:].strip()
            if not isinstance(parent, list):
                # Convert the last inserted mapping key into a list if needed.
                continue
            if item_text.startswith("[") and item_text.endswith("]"):
                parent.append(_parse_yaml_scalar(item_text))
            elif ":" in item_text:
                key, value = item_text.split(":", 1)
                node = {key.strip(): _parse_yaml_scalar(value.strip())}
                parent.append(node)
                stack.append((indent, node))
            else:
                parent.append(_parse_yaml_scalar(item_text))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            parent[key] = _parse_yaml_scalar(value)
        else:
            # Look ahead by current key naming convention: transitions/status maps are dicts;
            # simple indented dash blocks are lists.
            node: Any = [] if key in {"active_statuses", "terminal_statuses", "info_only_roles"} else {}
            parent[key] = node
            stack.append((indent, node))
    # Second pass for transition role lists: the simple parser above captures role keys as dicts,
    # but role values are lists of inline pairs.
    # If PyYAML is available, this fallback is not used.
    return root


def read_yaml(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8")
    # All orchestrator memory mirrors are written as JSON-shaped YAML so hooks
    # running under ``python -S`` can parse them without site-packages.
    try:
        return json.loads(text)
    except Exception:
        pass
    if yaml is not None:
        return yaml.safe_load(text) or default
    # Smoke YAML subset fallback for hand-authored config such as state-machine.yaml.
    data = _parse_simple_yaml(text)
    # Repair transition maps whose values are represented by indented dash lines.
    if path.name == "state-machine.yaml":
        transitions: dict[str, list[list[str]]] = {}
        current_role: str | None = None
        in_transitions = False
        for raw in text.splitlines():
            if raw.startswith("transitions:"):
                in_transitions = True
                current_role = None
                continue
            if in_transitions:
                if raw and not raw.startswith(" "):
                    break
                stripped = raw.strip()
                if not stripped:
                    continue
                if stripped.endswith(":") and not stripped.startswith("-"):
                    current_role = stripped[:-1]
                    transitions[current_role] = []
                elif stripped.startswith("-") and current_role:
                    value = stripped[1:].strip()
                    pair = _parse_yaml_scalar(value)
                    if isinstance(pair, list) and len(pair) == 2:
                        transitions[current_role].append([str(pair[0]), str(pair[1])])
        if transitions:
            data["transitions"] = transitions
    return data or default




def _json_like_yaml(data: Any) -> str:
    # JSON is valid YAML 1.2 and works under python -S when PyYAML is unavailable.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_yaml(path: Path, data: Any) -> None:
    """Atomically write YAML for human/runtime memory mirrors.

    Hooks may run with ``python -S``; when PyYAML is unavailable this writes
    JSON-shaped YAML, which is still valid YAML and keeps the reader fallback
    deterministic on Linux/macOS.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML and gives deterministic parsing in hooks executed with
    # ``python -S`` on Linux/macOS where PyYAML may not be importable.
    text = _json_like_yaml(data)
    last_error: Exception | None = None
    for attempt in range(3):
        fd, name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                if not text.endswith("\n"):
                    f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
            try:
                dir_fd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
            return
        except FileNotFoundError as exc:
            last_error = exc
            time.sleep(0.025 * (attempt + 1))
        finally:
            try:
                if Path(name).exists():
                    Path(name).unlink()
            except Exception:
                pass
    if last_error is not None:
        raise last_error


@contextlib.contextmanager
def file_lock(path: Path, timeout_seconds: float | None = None):
    """Portable POSIX advisory lock for Linux and macOS workspaces.

    The orchestrator runs on Unix-like developer machines and CI runners.  Both
    Ubuntu and macOS support ``fcntl.flock`` over regular files, so we use an
    adjacent ``*.lock`` file and a bounded non-blocking acquire loop instead of
    shell-specific ``flock(1)``.  The small metadata payload is diagnostic only;
    correctness comes from the kernel advisory lock.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = timeout_seconds
    if timeout is None:
        try:
            timeout = float(os.environ.get("CLAUDE_LOCK_TIMEOUT_SECONDS", "60"))
        except Exception:
            timeout = 60.0
    deadline = time.monotonic() + max(float(timeout), 0.1)
    with lock_path.open("a+", encoding="utf-8") as f:
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out acquiring lock {lock_path}")
                time.sleep(0.05)
        try:
            try:
                f.seek(0)
                f.truncate()
                f.write(json.dumps({"pid": os.getpid(), "path": str(path), "locked_at": now_iso()}, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
            yield
        finally:
            try:
                f.seek(0)
                f.truncate()
                f.flush()
            except Exception:
                pass
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def log_hook_error(name: str, exc: BaseException | str) -> None:
    ensure_dirs()
    message = str(exc)
    with hook_errors_path().open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {name}: {message}\n")


def load_registry() -> dict[str, Any]:
    return read_json(registry_path(), {"tasks": [], "phases": [], "task_dag": {}})


def save_registry(registry: dict[str, Any]) -> None:
    write_json(registry_path(), registry)
    try:
        write_yaml(registry_path().with_suffix(".yaml"), registry)
    except Exception:
        pass


def load_runtime_state() -> dict[str, Any]:
    return read_json(runtime_state_path(), {"spawn_counts": {}})


def save_runtime_state(runtime: dict[str, Any]) -> None:
    write_json(runtime_state_path(), runtime)
    try:
        write_yaml(runtime_state_yaml_path(), runtime)
    except Exception:
        pass


def find_task(registry: dict[str, Any], task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    for task in registry.get("tasks", []) or []:
        if isinstance(task, dict) and str(task.get("id")) == str(task_id):
            return task
    return None


def dag_worker_task_id() -> str | None:
    raw = (os.environ.get("CLAUDE_ACTIVE_TASK_ID") or os.environ.get("CLAUDE_TASK_ID") or "").strip()
    if raw and raw.lower() not in NONE_VALUES:
        return raw
    runtime = load_runtime_state()
    raw = str(runtime.get("active_task_id") or "").strip()
    return raw or None


def get_spawn_budget() -> int:
    try:
        return int(os.environ.get("CLAUDE_SPAWN_BUDGET") or load_runtime_state().get("spawn_budget") or 70)
    except Exception:
        return 70


def get_spawn_count(task_id: str | None) -> int:
    if not task_id:
        return 0
    counts = load_runtime_state().get("spawn_counts") or {}
    try:
        return int(counts.get(str(task_id)) or 0)
    except Exception:
        return 0


def bump_spawn_count(task_id: str | None, agent_type: str | None = None) -> int:
    if not task_id:
        return 0
    with file_lock(runtime_state_path()):
        runtime = load_runtime_state()
        counts = runtime.setdefault("spawn_counts", {})
        counts[str(task_id)] = int(counts.get(str(task_id)) or 0) + 1
        runtime["last_spawn_agent"] = agent_type
        runtime["last_spawn_at"] = now_iso()
        save_runtime_state(runtime)
        return counts[str(task_id)]


def task_is_ready(registry: dict[str, Any], task: dict[str, Any]) -> bool:
    done = {str(t.get("id")) for t in registry.get("tasks", []) if str(t.get("status")) == "done"}
    return all(str(dep) in done for dep in task.get("depends_on", []) or [])


def active_statuses() -> set[str]:
    data = read_yaml(project_root()/"orchestrator"/"rules"/"state-machine.yaml", {})
    return set(data.get("active_statuses") or {"claimed","in_progress","validator_tester_pending","needs_debug","ready_for_close","verified_pending_close"})


def write_patterns_conflict(path: str, pattern: str) -> bool:
    import fnmatch
    p = path.strip().replace("\\", "/")
    pat = pattern.strip().replace("\\", "/")
    if pat.endswith("/**"):
        return p.startswith(pat[:-3].rstrip("/") + "/") or p == pat[:-3].rstrip("/")
    return fnmatch.fnmatch(p, pat) or p == pat


def task_write_set(task: dict[str, Any]) -> list[str]:
    value = task.get("write_set") or []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(x).strip() for x in value if str(x).strip()]


def task_conflict_reasons(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Return deterministic reasons if two tasks cannot run in parallel."""
    reasons: list[str] = []
    acg = set(str(x) for x in (a.get("conflict_groups") or a.get("conflict_group") or []))
    bcg = set(str(x) for x in (b.get("conflict_groups") or b.get("conflict_group") or []))
    overlap = sorted(acg & bcg)
    if overlap:
        reasons.append(f"conflict_group={overlap}")
    for aw in task_write_set(a):
        for bw in task_write_set(b):
            if write_patterns_conflict(aw, bw) or write_patterns_conflict(bw, aw):
                reasons.append(f"write_set={aw}<->{bw}")
    return reasons


def tasks_conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool(task_conflict_reasons(a, b))


def active_conflict_blockers(registry: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    blockers=[]
    active=active_statuses()
    this_id=str(task.get("id"))
    for other in registry.get("tasks", []) or []:
        if str(other.get("id")) == this_id:
            continue
        status=str(other.get("status") or "")
        if status not in active:
            continue
        reasons = task_conflict_reasons(task, other)
        if reasons:
            blockers.append({"task_id": other.get("id"), "status": status, "reasons": reasons})
    return blockers


def promote_ready_tasks(registry: dict[str, Any]) -> dict[str, Any]:
    for task in registry.get("tasks", []) or []:
        status=str(task.get("status") or "")
        if status in {"todo", "blocked"} and task_is_ready(registry, task) and not task.get("last_blocker"):
            task["status"]="ready"
        elif status == "ready" and not task_is_ready(registry, task):
            task["status"]="todo"
    return registry


def workspace_relpath(path: Path) -> str:
    p = path.resolve()
    wr = workspace_root().resolve()
    pr = project_root().resolve()
    # In linked task worktrees, relative `orchestrator-state/...` paths would
    # create a second scheduler brain unless the worktree has been explicitly
    # provisioned.  Prefer absolute canonical paths for generated runtime state
    # when the workspace differs from the canonical scheduler root.
    try:
        p.relative_to(pr / "orchestrator-state")
        is_runtime_state = True
    except Exception:
        is_runtime_state = False
    if is_runtime_state and wr != pr:
        ws_state = wr / "orchestrator-state"
        if not ws_state.exists() and not ws_state.is_symlink():
            return p.as_posix()
        try:
            if ws_state.resolve() != (pr / "orchestrator-state").resolve():
                return p.as_posix()
        except Exception:
            return p.as_posix()
    for root in [wr, pr]:
        try:
            return p.relative_to(root).as_posix()
        except Exception:
            pass
    return path.as_posix()


def load_orchestrator_input() -> dict[str, Any]:
    return read_json(compiled_dir() / "orchestrator-input.json", {})


def configured_git_workflow() -> str:
    data = load_orchestrator_input()
    stack = data.get("stack") or {}
    raw = stack.get("git_workflow")
    if isinstance(raw, dict):
        raw = raw.get("mode") or raw.get("name")
    workflow = str(os.environ.get("CLAUDE_GIT_WORKFLOW") or raw or "pr-flow").strip()
    workflow = "".join(ch for ch in workflow if ch.isalnum() or ch in "_-")
    aliases = {"direct-main": "push-to-main", "directmain": "push-to-main", "push-main": "push-to-main", "gitflow": "git-flow", "prflow": "pr-flow"}
    return aliases.get(workflow, workflow or "pr-flow")
