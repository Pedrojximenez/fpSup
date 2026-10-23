#!/usr/bin/env python3
"""Single-frame checkerboard HDR (§30), v3: green per cell without interpolation, R/B by directional
colour-difference interpolation, per-colour per-column-group gain calibration.

    hdr_cd.py FRAME STOCK --out PNG [--crop r0,r1,c0,c1]

Layout (0242 = 01, 0738 = V), on the cell grid, cell column parity j:
  j even: R, Gr attenuated; Gb, B full          j odd: R, Gr full; Gb, B attenuated
1. Gains: for every plane and column parity, its scale against the full green of the same cells, measured on
   unclipped mid tones; every sample is divided by its own gain (this removes the column-period stripes).
2. G: every cell holds one full and one attenuated green -> inverse-variance mean of the two, the full one dropped
   near the clip. No neighbours used: full resolution, no staircase.
3. R (and B alike): where R is full and valid, D = R - G; at the other cells D is interpolated from the cells that
   have a full R (left, right and the four diagonals), each weighted by 1/(|dG| + eps) along its direction
   (directional: neighbours across a green edge count little) and dropped if clipped. R_interp = G + D_interp.
   That estimate is then fused with the cell's own attenuated R (inverse variance) -- in highlights, where the
   neighbours' full R are clipped, the cell's own attenuated sample carries it.
"""
import argparse, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from hdr_checker import planes                                        # noqa: E402

READ, SHOT, CLIPF = 25.0, 0.8, 0.85
FULL_ODD = dict(R=True, Gr=True, Gb=False, B=False)


def gain_maps(P, clip):
    """Per plane and column parity: gain relative to the full green, on cells where nothing is near the clip."""
    G = np.where((np.arange(P['Gr'].shape[1]) % 2 == 1)[None, :], P['Gr'], P['Gb'])   # the full green of each cell
    ok = (G > 200) & (G < 0.6 * clip)
    for c in P:
        ok &= P[c] < 0.6 * clip
    gains = {}
    for c in P:
        g = np.ones(P[c].shape[1])
        for par in (0, 1):
            m = ok[:, par::2]
            g[par::2] = np.median(P[c][:, par::2][m] / G[:, par::2][m])
        gains[c] = g
    return gains


def var_of(raw, g):
    return (READ + SHOT * np.maximum(raw, 0)) / g ** 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame'); ap.add_argument('stock'); ap.add_argument('--out', required=True)
    ap.add_argument('--crop', default='300,560,1300,1820')
    o = ap.parse_args()
    P, clip = planes(pathlib.Path(o.frame)); S, _ = planes(pathlib.Path(o.stock))
    # hot pixels: an attenuated sample far above its same-gain up/down neighbours would become a white speck
    # after x1/k; replace it by their mean (also catches a single bright outlier among full samples)
    for c in P:
        p = P[c]
        nbs = np.stack([np.roll(p, 1, 0), np.roll(p, -1, 0), np.roll(p, 2, 1), np.roll(p, -2, 1)])   # same gain
        nb = np.median(nbs, 0)
        sig = np.sqrt(READ + SHOT * np.maximum(nb, 0))
        hot = (p - nbs.max(0) > 4 * sig) & (p > 1.5 * nb + 6 * sig)     # isolated: above all four, and by a lot
        P[c] = np.where(hot, nb, p)
        print(f'{c}: {hot.mean() * 100:.3f}% hot samples replaced')
    gains = gain_maps(P, clip)
    for c in P:
        print(f'{c}: gain even cols {gains[c][0]:.4f}  odd cols {gains[c][1]:.4f}')
    X = {c: P[c] / gains[c][None, :] for c in P}                      # radiance in full-green units
    V = {c: var_of(P[c], gains[c][None, :]) for c in P}
    near = {c: P[c] >= CLIPF * clip for c in P}
    # joint clip: if any full-gain sample of this cell (or the neighbours we read) is near the clip, all full
    # samples of this cell are distrusted -- colours switch together
    full_mask = {c: (np.arange(P[c].shape[1]) % 2 == (1 if FULL_ODD[c] else 0))[None, :] for c in P}
    worst = np.max([np.where(full_mask[c], P[c], 0) for c in P], 0)
    worst = np.maximum(worst, np.maximum(np.roll(worst, 1, 1), np.roll(worst, -1, 1)))   # both column parities
    ftrust = np.clip((CLIPF * clip - worst) / (0.15 * clip), 0, 1)     # full samples fade out 0.70 -> 0.85 clip
    jbad = ftrust <= 0
    # --- 2. green per cell
    wr = np.where(near['Gr'], 0, 1 / V['Gr']) * np.where(full_mask['Gr'], ftrust, 1.0)
    wb = np.where(near['Gb'], 0, 1 / V['Gb']) * np.where(full_mask['Gb'], ftrust, 1.0)
    # the attenuated green sits at Gr (top-right) in even cell-columns and at Gb (bottom-left) in odd ones: used
    # alone it zig-zags one pixel diagonally from column to column (a comb on every slanted edge). Centre it:
    # [1, 2, 1] across the cell columns, so each estimate mixes both positions.
    att_g = np.where(full_mask['Gr'], X['Gb'], X['Gr'])
    att_v = np.where(full_mask['Gr'], V['Gb'], V['Gr'])
    att_ok = ~np.where(full_mask['Gr'], near['Gb'], near['Gr'])
    att_c = (np.roll(att_g, 1, 1) + 2 * att_g + np.roll(att_g, -1, 1)) / 4
    full_g = np.where(full_mask['Gr'], X['Gr'], X['Gb'])
    full_v = np.where(full_mask['Gr'], V['Gr'], V['Gb'])
    full_ok = ~np.where(full_mask['Gr'], near['Gr'], near['Gb'])
    wf = np.where(full_ok, 1 / full_v, 0) * ftrust
    wa = np.where(att_ok, 1 / (att_v * 6 / 16), 0)                    # [1,2,1]/4 of three samples: variance x 6/16
    G = (wf * full_g + wa * att_c) / np.maximum(wf + wa, 1e-12)
    G = np.where(wf + wa > 0, G, att_c)
    # --- 3. R and B in the colour-difference domain: every usable sample (own or neighbour, full or attenuated)
    # becomes D = X - G with variance V; neighbours are weighted by the green similarity along their direction
    out = {'G': G}
    sig = np.sqrt(READ + SHOT * np.maximum(G, 0))
    for c in ('R', 'B'):
        usable = ~near[c] & ~(full_mask[c] & jbad)                    # full samples distrusted near any clip
        D = np.where(usable, X[c] - G, 0.0)
        w_own = np.where(usable, 1 / V[c], 0.0) * np.where(full_mask[c], ftrust, 1.0)
        num, den = w_own * D, w_own.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0)):
            sh = lambda a: np.roll(np.roll(a, dy, 0), dx, 1)
            z = np.abs(sh(G) - G) / sig                                # green edge between the two cells
            dirw = np.exp(-0.5 * (z / 1.5) ** 2) * (0.5 if dx and dy else 1.0)
            w = sh(w_own) * dirw / 2                                   # a neighbour counts half its own weight
            num += w * sh(D); den += w
        Dm = num / np.maximum(den, 1e-30)
        out[c] = G + np.where(den > 0, Dm, 0.0)
    hdr = np.stack([out['R'], out['G'], out['B']], -1)
    ref = np.stack([S['R'], (S['Gr'] + S['Gb']) / 2, S['B']], -1)
    mid = (S['Gr'] > 200) & (S['Gr'] < 3000)
    wb_ = ref[mid].mean(0); wb_ = wb_[1] / wb_
    # stock WB applies to radiance in full-green units scaled like the stock frame's channels
    gcal = np.array([np.median(gains['R'][1::2]), 1.0, np.median(gains['B'][0::2])])
    hdr, ref = hdr * gcal * wb_, ref * wb_
    hi = np.percentile(hdr, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    Image.fromarray(np.concatenate([tone(ref), tone(hdr)], 0)[::2, ::2]).save(o.out)
    r0, r1, c0, c1 = (int(v) for v in o.crop.split(','))
    Image.fromarray(tone(hdr)[r0:r1, c0:c1]).save(str(o.out).replace('.png', '_crop.png'))
    print('saved', o.out)


if __name__ == '__main__':
    main()
