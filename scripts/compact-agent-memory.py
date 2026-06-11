#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from orchestrator.runtime.agent_memory_compaction import compact_agent, compact_all


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compact orchestrator agent MEMORY.yaml recent_events safely.")
    p.add_argument("--agent")
    p.add_argument("--all", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--threshold-lines", type=int, default=80, help="Maximum recent_events kept in MEMORY.yaml")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    payload = {"ok": True, "apply": args.apply, "keep": args.threshold_lines, "results": [compact_agent(args.agent, apply=args.apply, keep=args.threshold_lines)]} if args.agent else compact_all(apply=args.apply, keep=args.threshold_lines)
    if not args.quiet:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
