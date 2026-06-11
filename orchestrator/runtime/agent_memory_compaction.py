from __future__ import annotations
import shutil
from orchestrator.common import agent_memory_dir, agent_memory_path, now_iso, project_root, read_json, read_yaml, write_yaml, file_lock
from orchestrator.runtime.memory_yaml import ensure_agent_memory


def _contract_agents() -> list[str]:
    contract = read_json(project_root() / ".claude/orchestrator-contract.json", {})
    return sorted(((contract.get("trailer_schema") or {}).get("roles") or {}).keys())


def compact_agent(agent: str, *, apply: bool, keep: int) -> dict:
    ensure_agent_memory(agent)
    path = agent_memory_path(agent, "yaml")
    data = read_yaml(path, {}) or {}
    events = list(data.get("recent_events") or [])
    should = len(events) > keep
    result = {"agent": agent, "memory": str(path.relative_to(project_root())), "events": len(events), "should_compact": should, "applied": False}
    if not should or not apply:
        return result
    archive_dir = path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = now_iso().replace(":", "").replace("+", "Z")
    archive = archive_dir / f"MEMORY.full.{ts}.yaml"
    with file_lock(path):
        shutil.copy2(path, archive)
        data = read_yaml(path, {}) or {}
        events = list(data.get("recent_events") or [])
        data["recent_events_archive"] = str(archive.relative_to(project_root()))
        data["recent_events_archived_at"] = now_iso()
        data["recent_events"] = events[-keep:]
        data["updated_at"] = now_iso()
        write_yaml(path, data)
    result.update({"applied": True, "archive": str(archive.relative_to(project_root())), "kept": keep})
    return result


def compact_all(*, apply: bool, keep: int) -> dict:
    agents = sorted({d.name for d in agent_memory_dir().glob("*") if d.is_dir()}) or _contract_agents()
    return {"ok": True, "apply": apply, "keep": keep, "results": [compact_agent(agent, apply=apply, keep=keep) for agent in agents]}
