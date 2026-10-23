#!/usr/bin/env python3
"""Headroom of the attenuated group from a calib_att.py sweep: true level (full-group DN) where the attenuated
samples stop rising, against the full group's clip (3841). Also the attenuated/true ratio at low level.

    calib_headroom.py OUT [OUT ...]
"""
import pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calib_fit as C                                                 # noqa: E402


def main():
    for root in sys.argv[1:]:
        out = pathlib.Path(root)
        v = int(out.name.rsplit('_', 1)[1], 16) if out.name.rsplit('_', 1)[1].startswith('0x') else 32
        sh = v // 2
        frames = sorted([d for d in out.iterdir() if d.name.startswith('E') and int(d.name[1:]) >= 40],
                        key=lambda d: -int(d.name[1:]))
        Es = np.array([int(d.name[1:]) for d in frames], float)
        imgs = [C.load(d) for d in frames]
        print(f'== {out.name}')
        for c in ('R', 'Gr', 'B'):
            rp, cf, ca = C.PAIRS[c]
            Fs, As = [], []
            for a in imgs:
                F = a[rp::2, cf::4]; A = a[rp::2, ca::4]; n = min(F.shape[1], A.shape[1])
                F, A = F[:-sh, :n], A[sh:, :n]
                Fs.append(C.blocks(F)); As.append(C.blocks(A))
            Fs, As = np.array(Fs), np.array(As)
            ok = (Fs > 150) & (Fs < 2800)
            with np.errstate(all='ignore'):
                L = np.nanmedian(np.where(ok, Fs / Es[:, None, None], np.nan), 0)
            X = L[None] * Es[:, None, None]; g = ~np.isnan(X) & (X > 20)
            x, at = X[g], As[g]
            edges = np.geomspace(20, x.max(), 24); lut = []
            for lo, hi in zip(edges[:-1], edges[1:]):
                q = (x >= lo) & (x < hi)
                if q.sum() > 30:
                    lut.append((np.median(x[q]), np.median(at[q])))
            lut = np.array(lut)
            top = lut[:, 1].max(); sat = lut[np.argmax(lut[:, 1] >= 0.95 * top), 0]
            k500 = np.interp(500, lut[:, 0], lut[:, 1]) / 500
            print(f'  {c:2s}: att/true at 500 {k500:.4f}; att tops at {top:.0f} DN at true {sat:.0f} '
                  f'-> headroom over the full clip {np.log2(sat / 3841):+.2f} EV  (true range {lut[0,0]:.0f}..{lut[-1,0]:.0f})')


if __name__ == '__main__':
    main()
