#!/usr/bin/env python3
"""Bayer plane registration of a raw frame (Julien Acquaviva's sigma-fp-raw: in 3K / mode 98 the G2/B rows sit
0.5 px off the Bayer grid). Measures the sub-pixel shift of each colour plane against G1 by a low-band cross-spectrum phase
fit; prints the deviation from an ideal Bayer grid in OUTPUT pixels.

    rowphase.py DIR [DIR ...]       DIR holds frame.raw(.zst) + frame.json (resweep layout); y0/height from --y0/--h
                                    or, for captures/phase_stock/stockN, from that mode's attrs
Ideal grid: with the frame's phase [R/B, G1, G2, B/R] (row 0 = R or B, col 0 = R/B), G2 sits (+1, -1) output px from
G1 and B/R (+1, +1) from R/B. Deviation = measured - ideal; a 2-row same-colour vertical add (2x2) predicts -0.5 rows
for the second row of each pair (centroids 1,2 | 5,6 instead of 1,3 | 5,7 sensor rows).
"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np


def shift(a, b, fmax=0.07):
    """sub-pixel (dy, dx) with b(y, x) ~ a(y + dy, x + dx): weighted least-squares fit of the
    cross-spectrum phase over the low band (|f| < fmax cycles/plane px: below the aliasing; at 0.2 the 1x1 stock frames read 0.3 px off;
    a parabolic phase-correlation peak was biased by 0.1-0.3 px on synthetic binned frames)"""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    A = np.fft.fft2((a - a.mean()) * win); B = np.fft.fft2((b - b.mean()) * win)
    C = B * np.conj(A)
    fy = np.fft.fftfreq(a.shape[0])[:, None] + 0 * np.fft.fftfreq(a.shape[1])[None, :]
    fx = 0 * fy + np.fft.fftfreq(a.shape[1])[None, :]
    r = np.hypot(fy, fx)
    m = (r > 2.0 / min(a.shape)) & (r < fmax)                         # skip DC/shading and the aliased band
    w = np.abs(C[m]); ph = np.angle(C[m])
    M = np.stack([fy[m], fx[m]], 1) * (-2 * np.pi)
    sw = np.sqrt(w)
    d, *_ = np.linalg.lstsq(M * sw[:, None], ph * sw, rcond=None)
    return float(d[0]), float(d[1])


def measure(img):
    """img: Bayer image (rows even = R/B row). Returns deviation from the ideal grid, output px, per plane vs G1."""
    h, w = (img.shape[0] // 2) * 2, (img.shape[1] // 2) * 2
    img = img[:h, :w].astype(float)
    P = {'c00': img[0::2, 0::2], 'G1': img[0::2, 1::2], 'G2': img[1::2, 0::2], 'c11': img[1::2, 1::2]}
    ideal = {'c00': (0, -1), 'G2': (1, -1), 'c11': (1, 0)}           # output px relative to G1 at (0, 1)
    res = {}
    for k, (iy, ix) in ideal.items():
        dy, dx = shift(P['G1'], P[k])                                 # plane px
        res[k] = dict(dy=round(-2 * dy - iy, 3), dx=round(-2 * dx - ix, 3))   # shift(): phase sign gives -offset
    return res


def expected(vbin):
    """G2 row deviation predicted for a vbin-row same-colour vertical add: the two colours of a row pair can only
    use rows of their own parity, so for an even vbin the second row's centroid is 1 sensor row off (-1/vbin output
    px); an odd vbin tiles evenly (0). Measured on the stock modes: 1x1 0, 2x2 -0.50, 3x3 0, 3x6 -0.18
    (notes/IMX410_RULES.md §65)."""
    return 0.0 if vbin % 2 else -1.0 / vbin


SHORT = 1000                               # output rows: below this the halves are too few plane rows to measure


def judge(img, vbin, tol=None):
    """G2-vs-G1 (same colour: immune to the scene's colours) on the top and bottom halves; both must agree with
    the prediction. Cross-colour planes are reported but not judged (scene colour biases them).
    The check exists to tell the predicted offset from the wrong one (0 vs -0.5 rows, or a column swap): tol is half
    that gap, 0.2 (3x6's -1/6: half its gap to 0). It was 0.1 (good-light noise, stock 1x1 / 3x6 up to ~0.09); in
    full_v1 (dim room, max gain) 118 configs read 0.1-0.43 off -- narrow and short crops, 1x1 included, where no 0.5
    offset can exist -- and none came near the wrong value.  Short frames (< SHORT rows) are measured whole, once:
    a half of 55-400 plane rows read up to 0.43 off where the whole frame reads 0.15 (whole=True)."""
    e = expected(vbin)
    t = tol if tol is not None else (0.2 if e in (0.0, -0.5) else min(0.2, abs(e) / 2))
    if img.shape[0] < SHORT:
        parts = [measure(img)['G2']]
    else:
        h = (img.shape[0] // 4) * 2
        parts = [measure(img[:h])['G2'], measure(img[h:2 * h])['G2']]
    dy = [x['dy'] for x in parts]; dx = [x['dx'] for x in parts]
    r = dict(dy=dy, dx=dx, expected=e, tol=t,
             PASS=bool(all(abs(v - e) < t for v in dy) and all(abs(v) < 0.2 for v in dx)))
    if len(parts) == 1:
        r['whole'] = True
    return r


def main():
    import resweep as R
    import reconstruct as RC
    attrs = RC.load()[1]
    for d in map(pathlib.Path, sys.argv[1:]):
        mode = int(d.name[5:]) if d.name.startswith('stock') else None
        a = attrs.get(mode, {})
        fd = d / 'ae' if (d / 'ae').exists() else d
        if a.get('bits') == 14:                                       # the grab does not record the 14-bit packing
            m = json.loads((fd / 'frame.json').read_text()); m['bits'] = 14; (fd / 'frame.json').write_text(json.dumps(m))
        f, m = R.decode(fd)
        top, h = a.get('y0', 40), a.get('height', f[0].shape[0] - 80)
        img = f[0][top + 16:top + h - 16, 64:-64]
        j = judge(img, a.get('vbin', 1))
        print(d.name, f"cls {a.get('cls')} hbin {a.get('hbin')} vbin {a.get('vbin')}", json.dumps(j), flush=True)


if __name__ == '__main__':
    main()
