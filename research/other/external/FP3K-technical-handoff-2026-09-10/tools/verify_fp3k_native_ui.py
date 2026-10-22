"""Run the current complete-layout regression suite (v0.3.2)."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('verify_fp3k_layout_ui.py')), run_name="__main__")
