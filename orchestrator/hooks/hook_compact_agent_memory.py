from __future__ import annotations
import json
from orchestrator.runtime.agent_memory_compaction import compact_all


def main() -> int:
    result = compact_all(apply=True, keep=250)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreCompact"}, "memory_compaction": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
