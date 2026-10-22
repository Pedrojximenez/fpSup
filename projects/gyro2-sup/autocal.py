#!/usr/bin/env python3
"""Estimate a lens (focal length, fisheye k1 k2) from a Gyro2 take: no chart.

    autocal.py CLIP_DIR GRAY_RAW [--frames A:B] [--fix-k]

The gyro says how far the camera turned between two frames; tracked points say
where the picture went. A pinhole-plus-distortion model that maps one onto the
other is the lens. GRAY_RAW is the clip as 8-bit gray frames (header u32 n, w,
h), all at one size; the principal point is taken at its centre. Frames are
timed like the plugin: a line through the Vd positions, first row read 0.9 ms
after Vd, rows across the readout, each exposed for the EXIF exposure.

Pure rotation is assumed: on a hand-held take the lens also moves, and a near
subject then looks like a longer lens. Use a distant scene.
"""
import argparse, glob, struct, sys, pathlib
import numpy as np, cv2
from scipy.optimize import least_squares

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fsg2 as F

IDEAL = np.array([1 / 3, 2 / 15, 17 / 315, 62 / 2835])
VD_TO_READOUT_US = 900.0


def exif_exposure(buf):
    def ent(o):
        n = struct.unpack_from('<H', buf, o)[0]
        return {t: (ty, c, v) for t, ty, c, v in (struct.unpack_from('<HHII', buf, o + 2 + 12 * k) for k in range(n))}
    ex = ent(ent(8)[0x8769][2])
    n, d = struct.unpack_from('<II', buf, ex[0x829A][2])
    return n / d


def dng_fps(buf):
    root = struct.unpack_from('<I', buf, 4)[0]
    if root + 2 > len(buf):
        root = 8
    n = struct.unpack_from('<H', buf, root)[0]
    for k in range(n):
        t, ty, c, v = struct.unpack_from('<HHII', buf, root + 2 + 12 * k)
        if t == 0xC764:
            num, den = struct.unpack_from('<ii', buf, v)
            return num / den
    raise ValueError('no FrameRate tag')


def vd_line(recs, fps):
    """Fitted Vd position (samples) per frame, as the plugin does."""
    period_s = recs[0]['period_ps'] * 1e-12
    nominal = 1 / (fps * period_s)
    vds = sorted({r['base_idx'] + pos for r in recs for pos, kind, _ in r['events'] if kind == 3})
    vds = np.array(vds, float)
    idx = np.round((vds - vds[0]) / nominal)
    b, a = np.polyfit(idx, vds, 1)
    line = lambda i: a + b * i
    hooks = np.array([r['base_idx'] + r['frame_mark'] for r in recs], float)
    lags = [h - line(np.floor((h - line(0)) / b)) for h in hooks if h >= line(0)]
    lag = np.median(lags)
    off = np.array([round((h - lag - line(0)) / b) - r['frame_seq'] for h, r in zip(hooks, recs)])
    out = []
    for k, r in enumerate(recs):
        w = sorted(off[max(0, k - 4):k + 5])
        out.append(line(r['frame_seq'] + w[len(w) // 2]))
    return np.array(out)


def theta_of(theta_d, k):
    t = theta_d.copy()
    for _ in range(8):
        t2 = t * t
        f = t * (1 + k[0] * t2 + k[1] * t2 ** 2 + k[2] * t2 ** 3 + k[3] * t2 ** 4) - theta_d
        df = 1 + 3 * k[0] * t2 + 5 * k[1] * t2 ** 2 + 7 * k[2] * t2 ** 3 + 9 * k[3] * t2 ** 4
        t = t - f / df
    return t


def unproject(p, f, c, k):
    q = (p - c) / f
    rho = np.linalg.norm(q, axis=1) + 1e-12
    th = theta_of(rho, k)
    s = np.sin(th) / rho
    return np.stack([q[:, 0] * s, q[:, 1] * s, np.cos(th)], 1)


def project(d, f, c, k):
    r = np.linalg.norm(d[:, :2], axis=1) + 1e-12
    th = np.arctan2(r, d[:, 2])
    t2 = th * th
    thd = th * (1 + k[0] * t2 + k[1] * t2 ** 2 + k[2] * t2 ** 3 + k[3] * t2 ** 4)
    return c + f * (thd / r)[:, None] * d[:, :2]


def rotate(d, rv):
    """Rotate each direction by minus its rotation vector (the camera turned by rv)."""
    out = np.empty_like(d)
    for i, (v, w) in enumerate(zip(d, rv)):
        out[i] = cv2.Rodrigues(-w)[0] @ v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('clip'); ap.add_argument('gray')
    ap.add_argument('--frames', default=None)
    ap.add_argument('--fix-k', action='store_true', help='fit the focal length only (ideal rectilinear lens)')
    ap.add_argument('--pairs', type=int, default=250)
    ap.add_argument('--turn-min', type=float, default=0.15, help='degrees between frames')
    ap.add_argument('--turn-max', type=float, default=0.6)
    ap.add_argument('--fit-time', action='store_true', help='also fit a frame time shift')
    a = ap.parse_args()

    files = sorted(glob.glob(a.clip + '/*.DNG'))
    recs = [F.read_frame(open(p, 'rb').read()) for p in files]
    exposure = exif_exposure(open(files[0], 'rb').read())
    raw = open(a.gray, 'rb').read()
    n, W, H = struct.unpack_from('<III', raw, 0)
    frame = lambda k: np.frombuffer(raw, np.uint8, W * H, 12 + k * W * H).reshape(H, W)
    fps = dng_fps(open(files[0], 'rb').read())
    period = recs[0]['period_ps'] * 1e-12
    readout = recs[0]['readout_ns'] * 1e-9
    gs = recs[0]['gscale']

    # The gyro stream, cumulative (rad), by global sample index.
    first = recs[0]['base_idx']
    stream = {}
    for r in recs:
        for j, s in enumerate(r['samples']):
            stream[r['base_idx'] + j] = s
    idx = np.arange(first, max(stream) + 1)
    g = np.array([stream.get(i, (0, 0, 0)) for i in idx], float) * gs
    cum = np.vstack([np.zeros(3), np.cumsum(g, 0) * period])

    def angle_at(t_samples):
        x = np.clip(t_samples - first, 0, len(cum) - 1)
        lo = np.floor(x).astype(int); hi = np.minimum(lo + 1, len(cum) - 1); fr = (x - lo)[:, None]
        return cum[lo] + (cum[hi] - cum[lo]) * fr

    vd = vd_line(recs, fps)
    start = vd + VD_TO_READOUT_US * 1e-6 / period            # first-row readout, samples
    row_t = lambda k, y: start[k] + ((y / H) * readout - exposure / 2) / period

    lo, hi = (0, min(n, len(recs)) - 1)
    if a.frames:
        lo, hi = (int(x) for x in a.frames.split(':'))
    seq = [r['frame_seq'] for r in recs]
    cand = [k for k in range(lo, hi) if seq[k + 1] == seq[k] + 1]
    rng = np.random.default_rng(1)
    # keep the pairs that turned enough to say something
    turn = []
    for k in cand:
        dv = angle_at(np.array([row_t(k + 1, H / 2)]))[0] - angle_at(np.array([row_t(k, H / 2)]))[0]
        turn.append(np.linalg.norm(dv))
    # Enough turn to measure, little enough that the picture is not smeared
    # (at 1/50 s and 30 deg/s a frame blurs by ~17 px): 0.15-0.6 deg a frame.
    lo_t, hi_t = np.radians(a.turn_min), np.radians(a.turn_max)
    usable = [(t, k) for t, k in zip(turn, cand) if lo_t <= t <= hi_t]
    order = [k for _, k in sorted(usable, reverse=True)][:a.pairs]
    P0, P1, R0, R1 = [], [], [], []
    for k in order:
        A, B = frame(k), frame(k + 1)
        p0 = cv2.goodFeaturesToTrack(A, 300, 0.01, 12)
        if p0 is None:
            continue
        p1, st, _ = cv2.calcOpticalFlowPyrLK(A, B, p0, None, winSize=(21, 21), maxLevel=4)
        back, st2, _ = cv2.calcOpticalFlowPyrLK(B, A, p1, None, winSize=(21, 21), maxLevel=4)
        good = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.linalg.norm((back - p0)[:, 0], axis=1) < 0.5)
        p0, p1 = p0[good, 0], p1[good, 0]
        if len(p0) > 60:
            sel = rng.choice(len(p0), 60, replace=False); p0, p1 = p0[sel], p1[sel]
        P0.append(p0); P1.append(p1)
        R0.append(row_t(k, p0[:, 1])); R1.append(row_t(k + 1, p1[:, 1]))
    P0, P1 = np.vstack(P0), np.vstack(P1)
    R0, R1 = np.concatenate(R0), np.concatenate(R1)
    rv_gyro = angle_at(R1) - angle_at(R0)
    c = np.array([W / 2, H / 2])
    print(f'{len(order)} frame pairs, {len(P0)} point pairs, frame {W}x{H}, exposure {exposure * 1e3:.1f} ms')

    def cam_rv(signs, perm):
        return rv_gyro[:, perm] * signs

    def residual(params, signs, perm):
        f = params[0]
        k = IDEAL.copy()
        if len(params) > 1:
            k[0], k[1] = params[1], params[2]
        d = unproject(P0, f, c, k)
        return (project(rotate(d, cam_rv(signs, perm)), f, c, k) - P1).ravel()

    # Which gyro axis turns the picture which way: try them, at a plausible focal length.
    f0 = 0.85 * W                                        # ~ a normal lens; refined below
    best = None
    for perm in ([1, 0, 2],):                            # gyro X = pan (about camera y), Y = tilt, Z = roll
        for sx in (1, -1):
            for sy in (1, -1):
                for sz in (1, -1):
                    signs = np.array([sx, sy, sz], float)
                    r = least_squares(residual, [f0], args=(signs, perm), loss='soft_l1', f_scale=1.0, max_nfev=50,
                                      bounds=([0.2 * W], [10 * W]))
                    print(f'  signs {signs.astype(int).tolist()}: f {r.x[0]:7.1f} px, cost {r.cost:.0f}')
                    if best is None or r.cost < best[0]:
                        best = (r.cost, signs, perm, r.x[0])
    _, signs, perm, f1 = best
    print(f'axes: camera (x, y, z) = gyro {perm} x {signs.astype(int).tolist()}; focal alone: {f1:.1f} px')
    if a.fit_time:
        # also a time shift (ms) of the frames against the gyro
        def residual_t(params, signs, perm):
            nonlocal rv_gyro
            shift = params[-1] * 1e-3 / period
            rv_gyro = angle_at(R1 + shift) - angle_at(R0 + shift)
            return residual(params[:-1], signs, perm)
        rt = least_squares(residual_t, [f1, 0.0], args=(signs, perm), loss='soft_l1', f_scale=1.0,
                           bounds=([0.2 * W, -30.0], [10 * W, 30.0]))
        print(f'time shift: {rt.x[1]:+.2f} ms (focal {rt.x[0]:.1f} px, cost {rt.cost:.0f})')
        rv_gyro = angle_at(R1 + rt.x[1] * 1e-3 / period) - angle_at(R0 + rt.x[1] * 1e-3 / period)
        f1 = rt.x[0]
    p = [f1] if a.fix_k else [f1, IDEAL[0], IDEAL[1]]
    low = [0.2 * W] + ([] if a.fix_k else [-2.0, -5.0])
    high = [10 * W] + ([] if a.fix_k else [2.0, 5.0])
    r = least_squares(residual, p, args=(signs, perm), loss='soft_l1', f_scale=1.0, bounds=(low, high))
    res = r.fun.reshape(-1, 2)
    inl = np.linalg.norm(res, axis=1) < 2.0
    k = IDEAL.copy()
    if not a.fix_k:
        k[0], k[1] = r.x[1], r.x[2]
    print(f'fit: f {r.x[0]:.1f} px, k {np.round(k, 4).tolist()}; residual median {np.median(np.linalg.norm(res, axis=1)):.3f} px, inliers {inl.mean() * 100:.0f} %')
    # the corner against an ideal lens
    rc = np.hypot(W, H) / 2 / r.x[0]
    th = np.arctan(rc)
    thd = lambda kk: th * (1 + kk[0] * th ** 2 + kk[1] * th ** 4 + kk[2] * th ** 6 + kk[3] * th ** 8)
    print(f'corner vs ideal rectilinear: {(thd(k) / thd(IDEAL) - 1) * 100:+.2f} %')


if __name__ == '__main__':
    main()
