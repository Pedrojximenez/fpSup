#!/usr/bin/env python3
"""Analyse calib_att.py: per colour, full and attenuated responses against the true exposure (radiance x time).

    calib_fit.py OUT [--offset 32]
Radiance per block = full / E from exposures where full is in its linear range (200..2800 DN above black).
Prints, per colour: full / (L*E) (linearity of the full group) and att / (L*E) (the attenuated response) binned by
L*E, i.e. the exact coefficient to use at each brightness; and whether att is ~0 below the full clip (overflow).
"""
import json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

PAIRS = {'R': (0, 2, 0), 'Gr': (0, 3, 1), 'Gb': (1, 0, 2), 'B': (1, 1, 3)}


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    return img[top:] - img[1:top - 3].mean()


def blocks(a, B=16):
    n0, n1 = a.shape[0] // B * B, a.shape[1] // B * B
    return a[:n0, :n1].reshape(n0 // B, B, n1 // B, B).mean((1, 3))


def main():
    out = pathlib.Path(sys.argv[1]); off = int(sys.argv[3]) if len(sys.argv) > 3 else 32
    frames = sorted([d for d in out.iterdir() if d.name.startswith('E')], key=lambda d: -int(d.name[1:]))
    Es = np.array([int(d.name[1:]) for d in frames], float)
    imgs = [load(d) for d in frames]
    for c, (rp, cf, ca) in PAIRS.items():
        Fs, As = [], []
        for a in imgs:
            F = a[rp::2, cf::4]; A = a[rp::2, ca::4]
            n = min(F.shape[1], A.shape[1]); F, A = F[:, :n], A[:, :n]
            sh = off // 2                                                # plane rows are 2 raw rows apart
            F, A = F[:-sh], A[sh:]                                     # att at row y shows physical row y + off
            Fs.append(blocks(F)); As.append(blocks(A))
        Fs, As = np.array(Fs), np.array(As)                            # [exposure, by, bx]
        ok = (Fs > 200) & (Fs < 2800)
        rad = np.where(ok, Fs / Es[:, None, None], np.nan)
        L = np.nanmedian(rad, 0)                                       # DN per line, per block
        X = L[None] * Es[:, None, None]                                # true signal in full-group DN
        good = ~np.isnan(X)
        x, f, at = X[good], Fs[good], As[good]
        print(f'== {c}')
        for lo in (5, 10, 20, 50, 100, 200, 500, 1000, 2000, 3000, 4000, 8000, 16000, 32000, 64000, 128000):
            q = (x >= lo) & (x < lo * 2)
            if q.sum() > 30:
                print(f'  true {lo:6d}-{lo * 2:6d}: full/true {np.median(f[q] / x[q]):6.3f} (clip {np.mean(f[q] > 3700) * 100:3.0f}%)'
                      f'   att {np.median(at[q]):8.1f} DN  att/true {np.median(at[q] / x[q]):.5f}  n {q.sum()}')


if __name__ == '__main__':
    main()
