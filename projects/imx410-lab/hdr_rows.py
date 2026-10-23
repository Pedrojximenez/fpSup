#!/usr/bin/env python3
"""Single-frame green HDR from the row groups (IMX410_RULES §20c/§27): 0738 = v attenuates the odd Bayer rows
(Gb, B) by k, the even rows (R, Gr) keep full sensitivity. Per 2x2 cell: Y = Gr where Gr is below the clip,
else Gb / k. k is measured from cells where both are valid.

    hdr_rows.py POINT_DIR REF_DIR [--out png]
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
    return img[top:], img[1:top - 3].mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('point'); ap.add_argument('ref'); ap.add_argument('--out')
    a = ap.parse_args()
    x, bx = load(pathlib.Path(a.point)); r, br = load(pathlib.Path(a.ref))
    gr, gb = x[0::2, 1::2] - bx, x[1::2, 0::2] - bx
    clip = 4090 - bx
    ok = (gr > 200) & (gr < clip * 0.9) & (gb > 20)
    k = np.median(gb[ok] / gr[ok])
    w = np.clip((gr - 0.85 * clip) / (0.1 * clip), 0, 1)               # 0: Gr, 1: Gb/k
    y = (1 - w) * gr + w * gb / k
    yref = r[0::2, 1::2] - br
    print(f'k = {k:.4f} ({np.log2(1 / k):.2f} EV headroom); cells from Gb: {(w > 0.5).mean() * 100:.1f}%; '
          f'max Y {y.max():.0f} vs reference max {yref.max():.0f} ({np.log2(y.max() / yref.max()):.2f} EV more)')
    if a.out:
        from PIL import Image
        hi = y.max()
        tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) * 255).astype(np.uint8)
        Image.fromarray(np.concatenate([tone(yref), tone(y)], axis=0)[::2, ::2]).save(a.out)
        print('saved', a.out)


if __name__ == '__main__':
    main()
