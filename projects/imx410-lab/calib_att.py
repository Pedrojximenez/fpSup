#!/usr/bin/env python3
"""Exposure sweep for the checkerboard HDR (§30): is the attenuated group an overflow store or a low-gain read,
and what is its exact response? 0242 = 01, 0738 = V; the shutter is forced per frame through IMXB substitution
of SHS (0005/0006, the AE's own per-frame writes), so gain and everything else stay put.

    calib_att.py OUT [--v 0x20] [--lines 2600,1300,650,325,162,81,40,20]
exposure lines E = VMAX - 2*SHS (mode 10: VMAX 2700).
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--v', default='0x20')
    ap.add_argument('--lines', default='2600,1300,650,325,162,81,40,20')
    ap.add_argument('--vmax', type=int, default=2700, help='SoC frame length (longer frames allow longer exposures)')
    ap.add_argument('--hcg', type=int, default=0, help='05E1 value forced with --gain (0 LCG, 1 HCG)')
    ap.add_argument('--gain', type=int, default=None, help='analog gain code for 3D/3E and 3F/40 (0 = 0 dB, '
                    '4095(1-10^(-dB/20))); forced through IMXB with the shutter')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    s = F.Session(out, 0, True, 10)
    st = B.bus_state()
    try:
        s.write(0x0242, 1); s.write(0x0738, int(a.v, 16)); time.sleep(0.15)
        if a.vmax != 2700:
            vm = B.P().mem_get(0x30100020)[0]
            B.wr(0x30100020, ((a.vmax - 1) << 16) | (vm & 0xFFFF))      # restored by the session's close()
            time.sleep(0.3)
        for E in (int(x) for x in a.lines.split(',')):
            shs = (a.vmax - E) // 2
            subs = [(0x0005, shs & 0xFF), (0x0006, shs >> 8)]
            if a.gain is not None:
                subs += [(0x003D, a.gain & 0xFF), (0x003E, a.gain >> 8), (0x003F, a.gain & 0xFF), (0x0040, a.gain >> 8),
                         (0x05E1, a.hcg)]                              # HCG adds its own x3.7 (§5b)
            B.bus_subs(st, subs)
            time.sleep(0.25)
            ok = s.grab(out / f'E{E:04d}')
            print(f'E {E} lines (SHS {shs}):', 'ok' if ok else 'NO FRAME')
        B.bus_subs(st, [])
        s.write(0x0738, 0); time.sleep(0.25)
        s.grab(out / 'stock_E_auto')
    finally:
        B.bus_subs(st, [])
        s.write(0x0738, 0); s.write(0x0242, 0)
        s.close()
    (out / 'plan.json').write_text(json.dumps(dict(v=a.v, lines=a.lines, vmax=2700)))


if __name__ == '__main__':
    main()
