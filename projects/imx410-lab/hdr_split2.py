#!/usr/bin/env python3
"""Single-frame checkerboard HDR (§30), v4: two self-consistent images, blended once.

    hdr_split2.py FRAME STOCK --out PNG [--crops]

The checkerboard (0242 = 01, 0738 = V) splits the raw mosaic into two sparse Bayer mosaics of equal density:
  FULL: R, Gr of odd cell-columns + Gb, B of even cell-columns      ATT: the other half, at gain k
Each is demosaiced on its own at raw resolution (normalised Gaussian convolution: green first, then R-G and B-G
colour differences), so neither image ever mixes the two gains. k per colour = median(ATT/FULL) on mid tones.
HDR = (1 - w) FULL + w ATT/k with w from a smoothed clip map of the FULL raw samples (all colours at once).
"""
import argparse, json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

READ, SHOT = 25.0, 0.8


def gauss_nc(val, mask, sigma):
    """Normalised convolution: Gaussian-weighted mean of the masked samples (separable, numpy only)."""
    r = int(3 * sigma + 0.5)
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    def conv(a):
        out = np.zeros_like(a)
        for i, w in zip(x, k):
            out += w * np.roll(a, i, 0)
        a2 = out; out = np.zeros_like(a)
        for i, w in zip(x, k):
            out += w * np.roll(a2, i, 1)
        return out
    num, den = conv(np.where(mask, val, 0.0)), conv(mask.astype(np.float64))
    return num / np.maximum(den, 1e-9), den


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    return img[top:] - img[1:top - 3].mean(), 4090 - img[1:top - 3].mean()


def masks(shape):
    rr, cc = np.indices(shape)
    colour = np.select([(rr % 2 == 0) & (cc % 2 == 0), (rr % 2 == 0) & (cc % 2 == 1), (rr % 2 == 1) & (cc % 2 == 0)],
                       ['R', 'Gr', 'Gb'], 'B')
    odd_cell = (cc // 2) % 2 == 1
    full = np.where((colour == 'R') | (colour == 'Gr'), odd_cell, ~odd_cell)
    return colour, full


def demosaic(raw, sel, colour, sigma_g=1.4, sigma_c=2.2):
    """Sparse-Bayer demosaic of the samples where sel is True: G by normalised convolution, R/B as G + NC(X - G)."""
    gm = sel & ((colour == 'Gr') | (colour == 'Gb'))
    G, _ = gauss_nc(raw, gm, sigma_g)
    out = {'G': G}
    for c in ('R', 'B'):
        cm = sel & (colour == c)
        D, _ = gauss_nc(raw - G, cm, sigma_c)
        out[c] = G + D
    return np.stack([out['R'], out['G'], out['B']], -1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame'); ap.add_argument('stock'); ap.add_argument('--out', required=True)
    o = ap.parse_args()
    raw, clip = load(pathlib.Path(o.frame)); st, _ = load(pathlib.Path(o.stock))
    colour, full = masks(raw.shape)
    # hot isolated samples (both mosaics): above all four same-colour same-gain neighbours by far
    nbs = np.stack([np.roll(raw, 2, 0), np.roll(raw, -2, 0), np.roll(raw, 4, 1), np.roll(raw, -4, 1)])
    sig = np.sqrt(READ + SHOT * np.maximum(np.median(nbs, 0), 0))
    hot = (raw - nbs.max(0) > 4 * sig) & (raw > 1.5 * np.median(nbs, 0) + 6 * sig)
    raw = np.where(hot, np.median(nbs, 0), raw)
    F = demosaic(raw, full, colour)
    A = demosaic(raw, ~full, colour)
    # ATT = a * FULL + c per colour, fitted where FULL is linear (400..2400 DN): the attenuated rows carry a few DN
    # of offset (it would become ~100 DN after /k) and FULL compresses ~10 % above ~3000 DN (fit must avoid it)
    # robust: binned medians of raw pairs from the same place (G: the two greens of a cell; R, B: the attenuated
    # sample against the mean of its two full neighbours), then a line through the bin medians
    cg = lambda x: x
    gr, gb, rr_, bb = raw[0::2, 1::2], raw[1::2, 0::2], raw[0::2, 0::2], raw[1::2, 1::2]
    odd = (np.arange(gr.shape[1]) % 2 == 1)[None, :]
    nbm = lambda x: (np.roll(x, 1, 1) + np.roll(x, -1, 1)) / 2
    pairs = [(np.where(odd, nbm(rr_), np.nan), np.where(odd, np.nan, rr_)),        # R: full on odd cols
             (np.where(odd, gr, gb), np.where(odd, gb, gr)),                      # G
             (np.where(odd, np.nan, nbm(bb)), np.where(odd, bb, np.nan))]         # B: full on even cols
    pairs[0] = (np.where(odd, np.nan, nbm(rr_)), np.where(odd, np.nan, rr_))       # att R sits on even cols
    pairs[2] = (np.where(odd, nbm(bb), np.nan), np.where(odd, bb, np.nan))         # att B sits on odd cols
    fit = []
    for f, a_ in pairs:
        xs, ys = [], []
        for lo in range(400, 2400, 200):
            q = (f >= lo) & (f < lo + 200) & ~np.isnan(a_)
            if q.sum() > 200:
                xs.append(np.median(f[q])); ys.append(np.median(a_[q]))
        fit.append(tuple(np.polyfit(xs, ys, 1)))
    print('ATT = a FULL + c:', [(round(a_, 4), round(c_, 1)) for a_, c_ in fit],
          ' EV:', [round(float(np.log2(1 / a_)), 2) for a_, _ in fit], f' hot {hot.mean() * 100:.3f}%')
    A = np.stack([(A[..., i] - fit[i][1]) / fit[i][0] for i in range(3)], -1)
    # clip map from the FULL raw samples of every colour, smoothed, so all channels hand over together
    near = np.where(full, raw, 0) / clip
    nearmax, _ = gauss_nc(near, full, 2.0)
    peak = np.maximum(nearmax, np.where(full, near, 0))
    peak, _ = gauss_nc(peak, np.ones_like(full), 1.5)
    w = np.clip((peak - 0.35) / 0.25, 0, 1)                          # done by 60 %: before FULL compresses
    H = (1 - w[..., None]) * F + w[..., None] * A
    # stock reference: plain demosaic of every sample
    S = demosaic(st, np.ones_like(full), colour, 1.0, 1.5)
    mid = (S[..., 1] > 200) & (S[..., 1] < 3000)
    wb = S[mid].mean(0); wb = wb[1] / wb
    H, S = H * wb, S * wb
    hi = np.percentile(H, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    th, ts = tone(H), tone(S)
    Image.fromarray(np.concatenate([ts, th], 0)[::4, ::4]).save(o.out)
    for n, (r0, r1, c0, c1) in dict(edge=(360, 600, 1320, 1920), card=(720, 960, 2640, 3240),
                                    rim=(600, 840, 2240, 2840), dark=(0, 240, 40, 640)).items():
        Image.fromarray(np.concatenate([ts[r0:r1, c0:c1], th[r0:r1, c0:c1]], 1)).save(str(o.out).replace('.png', f'_{n}.png'))
    print('saved', o.out)


if __name__ == '__main__':
    main()
