#!/usr/bin/env python3
"""Real sensor frame length vs SoC VMAX (direct write), by signal at SHS 4 with gain held at 0 dB: signal is
proportional to the real frame length (exposure = frame - 8 lines). VMAX list walked down then up (hysteresis).

    vmaxreal.py OUT [--vmax 4188,3500,...]
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
from vmaxmin import period, window, VREG, WREG                                      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--rows', type=int, default=0, help='crop the sensor + receiver to N image rows first')
    ap.add_argument('--fast', type=int, default=0, help='1x1 fast AD on V1: mode-8 Family A values + 0001=2C + receiver 4176 + this HMAX')
    ap.add_argument('--hmax', type=int, help='SoC line length written after setup (no other change)')
    ap.add_argument('--timw', type=int, help='V1 rows with the timing-table line length (TIM +0xC, = width + 4) set to this')
    ap.add_argument('--r38w', type=int, help='V1 rows with the DCLP horizontal word count (R38 +8) set to this (receiver px/12 + 1)')
    ap.add_argument('--r38', type=int, help='V1 rows with the DCLP table row (R38) taken from this donor')
    ap.add_argument('--donor', type=int, help='virtual base from this donor (own sensor window kept) instead of V1')
    ap.add_argument('--sensor', default='', help='sensor writes REG=VAL,... after the window, then a restart')
    ap.add_argument('--shutter', type=int, default=4000, help='fixed shutter in µs (AE off: no multi-frame exposure)')
    ap.add_argument('--vmax', default='4188,3500,2700,2300,2100,2062,2000,1800,1500,1031,1500,2062,2700,4188')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    rows, rx0 = None, None
    if a.donor:
        import vmode
        vmode.KEEP_WINDOW = True
        rows = vmode.donor_rows(a.donor)
    if a.r38:
        import vmode
        rows = vmode.donor_rows(10)
        rows['R38'] = vmode.donor_rows(a.r38)['R38']
    if a.r38w:
        import vmode, struct
        rows = rows or vmode.donor_rows(10)
        r = bytearray(rows['R38']); print('R38 +6/+8 was', struct.unpack_from('<HH', r, 6), flush=True)
        struct.pack_into('<H', r, 8, a.r38w); rows['R38'] = bytes(r)
    if a.timw:
        import vmode, struct
        rows = rows or vmode.donor_rows(10)
        t = bytearray(rows['TIM']); print('TIM +0xA/+0xC was', struct.unpack_from('<HH', t, 0xA), flush=True)
        struct.pack_into('<H', t, 0xC, a.timw); rows['TIM'] = bytes(t)
    b = R.Base(out, 'V1', rows=rows); s = b.s; s.pair = False
    sent = F.SENT

    def trip(timeout=1.0):              # above ~400 fps the DMA rewrites the tail before a verified write reads back
        for i in range(4):
            B.wr(s.tail + 4 * i, sent, verify=False)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if B.P().mem_get(s.tail)[0] != sent:
                return True
        return False
    s._trip = trip
    v0, w0 = B.P().mem_get(VREG)[0], B.P().mem_get(WREG)[0]; top = (s.base_window >> 16) or 20
    h0 = B.P().mem_get(0x30100004)[0]
    print('base VMAX', (v0 >> 16) + 1, 'HMAX', (B.P().mem_get(0x30100004)[0] & 0x3FFF) + 1, 'window', hex(w0),
          'lines', B.P().mem_get(0x301005D8)[0], 'top', top, flush=True)
    if a.rows:
        window(s, top, a.rows)
    if a.fast:
        import bins, l7
        for r, v in bins.diff('8', '139'):          # Family A: fast (mode 8) values where 3x3 fast and normal differ
            s.write(r, v)
        s.write(0x0001, 0x2C)
        rx0 = B.P().mem_get(0x3010000C)[0]
        B.wr(0x3010000C, (rx0 & 0xFFFF0000) | (4176 // 12))
        B.wr(0x30100004, (a.fast - 1) | (a.fast - 1) << 16)
        b.restart(); time.sleep(0.3)
        l7.rewindow(s, 0)
        fr0 = pathlib.Path(a.out) / 'fastcheck'
        if s.grab(fr0):
            f, m = R.decode(fr0)
            im = f[0][top:]
            rr = im[:, 60:-60].mean(1)
            print(f'fast check: shape {im.shape} even/odd {rr[0::2].mean() / max(rr[1::2].mean(), 1):.3f} '
                  f'blank rows {int((im[:, 60:-60].std(1) < 1).sum())} lines {B.P().mem_get(0x301005D8)[0]}', flush=True)
        else:
            print('fast check: NO FRAME', flush=True)
    if a.hmax:
        B.wr(0x30100004, (a.hmax - 1) | (a.hmax - 1) << 16); time.sleep(0.2)
    if a.sensor:
        for e in a.sensor.split(','):
            r, v = (int(q, 16) for q in e.split('='))
            s.write(r, v)
        b.restart(); time.sleep(0.2)
    st = B.bus_state(); res = []
    try:
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, 0), (0x003E, 0), (0x003F, 0), (0x0040, 0)])   # SHS 4: exposure = VMAX - 8
        print(B.P().sh(f'imager fixed_shutter 1 {a.shutter}').strip()[-80:], flush=True)
        for i, vm in enumerate(int(x) for x in a.vmax.split(',')):
            B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
            p = period(s, 1.0)
            d = out / f'{i:02d}_v{vm}'
            ok = s.grab(d)
            row = dict(vmax=vm, ms=p and p * 1e3, frame=ok, r48=B.P().mem_get(0x30100048)[0], lines=B.P().mem_get(0x301005D8)[0])
            if ok:
                f, m = R.decode(d)
                img = f[0][top:top + a.rows] if a.rows else f[0][top:]
                row.update(sig=float(img[:, 100:-100].mean() - f[0][2:top - 2, 100:-100].mean()),
                           top=float(img[:300, 100:-100].mean()), bot=float(img[-300:, 100:-100].mean()))
                for q in d.glob('frame*.raw'):
                    q.unlink()
            res.append(row)
            print(f"VMAX {vm} period {row['ms'] or 0:.2f} ms sig {row.get('sig', 0):.1f} sig/VMAX×1000 {1000 * row.get('sig', 0) / vm:.2f} "
                  f"48 0x{row['r48']:08X} lines {row['lines']}", flush=True)
            (out / 'res.json').write_text(json.dumps(res, indent=1))
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(WREG, w0); B.P().sh('imager fixed_shutter 0')
            if a.fast:
                B.wr(0x3010000C, rx0)
            B.wr(0x30100004, h0)
        finally:
            b.close()


if __name__ == '__main__':
    main()
