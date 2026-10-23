#!/usr/bin/env python3
"""Colour comparison for the row-group HDR (§27): stock frame vs 0738-attenuated frame, demosaiced per 2x2 cell.

    hdr_color.py POINT_DIR REF_DIR --out PNG

Cells: R, Gr from the full-sensitivity even rows; Gb, B from the attenuated odd rows (scaled back by 1/k).
  G  = Gr below the clip, Gb/k above (smooth blend)
  B  = G x a smoothed B/Gb ratio (B is attenuated everywhere: its noise is taken out of the chroma, not the luma)
  R  = R where R is below the clip; where R clipped it is ESTIMATED as G x the R/G ratio of nearby unclipped cells
       (this is the colour HDR limit: no attenuated R sample exists)
White balance: grey world on the mid tones of the reference. Tone: same log curve for both halves.
"""
import argparse, json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    a = img[top:]
    b = img[1:top - 3].mean()
    return [a[i::2, j::2] - b for i, j in ((0, 0), (0, 1), (1, 0), (1, 1))], 4090 - b


def blur(x, n=15):
    """Box mean over n x n (summed-area table; no scipy here)."""
    n = max(1, int(n)) | 1
    p = np.pad(x, n // 2 + 1, mode='edge')
    c = p.cumsum(0).cumsum(1)
    s = c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]
    return (s / (n * n))[:x.shape[0], :x.shape[1]]


def fill(ratio, valid, n=31):
    """Mean of `ratio` over valid cells in an n x n window, the window doubling where it holds no valid cell;
    whatever stays uncovered gets the global median (never 0 -- a 0 ratio paints the area in the complement colour)."""
    est = np.full(ratio.shape, np.median(ratio[valid]) if valid.any() else 1.0)
    todo = np.ones(ratio.shape, bool)
    while todo.any() and n < 4 * max(ratio.shape):
        num, den = blur(np.where(valid, ratio, 0), n), blur(valid.astype(float), n)
        ok = todo & (den > 0.02)
        est[ok] = num[ok] / den[ok]
        todo &= ~ok
        n *= 2
    return est


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('point'); ap.add_argument('ref'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    (R, Gr, Gb, B), clip = load(pathlib.Path(a.point))
    (r0, gr0, gb0, b0), clip0 = load(pathlib.Path(a.ref))
    ok = (Gr > 200) & (Gr < 0.9 * clip) & (Gb > 10)
    k = np.median(Gb[ok] / Gr[ok])
    w = np.clip((Gr - 0.85 * clip) / (0.1 * clip), 0, 1)
    G = (1 - w) * Gr + w * Gb / k
    # B: the measured value (attenuated rows, scaled by 1/k); in the shadows, where it is mostly noise, its
    # chroma (B/G) is smoothed and applied to the clean G -- luminance never comes from the noisy B
    bg_local = np.clip((B / k) / np.maximum(G, 1e-3), 0, 8)
    bg_smooth = np.clip(blur(B, 63) / np.maximum(blur(Gb, 63), 1e-3), 0, 8)     # ratio of means: unbiased in noise
    wb_ = np.clip((Gb - 15) / 60, 0, 1)                                # enough attenuated signal: trust it
    B_ = G * ((1 - wb_) * bg_smooth + wb_ * blur(bg_local, 5))
    # R: soft hand-over from the measured R to G x (R/G of nearby unclipped cells) as R approaches the clip
    # R: where R nears the clip, take R/G from unclipped cells nearby (small window first, growing as needed);
    # the hand-over starts early and is wide so no edge shows a step
    valid = (R < 0.75 * clip) & (Gr > 100) & (Gr < 0.75 * clip)
    rg = fill(np.clip(R / np.maximum(Gr, 1), 0, 8), valid, 9)
    wr = np.clip((np.maximum(R, Gr * np.median(R[valid] / Gr[valid])) - 0.6 * clip) / (0.3 * clip), 0, 1)
    wr = blur(wr, 5)
    R_ = (1 - wr) * R + wr * G * rg
    rclip = wr > 0.5
    ref = np.stack([r0, (gr0 + gb0) / 2, b0], -1)
    hdr = np.stack([R_, G, B_], -1)
    mid = (gr0 > 200) & (gr0 < 3000)
    wb = ref[mid].mean(0); wb = wb[1] / wb
    ref, hdr = ref * wb, hdr * wb
    hi = np.percentile(hdr, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    Image.fromarray(np.concatenate([tone(ref), tone(hdr)], 0)[::2, ::2]).save(a.out)
    print(f'k = {k:.4f} ({np.log2(1 / k):.2f} EV); R estimated in {rclip.mean() * 100:.1f}% of cells; saved {a.out}')


if __name__ == '__main__':
    main()
