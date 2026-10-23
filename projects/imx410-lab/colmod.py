#!/usr/bin/env python3
"""Column-period structure: per row parity and per column mod 4 (and mod 8), signal relative to a reference.
A period-4 split (columns 0-1 vs 2-3) would put every colour on both sides -> colour HDR by column bank.

    colmod.py DIR POINT [POINT ...]          (reference: DIR/ref_m*_a, or --ref NAME)
"""
import argparse, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rich                                                           # noqa: E402


def load(d):
    (img, *_), top = rich.frames(d)
    return img[top:] - img[1:top - 3].mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir'); ap.add_argument('points', nargs='+'); ap.add_argument('--ref')
    a = ap.parse_args()
    root = pathlib.Path(a.dir)
    r = load(root / a.ref) if a.ref else load(next(root.glob('ref_m*_a')))
    W = (r.shape[1] // 8) * 8
    mid = (r > 150) & (r < 2500)
    for n in a.points:
        x = load(root / n)
        if x.shape != r.shape:
            print(n, 'shape differs'); continue
        cells = []
        for rp in (0, 1):
            vals = []
            for c in range(8):
                m = mid[rp::2, c:W:8]
                vals.append(x[rp::2, c:W:8][m].mean() / max(r[rp::2, c:W:8][m].mean(), 1e-3))
            cells.append(' '.join(f'{v:.3f}' for v in vals))
        print(f'{n:22s} even rows c%8: {cells[0]}\n{"":22s} odd  rows c%8: {cells[1]}')


if __name__ == '__main__':
    main()
