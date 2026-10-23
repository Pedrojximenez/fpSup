#!/usr/bin/env python3
"""Anti-flicker (RESEARCH_DIRECTION #6). The rolling shutter samples the light in time: row r is exposed at
t = r * HMAX / 72 MHz (+ frame start), so the row profile of a short exposure divided by that of a long one is the
lamp's waveform.

    flicker.py OUT [--parts wave,band,lock]
  wave  exposure 100 µs (gain held high) vs full-frame reference: waveform, frequency, depth
  band  banding amplitude for exposures 1000 / 4167 / 8333 / 16600 µs
  lock  HMAX 480 x VMAX 2500 = exactly 60.000 fps, then VMAX 2502: flicker phase over successive frames
Virtual V1 (mode 10 rows), SHS/gain/HCG held by IMXB substitution, fixed shutter (AE off).
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
from vmaxmin import VREG                                              # noqa: E402

HREG = 0x30100004


def fit(p, dt_us, fmin=40, fmax=1000):
    """best fundamental f (Hz) for a + sum_{h=1..3} harmonics; returns f, depth (peak-peak / mean of the fit), phase"""
    t = np.arange(len(p)) * dt_us * 1e-6
    best = None
    for f in np.arange(fmin, fmax, 0.25):
        cols = [np.ones_like(t)]
        for h in (1, 2, 3):
            cols += [np.cos(2 * np.pi * h * f * t), np.sin(2 * np.pi * h * f * t)]
        A = np.stack(cols, 1)
        c, *_ = np.linalg.lstsq(A, p, rcond=None)
        r = float(np.sum((A @ c - p) ** 2))
        if best is None or r < best[0]:
            best = (r, f, c, A)
    r, f, c, A = best
    m = A @ c
    return dict(f=float(f), depth=float((m.max() - m.min()) / c[0]), phase=float(np.arctan2(-c[2], c[1])),
                resid=float(np.sqrt(r / len(p)) / c[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--parts', default='wave,band,lock')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    parts = a.parts.split(',')
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, 'V1'); s = b.s; s.pair = False
    v0, h0 = B.P().mem_get(VREG)[0], B.P().mem_get(HREG)[0]
    top = s.base_window >> 16
    st = B.bus_state(); res = {}

    def setexp(t_us, vmax, hmax, code):
        L = t_us * 72 / hmax
        shs = max(4, round((vmax - L) / 2))
        B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, code & 0xFF), (0x003E, code >> 8),
                        (0x003F, code & 0xFF), (0x0040, code >> 8), (0x05E1, 0)])
        time.sleep(0.3)
        return (vmax - 2 * shs) * hmax / 72

    def prof(name):
        d = out / name
        if not s.grab(d):
            return None
        f, m = R.decode(d)
        p = f[0][top:, 100:-100].mean(1)
        for q in d.glob('frame*.raw'):
            q.unlink()
        np.save(out / f'{name}.npy', p)
        return p

    def code_for(gain):
        return int(min(3899, max(0, round(4095 - 4095 / gain))))

    try:
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        vmax, hmax = (v0 >> 16) + 1, 445
        dt = hmax / 72
        setexp(16600, vmax, hmax, 0)
        ref = prof('ref')
        res['ref_level'] = float(ref.mean())
        if 'wave' in parts:
            e = setexp(100, vmax, hmax, code_for(16600 / 100))
            p = prof('short100')
            w = (p - 256) / np.maximum(ref - 256, 1)
            r = fit(w / w.mean(), dt)
            res['wave'] = dict(exposure_us=e, **r)
            print(f'wave: exposure {e:.0f} µs  flicker {r["f"]:.2f} Hz  depth {100 * r["depth"]:.1f} %  fit resid {100 * r["resid"]:.2f} %', flush=True)
        if 'band' in parts:
            res['band'] = {}
            for t in (1000, 4167, 8333, 16600):
                e = setexp(t, vmax, hmax, code_for(16600 / t))
                p = prof(f'band{t}')
                w = (p - 256) / np.maximum(ref - 256, 1)
                w = w / w.mean()
                r = fit(w, dt, 100, 140)
                res['band'][t] = dict(exposure_us=e, std=float(w.std()), **r)
                print(f'band: exposure {e:.0f} µs  row-profile std {100 * w.std():.2f} %  fitted depth {100 * r["depth"]:.2f} % at {r["f"]:.1f} Hz', flush=True)
        if 'lock' in parts:
            res['lock'] = {}
            B.wr(HREG, (480 - 1) | (480 - 1) << 16)
            for vm in (2500, 2502):
                B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
                setexp(1000, vm, 480, code_for(16.6))
                seq = []
                for k in range(8):
                    fc = s_fc()
                    p = prof(f'lock{vm}_{k}')
                    w = (p - 256) / np.maximum(ref[:len(p)] - 256, 1)
                    r = fit(w / w.mean(), 480 / 72, 100, 140)
                    seq.append(dict(fc=fc, f=r['f'], phase=r['phase'], depth=r['depth']))
                    time.sleep(0.2)
                res['lock'][vm] = seq
                ph = np.unwrap([q['phase'] for q in seq])
                print(f'lock VMAX {vm} ({72e6 / (480 * vm):.3f} fps): phases', ' '.join(f'{x:.2f}' for x in ph),
                      ' frame counts', [q['fc'] for q in seq], flush=True)
        (out / 'res.json').write_text(json.dumps(res, indent=1))
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(HREG, h0); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()


def s_fc():
    r = B.P().sh('imager mode_now')
    for line in r.splitlines():
        if line.startswith('frame_count'):
            return int(line.split(',')[0].split(':')[1])
    return -1


if __name__ == '__main__':
    main()
