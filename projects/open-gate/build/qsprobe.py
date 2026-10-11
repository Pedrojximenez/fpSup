#!/usr/bin/env python3
"""Compatibility entry point for the project-neutral Quick Set probe.

The implementation lives in ``research/ui/tools`` because its timing and USB
toggle rules apply to every camera UI project, not just OpenGate.
"""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[3]
runpy.run_path(str(ROOT / "research" / "ui" / "tools" / "qsprobe.py"),
               run_name="__main__")
