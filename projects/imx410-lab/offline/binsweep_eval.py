#!/usr/bin/env python3
"""Evaluate binsweep.py points against their own session reference (same base readout, same session).

    binsweep_eval.py captures/binsweep/BASE

Per point: k (level vs ref, G), noise = temporal σ in ref units / ref σ at the same scene level (lower = the
merge uses more light), MTF x/y at 0.2 and 0.3 cy/px vs ref, shift (dy,dx) vs ref, colour registration: vertical
shift of R and B planes against G (rows of the output; the vbin3 fringes), corr with ref.
Flags: noise < 0.93 with corr > 0.98 (a fuller merge), |colour shift| change > 0.15 row.
"""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bins_compare as C


def pair(d):
    try:
        (a, b), _ = C.load(d)
    except Exception:
        return None
    return a, b


def plane_shift(p, q):
    """sub-pixel vertical shift of q against p (column-mean gradient profiles, phase correlation)."""
    gp, gq = np.diff(p, axis=0), np.diff(q, axis=0)
    F = np.fft.fft2(gq) * np.conj(np.fft.fft2(gp))
    F /= np.abs(F) + 1e-9
    c = np.real(np.fft.ifft2(F)).sum(1)
    i = int(np.argmax(c)); n = len(c)
    y0, y1, y2 = c[i - 1], c[i], c[(i + 1) % n]
    sub = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) if (y0 - 2 * y1 + y2) != 0 else 0
    s = i + sub
    return s - n if s > n / 2 else s


def colour_shift(x):
    h = x.shape[0] // 2 * 2
    R, G1, G2, B_ = x[0:h:2, 0::2], x[0:h:2, 1::2], x[1:h:2, 0::2], x[1:h:2, 1::2]
    G = (G1 + G2) / 2
    m = min(R.shape[1], B_.shape[1], G.shape[1])
    return plane_shift(G[:, :m], R[:, :m]), plane_shift(G[:, :m], B_[:, :m])


def noise(ref, refn, v, vn, k):
    out = []
    for lo, hi in ((40, 160), (160, 640), (640, 2000)):
        sv, sr = [], []
        for i, j in ((0, 1), (1, 0)):
            lev = ref[i::2, j::2]; m = (lev >= lo) & (lev < hi)
            sv.append(vn[i::2, j::2][m] / k); sr.append(refn[i::2, j::2][m])
        sv, sr = np.concatenate(sv), np.concatenate(sr)
        if sv.size > 2000:
            out.append(sv.std() / sr.std())
    return float(np.mean(out)) if out else np.nan


def main():
    base = pathlib.Path(sys.argv[1])
    rows = []
    for rd in sorted(p for p in base.iterdir() if p.is_dir()):
        rp = pair(rd / 'ref')
        if rp is None:
            continue
        ra, rb = rp
        ref, refn = (ra + rb) / 2, (ra - rb) / np.sqrt(2)
        cs0 = colour_shift(ref)
        for vd in sorted(p for p in rd.iterdir() if p.is_dir() and p.name != 'ref'):
            if (vd / 'nofail').exists():
                rows.append((rd.name, vd.name, 'NO FRAME')); continue
            vp = pair(vd)
            if vp is None:
                continue
            va, vb = vp
            v, vn = (va + vb) / 2, (va - vb) / np.sqrt(2)
            h, w = min(ref.shape[0], v.shape[0]), min(ref.shape[1], v.shape[1])
            r_, v_, rn_, vn_ = ref[:h, :w], v[:h, :w], refn[:h, :w], vn[:h, :w]
            dy, dx = C.register(r_[20:-20, 20:-20], v_)
            dy -= 20; dx -= 20
            if abs(dy) > 40 or abs(dx) > 40:
                rows.append((rd.name, vd.name, f'moved {dy},{dx}')); continue
            sr, sv = C.overlap(r_, v_, dy, dx)
            A, V, An, Vn = r_[sr], v_[sv], rn_[sr], vn_[sv]
            g = A[0::2, 1::2]; gv = V[0::2, 1::2]
            ok = (g > 40) & (g < 2500) & (gv < 3800)
            if ok.sum() < 1000:
                rows.append((rd.name, vd.name, 'no mid tones')); continue
            k = float(np.median(gv[ok] / g[ok]))
            corr = float(np.corrcoef(A[::3, ::3].ravel(), V[::3, ::3].ravel())[0, 1])
            nz = noise(A, An, V, Vn, k)
            M = C.mtf(A[0::2, 1::2], An[0::2, 1::2] / np.sqrt(2), V[0::2, 1::2] / k, Vn[0::2, 1::2] / np.sqrt(2) / k)
            cs = colour_shift(V)
            flag = []
            if nz < 0.93 and corr > 0.98: flag.append('FULLER')
            if nz > 1.10: flag.append('noisier')
            if abs(abs(cs[0]) - abs(cs0[0])) > 0.15 or abs(abs(cs[1]) - abs(cs0[1])) > 0.15: flag.append('COLOUR')
            if abs(k - 1) > 0.05: flag.append(f'k{k:.2f}')
            rows.append((rd.name, vd.name, f'k {k:5.3f} noise {nz:5.3f} corr {corr:.3f} shift {dy:+d},{dx:+d} '
                         f'MTFx {M["x"][1]:.2f}/{M["x"][2]:.2f} MTFy {M["y"][1]:.2f}/{M["y"][2]:.2f} '
                         f'colR {cs[0]:+.2f} colB {cs[1]:+.2f} (ref {cs0[0]:+.2f},{cs0[1]:+.2f}) {" ".join(flag)}'))
    for r in rows:
        print(*r)
    (base / 'eval.txt').write_text('\n'.join(' '.join(r) for r in rows))


if __name__ == '__main__':
    main()
