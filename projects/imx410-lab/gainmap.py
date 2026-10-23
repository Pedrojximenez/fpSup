#!/usr/bin/env python3
"""Gain / conversion-gain map (supporting research: which analog gain + HCG is cleanest per ISO).

    gainmap.py OUT BASE        BASE = V1 (12-bit 1x1) | V2 (14-bit 1x1)
For analog gain 0..30 dB (3 dB steps) x HCG (05E1) 0/1: SHS, gain and HCG held by IMXB substitution, exposure scaled
by 1/gain so the frame keeps a similar DN spread; one frame pair per point. Offline: offline/gainmap_eval.py
(photon transfer: DN/e- from block mean-variance, read noise from OB rows, dynamic range).
"""
import json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import vmode                                                          # noqa: E402

GAINS = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30]
T0 = 16000.0                                       # µs at 0 dB


def main():
    out, base = pathlib.Path(sys.argv[1]), sys.argv[2]
    d0 = out / base; d0.mkdir(parents=True, exist_ok=True)
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    if base == 'V2':
        vmode.KEEP_WINDOW = True
    b = R.Base(d0, base); s = b.s; s.pair = True
    st = B.bus_state(); log = []
    try:
        vmax = (B.P().mem_get(0x30100020)[0] >> 16) + 1
        hw = B.P().mem_get(0x30100004)[0]
        hmax = min(hw & 0x3FFF, (hw >> 16) & 0x3FFF) + 1
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        for hcg in (0, 1):
            for g in GAINS:
                code = round(4095 - 4095 / 10 ** (g / 20))
                t = T0 / 10 ** (g / 20)
                shs = max(4, round((vmax - t * 72 / hmax) / 2))
                B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, code & 0xFF), (0x003E, code >> 8),
                                (0x003F, code & 0xFF), (0x0040, code >> 8), (0x05E1, hcg)])
                time.sleep(0.3)
                d = d0 / f'h{hcg}_g{g:02d}'
                ok = s.grab(d)
                if ok and b.bits == 14:
                    m = json.loads((d / 'frame.json').read_text()); m['bits'] = 14
                    (d / 'frame.json').write_text(json.dumps(m))
                e = dict(hcg=hcg, gain_db=g, code=code, shs=shs, exposure_us=(vmax - 2 * shs) * hmax / 72, ok=ok,
                         bits=b.bits, top=s.base_window >> 16)
                log.append(e)
                print(base, e, flush=True)
                (d0 / 'log.json').write_text(json.dumps(log, indent=1))
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()


if __name__ == '__main__':
    main()
