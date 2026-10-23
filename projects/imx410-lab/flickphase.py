#!/usr/bin/env python3
"""Flicker band placement by phase (user's idea, 2026-10-21): 2x2 fast, 1920x1080 crop (readout ~5.1 ms), frame
locked near one lamp period, short exposure. Let the phase drift (VMAX slightly long), sample many frames, measure
band strength vs flicker phase at the frame start; then park the phase at the best value and lock.

    flickphase.py OUT [--lamp 119.94] [--exp 500]
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import vmode, l7                                                      # noqa: E402
from vmaxmin import VREG, WREG                                        # noqa: E402

HMAX = 330


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--lamp', type=float, default=119.94); ap.add_argument('--exp', type=float, default=500)
    ap.add_argument('--n', type=int, default=48)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    vmode.KEEP_WINDOW = True
    b = R.Base(out, 'V1', rows=vmode.donor_rows(11)); s = b.s; s.pair = False
    v0, w0 = B.P().mem_get(VREG)[0], B.P().mem_get(WREG)[0]
    h0, rx0 = B.P().mem_get(0x30100004)[0], B.P().mem_get(0x3010000C)[0]
    top = 20
    st = B.bus_state(); res = dict(lamp=a.lamp, exp_us=a.exp)
    vlock = round(72e6 / (HMAX * a.lamp))                 # one lamp period per frame
    dt = HMAX / 72e6                                      # seconds per output line

    def subs(exp_us, vm, code):
        L = exp_us * 72 / HMAX
        shs = max(4, round((vm - L) / 2))
        B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, code & 0xFF), (0x003E, code >> 8),
                        (0x003F, code & 0xFF), (0x0040, code >> 8), (0x05E1, 0)])

    def prof(name):
        d = out / name
        if not s.grab(d):
            return None
        f, m = R.decode(d)
        blk = float(np.median(f[0][6:16, 60:-60]))           # OB rows of this mode (black is not 256 here)
        p = f[0][top:end, 60:-60].mean(1) - blk
        for q in d.glob('frame*.raw'):
            q.unlink()
        np.save(d.with_suffix('.npy'), p)
        return p

    try:
        for r, v in ((0x0003, 1), (0x0022, 1000 & 0xFF), (0x0023, 1000 >> 8), (0x0024, 540 & 0xFF), (0x0025, 540 >> 8)):
            s.write(r, v)
        b.restart(); time.sleep(0.3)
        ln = min(B.P().mem_get(0x301005D8)[0] for _ in range(3))
        end = ln - 2
        B.wr(WREG, (w0 & 0xFFFF0000) | end)
        full = (rx0 & 0xFFFF) * 12; x0 = ((full - 1920) // 2) // 12 * 12
        B.wr(0x3010000C, (x0 + 1920) // 12 | (x0 // 12) << 16)
        time.sleep(0.1); l7.rewindow(s, 0)
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        # flat reference: exposure = one lamp period
        B.wr(VREG, ((vlock - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.2)
        subs(1e6 / a.lamp, vlock, 0); time.sleep(0.3)
        ref = prof('ref')
        # drift: frame a little longer than the period, short exposure
        vdrift = vlock + 12
        B.wr(VREG, ((vdrift - 1) << 16) | (v0 & 0xFFFF))
        subs(a.exp, vdrift, int(4095 - 4095 / min(20.0, 1e6 / a.lamp / a.exp)))
        time.sleep(0.4)
        t = np.arange(len(ref)) * dt
        cs, sn = np.cos(2 * np.pi * a.lamp * t), np.sin(2 * np.pi * a.lamp * t)
        rows = []
        for k in range(a.n):
            p = prof(f'd{k:02d}')
            if p is None:
                continue
            w = p / np.maximum(ref, 1); w = w / w.mean()
            A = np.stack([np.ones_like(t), cs, sn], 1)
            c, *_ = np.linalg.lstsq(A, w, rcond=None)
            ph = float(np.arctan2(-c[2], c[1]))           # lamp phase at the first output line
            rows.append(dict(k=k, phase=ph, pp=float(np.ptp(np.convolve(w, np.ones(15) / 15, 'valid'))), std=float(w.std())))
            time.sleep(0.05)
        res['drift'] = rows
        rows.sort(key=lambda r: r['phase'])
        best = min(rows, key=lambda r: r['std']); worst = max(rows, key=lambda r: r['std'])
        print(f'readout {len(ref) * dt * 1e3:.2f} ms of a {1e3 / a.lamp:.2f} ms period; frames {len(rows)}', flush=True)
        for r in rows:
            print(f"phase {r['phase']:+.2f} rad  band std {100 * r['std']:.1f} %  p-p {100 * r['pp']:.1f} %", flush=True)
        print(f"best phase {best['phase']:+.2f} (std {100 * best['std']:.1f} %), worst {worst['phase']:+.2f} (std {100 * worst['std']:.1f} %)", flush=True)
        # park: wait until the drifting phase is near the best, then lock
        tgt = best['phase']; locked = []
        for _ in range(60):
            p = prof('park'); w = p / np.maximum(ref, 1); w = w / w.mean()
            c, *_ = np.linalg.lstsq(np.stack([np.ones_like(t), cs, sn], 1), w, rcond=None)
            ph = float(np.arctan2(-c[2], c[1]))
            if abs(np.angle(np.exp(1j * (ph - tgt)))) < 0.25:
                B.wr(VREG, ((vlock - 1) << 16) | (v0 & 0xFFFF))
                break
        for k in range(8):
            time.sleep(0.25)
            p = prof('locked'); w = p / np.maximum(ref, 1); w = w / w.mean()
            c, *_ = np.linalg.lstsq(np.stack([np.ones_like(t), cs, sn], 1), w, rcond=None)
            locked.append(dict(phase=float(np.arctan2(-c[2], c[1])), std=float(w.std())))
        res['locked'] = locked
        print('locked at VMAX', vlock, ':', ' '.join(f"{q['phase']:+.2f}/{100 * q['std']:.1f}%" for q in locked), flush=True)
        (out / 'res.json').write_text(json.dumps(res, indent=1))
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(WREG, w0); B.wr(0x30100004, h0); B.wr(0x3010000C, rx0)
            B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()


if __name__ == '__main__':
    main()
