#!/usr/bin/env python3
"""Multi-frame long exposure (0007/0008, IMX410_RULES §44; RESEARCH_DIRECTION #5).

    lexp.py OUT [--parts period,r08,shs,noise]

Virtual V1 (mode 10 rows), sensor cropped to 254 rows so a 16-frame burst fits, main SHS and gain held by IMXB
substitution (+ fixed shutter so AE does not open SoC multi-frame exposure). 0007/0008 by substitution too.
  period  0007 = 0,1,2,3,7: 16 consecutive frames (frame_cb burst) -> which frames carry an image, and their level
  r08     0007 = 0, 0008 = 01: single grabs for ~10 s with time stamps -> spacing of the bright frames
  shs     0007 = 1: SHS sweep, bright-frame level -> where the exposure reaches zero
  noise   0007 = 3 bursts (single 4-frame exposures) vs 0007 = 0 bursts (sums of 4 consecutive frames):
          temporal noise per signal level from pairs
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import hsburst                                                        # noqa: E402
from vmaxmin import window, VREG, WREG                                # noqa: E402
from decode12 import decode12                                         # noqa: E402

ROWS = 254


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--parts', default='period,r08,shs,noise')
    ap.add_argument('--gain', type=lambda x: int(x, 0), default=0x400)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    parts = a.parts.split(',')
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, 'V1'); s = b.s; s.pair = False
    v0, w0 = B.P().mem_get(VREG)[0], B.P().mem_get(WREG)[0]
    top = s.base_window >> 16
    vmax = (v0 >> 16) + 1
    st = B.bus_state(); res = dict(vmax=vmax, rows=ROWS)
    g = a.gain

    def subs(shs=4, r7=0, r8=0):
        B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x0007, r7), (0x0008, r8),
                        (0x003D, g & 0xFF), (0x003E, g >> 8), (0x003F, g & 0xFF), (0x0040, g >> 8)])

    def frames(meta, raws):
        return [decode12(r, meta['h'], meta['words']).astype(np.float32)[top:top + ROWS, 60:-60] for r in raws]

    try:
        window(s, top, ROWS)
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        if 'period' in parts:
            res['period'] = {}
            for n in (0, 1, 2, 3, 7):
                subs(r7=n); time.sleep(0.5)
                meta, raws = hsburst.burst(s, n=16)
                lv = [float(f.mean()) for f in frames(meta, raws)]
                res['period'][n] = dict(levels=lv, dt=np.diff([e[0] for e in meta['ents']]).tolist()[:20])
                print(f'0007={n}: levels', ' '.join(f'{x:.0f}' for x in lv), flush=True)
        if 'r08' in parts:
            subs(r7=0, r8=1); time.sleep(0.3)
            seq = []
            t0 = time.time()
            while time.time() - t0 < 10:
                d = out / 'r08' / f'{len(seq):03d}'
                if s.grab(d):
                    f, m = R.decode(d)
                    seq.append((time.time() - t0, float(f[0][top:top + ROWS, 60:-60].mean())))
                    for q in d.glob('frame*.raw'):
                        q.unlink()
            res['r08'] = seq
            br = [t for t, l in seq if l > min(x for _, x in seq) + 20]
            print('0008=01: grabs', len(seq), 'bright at', [round(t, 2) for t in br], 'levels', sorted({round(l) for _, l in seq})[:5], '...', flush=True)
        if 'shs' in parts:
            res['shs'] = {}
            for shs in (4, 700, 1340, 1360, 2000, 2600, 2690, 2710, 3000):
                subs(shs=shs, r7=1); time.sleep(0.4)
                meta, raws = hsburst.burst(s, n=8)
                lv = [float(f.mean()) for f in frames(meta, raws)]
                res['shs'][shs] = lv
                print(f'0007=1 SHS {shs}: max level {max(lv):.1f} levels', ' '.join(f'{x:.0f}' for x in lv), flush=True)
        if 'noise' in parts:
            subs(r7=3); time.sleep(0.5)
            meta, raws = hsburst.burst(s, n=16)
            fl = frames(meta, raws)
            lv = np.array([f.mean() for f in fl])
            longs = [fl[i] for i in np.nonzero(lv > lv.min() + 0.5 * (lv.max() - lv.min()))[0]]
            subs(r7=0); time.sleep(0.5)
            meta, raws = hsburst.burst(s, n=16)
            fs = frames(meta, raws)
            sums = [sum(fs[i:i + 4]) - 3 * 256 for i in (0, 4, 8, 12)]       # black 256 per frame: keep one
            bl = float(np.median(fl[0][:4]))
            res['noise'] = dict(n_long=len(longs))
            if len(longs) >= 2:
                A, Bq = longs[0], longs[1]
                C, D = sums[0], sums[1]
                ref = (A + Bq) / 2
                bins = np.percentile(ref, [5, 20, 40, 60, 80, 95])
                rows = []
                for lo, hi in zip(bins[:-1], bins[1:]):
                    m = (ref >= lo) & (ref < hi)
                    n1 = float(np.std((A - Bq)[m]) / np.sqrt(2)); n2 = float(np.std((C - D)[m]) / np.sqrt(2))
                    rows.append(dict(level=float(ref[m].mean()), level_sum=float(((C + D) / 2)[m].mean()), long=n1, sum4=n2))
                    print(f'level {ref[m].mean():.0f} (sum {((C + D) / 2)[m].mean():.0f}): noise long {n1:.2f}  sum of 4 {n2:.2f}  ratio {n2 / n1:.2f}', flush=True)
                res['noise']['bins'] = rows
            for i, f in enumerate(longs[:2] + sums[:2]):
                np.save(out / f'noise_{i}.npy', f[::2, ::2])
        (out / 'res.json').write_text(json.dumps(res, indent=1, default=str))
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(WREG, w0); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()


if __name__ == '__main__':
    main()
