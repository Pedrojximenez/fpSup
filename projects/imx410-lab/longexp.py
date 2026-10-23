#!/usr/bin/env python3
"""Long exposure for ultra-low fps / slow shutter (2026-10-23; IMX410_RULES §44): only needed below what VMAX alone
reaches. Per base (virtual donor rows, firmware switch), fixed analog gain 0x400:
  vmax   SHS 4, VMAX = 2700 .. 65535: signal/(VMAX-8) must stay constant (is the 16-bit VMAX usable to its end?)
  accum  VMAX 2700, SHS 4, 0007 = n (1, 2, 4): 12 consecutive frames (frame_cb burst): bright every n+1 frames at
         (n+1) x the n = 0 level, black in between, frame interval = VMAX law
  shs    n = 2 with SHS = VMAX/2: where the shutter sits inside the accumulated exposure
0007/0008 are rewritten by the firmware every frame, so they are held by IMXB substitution (as AE would carry them).
Nothing is written to the settings area or the card.

    longexp.py OUT [--base V1,V3,V2]
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B
import resweep as R
import hsburst
from decode12 import decode12
from decode14 import decode14

VREG = 0x30100020
GAIN = [(0x003D, 0x00), (0x003E, 0x04), (0x003F, 0x00), (0x0040, 0x04)]


def good_rows(x, top):
    # V3 r1: the donor-98 full readout ran past the readable rows -- the last ~487 rows read 4095 and polluted every
    # mean (§64). Use only rows that are not mostly clipped.
    img = x[top + 4:-4, 60:-60]
    return img[(img > 4000).mean(1) < 0.5]


def level(d, top, bits):
    if bits == 14:
        m = json.loads((d / 'frame.json').read_text()); m['bits'] = 14; (d / 'frame.json').write_text(json.dumps(m))
    f, _ = R.decode(d)
    return float(np.mean([good_rows(x, top).mean() - x[4:max(top - 4, 6), 60:-60].mean() for x in f]))


def one(base, out):
    d0 = out / base; d0.mkdir(parents=True, exist_ok=True)
    import struct, vmode
    vmode.KEEP_WINDOW = True       # r1-r3 ran without it: vmode rewrote the donor window, the source of the 'bottom 487 rows
                                   # clipped' (SMC_VERIFY round 13) -- good_rows() stays as a guard
    donor = R.BASES[base][0]
    top = struct.unpack_from('<H', vmode.donor_rows(donor)['TIM'], 0xE)[0]     # first image row of the donor
    b = R.Base(d0, base); s = b.s; s.pair = True
    bits = 14 if base == 'V2' else 12
    st = B.bus_state(); res = dict(base=base)
    v0 = B.P().mem_get(VREG)[0]; vbase = (v0 >> 16) + 1
    try:
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        # 1. VMAX range
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0)] + GAIN); time.sleep(0.3)
        pts = []
        for vm in (vbase, 8000, 12000, 16000, 16384):           # 16385 wedged the shell (14-bit field wraps to a tiny VMAX)
            want = ((vm - 1) << 16) | (v0 & 0xFFFF)
            B.wr(VREG, want, verify=False); time.sleep(max(0.3, 3 * vm * 445 / 72e6))
            got = B.P().mem_get(VREG)[0]               # longexp r1: VMAX 32000 "did not stick" -- record what the
            if got != want:                            # register keeps instead of stopping (field width?)
                pts.append((vm, None)); res.setdefault('vmax_readback', {})[vm] = f'0x{got:08X}'
                print('vmax', vm, 'reads back', hex(got), flush=True)
                continue
            dd = d0 / f'vmax{vm}'
            if s.grab(dd):
                pts.append((vm, level(dd, top, bits)))
            else:
                pts.append((vm, None))
            print('vmax', vm, pts[-1][1], flush=True)
        k = [p[1] / (p[0] - 8) for p in pts if p[1] is not None]
        res['vmax'] = dict(points=pts, k=k, max_ok=max((p[0] for p in pts if p[1] is not None), default=None),
                           PASS=bool(k) and (max(k) - min(k)) / max(k) < 0.06)
        print('vmax', res['vmax'], flush=True)
        # 2. accumulation: consecutive frames
        B.wr(VREG, ((vbase - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
        res['accum'] = {}
        for n in (0, 1, 2, 4):
            B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x0007, n), (0x0008, 0)] + GAIN); time.sleep(0.5)
            meta, raws = hsburst.burst(s, n=12, enum=1 if bits == 14 else 0)
            dec = decode14 if bits == 14 else decode12
            lv, obs = [], []
            for r in raws:
                a = dec(r, meta['h'], meta['words']).astype(np.float64) / (4 if bits == 14 else 1)
                lv.append(float(good_rows(a, top).mean() - a[4:max(top - 4, 6), 60:-60].mean()))
                obs.append(float(a[4:max(top - 4, 6), 60:-60].mean()))
            dt = [int(x) for x in np.diff([e[0] for e in meta['ents']])]
            res['accum'][n] = dict(levels=[round(x, 1) for x in lv], obs=[round(x, 1) for x in obs], dt=dt)
            print('accum', n, [round(x) for x in lv], dt[:6], flush=True)
        # judge: n = 0 level L; for n, bright frames ~ (n+1) L every n+1 frames, the others ~ 0
        L = float(np.median(res['accum'][0]['levels']))
        for n in (1, 2, 4):
            lv = np.array(res['accum'][n]['levels'])
            bright = lv > 0.5 * (n + 1) * L
            if 'obs' in res['accum'][n]:
                bright = np.array(res['accum'][n]['obs']) > 100          # empty frames read ~0 in the OB rows
            idx = np.nonzero(bright)[0]
            per = np.diff(idx).tolist()
            ratio = float(np.median(lv[bright]) / L) if bright.any() else 0.0
            # empty frames read OB 0 and a flat image pedestal (~256 above OB) -- longexp5: judging their image-minus-OB
            # against 0 failed every n although period and ratio were right; empty = OB ~ 0 is the test
            obs_ = np.array(res['accum'][n]['obs'])
            res['accum'][n].update(period=per, ratio=round(ratio, 3),
                                   PASS=bool(len(idx) >= 2 and all(p == n + 1 for p in per) and abs(ratio - (n + 1)) < 0.1 * (n + 1)
                                             and np.all(obs_[~bright] < 5)))
            print('accum judge', n, res['accum'][n]['period'], res['accum'][n]['ratio'], res['accum'][n]['PASS'], flush=True)
        # 3. shutter inside an accumulated exposure
        res['shs_scan'] = {}
        for shs in (vbase // 4, vbase // 2, 3 * vbase // 4):      # exposure law with accumulation (n = 2)
            B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x0007, 2), (0x0008, 0)] + GAIN); time.sleep(0.5)
            meta, raws = hsburst.burst(s, n=6, enum=1 if bits == 14 else 0)
            dec = decode14 if bits == 14 else decode12
            vals = []
            for r in raws:
                a = dec(r, meta['h'], meta['words']).astype(np.float64) / (4 if bits == 14 else 1)
                if a[4:max(top - 4, 6), 60:-60].mean() > 100:
                    vals.append(float(good_rows(a, top).mean() - a[4:max(top - 4, 6), 60:-60].mean()))
            res['shs_scan'][shs] = dict(ratio=round(max(vals) / L, 3) if vals else None, lines=round(max(vals) / L * (vbase - 4)) if vals else None)
            print('shs', shs, res['shs_scan'][shs], flush=True)
        B.bus_subs(st, [(0x0005, (vbase // 2) & 0xFF), (0x0006, (vbase // 2) >> 8), (0x0007, 2), (0x0008, 0)] + GAIN); time.sleep(0.5)
        meta, raws = hsburst.burst(s, n=12, enum=1 if bits == 14 else 0)
        dec = decode14 if bits == 14 else decode12
        lv = []
        for r in raws:
            a = dec(r, meta['h'], meta['words']).astype(np.float64) / (4 if bits == 14 else 1)
            lv.append(float(good_rows(a, top).mean() - a[4:max(top - 4, 6), 60:-60].mean()))
        br = max(lv)
        res['shs'] = dict(levels=[round(x, 1) for x in lv], bright_over_L=round(br / L, 3),
                          expected_if_shs_cuts_first_frame=round(3 - (vbase // 2) / vbase, 3))
        print('shs', res['shs'], flush=True)
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0'); B.wr(VREG, v0)
        finally:
            b.close()
    (d0 / 'result.json').write_text(json.dumps(res, indent=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--base', default='V1,V3,V2')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    import fastsweep as F
    F.cached_assemble(); B.not_recording()
    for base in a.base.split(','):
        one(base, out)


if __name__ == '__main__':
    main()
