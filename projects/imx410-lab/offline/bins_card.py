#!/usr/bin/env python3
"""Edge / aliasing crops of one region (default: the QR code) for every merge, next to the 1x1 frame merged
digitally to the same size, all upscaled to the same display size.  bins_card.py CAPTURE_DIR [y0 y1 x0 x1 in 1x1 px]"""
import pathlib, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bins_compare as C

cap = pathlib.Path(sys.argv[1])
Y0, Y1, X0, X1 = (int(v) for v in sys.argv[2:6]) if len(sys.argv) > 5 else (300, 1000, 3400, 4100)
(b1, b2), _ = C.load(cap / 'm10_1x1')
base = (b1 + b2) / 2


def demosaic(x):
    """bilinear; G on (0,1),(1,0), R (0,0), B (1,1) in the 1x1 frame's phase."""
    H, W = x.shape
    m = np.zeros((3, H, W)); m[0, 0::2, 0::2] = 1; m[1, 0::2, 1::2] = 1; m[1, 1::2, 0::2] = 1; m[2, 1::2, 1::2] = 1
    p = lambda z: np.pad(z, 1, mode='reflect')
    def conv(z, k):
        q = p(z); return sum(k[i][j] * q[i:i + H, j:j + W] for i in range(3) for j in range(3))
    kg = [[0, .25, 0], [.25, 1, .25], [0, .25, 0]]; kr = [[.25, .5, .25], [.5, 1, .5], [.25, .5, .25]]
    return np.stack([conv(x * m[0], kr), conv(x * m[1], kg), conv(x * m[2], kr)], -1)


ref_crop = base[Y0:Y1, X0:X1]
rgb = demosaic(ref_crop)
BLK = np.percentile(rgb.reshape(-1, 3), 1, axis=0)
wb = np.percentile(rgb.reshape(-1, 3), 97, axis=0) - BLK; wb = wb[1] / wb
scale = 1 / (np.percentile(rgb[..., 1], 99) - BLK[1])
OUT = (X1 - X0, Y1 - Y0)


def show(x):
    v = np.clip((demosaic(x) - BLK) * wb * scale, 0, 1) ** (1 / 2.2)
    return Image.fromarray((v * 255).astype(np.uint8)).resize(OUT, Image.NEAREST)


tiles = [('1x1', show(ref_crop))]
order = ['vbin2', 'vbin2_14', 'h2_3B', 'm98_2x2', 'vbin3', 'm139_3x3', 'm8_native']
for name in order:
    hb, vb = C.FACT[name]
    (v1, v2), _ = C.load(cap / name)
    r1 = C.merge(b1, hb, vb)
    dy, dx = C.register(r1, v1)
    best = None
    for ey in (-1, 0, 1):
        for ex in (-1, 0, 1):
            a_, b_ = C.overlap(r1, v1, dy + ey, dx + ex)
            c_ = np.corrcoef(r1[a_][::3, ::3].ravel(), v1[b_][::3, ::3].ravel())[0, 1]
            if best is None or c_ > best[0]: best = (c_, dy + ey, dx + ex)
    _, dy, dx = best
    y0, y1 = Y0 // (2 * vb) * 2, Y1 // (2 * vb) * 2; x0, x1 = X0 // (2 * hb) * 2, X1 // (2 * hb) * 2
    ref_m = C.merge(base, hb, vb)[y0:y1, x0:x1]
    v = ((v1 + v2) / 2)[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    if (dy % 2, dx % 2) != (0, 0):
        print(name, 'odd offset', dy, dx)
    vv = v.copy()
    for i, j in C.PH:                                     # per colour v = k·ref + c  ->  ref scale
        xr, yv = ref_m[i::2, j::2].ravel(), v[i::2, j::2].ravel()
        ok = (xr > 20) & (xr < 2500) & (yv < 3500)
        k, c = np.polyfit(xr[ok], yv[ok], 1)
        vv[i::2, j::2] = (v[i::2, j::2] - c) / k
    tiles.append((f'{name} sensor', show(vv)))
    tiles.append((f'{hb}x{vb} digital', show(ref_m)))
W, H = OUT
cols = 3
rows_ = [[tiles[0]]] + [tiles[i:i + 2] for i in range(1, len(tiles), 2)]
canvas = Image.new('RGB', (2 * W + 10, len(rows_) * (H + 24)), 'white')
d = ImageDraw.Draw(canvas)
for r, row in enumerate(rows_):
    for c, (lab, im) in enumerate(row):
        canvas.paste(im, (c * (W + 10), r * (H + 24) + 22)); d.text((c * (W + 10) + 4, r * (H + 24) + 4), lab, fill='black')
canvas.save(cap / 'card_grid.png')
print('saved', cap / 'card_grid.png', canvas.size)
