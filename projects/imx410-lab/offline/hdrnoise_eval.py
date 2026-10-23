#!/usr/bin/env python3
"""hdrnoise.py results: temporal noise vs signal per configuration (12-bit DN scale, frame pairs), OB read noise,
and for the checkerboard configurations (C, E) the full-brightness group only (pixels whose level is >= 0.7x the
same pixel in the plain configuration B / D)."""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import resweep as R

base = pathlib.Path(sys.argv[1])
SIG = [3, 10, 30, 100, 300, 1000]


def load(cfg, g):
    d = base / f'{cfg}_{g}dB'
    if not (d / 'meta.json').exists():
        return None
    m = json.loads((d / 'meta.json').read_text())
    fr, mm = R.decode(d / 'g0' / 'p')
    top = m['top']
    a, b = fr[0], fr[1]
    ob = (a[4:top - 4, 100:-100], b[4:top - 4, 100:-100])
    return m, a[top + 20:top + 1000, 100:-100], b[top + 20:top + 1000, 100:-100], ob


def curve(a, b, black, mask=None):
    mean = (a + b) / 2 - black; diff = (a - b) / np.sqrt(2)
    out = {}
    for s in SIG:
        sel = (mean > s / 1.5) & (mean < s * 1.5)
        if mask is not None:
            sel &= mask
        if sel.sum() > 500:
            out[s] = float(np.std(diff[sel]))
    return out


for g in ('0', '26.4'):
    print(f'== {g} dB  (noise in DN12 at signal levels {SIG})')
    plain = {}
    for cfg in 'ABCDE':
        x = load(cfg, g)
        if not x:
            print(cfg, 'missing'); continue
        m, a, b, ob = x
        black = float(np.median(np.concatenate([ob[0].ravel(), ob[1].ravel()])))
        rn = float(np.std(ob[0] - ob[1]) / np.sqrt(2))
        mask = None
        if cfg in 'CE':
            ref = plain.get('B' if cfg == 'C' else 'D')
            if ref is not None and ref.shape == a.shape:
                mask = ((a + b) / 2 - black) >= 0.7 * ref
        if cfg in 'BD':
            plain[cfg] = (a + b) / 2 - black
        c = curve(a, b, black, mask)
        print(f'{cfg}: bits {m["bits"]} exp {m["exposure_us"]:.0f}µs black {black:.1f} OB read noise {rn:.2f} | ' +
              '  '.join(f'{s}:{v:.2f}' for s, v in c.items()) + (f'  (full group {mask.mean():.2f} of px)' if mask is not None else ''))
