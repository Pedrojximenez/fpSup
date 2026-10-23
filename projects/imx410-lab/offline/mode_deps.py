#!/usr/bin/env python3
"""Which mode attributes determine each mode-table register (70 modes, research/imx410/analysis/*.csv).

    mode_deps.py [--md]

For each varying register: the smallest set (1 or 2) of mode attributes that determines its value with no
conflict across all 70 modes, plus an exact linear law when one exists (reg = a*attr + b).
Attributes: geometry fields (width, height, the bin/skip fields 0x44..0x60, fps), HMAX, VMAX, bit depth.
"""
import csv, itertools, pathlib, sys
from collections import defaultdict

A = pathlib.Path(__file__).resolve().parents[3] / 'research' / 'imx410' / 'analysis'
modes = list(csv.DictReader(open(A / 'imx410_modes.csv')))
geo = {r['mode_id']: r for r in csv.DictReader(open(A / 'imx410_mode_geometry.csv'))}
tim = {r['mode_id']: r for r in csv.DictReader(open(A / 'imx410_timing.csv'))}
NAMES = {'field_0x04': 'width', 'field_0x08': 'height', 'field_0x34': 'marg_x', 'field_0x38': 'marg_y',
         'field_0x40': 'fps', 'field_0x44': 'f44', 'field_0x48': 'f48', 'field_0x4c': 'f4c', 'field_0x50': 'f50',
         'field_0x54': 'f54', 'field_0x58': 'f58', 'field_0x5c': 'f5c', 'field_0x60': 'f60'}
attrs = {}
for m in modes:
    i = m['mode_id']
    a = {n: int(geo[i][f]) for f, n in NAMES.items()}
    a.update(hmax=int(tim[i]['hmax_cycles']), vmax=int(tim[i]['vmax_lines']), bits=int(tim[i]['raw_bit_depth']))
    attrs[i] = a
regs = [k for k in modes[0] if k.startswith('reg_')]
an = list(attrs[modes[0]['mode_id']])


def determines(keys, reg):
    seen = {}
    for m in modes:
        k = tuple(attrs[m['mode_id']][x] for x in keys)
        v = int(m[reg])
        if seen.setdefault(k, v) != v:
            return False
    return True


def linear(reg, x):
    pts = {(attrs[m['mode_id']][x], int(m[reg])) for m in modes}
    xs = sorted({p[0] for p in pts})
    if len(xs) < 3:
        return None
    (x0, y0), (x1, y1) = sorted(pts)[0], sorted(pts)[-1]
    if x1 == x0:
        return None
    a = (y1 - y0) / (x1 - x0)
    b = y0 - a * x0
    if all(abs(a * px + b - py) < 0.51 for px, py in pts):
        return f'{a:.4g}*{x}{b:+.4g}'
    return None


out = []
for r in regs:
    vals = sorted({int(m[r]) for m in modes})
    if len(vals) == 1:
        continue
    found = None
    for n in (1, 2):
        cands = [c for c in itertools.combinations(an, n) if determines(c, r)]
        if cands:
            found = cands
            break
    lin = next((l for x in ('hmax', 'vmax', 'width', 'height', 'fps') for l in [linear(r, x)] if l), None)
    out.append((r[4:], len(vals), found, lin, vals))
for r, nv, found, lin, vals in out:
    f = ' | '.join('+'.join(c) for c in found[:4]) if found else 'needs 3+ attrs (or mode-specific)'
    print(f'{r}  {nv} vals {[hex(v) for v in vals][:7]}  <- {f}{"   LAW " + lin if lin else ""}')
