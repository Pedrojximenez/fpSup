#!/usr/bin/env python3
"""Read the resident OG UI state (72 bytes at 0xC0732700) and decode it.

    python3 dump_ui_state.py LABEL

Reads only 0xC0732700..0xC0732747.  Saves the raw dump next to this file as
ui_state_<LABEL>.bin and prints decode_og3k_ui_state.py's summary plus the
missing-record list, so a good boot and an early-QS boot can be diffed.
"""
import signal
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(90)
from putfile import mem_get  # noqa: E402

UI_STATE, WORDS = 0xC0732700, 18

label = sys.argv[1]
words = mem_get(UI_STATE, WORDS)
if any(w is None for w in words):
    sys.exit(f'incomplete read: {words}')
out = HERE / f'ui_state_{label}.bin'
out.write_bytes(struct.pack(f'<{WORDS}I', *words))
print(f'saved {out.name}')
import os  # noqa: E402
subprocess.run([sys.executable, str(BUILD / 'decode_og3k_ui_state.py'), str(out)],
               cwd=BUILD, check=False, env={**os.environ, 'OG_TARGET': 'og2k'})
