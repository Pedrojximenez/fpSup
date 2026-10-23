#!/usr/bin/env python3
"""Does the sensor really run at the SoC's VMAX? (vmaxmin.py: the frame counter follows VMAX down to 0.91 ms, frames
stay intact, but the image level does not move with VMAX.) Exposure = (VMAX_sensor - 2*SHS) lines: sweep SHS at a
fixed SoC VMAX and find where the image goes black. Zero at SHS = VMAX/2 -> the sensor follows the SoC; zero further
out -> the sensor runs its own, longer frame.

    shszero.py OUT --rows N --vmax V --shs 4,20,...
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
from vmaxmin import window, period, VREG, WREG                        # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--rows', type=int, default=254); ap.add_argument('--vmax', type=int, default=147)
    ap.add_argument('--shs', default='4,20,40,60,70,73,80,100,120,140,146,160,200')
    ap.add_argument('--extra', default='', help='SoC writes ADDR=VAL,... after the VMAX write')
    ap.add_argument('--donor', type=int, help='virtual mode from this donor instead of V1 (no window change)')
    ap.add_argument('--timv', type=int, help='with --donor: timing-table VMAX written into the virtual row')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / ((f'd{a.donor}_t{a.timv}_v{a.vmax}' if a.donor else f'n{a.rows}_v{a.vmax}') + ('_x' + a.extra.replace('=', '_').replace(',', '_') if a.extra else '')); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    rows = None
    if a.donor:
        import vmode, struct
        rows = vmode.donor_rows(a.donor)
        if a.timv:
            t = bytearray(rows['TIM']); struct.pack_into('<H', t, 8, a.timv); rows['TIM'] = bytes(t)
    b = R.Base(out, 'V1', rows=rows)
    s = b.s; s.pair = False
    v0, w0 = B.P().mem_get(VREG)[0], B.P().mem_get(WREG)[0]
    top = s.base_window >> 16
    st = B.bus_state(); res = []
    try:
        if not a.donor:
            window(s, top, a.rows)
        if a.vmax:
            B.wr(VREG, ((a.vmax - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.2)
        for e in [x for x in a.extra.split(',') if x]:
            ad, va = (int(q, 0) for q in e.split('='))
            B.wr(ad, va)
        time.sleep(0.2)
        print('SoC VMAX', (B.P().mem_get(VREG)[0] >> 16) + 1, 'HMAX', (B.P().mem_get(0x30100004)[0] & 0x3FFF) + 1, flush=True)
        B.bus_on(st)
        for shs in [int(x) for x in a.shs.split(',')]:
            B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, 0), (0x003E, 0), (0x003F, 0), (0x0040, 0)])
            time.sleep(0.15)
            p = period(s)
            d = out / f's{shs:04d}'
            ok = s.grab(d)
            row = dict(shs=shs, frame=ok, ms=None if p is None else p * 1e3)
            if ok:
                f, m = R.decode(d)
                img = f[0][top:top + a.rows] if not a.donor else f[0][top:]
                row.update(lvl=float(img.mean()), ob=float(f[0][2:top - 2].mean()))
                for q in d.glob('frame*.raw'):
                    q.unlink()
            res.append(row)
            print(f"SHS {shs} frame {ok} period {row['ms'] or 0:.2f} ms lvl {row.get('lvl', 0):.1f} ob {row.get('ob', 0):.1f}", flush=True)
            (out / 'res.json').write_text(json.dumps(res, indent=1))
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(WREG, w0)
        finally:
            b.close()


if __name__ == '__main__':
    main()
