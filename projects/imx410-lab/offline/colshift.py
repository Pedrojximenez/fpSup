#!/usr/bin/env python3
"""Vertical colour registration of a Bayer frame: shift (output rows) of the R and B planes against G, by a
linearised least-squares fit R ~ a*(G + s*dG/dy) + b on high-gradient pixels. A clean merge keeps R and B where
the CFA puts them; the vbin3 fringes are a non-zero extra shift.  colshift.py DIR... (each with frame.raw)"""
import pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bins_compare as C


def planes(x, gph):
    h, w = x.shape[0] // 2 * 2, x.shape[1] // 2 * 2
    p = {ph: x[ph[0]:h:2, ph[1]:w:2] for ph in C.PH}
    g1, g2 = gph
    G = (p[g1] + p[g2]) / 2                       # G at the cell centre row (+0.5)
    others = [ph for ph in C.PH if ph not in gph]
    return G, p[others[0]], p[others[1]], others


def shift(G, X, row_offset):
    """s in cell rows such that X(y) ~ a G(y + s); row_offset = X's CFA row minus G's centre (−0.5 / +0.5)."""
    dG = (np.roll(G, -1, 0) - np.roll(G, 1, 0)) / 2
    m = np.zeros(G.shape, bool); m[2:-2, 2:-2] = True
    m &= np.abs(dG) > np.percentile(np.abs(dG[m]), 90)
    A = np.stack([G[m], dG[m], np.ones(m.sum())], 1)
    coef, *_ = np.linalg.lstsq(A, X[m], rcond=None)
    a, ad, b = coef
    return ad / a - row_offset / 2               # in cell rows; CFA geometry removed


def colshift(d):
    (a, b), _ = C.load(d)
    x = (a + b) / 2
    meds = [np.median(x[i::2, j::2]) for i, j in C.PH]
    gph = (C.PH[0], C.PH[3]) if abs(meds[0] - meds[3]) < abs(meds[1] - meds[2]) else (C.PH[1], C.PH[2])
    G, X1, X2, oth = planes(x, gph)
    return [(o, shift(G, X, o[0] - 0.5)) for o, X in ((oth[0], X1), (oth[1], X2))]


if __name__ == '__main__':
    for d in sys.argv[1:]:
        r = colshift(pathlib.Path(d))
        print(d, '  '.join(f'{o}: {s:+.3f}' for o, s in r))
