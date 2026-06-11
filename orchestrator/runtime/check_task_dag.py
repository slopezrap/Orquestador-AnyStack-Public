from __future__ import annotations
import argparse, json
from typing import Any
from orchestrator.common import load_registry, task_conflict_reasons
import time


def check_registry(reg: dict[str, Any]) -> dict[str, Any]:
    tasks = reg.get("tasks", []) or []
    ids = [str(t.get("id")) for t in tasks if t.get("id")]
    id_set = set(ids)
    errors: list[str] = []
    warnings: list[str] = []

    if len(ids) != len(id_set):
        seen=set(); dup=[]
        for x in ids:
            if x in seen and x not in dup:
                dup.append(x)
            seen.add(x)
        errors.append("duplicate task ids: " + ", ".join(dup))

    graph: dict[str, list[str]] = {str(t.get("id")): [str(d) for d in (t.get("depends_on") or [])] for t in tasks if t.get("id")}
    for tid, deps in graph.items():
        for dep in deps:
            if dep not in id_set:
                errors.append(f"{tid} depends on unknown task {dep}")

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in visiting:
            start = stack.index(node) if node in stack else 0
            errors.append("cycle: " + " -> ".join(stack[start:] + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for dep in graph.get(node, []):
            if dep in graph:
                dfs(dep)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for tid in graph:
        dfs(tid)

    by_id = {str(t.get("id")): t for t in tasks if t.get("id")}
    dag = reg.get("task_dag") or {}
    if not dag.get("parallelism"):
        errors.append("task_dag missing parallelism")
    if not dag.get("parallel_groups"):
        errors.append("task_dag missing parallel_groups")
    if not dag.get("lock_model"):
        errors.append("task_dag missing lock_model")
    for group in dag.get("parallel_groups") or []:
        tids = [str(x) for x in group.get("task_ids") or []]
        for idx, tid in enumerate(tids):
            for other in tids[idx+1:]:
                if tid in by_id and other in by_id:
                    reasons = task_conflict_reasons(by_id[tid], by_id[other])
                    if reasons:
                        errors.append(f"parallel group {group.get('id')} conflicts: {tid}<->{other}: {reasons}")
    for t in tasks:
        tid=str(t.get("id"))
        if not t.get("title"):
            errors.append(f"{tid}: missing title")
        if not t.get("description"):
            errors.append(f"{tid}: missing description")
        elif len(str(t.get("description"))) < 120:
            errors.append(f"{tid}: description too short")
        if not t.get("write_set"):
            warnings.append(f"{tid}: empty write_set")
        if not t.get("verification_refs"):
            warnings.append(f"{tid}: empty verification_refs")
        if not t.get("locks"):
            errors.append(f"{tid}: missing locks")
        if not (t.get("parallel") or {}).get("safe_group"):
            errors.append(f"{tid}: missing parallel.safe_group")

    return {"ok": not errors, "errors": sorted(set(errors)), "warnings": sorted(set(warnings)), "tasks": len(tasks), "edges": sum(len(v) for v in graph.values()), "parallel_groups": len(dag.get('parallel_groups') or [])}


def _load_registry_retry(attempts: int = 40, delay: float = 0.05) -> dict[str, Any]:
    reg: dict[str, Any] = {}
    for _ in range(attempts):
        reg = load_registry()
        tasks = reg.get("tasks") or []
        dag = reg.get("task_dag") or {}
        if tasks and dag.get("parallelism") and dag.get("parallel_groups") and dag.get("lock_model"):
            return reg
        time.sleep(delay)
    return reg


def main(argv=None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    result = check_registry(_load_registry_retry())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
