#!/usr/bin/env python3
from __future__ import annotations
import runpy, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    runpy.run_module('orchestrator.runtime.orchestrator_doctor', run_name="__main__")
