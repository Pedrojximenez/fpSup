#!/usr/bin/env python3
"""READ-ONLY: decode the --ui-diag ui_layout log (0xC0732800, 128 bytes) and
the ui_layout state (0xC07327C8), plus the UI hit count.

    python3 read_qslog.py LABEL
"""
import json, signal, subprocess, sys
from pathlib import Path
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(90)
from putfile import mem_get

NAMES = {}
req = mem_get(0xC07327C8, 12)
log = mem_get(0xC0732800, 32)
print(f'snapshot taken {req[0]}  releases {req[1]}  last released 0x{req[2]:08X}')
for i in range(3):
    obj = req[4 + 2 * i]
    print(f'  QS layout #{i} 0x{obj:08X}  snapshot tree 0x{log[i]:08X}  record now 0x{req[5 + 2 * i]:08X}')
n = log[3]
print(f'log entries {n}')
for k in range(min(n, 7)):
    obj, tree, rec, fl = log[4 + 4 * k:8 + 4 * k]
    tags = [t for bit, t in ((16, 'cache-holds-other'), (17, 'current'), (18, 'held'),
                             (19, 'cache-busy'), (20, 'RELEASED')) if fl >> bit & 1]
    print(f'  #{k} layout 0x{obj:08X} tree 0x{tree:08X} recorded 0x{rec:08X} refcount {fl & 0xFFFF} {tags}')
c = mem_get(0xC37B7254, 2)
print(f'cache+4 0x{c[1]:08X}')
out = Path(__file__).with_name(f'qslog_{sys.argv[1]}.json')
out.write_text(json.dumps(dict(req=req, log=log, cache4=c[1]), indent=1))
r = subprocess.run([sys.executable, str(Path(__file__).with_name('dump_ui_state.py')), sys.argv[1]],
                   capture_output=True, text=True)
print('\n'.join(l for l in r.stdout.splitlines()
                if '"unique_exact_hits"' in l or '"post_install_stock_records"' in l))
