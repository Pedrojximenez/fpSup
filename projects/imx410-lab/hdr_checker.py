#!/usr/bin/env python3
"""True single-frame colour HDR from the 2x2-cell checkerboard (§30): with 0242 = 01 and 0738 = V,
cell columns alternate: even cell-columns have R/Gr attenuated and Gb/B full, odd cell-columns the reverse.
Every colour therefore has measured full and attenuated samples in the same frame -- nothing is estimated.

    hdr_checker.py FRAME STOCK --out PNG

Per colour plane (cell grid): full samples on one column parity, attenuated on the other; each is interpolated
horizontally to every cell (neighbour mean). k per colour = median(attenuated / interpolated full) on mid tones.
Merge per cell: the full value where it (and its neighbours used) is below 80 % of the clip, else attenuated / k,
with a smooth hand-over. Cells -> (R, (Gr+Gb)/2, B); grey-world WB on the stock frame; same log curve for both.
"""
import argparse, json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

PH = dict(R=(0, 0), Gr=(0, 1), Gb=(1, 0), B=(1, 1))
FULL_ODD = dict(R=True, Gr=True, Gb=False, B=False)                   # full samples on odd cell-columns?


def planes(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    a, b = img[top:], img[1:top - 3].mean()
    return {k: a[i::2, j::2] - b for k, (i, j) in PH.items()}, 4090 - b


def spread(p, odd):
    """Keep the samples on one column parity, fill the other parity with the mean of its two neighbours."""
    out = p.copy()
    s = 0 if odd else 1                                                 # columns to fill
    left = np.roll(p, 1, axis=1); right = np.roll(p, -1, axis=1)
    out[:, s::2] = (left[:, s::2] + right[:, s::2]) / 2
    mx = p.copy(); mx[:, s::2] = np.maximum(left[:, s::2], right[:, s::2])   # worst neighbour, for clip tests
    return out, mx


def merge_all(P, clip):
    """All four colours switch together: per cell, one hand-over weight from the colour closest to its clip
    (separate weights put the switch at different places per colour -> coloured fringes on every edge)."""
    F, Fmax, A, K = {}, {}, {}, {}
    for c in PH:
        F[c], Fmax[c] = spread(P[c], FULL_ODD[c])
        A[c], _ = spread(P[c], not FULL_ODD[c])
        ok = (Fmax[c] > 150) & (Fmax[c] < 0.8 * clip) & (A[c] > 10)
        K[c] = np.median(A[c][ok] / F[c][ok])
    worst = np.max([Fmax[c] for c in PH], axis=0)
    w = np.clip((worst - 0.7 * clip) / (0.15 * clip), 0, 1)
    out = {c: (1 - w) * F[c] + w * A[c] / K[c] for c in PH}
    for c in PH:
        print(f'{c}: k = {K[c]:.4f} ({np.log2(1 / K[c]):.2f} EV)')
    print(f'{(w > 0.5).mean() * 100:.1f}% of cells from the attenuated samples')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame'); ap.add_argument('stock'); ap.add_argument('--out', required=True)
    o = ap.parse_args()
    P, clip = planes(pathlib.Path(o.frame)); S, _ = planes(pathlib.Path(o.stock))
    H = merge_all(P, clip)
    hdr = np.stack([H['R'], (H['Gr'] + H['Gb']) / 2, H['B']], -1)
    ref = np.stack([S['R'], (S['Gr'] + S['Gb']) / 2, S['B']], -1)
    mid = (S['Gr'] > 200) & (S['Gr'] < 3000)
    wb = ref[mid].mean(0); wb = wb[1] / wb
    hdr, ref = hdr * wb, ref * wb
    hi = np.percentile(hdr, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    Image.fromarray(np.concatenate([tone(ref), tone(hdr)], 0)[::2, ::2]).save(o.out)
    print('saved', o.out)


if __name__ == '__main__':
    main()
