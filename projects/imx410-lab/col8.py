#!/usr/bin/env python3
"""Look for an 8-column period of the attenuated group: per colour, signal in raw columns 0-3 vs 4-7 (mod 8),
relative to the run's reference (checkerboard on). A period-8 grouping would show, for every colour, the
attenuation following col%8 // 4 instead of col%4 // 2.

    col8.py DIR
"""
import json, pathlib, re, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rich                                                           # noqa: E402

PH = dict(R=(0, 0), Gr=(0, 1), Gb=(1, 0), B=(1, 1))


def stats(a):
    """per colour: mean in each of the 4 same-colour column slots mod 8 (raw col%8 = j, j+2, j+4, j+6)."""
    out = {}
    W = (a.shape[1] // 8) * 8
    for k, (i, j) in PH.items():
        out[k] = np.array([np.mean(a[i::2, j + 2 * s:W:8]) for s in range(4)])
    return out


def main():
    root = pathlib.Path(sys.argv[1])
    load = lambda d: (lambda t: t[0][0][t[1]:] - t[0][0][1:t[1] - 3].mean())(rich.frames(d))
    ref = load(next(root.glob('ref_m10_a')))
    rs = stats(ref)
    print('reference (checker on), slots j,j+2,j+4,j+6 per colour:',
          {k: np.round(v / v.max(), 2).tolist() for k, v in rs.items()})
    hits = []
    for d in sorted(root.iterdir()):
        if not re.match(r'0x', d.name) or not (d / 'frame.raw').exists():
            continue
        try:
            x = stats(load(d))
        except Exception:
            continue
        # pattern per colour: which slots are "bright" (> half of the max)
        pat = {k: tuple(int(b) for b in (v > 0.5 * v.max())) for k, v in x.items()}
        refpat = {k: tuple(int(b) for b in (v > 0.5 * v.max())) for k, v in rs.items()}
        if pat != refpat:
            hits.append((d.name, {k: np.round(v / max(v.max(), 1e-3), 2).tolist() for k, v in x.items()}, pat))
    for n, v, p in hits:
        print(n, p, v)
    print(len(hits), 'points changed the column pattern')


if __name__ == '__main__':
    main()
