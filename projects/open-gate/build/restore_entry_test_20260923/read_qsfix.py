#!/usr/bin/env python3
"""READ-ONLY: ui_layout state (0xC07327C8: snapshot taken, stale layout,
releases, last released), the UicResourceCache head, QS_CINE refcount, and the
UI hit count."""
import signal, subprocess, sys
from pathlib import Path
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(90)
from putfile import mem_get
r = mem_get(0xC07327C8, 12)
print('ui_layout  snap', r[0], ' releases', r[1], ' last released', hex(r[2]))
for i in range(3):
    print(f'  recorded layout 0x{r[4 + 2*i]:08X}  pre-arm tree 0x{r[5 + 2*i]:08X}')
c = mem_get(0xC37B7254, 2)
print('cache+4', hex(c[1]))
if c[1]:
    t = mem_get(c[1] + 0xC, 1)[0]
    print('cached layout tree', hex(t), ' refcount', mem_get(t + 0xC, 1)[0] if t else None)
HERE = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(HERE / 'dump_ui_state.py'), sys.argv[1] if len(sys.argv) > 1 else 'qsfix'],
               check=False)
