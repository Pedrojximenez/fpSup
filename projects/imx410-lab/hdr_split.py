#!/usr/bin/env python3
"""Single-frame monochrome HDR from split colour gain (IMX410_RULES §14):
G pixels at high analog gain (3F/40), R/B at low (3D/3E), one exposure.

    hdr_split.py captures/split/rb0_g3900 captures/split/ref --ratio 21.0

Per 2x2 Bayer cell (R G / G B): luminance in "base-gain G units".
  shadows: Y = (G1 + G2) / 2 / ratio          (high gain: low read noise)
  highlights (G near clip): Y = kR·R + kB·B   (R/B at base gain, unclipped)
  kR, kB from cells where both are valid; a smooth blend between.
The reference (every pixel at the base gain) gives the same Y the plain way, for comparison.
"""
import argparse, json, pathlib, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

CLIP = 4000


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = (m['window'] >> 16) if m.get('ystart') == 0 else 0
    black = img[1:max(top - 3, 2)].mean() if top else 252.0
    a = img[top:]
    return a, black


def planes(a, black):
    r, g1, g2, b = (a[i::2, j::2] - black for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
    return r, (g1 + g2) / 2, b, np.maximum(a[0::2, 1::2], a[1::2, 0::2])


def local_noise(y, mask):
    """Std of the difference of horizontal neighbours / sqrt 2, inside a mask."""
    d = (y[:, 1:] - y[:, :-1])[mask[:, 1:] & mask[:, :-1]]
    return d.std() / np.sqrt(2) if d.size else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('split')
    ap.add_argument('ref')
    ap.add_argument('--ratio', type=float, required=True, help='G gain / R-B gain (law)')
    a = ap.parse_args()
    s, bs = load(pathlib.Path(a.split))
    q, bq = load(pathlib.Path(a.ref))
    r, g, b, graw = planes(s, bs)
    rr, gr_, br, _ = planes(q, bq)

    # colour coefficients, from cells where G (high) is well inside its range
    ok = (graw < CLIP * 0.8) & (g > 40) & (r > 4) & (b > 4)
    yg = g / a.ratio
    kR = np.median(yg[ok] / r[ok]) / 2
    kB = np.median(yg[ok] / b[ok]) / 2
    yrb = kR * r + kB * b
    w = np.clip((graw - CLIP * 0.7) / (CLIP * 0.25), 0, 1)       # 0: G, 1: R/B
    y = (1 - w) * yg + w * yrb

    # the plain way from the reference: every pixel at the base gain
    yref = gr_
    shadow = yref < np.percentile(yref, 10)
    print(f'kR {kR:.3f}  kB {kB:.3f}  cells from R/B: {(w > 0.5).mean() * 100:.2f}%  '
          f'G clipped: {(graw >= CLIP).mean() * 100:.2f}%')
    print(f'shadow noise (darkest 10% of the scene), base-gain units: '
          f'reference {local_noise(yref, shadow):.3f}  split {local_noise(y, shadow):.3f}  '
          f'(G-only part {local_noise(yg, shadow):.3f})')
    print(f'reference clipped {(np.maximum(q[0::2, 1::2], q[1::2, 0::2]) >= CLIP).mean() * 100:.3f}%  '
          f'split highlight max {y.max():.0f} (ref max {yref.max():.0f})')
    try:
        from PIL import Image
        def tone(v, hi):
            return (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) * 255).astype(np.uint8)
        hi = max(y.max(), yref.max())
        both = np.concatenate([tone(yref, hi), tone(y, hi)], axis=1)
        out = pathlib.Path(a.split) / 'mono_hdr_vs_ref.png'
        Image.fromarray(both[::2, ::2]).save(out)
        print('saved', out)
    except ImportError:
        pass


if __name__ == '__main__':
    main()
