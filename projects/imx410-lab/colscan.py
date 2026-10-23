#!/usr/bin/env python3
"""Scan every captured point for a column grouping with period 4 (two raw columns per group): within each colour
plane, even plane-columns (raw col % 4 in {0,1}) against odd plane-columns ({2,3}), relative to the dir's reference.
A real column-pair grouping would split all four colours. Also reports the period-2 (column parity) split.

    colscan.py DIR [DIR ...]   -> prints points whose period-4 split exceeds 2 % in at least two colours
"""
import json, pathlib, sys
from multiprocessing import Pool
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

PH = dict(R=(0, 0), Gr=(0, 1), Gb=(1, 0), B=(1, 1))


def stats(d):
    try:
        m = json.loads((d / 'frame.json').read_text())
        img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float32)
    except Exception:
        return None
    top = m['window'] >> 16
    a = img[top:] - img[1:top - 3].mean()
    out = {}
    for k, (i, j) in PH.items():
        p = a[i::2, j::2]
        W = (p.shape[1] // 2) * 2
        ok = (p > 100) & (p < 3500)
        e = p[:, 0:W:2][ok[:, 0:W:2]].mean() if ok[:, 0:W:2].any() else np.nan
        o = p[:, 1:W:2][ok[:, 1:W:2]].mean() if ok[:, 1:W:2].any() else np.nan
        out[k] = (e, o)
    return str(d), out


def main():
    jobs = []
    for root in sys.argv[1:]:
        root = pathlib.Path(root)
        jobs += [d for d in root.iterdir() if (d / 'frame.raw').exists() and (d / 'frame.json').exists()]
    with Pool(6) as pool:
        res = dict(r for r in pool.imap_unordered(stats, jobs, chunksize=4) if r)
    by_dir = {}
    for p, s in res.items():
        by_dir.setdefault(str(pathlib.Path(p).parent), {})[pathlib.Path(p).name] = s
    for root, pts in sorted(by_dir.items()):
        refs = [v for k, v in pts.items() if k.startswith('ref_')]
        if not refs:
            continue
        base = {k: np.nanmedian([r[k][0] / r[k][1] for r in refs]) for k in PH}
        for name, s in sorted(pts.items()):
            if name.startswith('ref_'):
                continue
            split = {k: (s[k][0] / s[k][1]) / base[k] for k in PH if s[k][1] and not np.isnan(s[k][0])}
            big = [k for k, v in split.items() if abs(v - 1) > 0.02]
            if len(big) >= 2:
                print(f'{pathlib.Path(root).name:22s} {name:22s} ' + ' '.join(f'{k} {v:.3f}' for k, v in split.items()))
    print('scanned', len(res), 'frames')


if __name__ == '__main__':
    main()
