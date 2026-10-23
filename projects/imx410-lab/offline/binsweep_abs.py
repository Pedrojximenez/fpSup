#!/usr/bin/env python3
"""Absolute temporal noise (G, frame pair) of each register's session reference and of chosen points, at fixed
raw level bands -- separates a register's effect from a reference that happened to be off.
    binsweep_abs.py captures/binsweep/BASE [REG ...]"""
import pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bins_compare as C

BANDS = ((40, 160), (160, 640), (640, 2000))


def absnoise(d):
    (a, b), _ = C.load(d)
    m, n = (a + b) / 2, (a - b) / np.sqrt(2)
    out = []
    for lo, hi in BANDS:
        s = []
        for i, j in ((0, 1), (1, 0)):
            lev = m[i::2, j::2]; k = (lev >= lo) & (lev < hi)
            s.append(n[i::2, j::2][k])
        s = np.concatenate(s)
        out.append(s.std() if s.size > 2000 else np.nan)
    return out


base = pathlib.Path(sys.argv[1])
regs = sys.argv[2:]
for rd in sorted(p for p in base.iterdir() if p.is_dir()):
    if not (rd / 'ref' / 'frame2.raw').exists():
        continue
    r = absnoise(rd / 'ref')
    line = f'{rd.name} ref ' + ' '.join(f'{x:6.2f}' for x in r)
    if rd.name in regs:
        for vd in sorted(p for p in rd.iterdir() if p.is_dir() and p.name != 'ref' and (p / 'frame2.raw').exists()):
            line += f'\n      {vd.name}  ' + ' '.join(f'{x:6.2f}' for x in absnoise(vd))
    print(line, flush=True)
