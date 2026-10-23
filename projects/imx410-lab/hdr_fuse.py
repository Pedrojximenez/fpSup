#!/usr/bin/env python3
"""Noise-optimal fusion for the single-frame checkerboard HDR (§30), instead of a hard switch.

    hdr_fuse.py FRAME STOCK --out PNG [--compare PNG_FROM_HDR_CHECKER]

Per colour plane (cell grid), with gain g = 1 on its full cell-columns and k on its attenuated ones:
  1. hot samples: an attenuated sample more than 6 sigma above the median of its up/down neighbours (same gain)
     is replaced by that median (x(1/k) would turn a hot pixel into a white speck)
  2. radiance x = raw / g, variance v = (READ^2 + SHOT * raw) / g^2; a sample >= 92 % of the clip has no weight
  3. each cell = inverse-variance mean of itself and its left/right neighbours (the other gain), each neighbour also
     weighted by exp(-z^2 / 2 TAU^2), z = its difference to this cell in noise units: neighbours across an edge
     drop out, so edges are not smeared; a clipped cell takes its neighbours' attenuated values
Cells -> (R, (Gr+Gb)/2, B), grey-world WB on the stock frame, same log curve as hdr_checker.py.
"""
import argparse, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from hdr_checker import planes, PH, FULL_ODD                         # noqa: E402

READ, SHOT, TAU = 25.0, 0.8, 2.5                                      # DN^2, DN per DN, noise units


def kgain(p, full_odd, clip):
    f = p[:, 1::2] if full_odd else p[:, 0::2]
    a = p[:, 0::2] if full_odd else p[:, 1::2]
    n = min(f.shape[1], a.shape[1])
    f, a = f[:, :n], a[:, :n]
    ok = (f > 150) & (f < 0.8 * clip) & (a > 10)
    return np.median(a[ok] / f[ok])


def fuse(p, clip, full_odd, k, joint_bad):
    g = np.ones(p.shape[1]); g[(0 if full_odd else 1)::2] = k          # attenuated columns
    p = p.copy()
    att = np.zeros(p.shape, bool); att[:, (0 if full_odd else 1)::2] = True
    up, dn = np.roll(p, 1, 0), np.roll(p, -1, 0)
    med = np.median(np.stack([up, dn, p]), 0)
    sig = np.sqrt(READ + SHOT * np.maximum(med, 0))
    hot = att & (p - (up + dn) / 2 > 6 * sig)
    p[hot] = ((up + dn) / 2)[hot]
    x = p / g
    v = (READ + SHOT * np.maximum(p, 0)) / g ** 2
    # a full-gain sample is dropped when ANY colour's full sample in this cell is near the clip: all colours then
    # move to their attenuated values together (per-colour decisions fringe every edge)
    bad = (p >= 0.92 * clip) | (~att & joint_bad)
    w0 = np.where(~bad, 1 / v, 0.0)
    num, den = w0 * x, w0.copy()
    for s in (1, -1):
        xn, vn, wn = np.roll(x, s, 1), np.roll(v, s, 1), np.roll(w0, s, 1)
        z2 = (xn - x) ** 2 / (vn + v)
        edge = np.where(w0 > 0, np.exp(-z2 / (2 * TAU ** 2)), 1.0)      # a clipped cell trusts its neighbours
        num += wn * edge * xn
        den += wn * edge
    return num / np.maximum(den, 1e-12), hot.mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame'); ap.add_argument('stock'); ap.add_argument('--out', required=True)
    ap.add_argument('--compare')
    o = ap.parse_args()
    P, clip = planes(pathlib.Path(o.frame)); S, _ = planes(pathlib.Path(o.stock))
    H = {}
    # joint clip map on the cell grid: the highest full-gain sample of any colour in the cell (and its neighbours)
    full = []
    for c in PH:
        f = P[c].copy(); f[:, (0 if FULL_ODD[c] else 1)::2] = 0     # keep only full-gain samples
        full.append(f)
    worst = np.max(full, 0)
    worst = np.maximum(worst, np.maximum(np.roll(worst, 1, 1), np.roll(worst, -1, 1)))
    joint_bad = worst >= 0.85 * clip
    for c in PH:
        k = kgain(P[c], FULL_ODD[c], clip)
        H[c], hot = fuse(P[c], clip, FULL_ODD[c], k, joint_bad)
        print(f'{c}: k = {k:.4f} ({np.log2(1 / k):.2f} EV), hot samples fixed {hot * 100:.3f}%')
    hdr = np.stack([H['R'], (H['Gr'] + H['Gb']) / 2, H['B']], -1)
    ref = np.stack([S['R'], (S['Gr'] + S['Gb']) / 2, S['B']], -1)
    mid = (S['Gr'] > 200) & (S['Gr'] < 3000)
    wb = ref[mid].mean(0); wb = wb[1] / wb
    hdr, ref = hdr * wb, ref * wb
    hi = np.percentile(hdr, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    rows = [tone(ref), tone(hdr)]
    Image.fromarray(np.concatenate(rows, 0)[::2, ::2]).save(o.out)
    # 1:1 crops (cell grid) around an edge of the lampshade, for judging detail: old vs new
    if o.compare:
        old = np.asarray(Image.open(o.compare))
    crop = (slice(300, 560), slice(1300, 1820))
    Image.fromarray(tone(hdr)[crop]).save(str(o.out).replace('.png', '_crop.png'))
    print('saved', o.out)


if __name__ == '__main__':
    main()
