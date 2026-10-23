#!/usr/bin/env python3
"""Evaluate zaf.py: per step against ref2 (ref1 vs ref2 = the floor). Global metrics (resweep_eval labels) plus a
sparse-pixel search: pixels that move > 6 sigma between step and reference, and whether their positions repeat
with a period (phase pixels would)."""
import pathlib, sys, json
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import resweep as R
import resweep_eval as E

base = pathlib.Path(sys.argv[1])
steps = [s['step'] for s in json.loads((base / 'steps.json').read_text())]
ref = base / 'ref2'
fl = {sub: E.floors([E.load(base / 'ref1' / sub), E.load(ref / sub)]) for sub in ('p', 'f10', 'd')}

def frame(d):
    fr, m = R.decode(d)
    top = (m.get('window', 0) >> 16); top -= top % 2
    return fr, top

def sparse(a, b, n0):
    d = a - b
    z = (d - np.median(d)) / (1.4826 * np.median(np.abs(d - np.median(d))) + 1e-6)
    ys, xs = np.nonzero(np.abs(z) > 6)
    best = []
    for P in (8, 12, 16, 24, 32, 48, 64):
        if len(ys) < 20:
            break
        h = np.bincount((ys % P) * P + (xs % P), minlength=P * P)
        best.append((h.max() / max(len(ys) / (P * P), 1e-9), P))
    return len(ys), max(best) if best else None

r0, top = frame(ref / 'd')
for s in steps:
    if s == 'ref2':
        continue
    lab = {sub: E.label(E.load(base / s / sub), E.load(ref / sub), fl[sub]) for sub in ('p', 'f10', 'd')}
    fr, _ = frame(base / s / 'd')
    a, b = fr[0][top:], r0[0][top:]
    n, per = sparse(a, b, None)
    st = E.load(base / s / 'p')['status']
    print(f'{s:6s} p[{lab["p"]}] f10[{lab["f10"]}] d[{lab["d"]}] | >6σ px {n}, best period peak {per} | rx {int(st[0])}/{int(st[1]):X} rows {a.shape}')
