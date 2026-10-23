#!/usr/bin/env python3
"""Compare every sensor merge (bins.py) against the 1x1 frame merged digitally (same-colour box average).

    bins_compare.py CAPTURE_DIR            (holds m10_1x1/ and the variants, each frame.raw + frame2.raw)

Per variant: registration on the digitally merged 1x1 reference; per-colour gain k and offset c (V = k R + c);
temporal noise (frame pair) of V/k against the reference's own merged temporal noise at the same scene level;
relative MTF |H| = |<V R*>| / <R R*> (cross spectrum, insensitive to noise) along x and y on the G plane;
colour: per-colour k spread (a pure merge keeps the colours: equal k).
"""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from decode12 import decode12
from decode14 import decode14

FACT = {'m10_end': (1, 1), 'm98_2x2': (2, 2), 'm58_2x2fast': (2, 2), 'vbin2': (1, 2), 'vbin2_14': (1, 2), 'h2_3B': (2, 1),
        'm139_3x3': (3, 3), 'm8_3x3fast': (3, 3), 'vbin3': (1, 3), 'm140_3x6': (3, 6), 'm8_native': (3, 3), 'm12_3x6fast': (3, 6), 'vbin3': (1, 3), 'v3_noset': (1, 3), 'v3_fix': (1, 3), 'v2_noset': (1, 2), 'v3_14': (1, 3)}
PH = ((0, 0), (0, 1), (1, 0), (1, 1))


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    dec, sc = (decode14, 0.25) if m.get('bits') == 14 else (decode12, 1.0)
    fr = [dec((d / n).read_bytes(), m['height'], m['line_words']).astype(float) * sc for n in ('frame.raw', 'frame2.raw')]
    r = fr[0][:, 60:-60].mean(1)
    top = int(np.argmax(r > np.median(r[1:4]) + 25))
    top -= top % 2
    out = []
    for f in fr:
        blk = np.zeros_like(f[:1])
        img = f[top:].copy()
        for i, j in PH:
            b = np.median(f[1:max(top - 2, 2)][(i + 1) % 2::2, j::2]) if top > 6 else 0
            img[i::2, j::2] -= b
        h, w = img.shape
        out.append(img[:h // 2 * 2, 40:(w - 40) // 2 * 2 + 40][:, :(w - 80) // 2 * 2])
    return out, top


def merge(x, hb, vb):
    H, W = x.shape[0] // 2 // vb * vb, x.shape[1] // 2 // hb * hb
    o = np.zeros((2 * H // vb, 2 * W // hb))
    for i, j in PH:
        p = x[i::2, j::2][:H, :W]
        o[i::2, j::2] = p.reshape(H // vb, vb, W // hb, hb).mean((1, 3))
    return o


def lum(x):
    return x[:-1, :-1] + x[1:, :-1] + x[:-1, 1:] + x[1:, 1:]


def register(ref, v):
    """Integer pixel offset of ref (smaller) inside v, by FFT cross-correlation of the 2x2-box luminance."""
    a, b = np.log1p(np.clip(lum(ref), 0, None)), np.log1p(np.clip(lum(v), 0, None))   # log: clipped highlights
    a = (a - a.mean()) / a.std(); b = (b - b.mean()) / b.std()                         # must not dominate
    H, W = max(a.shape[0], b.shape[0]) * 2, max(a.shape[1], b.shape[1]) * 2
    c = np.fft.irfft2(np.fft.rfft2(b, (H, W)) * np.conj(np.fft.rfft2(a, (H, W))), (H, W))
    dy, dx = np.unravel_index(np.argmax(c), c.shape)
    dy = dy - H if dy > H // 2 else dy; dx = dx - W if dx > W // 2 else dx
    return dy, dx


def overlap(ref, v, dy, dx):
    y0, x0 = max(0, -dy), max(0, -dx)
    y1, x1 = min(ref.shape[0], v.shape[0] - dy), min(ref.shape[1], v.shape[1] - dx)
    y0 += y0 % 2; x0 += x0 % 2; y1 -= (y1 - y0) % 2; x1 -= (x1 - x0) % 2
    return (slice(y0, y1), slice(x0, x1)), (slice(y0 + dy, y1 + dy), slice(x0 + dx, x1 + dx))


def spec(img, nimg):
    """noise-corrected power spectrum: |F(mean)|^2 - |F((f1-f2)/2)|^2 (same noise power as the mean)."""
    win = np.outer(np.hanning(img.shape[0]), np.hanning(img.shape[1]))
    P = np.abs(np.fft.fft2((img - img.mean()) * win)) ** 2
    N = np.abs(np.fft.fft2((nimg - nimg.mean()) * win)) ** 2
    return P, N


def mtf(r, rn, v, vn):
    """relative MTF sqrt(signal power V / signal power R) along x and y at 0.1..0.45 cycles per plane pixel,
    noise power removed with the frame-pair difference. Insensitive to sub-pixel shifts."""
    PR, NR = spec(r, rn); PV, NV = spec(v, vn)
    fy, fx = np.fft.fftfreq(r.shape[0])[:, None], np.fft.fftfreq(r.shape[1])[None, :]
    res = {}
    for ax, f, g in (('x', np.abs(fx) + 0 * fy, np.abs(fy) + 0 * fx), ('y', np.abs(fy) + 0 * fx, np.abs(fx) + 0 * fy)):
        row = []
        for c in (0.1, 0.2, 0.3, 0.4, 0.45):
            m = (np.abs(f - c) < 0.025) & (g < 0.06)
            sr, sv = (PR[m] - NR[m]).sum(), (PV[m] - NV[m]).sum()
            row.append(np.sqrt(sv / sr) if sr > 0 and sv > 0 else np.nan)
        res[ax] = row
    return res


def main():
    cap = pathlib.Path(sys.argv[1])
    (b1, b2), _ = load(cap / 'm10_1x1')
    rows = []
    for name, (hb, vb) in FACT.items():
        d = cap / name
        if not (d / 'frame2.raw').exists():
            print(f'{name:12s} -- not captured'); continue
        (v1, v2), top = load(d)
        r1, r2 = merge(b1, hb, vb), merge(b2, hb, vb)
        dy, dx = register(r1, v1)
        best = None                                           # refine ±1 on raw pixels: keeps the CFA phases matched
        for ey in (-1, 0, 1):
            for ex in (-1, 0, 1):
                a_, b_ = overlap(r1, v1, dy + ey, dx + ex)
                c_ = np.corrcoef(r1[a_][::3, ::3].ravel(), v1[b_][::3, ::3].ravel())[0, 1]
                if best is None or c_ > best[0]:
                    best = (c_, dy + ey, dx + ex)
        _, dy, dx = best
        sr, sv = overlap(r1, v1, dy, dx)
        R1, R2, V1, V2 = r1[sr], r2[sr], v1[sv], v2[sv]
        if R1.shape[0] < 100:
            print(f'{name:12s} -- overlap too small {R1.shape}'); continue
        corr = np.corrcoef(lum(R1)[::3, ::3].ravel(), lum(V1)[::3, ::3].ravel())[0, 1]
        kc = []
        for i, j in PH:
            x, y = ((R1 + R2) / 2)[i::2, j::2].ravel(), ((V1 + V2) / 2)[i::2, j::2].ravel()
            ok = (x > 20) & (x < 2500) & (y < 3500)
            kc.append(np.polyfit(x[ok], y[ok], 1))
        kc = np.array(kc)
        meds = [np.median(R1[i::2, j::2]) for i, j in PH]
        g = (0, 3) if abs(meds[0] - meds[3]) < abs(meds[1] - meds[2]) else (1, 2)
        k = kc[list(g), 0].mean()
        # temporal noise vs scene level (reference units), G phases
        out = {}
        for lo, hi in ((10, 40), (40, 160), (160, 640), (640, 2000)):
            sv_, sr_ = [], []
            for p in g:
                i, j = PH[p]
                lev = ((R1 + R2) / 2)[i::2, j::2]
                m = (lev >= lo) & (lev < hi)
                sv_.append(((V1 - V2)[i::2, j::2][m] / np.sqrt(2) / kc[p, 0]))
                sr_.append(((R1 - R2)[i::2, j::2][m] / np.sqrt(2)))
            sv_, sr_ = np.concatenate(sv_), np.concatenate(sr_)
            if sv_.size > 2000:
                out[(lo, hi)] = (sv_.std(), sr_.std())
        gi, gj = PH[g[0]]
        M = mtf(((R1 + R2) / 2)[gi::2, gj::2], ((R1 - R2) / 2)[gi::2, gj::2],
                ((V1 + V2) / 2)[gi::2, gj::2] / kc[g[0], 0], ((V1 - V2) / 2)[gi::2, gj::2] / kc[g[0], 0])
        rows.append((name, hb, vb, dy, dx, corr, kc, k, out, M))
        print(f'\n== {name}  merge {hb}x{vb}  offset dy {dy} dx {dx}  corr {corr:.4f}  overlap {R1.shape}')
        print('   per colour V = k·R + c :', '  '.join(f'k {a:.3f} c {b:+.0f}' for a, b in kc), f'  (G phases {g})')
        print('   temporal noise σ (ref units)  level: sensor-merge / digital-merge')
        for (lo, hi), (a, b) in out.items():
            print(f'      {lo:4d}-{hi:<5d}  {a:6.2f} / {b:6.2f}   ratio {a / b:5.2f}')
        print('   relative MTF |H| at 0.1/0.2/0.3/0.4/0.45 cy/px  x:', ' '.join(f'{q:.2f}' for q in M['x']),
              '  y:', ' '.join(f'{q:.2f}' for q in M['y']))
    np.save(cap / 'summary.npy', np.array(rows, dtype=object), allow_pickle=True)


if __name__ == '__main__':
    main()
