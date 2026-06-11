#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    raise SystemExit(subprocess.call([str(ROOT / "scripts" / "python-safe.sh"), "-m", "orchestrator.runtime.runtime_ops", "audit_agent_trailer_vocabulary", *sys.argv[1:]], cwd=ROOT))
