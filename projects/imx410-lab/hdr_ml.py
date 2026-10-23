#!/usr/bin/env python3
"""Single-frame checkerboard HDR (§30), v5: Dual-ISO (Magic Lantern cr2hdr) order on our column-pair checkerboard.

    hdr_ml.py FRAME STOCK --out PNG

Order (see notes/HDR_RECON_REFS.md):
 0. REGISTRATION (the root cause of the dark band / comb / bead rings of v1-v4): the attenuated sample in output
    row y shows physical row y + off, off = the 0738 value in raw rows (G: 16.8 / 32.3 / 64.0 for 0738 = 10/20/40;
    R and B drift ~4-5 rows from top to bottom of the frame). Measured from the frame itself (block matching of
    full vs att of each colour), att samples moved to their physical row (per-colour line, linear row interp).
 1. One radiance scale: full-gain pixels as-is; attenuated pixels through a per-colour monotone LUT att ->
    full-equivalent, fitted on block means of adjacent full/att pairs (the att/full ratio is not constant: it falls
    ~20 % from 100 to 3500 DN, so a straight line leaves the hand-over 5-10 % off). Then every colour is scaled to
    the stock frame's units (0242 = 01 also scales full B by ~0.85).
 2. Bad samples: isolated hot and cold samples (cr2hdr find_and_fix_bad_pixels); column phases col % 16 in
    {1, 5, 9} (detected from the frame) misbehave at strong vertical gradients in checker mode -> clamped to the range
    of their same-colour, same-gain neighbours 4 columns left/right (this was the period-16 comb).
 3. Reliability: full pixels fade out near the clip (t0..t1 of clip, from the brightest full sample in a 5x5
    window, so all colours hand over together); attenuated pixels are kept where the full neighbourhood is
    clipped, or where they differ from the interpolation of full neighbours by more than noise (cr2hdr alias map,
    per-sample chi^2 clipped so one outlier cannot trigger it); elsewhere the (less noisy) interpolation wins.
 4. Each unreliable pixel is replaced (smooth blend) by an edge-aware estimate from same-colour OTHER-gain
    neighbours: green first (horizontal / centred vertical / diagonal candidates, weighted by gradient), then
    R and B in the colour-difference domain against that green.
 5. cr2hdr chroma median on the mosaic (plus-5 cells, 3x3 where att-only), ONE demosaic of the repaired RGGB mosaic
    (Hamilton-Adams green + colour-difference R/B) in an asinh (log-like) domain, chroma blur where att-only.
Runs in ~8 s on a 2022 x 6064 frame (numpy only). HDRML_DEBUG=1/2 dumps weight maps next to --out.
"""
import argparse, json, pathlib, sys, time
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

F32 = np.float32
READ_F, READ_A, SHOT = 100.0, 70.0, 2.0        # var (DN^2): full read, att read (att units), shot per DN (§ notes)
ASINH_S = 24.0                                 # asinh domain: linear below ~24 DN, log above


def sh(a, dy, dx):
    """a shifted so that out[y, x] = a[y + dy, x + dx] (wrapping at the borders)."""
    return np.roll(a, (-dy, -dx), (0, 1))


def gblur(a, sigma):
    r = int(3 * sigma + 0.5)
    x = np.arange(-r, r + 1); k = np.exp(-0.5 * (x / sigma) ** 2); k /= k.sum()
    out = np.zeros_like(a)
    for i, w in zip(x, k):
        out += F32(w) * sh(a, 0, i)
    a2, out = out, np.zeros_like(a)
    for i, w in zip(x, k):
        out += F32(w) * sh(a2, i, 0)
    return out


def lmax(a, ry, rx):
    out = a.copy()
    for dy in range(-ry, ry + 1):
        for dx in range(-rx, rx + 1):
            if dy or dx:
                np.maximum(out, sh(a, dy, dx), out=out)
    return out


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    if m.get('bits') == 14:                                            # l7.py 14-bit frames
        from decode14 import decode14
        img = decode14((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(F32)
        full = 16378.0
    else:
        img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(F32)
        full = 4090.0
    top = m['window'] >> 16
    blk = float(img[1:top - 3].mean())
    return img[top:] - F32(blk), full - blk


def classes(shape):
    rr, cc = np.indices(shape)
    r, c4 = rr % 2, cc % 4
    col = np.where(r == 0, np.where(cc % 2 == 0, 0, 1), np.where(cc % 2 == 0, 2, 3))     # 0 R 1 Gr 2 Gb 3 B
    full = ((r == 0) & (c4 >= 2)) | ((r == 1) & (c4 <= 1))
    return col, full


# full position (row parity, col mod 4) and the adjacent attenuated one of the same colour, same row
PAIRS = {0: (0, 2, 0), 1: (0, 3, 1), 2: (1, 0, 2), 3: (1, 1, 3)}


def block_means(a, B=8):
    n0, n1 = a.shape[0] // B * B, a.shape[1] // B * B
    b = a[:n0, :n1].reshape(n0 // B, B, n1 // B, B)
    return b.mean((1, 3)), b.std((1, 3)), b.max((1, 3))


def fit_lut(raw, clip, attok=None):
    """Per colour: monotone piecewise-linear att -> full map from flat 16x32-px blocks (cr2hdr match_exposures
    does a robust line through medians; our response is curved, so we keep the curve)."""
    luts = {}
    for c, (r, cf, ca) in PAIRS.items():
        fm, fs, fx = block_means(raw[r::2, cf::4]); am, _, ax = block_means(raw[r::2, ca::4])
        ok = (fs < 0.04 * fm + 30) & (fx < 0.97 * clip) & (fm > 20)
        if attok is not None:                                          # blocks without registered att data
            ok &= block_means(attok[r::2, ca::4].astype(F32))[0][:ok.shape[0], :ok.shape[1]] > 0.999
        x, y = am[ok], fm[ok]
        # bins in the (block-mean, nearly noise-free) full value, log spaced; median att per bin
        be = np.geomspace(20, 0.97 * clip, 33)
        xs, ys = [], []
        for a, b in zip(be[:-1], be[1:]):
            q = (y >= a) & (y < b)
            if q.sum() >= 8:
                xs.append(np.median(x[q])); ys.append(np.median(y[q]))
        xs, ys = np.array(xs), np.array(ys)
        keep = np.r_[True, np.diff(np.maximum.accumulate(xs)) > 0.05] & (xs >= np.maximum.accumulate(xs))
        xs, ys = xs[keep], ys[keep]
        nb = len(xs)
        top = ys >= ys[-1] * 0.6
        hi = np.polyfit(xs[top], ys[top], 1) if top.sum() >= 3 else np.polyfit(xs[-3:], ys[-3:], 1)
        mid = (ys > 300) & (ys < 0.7 * clip)
        if mid.sum() < 2:                                              # few flat mid-tone blocks: widen
            mid = (ys > 60) & (ys < 0.9 * clip)
        lo = np.polyfit(xs[mid], ys[mid], 1) if mid.sum() >= 2 else hi
        luts[c] = (xs, ys, hi, lo)
        print(f'LUT {"R Gr Gb B".split()[c]}: att {xs[0]:.0f}..{xs[-1]:.0f} -> full {ys[0]:.0f}..{ys[-1]:.0f};'
              f' {nb} bins; top k {1 / hi[0]:.4f} ({np.log2(hi[0]):.2f} EV), mid k {1 / lo[0]:.4f} c {-lo[1] / lo[0]:.1f}')
    return luts


def apply_lut(v, lut):
    xs, ys, hi, lo = lut
    out = np.interp(v, xs, ys)
    out = np.where(v > xs[-1], ys[-1] + (v - xs[-1]) * hi[0], out)
    out = np.where(v < xs[0], ys[0] + (v - xs[0]) * lo[0], out)
    return out.astype(F32), (np.interp(v, xs[1:], np.diff(ys) / np.maximum(np.diff(xs), 1e-3))).astype(F32)


def wavg(cands):
    """cands: list of (value, gradient, base weight); soft directional choice w = base / (grad + eps)^2."""
    num = np.zeros_like(cands[0][0]); den = np.zeros_like(num)
    for v, g, b in cands:
        w = b / (g * g + 1.0)
        num += w * v; den += w
    return num / den


def green_from_other_gain(M, eps):
    """Estimate at every green pixel from the other-gain greens (all offsets below are other gain, see notes)."""
    gH = (sh(M, 0, -2) + sh(M, 0, 2)) / 2
    dH = np.abs(sh(M, 0, -2) - sh(M, 0, 2))
    out = {}
    for s in (-1, 1):                                   # Gr: near column s=-1 / far +3; Gb: s=+1 / far -3
        near = (sh(M, -1, s) + sh(M, 1, s)) / 2
        far = (sh(M, -1, -3 * s) + sh(M, 1, -3 * s)) / 2
        gV = 0.75 * near + 0.25 * far
        dV = np.abs(sh(M, -1, s) - sh(M, 1, s)) + 0.5 * np.abs(sh(M, -1, -3 * s) - sh(M, 1, -3 * s))
        gD1 = (sh(M, -2, -2) + sh(M, 2, 2)) / 2; dD1 = np.abs(sh(M, -2, -2) - sh(M, 2, 2))
        gD2 = (sh(M, -2, 2) + sh(M, 2, -2)) / 2; dD2 = np.abs(sh(M, -2, 2) - sh(M, 2, -2))
        out[s] = wavg([(gH, dH / eps, 1.0), (gV, dV / (1.5 * eps), 1.0), (gD1, dD1 / eps, 0.5), (gD2, dD2 / eps, 0.5)])
    return out


def green_at_rb(G, eps):
    """Green at R/B positions from the 4 adjacent greens, gradient-weighted (no same-colour Laplacian:
    the same-colour neighbours at +-2 are of mixed gain/reliability)."""
    l, r, u, d = sh(G, 0, -1), sh(G, 0, 1), sh(G, -1, 0), sh(G, 1, 0)
    return wavg([((l + r) / 2, np.abs(l - r) / eps, 1.0), ((u + d) / 2, np.abs(u - d) / eps, 1.0)])


def rb_from_other_gain(M, Gh, sig):
    """X = Gh + weighted mean of (X - Gh) over same-colour other-gain neighbours (0,+-2), (+-2,+-2); neighbours
    across a green edge count little."""
    D = M - Gh
    num = np.zeros_like(M); den = np.zeros_like(M)
    for dy, dx, b in ((0, -2, 1.0), (0, 2, 1.0), (-2, -2, 0.5), (-2, 2, 0.5), (2, -2, 0.5), (2, 2, 0.5)):
        z = (sh(Gh, dy, dx) - Gh) / sig
        w = F32(b) * np.exp(-0.5 * (z / 2.0) ** 2)
        num += w * sh(D, dy, dx); den += w
    return Gh + num / np.maximum(den, 1e-6)


def demosaic(M, col, chroma_w=None, chroma_sigma=2.0):
    """Hamilton-Adams green + colour-difference R/B, in the asinh domain (ratios, not differences, at bright
    points: no overshoot rings on small highlights)."""
    Y = np.arcsinh(M / ASINH_S).astype(F32)
    isG = (col == 1) | (col == 2)
    l2, r2, u2, d2 = sh(Y, 0, -2), sh(Y, 0, 2), sh(Y, -2, 0), sh(Y, 2, 0)
    l, r, u, d = sh(Y, 0, -1), sh(Y, 0, 1), sh(Y, -1, 0), sh(Y, 1, 0)
    gH = (l + r) / 2 + (2 * Y - l2 - r2) / 4
    gV = (u + d) / 2 + (2 * Y - u2 - d2) / 4
    dH = np.abs(l - r) + np.abs(2 * Y - l2 - r2)
    dV = np.abs(u - d) + np.abs(2 * Y - u2 - d2)
    wH = 1 / (dH * dH + 1e-4); wV = 1 / (dV * dV + 1e-4)
    G = np.where(isG, Y, (wH * gH + wV * gV) / (wH + wV))
    out = [None, G, None]
    for ci, cc in ((0, 0), (2, 3)):
        isX = col == cc
        D = np.where(isX, Y - G, 0).astype(F32)
        # at the opposite colour: diagonal mean; at greens: the two neighbours in the row/col that has X
        diag = (sh(D, -1, -1) + sh(D, -1, 1) + sh(D, 1, -1) + sh(D, 1, 1)) / 4
        opp = 3 if cc == 0 else 0
        Dx = np.where(col == opp, diag, D)
        hz = (sh(Dx, 0, -1) + sh(Dx, 0, 1)) / 2
        vt = (sh(Dx, -1, 0) + sh(Dx, 1, 0)) / 2
        rowX = (np.indices(M.shape)[0] % 2) == (0 if cc == 0 else 1)
        Dg = np.where(rowX, hz, vt)            # a green in X's row has X left/right, else above/below
        Dall = np.where(isX, D, np.where(isG, Dg, Dx))
        out[ci] = G + Dall
    if chroma_w is not None:
        # chroma (log-ratio) blur where the content is attenuated-only: a highlight sampled by half the pixels
        # aliases into pixel-scale colour speckle that the cell median cannot reach
        for i in (0, 2):
            d = out[i] - G
            out[i] = G + d + chroma_w * (gblur(d.astype(F32), chroma_sigma) - d)
    rgb = np.stack(out, -1)
    return np.sinh(rgb) * F32(ASINH_S)


def chroma_median(M, col, mask, mask9=None):
    """cr2hdr chroma_smooth_2x2: per 2x2 cell, R-G and B-G (log domain) replaced by the median over the cell and
    its 4 neighbour cells (plus shape), where `mask` (per cell) is set."""
    Y = np.arcsinh(M / ASINH_S).astype(F32)
    R, Gr, Gb, B = Y[0::2, 0::2], Y[0::2, 1::2], Y[1::2, 0::2], Y[1::2, 1::2]
    ge = (Gr + Gb) / 2
    out = Y.copy()
    for X, (r, c) in ((R, (0, 0)), (B, (1, 1))):
        dX = X - ge
        st = np.stack([dX, sh(dX, 0, -1), sh(dX, 0, 1), sh(dX, -1, 0), sh(dX, 1, 0)])
        med = np.median(st, 0)
        if mask9 is not None:                                          # cr2hdr chroma_smooth_3x3 where att-only
            st9 = np.stack([sh(dX, dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
            med = np.where(mask9, np.median(st9, 0), med)
        out[r::2, c::2] = np.where(mask, ge + med, X)
    return (np.sinh(out) * F32(ASINH_S)).astype(F32)


def fix_edge_columns(M, full, thr=4.0):
    """Checkerboard mode only: some column phases (col % 16 == 5 most, 1 and 9 less) read darker wherever there is
    a strong vertical gradient (~ -14 % of it, both edge directions; stock frames are clean) -> period-16 dark
    combs hanging from bright edges. Detect the phases from the frame, clamp their samples to the range of the
    same-colour same-gain neighbours 4 columns left/right."""
    lr = (sh(M, 0, -4), sh(M, 0, 4))
    res = M - (lr[0] + lr[1]) / 2
    g = np.abs(sh(M, -2, 0) - sh(M, 2, 0))
    strong = g > 400
    cols = np.arange(M.shape[1]) % 16
    med = np.array([np.median((res / np.maximum(g, 1))[strong & full & (cols[None, :] == c)]) * 100 for c in range(16)])
    rate = np.array([np.mean(np.abs(res[q]) > 0.3 * g[q]) for q in (strong & full & (cols[None, :] == c) for c in range(16))])
    isg = np.isin(np.arange(16) % 4, (0, 3))
    ref = np.array([np.median(rate[isg == isg[c]]) for c in range(16)])
    bad = [c for c in range(16) if abs(med[c] - np.median(med)) > thr or rate[c] > 1.1 * ref[c]]
    out = M
    if bad:
        print(f'edge-column phases: col%16 {bad}  bias {np.round(med[bad] - np.median(med), 1)} % of grad, '
              f'outlier rate x{np.round(rate[bad] / ref[bad], 2)} '
              f'(clamped, both gains: the attenuated samples of these columns misbehave at the same places)')
        q = np.isin(cols, bad)[None, :]
        out = np.where(q, np.clip(M, np.minimum(*lr), np.maximum(*lr)), M)
    return out


def estimate_row_offset(raw, clip, max_rows=300, step=24):
    """The attenuated sample of output row y shows physical row y + off (off ~ the 0738 value in raw rows:
    0x10 -> ~16, 0x20 -> ~32, 0x40 -> ~64). Block-wise search on clipped-log images of each colour (full vs att of
    the same colour, same row), sub-row parabola. Measured on 0x20: G 32.2 at every height, but R and B drift from
    ~28.7 at the top to ~33 at the bottom -> one line off_c(y) = a_c + b_c * y per colour (fit through 250-row band
    medians). Returns {colour: (a, b)}."""
    T = 0.6 * clip
    allf, fits = [], {}
    for c, (rp, cf, ca) in PAIRS.items():
        F = raw[rp::2, cf::4]; A = raw[rp::2, ca::4]
        n1 = min(F.shape[1], A.shape[1]); F, A = F[:, :n1], A[:, :n1]
        k = np.median(A[(F > 300) & (F < T)]) / np.median(F[(F > 300) & (F < T)])
        lF = np.log(np.clip(F, 30, T)); lA = np.log(np.clip(A / k, 30, T))
        H, W = lF.shape; R = max_rows // 2
        found = []
        for by in range(R, H - R - 48, step):
            for bx in range(0, W - 48, step):
                f = lF[by: by + 48, bx: bx + 48]
                if f.std() < 0.4:
                    continue
                errs = np.array([np.mean(np.abs(lA[by - d: by - d + 48, bx: bx + 48] - f)) for d in range(-R, R + 1)])
                i = int(np.argmin(errs))
                if errs[i] < 0.6 * errs[R] and 0 < i < 2 * R:
                    a, b_, cc = errs[i - 1], errs[i], errs[i + 1]
                    found.append((2 * (by + 24) + rp, 2 * (i - R + 0.5 * (a - cc) / (a - 2 * b_ + cc))))
        found = np.array(found).reshape(-1, 2); allf.append(found)
        xs, ys, ws = [], [], []
        for lo in range(0, raw.shape[0], 250):
            q = (found[:, 0] >= lo) & (found[:, 0] < lo + 250)
            if q.sum() >= 4:
                xs.append(np.median(found[q, 0])); ys.append(np.median(found[q, 1])); ws.append(np.sqrt(q.sum()))
        if len(xs) >= 3:
            fits[c] = tuple(np.polyfit(xs, ys, 1, w=ws)[::-1])
        elif len(found) >= 5:
            fits[c] = (float(np.median(found[:, 1])), 0.0)
    pooled = np.concatenate(allf)
    if len(pooled) < 5:
        print(f'row offset: only {len(pooled)} blocks, assuming 0'); return {c: (0.0, 0.0) for c in range(4)}
    for c in range(4):
        fits.setdefault(c, (float(np.median(pooled[:, 1])), 0.0))
    print('row offset of the attenuated group (raw rows, top -> bottom): ' + '  '.join(
        f'{n} {fits[c][0]:.1f}->{fits[c][0] + fits[c][1] * raw.shape[0]:.1f}' for c, n in enumerate('R Gr Gb B'.split()))
        + f'  ({len(pooled)} blocks)')
    return fits


def register_att(raw, full, fits):
    """Move every attenuated sample to the physical row it shows: att at physical row p = linear interpolation of
    the same colour's att samples at output row p - off_c(p) (same-colour rows are 2 apart). Returns the registered
    mosaic and a mask of att samples that had data."""
    out = raw.copy(); ok = np.ones(raw.shape, bool)
    for c, (rp, cf, ca) in PAIRS.items():
        a, b = fits[c]
        if a == 0 and b == 0:
            continue
        P = raw[rp::2, ca::4]                                         # one colour's att plane, rows 2 apart
        n = P.shape[0]
        prow = 2 * np.arange(n) + rp
        src = (prow - (a + b * prow) - rp) / 2.0                       # source index in plane rows
        i0 = np.floor(src).astype(int); f = (src - i0).astype(F32)[:, None]
        good = (i0 >= 2) & (i0 + 1 < n)                                 # first output rows are junk
        i0c = np.clip(i0, 0, n - 2)
        Q = (1 - f) * P[i0c] + f * P[i0c + 1]
        out[rp::2, ca::4] = Q
        ok[rp::2, ca::4] = good[:, None]
    return out, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('frame'); ap.add_argument('stock'); ap.add_argument('--out', required=True)
    ap.add_argument('--t0', type=float, default=0.80, help='full pixels start handing over at t0*clip')
    ap.add_argument('--t1', type=float, default=0.93, help='... and are fully replaced at t1*clip')
    ap.add_argument('--no-alias', action='store_true'); ap.add_argument('--no-chroma', action='store_true')
    ap.add_argument('--offset', type=int, default=None, help='att-group row offset (default: measured; = the 0738 value)')
    ap.add_argument('--lut', default=None, help='JSON {colour: [[att, true], ...]} from a calibration sweep')
    ap.add_argument('--k', default=None, help='fixed attenuation per colour "R,G,B" (att = k * full): skips the '
                    'per-frame LUT fit, e.g. 0738=0x80 -> "0.0244,0.0146,0.0244"')
    o = ap.parse_args()
    t_start = time.time()
    raw, clip = load(pathlib.Path(o.frame)); st, _ = load(pathlib.Path(o.stock))
    col, full = classes(raw.shape)
    # ---- 0. register the attenuated group: att samples of output row y belong to physical row y + off
    if o.offset is None:
        fits = estimate_row_offset(raw, clip)
    else:
        fits = {c: (float(o.offset), 0.0) for c in range(4)}
    raw, attok = register_att(raw, full, fits)
    attok |= full
    # ---- 1. one radiance scale
    if o.lut:
        import json as _j
        L = _j.loads(pathlib.Path(o.lut).read_text()); luts = {}
        for c in range(4):
            pts = np.array(L[str(c)]); xs, ys = pts[:, 0], pts[:, 1]
            hi = np.polyfit(xs[-4:], ys[-4:], 1); lo = np.polyfit(xs[:6], ys[:6], 1)
            luts[c] = (xs, ys, hi, lo)
        print('calibrated LUT from', o.lut)
    elif o.k:
        kr, kg, kb = (float(x) for x in o.k.split(','))
        luts = {}
        for c, k in zip(range(4), (kr, kg, kg, kb)):
            xs = np.array([0.0, 4095.0]); ys = xs / k
            luts[c] = (xs, ys, np.array([1 / k, 0.0]), np.array([1 / k, 0.0]))
        print('fixed k (R, G, B):', kr, kg, kb)
    else:
        luts = fit_lut(raw, clip, attok)
    M = raw.copy(); slope = np.ones_like(raw)
    for c in range(4):
        m = (col == c) & ~full
        M[m], _ = apply_lut(raw[m], luts[c])
        slope[m] = luts[c][3][0]                     # noise gain: mid-range 1/k (local LUT slope is noisy)
    # per colour, full -> stock units (0242 = 01 changes full B by ~0.85)
    scale = np.ones(4, F32)
    for c, (r, cf, _) in PAIRS.items():
        fm, fs, fx = block_means(raw[r::2, cf::4]); sm, ss, sx = block_means(st[r::2, cf::4])
        ok = (ss < 0.04 * sm + 30) & (sx < 0.8 * clip) & (fx < 0.8 * clip) & (sm > 200)
        scale[c] = np.median(sm[ok] / fm[ok])
    print('full -> stock scale R Gr Gb B:', np.round(scale, 4))
    scl = scale[col]
    # noise variance in full units (§ temporal pair: full var = 100 + 2 L; att var = 70 + 2 k L in att DN)
    Lpos = np.maximum(M, 0)
    V = np.where(full, READ_F + SHOT * Lpos, READ_A * slope ** 2 + SHOT * Lpos).astype(F32)
    # ---- 2. hot pixels (same colour, same gain: (+-2,0), (0,+-4), (+-2,+-4))
    nbs = np.stack([sh(M, dy, dx) for dy, dx in ((-2, 0), (2, 0), (0, -4), (0, 4), (-2, -4), (-2, 4), (2, -4), (2, 4))])
    nmax = nbs.max(0); nmed = np.median(nbs, 0); nmin = nbs.min(0)
    hot = (M - nmax > 4 * np.sqrt(V)) & (M > 1.5 * np.maximum(nmed, 0) + 6 * np.sqrt(V))
    # cold (cr2hdr: 'much darker than the brightest neighbour'): below all eight and below half their median
    sN = np.sqrt(np.where(full, READ_F, READ_A * slope ** 2) + SHOT * np.maximum(nmed, 0))
    cold = (nmin - M > 4 * sN) & (M < 0.5 * nmed - 4 * sN)
    M = np.where(hot | cold, nmed, M); del nbs
    M = fix_edge_columns(M, full).astype(F32)
    print(f'hot {hot.mean() * 100:.3f}%  cold {cold.mean() * 100:.3f}%')
    # ---- 3a. full-pixel reliability: brightest full raw sample (any colour) in 5x5, ramp t0..t1
    peak = lmax(np.where(full, raw, 0).astype(F32), 2, 2)
    cF = np.clip((o.t1 * clip - peak) / ((o.t1 - o.t0) * clip), 0, 1).astype(F32)
    cF = np.where(raw >= 0.995 * clip, 0, cF) * full                  # a clipped full sample is never kept
    noatt = lmax((~attok).astype(F32), 4, 4) > 0                       # rows without att data: nothing to replace with
    cF = np.where(full & noatt, 1.0, cF).astype(F32)
    # ---- 4. estimates from other-gain neighbours
    sig = np.sqrt(np.maximum(V, 1)).astype(F32)
    Mw = M * scl                                                       # colour-balanced (stock units)
    sigw = sig * scl
    gest = green_from_other_gain(Mw, gblur(sigw, 1.0) * 2)
    isG = (col == 1) | (col == 2)
    Eg = np.where(col == 1, gest[-1], gest[1])
    # att greens: interpolation of full greens is only valid where those are reliable
    fullnb = gblur(np.where(full, cF, 0).astype(F32), 1.5) / np.maximum(gblur(full.astype(F32), 1.5), 1e-3)
    # alias map (cr2hdr): keep the native attenuated sample where it disagrees with the interpolation beyond noise
    Vg_e = gblur(np.where(full, V, 0).astype(F32), 1.5) / np.maximum(gblur(full.astype(F32), 1.5), 1e-3) / 3
    def alias_weight(native, est, Vn):
        z2 = (native - est) ** 2 / (Vn + Vg_e * scl ** 2)                # chi^2 per att sample, 1 for pure noise
        z2 = np.where(full, 0, np.minimum(z2, 9.0)).astype(F32)         # one outlier (hot / odd sample) can't trigger
        z2 = gblur(z2, 1.5) / np.maximum(gblur((~full).astype(F32), 1.5), 1e-3)   # local mean over ~14 att samples
        return lmax(np.clip((z2 - 2.0) / 2.0, 0, 1).astype(F32), 1, 2)
    al_g = np.zeros_like(M) if o.no_alias else alias_weight(Mw, Eg, V * scl ** 2)
    keepA = (1 - fullnb * (1 - al_g)) * attok                          # weight of the native att sample
    keep = np.where(full, cF, keepA)
    G1 = np.where(isG, keep * Mw + (1 - keep) * Eg, 0).astype(F32)
    Gh = green_at_rb(G1, gblur(sigw, 1.0) * 2)
    Erb = rb_from_other_gain(Mw, Gh, gblur(sigw, 1.0) * 1.5)
    if not o.no_alias:
        al_rb = alias_weight(Mw, Erb, V * scl ** 2)
        keepA = (1 - fullnb * (1 - np.where(isG, al_g, al_rb))) * attok
        keep = np.where(full, cF, keepA)
    E = np.where(isG, Eg, Erb)
    R = (keep * Mw + (1 - keep) * E).astype(F32)
    print(f'replaced: full {np.mean(1 - cF[full]) * 100:.1f}%  att {np.mean(1 - keep[~full]) * 100:.1f}%')
    if __import__('os').environ.get('HDRML_DEBUG') == '2':
        np.savez(str(o.out).replace('.png', '_full_dbg.npz'), keep=keep, M=Mw, R=R, E=E)
    if __import__('os').environ.get('HDRML_DEBUG'):
        np.savez_compressed(str(o.out).replace('.png', '_dbg.npz'), keep=keep[600:960, 2240:3240], cF=cF[600:960, 2240:3240],
                            fullnb=fullnb[600:960, 2240:3240], alg=al_g[600:960, 2240:3240], Mw=Mw[600:960, 2240:3240], E=E[600:960, 2240:3240], R=R[600:960, 2240:3240])
    # ---- 5. chroma median where the mosaic is noisy (replaced or attenuated-native samples) and bright enough
    if not o.no_chroma:
        noisy = np.where(full, 1 - keep, keep)                          # att-derived content
        cell = gblur(noisy.astype(F32), 2.0)[0::2, 0::2]
        gcell = (R[0::2, 1::2] + R[1::2, 0::2]) / 2
        R = chroma_median(R, col, (cell > 0.15) & (gcell > 4 * ASINH_S), cell > 0.6)
    cw = None
    if not o.no_chroma:
        cw = np.clip(gblur(np.where(full, 1 - keep, 0).astype(F32), 2.0) * 4, 0, 1).astype(F32)
    H = demosaic(R, col, cw)
    S = demosaic(st, col)                                 # stock: same demosaic, stock units
    print(f'reconstruction {time.time() - t_start:.1f} s')
    mid = (S[..., 1] > 200) & (S[..., 1] < 3000)
    wb = S[mid].mean(0); wb = wb[1] / wb
    H, S = H * wb, S * wb
    hi = np.percentile(H, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    th, ts = tone(H), tone(S)
    Image.fromarray(np.concatenate([ts, th], 0)[::4, ::4]).save(o.out)
    for n, (r0, r1, c0, c1) in dict(edge=(360, 600, 1320, 1920), card=(720, 960, 2640, 3240),
                                    rim=(600, 840, 2240, 2840), dark=(0, 240, 40, 640)).items():
        Image.fromarray(np.concatenate([ts[r0:r1, c0:c1], th[r0:r1, c0:c1]], 1)).save(str(o.out).replace('.png', f'_{n}.png'))
    print('saved', o.out)


if __name__ == '__main__':
    main()
