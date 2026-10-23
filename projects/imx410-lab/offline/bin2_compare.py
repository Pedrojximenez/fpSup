#!/usr/bin/env python3
"""Stock-style sensor 2x2 (0001=39) vs sensor vertical 2:1 + host horizontal same-colour average, same scene.
    bin2_compare.py A_DIR(sensor2x2) B_DIR(vbin2)   -- dirs hold after/frame.raw + frame.json (12-bit)"""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from decode12 import decode12

def load(d):
    m = json.loads((d / 'after' / 'frame.json').read_text())
    return decode12((d / 'after' / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(float)

def first_image_row(a):
    r = a[:, 50:-50].mean(1)
    return int(np.argmax(r > r[1:6].mean() + 40))

def hav(a):                                   # same-colour horizontal pairs: cols (0,2)->0, (1,3)->1 per 4
    w = a.shape[1] // 4 * 4
    q = a[:, :w].reshape(a.shape[0], -1, 4)
    return np.stack([(q[..., 0] + q[..., 2]) / 2, (q[..., 1] + q[..., 3]) / 2], -1).reshape(a.shape[0], -1)

A, B = load(pathlib.Path(sys.argv[1])), load(pathlib.Path(sys.argv[2]))
ta, tb = first_image_row(A), first_image_row(B)
print('first image row', ta, tb, ' OB mean', A[1:ta - 2].mean().round(1), B[1:tb - 2].mean().round(1))
print('OB noise (same-colour diff/√2)  2x2:', (np.diff(A[1:ta - 2, 40:-40:2], axis=1).std() / 2**.5).round(2),
      '  vbin2 raw:', (np.diff(B[1:tb - 2, 40:-40:2], axis=1).std() / 2**.5).round(2),
      '  vbin2+havg:', (np.diff(hav(B[1:tb - 2])[:, 40:-40:2], axis=1).std() / 2**.5).round(2))
bA, bB = A[1:ta - 2].mean(), B[1:tb - 2].mean()
a, b = A[ta:] - bA, hav(B[tb:]) - bB
# pixel-level registration (same-phase planes), which also finds the CFA parity
best = None
for dy in range(-24, 25):
    for dx in range(-8, 9):
        pa = a[30:600, 20:2900]; pb = b[30 + dy:600 + dy, 20 + dx:2900 + dx]
        c = np.corrcoef(pa[::2, ::2][::3, ::3].ravel(), pb[::2, ::2][::3, ::3].ravel())[0, 1]
        if best is None or c > best[0]: best = (c, dy, dx)
c, dy, dx = best
print(f'registration (pixels) dy {dy} dx {dx} corr {c:.4f}')
H = (min(a.shape[0], b.shape[0] - dy) - 60) // 2 * 2; W = (min(a.shape[1], b.shape[1] - dx) - 40) // 2 * 2
ca = a[30:30 + H, 20:20 + W]
cb = b[30 + dy:30 + dy + H, 20 + dx:20 + dx + W]
for name, (i, j) in zip(('R', 'Gr', 'Gb', 'B'), ((0, 0), (0, 1), (1, 0), (1, 1))):
    pa, pb = ca[i::2, j::2], cb[i::2, j::2]
    ok = (pa > 30) & (pa < 3000) & (pb > 30) & (pb < 3000)
    print(f'{name}: level ratio 2x2/vbin2h = {np.median(pa[ok] / pb[ok]):.3f}')
# noise vs level: local same-colour residual (pixel - mean of 4 same-colour neighbours) in flat areas, binned by level
def resid(x):
    out = []
    for i, j in ((0, 1), (1, 0)):
        p = x[i::2, j::2]
        r = p[1:-1, 1:-1] - (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) / 4
        out.append((p[1:-1, 1:-1], r))
    return out
ka = np.median([np.median(ca[i::2, j::2][(ca[i::2, j::2] > 30) & (cb[i::2, j::2] > 30) & (ca[i::2, j::2] < 3000)] /
                cb[i::2, j::2][(ca[i::2, j::2] > 30) & (cb[i::2, j::2] > 30) & (ca[i::2, j::2] < 3000)]) for i, j in ((0, 1), (1, 0))])
print('\nnoise in flat areas (G, residual × 0.894 ≈ σ), vbin2h scaled to 2x2 level by', round(ka, 3))
edges = [0, 5, 10, 20, 40, 80, 160, 320, 640, 1280, 2560]
print('level(2x2 DN)   σ 2x2   σ vbin2h   ratio   n')
for lo, hi in zip(edges[:-1], edges[1:]):
    sa, sb, n = [], [], 0
    for (pa, ra), (pb, rb) in zip(resid(ca), resid(cb * ka)):
        g = np.abs(np.gradient(pa)[0]) + np.abs(np.gradient(pa)[1])
        flat = (g < 3 + 0.03 * pa) & (pa >= lo) & (pa < hi) & (np.abs(np.gradient(pb)[0]) + np.abs(np.gradient(pb)[1]) < 3 + 0.03 * pb)
        sa.append(ra[flat]); sb.append(rb[flat]); n += flat.sum()
    if n < 2000: continue
    sa, sb = np.concatenate(sa), np.concatenate(sb)
    mad = lambda r: 1.4826 * np.median(np.abs(r - np.median(r))) * 0.894
    print(f'{lo:5d}-{hi:<5d}     {mad(sa):6.2f}   {mad(sb):6.2f}    {mad(sb) / mad(sa):5.2f}  {n}')
# sharpness: high-frequency energy of G on textured areas
def hf(x):
    g = x[0::2, 1::2]
    return np.abs(np.diff(g, axis=1)).mean() + np.abs(np.diff(g, axis=0)).mean()
print('\nG high-frequency energy (incl. noise): 2x2', round(hf(ca), 2), ' vbin2h', round(hf(cb * ka), 2))
np.save(pathlib.Path(sys.argv[1]) / 'crop.npy', ca.astype(np.float32)); np.save(pathlib.Path(sys.argv[2]) / 'crop_h.npy', (cb * ka).astype(np.float32))
