#!/usr/bin/env python3
"""High-speed strip on the stock 2x2 fast class (virtual mode from donor 11: 3032x2012, HMAX 330, 12-bit fast AD).
Step 1 (--probe): window on (0003=1), start S / height H written to 0022-0025, report the receiver line count.
Step 2: receiver window to the delivered rows, 0016 small, VMAX floor search with gain held, SHS 4, fixed shutter.

    hs11.py OUT --start S --h H [--v016 2] [--vmax 300,...] [--probe]
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import vmode, l7                                                      # noqa: E402
from vmaxmin import period, VREG, WREG                                # noqa: E402


def lines():
    return [B.P().mem_get(0x301005D8)[0] for _ in range(3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--start', type=int, default=1000); ap.add_argument('--h', type=int, default=100)
    ap.add_argument('--v016', type=int, default=0); ap.add_argument('--vmax', default='')
    ap.add_argument('--rx', type=int, default=0, help='receiver window end row (0 = from the measured line count)')
    ap.add_argument('--probe', action='store_true')
    ap.add_argument('--donor', type=int, default=11, help='virtual base donor (11 = 2x2 fast, 8 = 3x3 fast)')
    ap.add_argument('--hcrop', type=int, default=0, help='receiver horizontal crop to this many px, centred (multiple of 12)')
    ap.add_argument('--hmax', type=int, default=0, help='SoC line length after setup (0 = donor value)')
    ap.add_argument('--burstn', type=int, default=16)
    ap.add_argument('--burst', default='', help='VMAX values at which to take a frame_cb burst (16 frames, 64 completion times)')
    ap.add_argument('--gain', type=lambda x: int(x, 0), default=0, help='analog gain code held on 003D-0040 (3800 ~ x14)')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / f'd{a.donor}_s{a.start}_h{a.h}_b{a.v016}_w{a.hcrop}_hm{a.hmax}'; out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    vmode.KEEP_WINDOW = True
    b = R.Base(out, 'V1', rows=vmode.donor_rows(a.donor)); s = b.s; s.pair = False
    v0, w0 = B.P().mem_get(VREG)[0], B.P().mem_get(WREG)[0]
    import struct as _st
    top = _st.unpack_from('<H', vmode.donor_rows(a.donor)['TIM'], 0xE)[0]   # timing row: first image row (11: 20, 8: 14)
    h0, rx0 = B.P().mem_get(0x30100004)[0], B.P().mem_get(0x3010000C)[0]

    def trip(timeout=1.0):                            # fast frames: the DMA rewrites the tail before a verified write
        for i in range(4):
            B.wr(s.tail + 4 * i, F.SENT, verify=False)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if B.P().mem_get(s.tail)[0] != F.SENT:
                return True
        return False
    print('base: window 0x%08X VMAX %d HMAX %d lines %s' % (w0, (v0 >> 16) + 1, (B.P().mem_get(0x30100004)[0] & 0x3FFF) + 1, lines()), flush=True)
    st = B.bus_state(); res = []
    try:
        for r, v in ((0x0003, 1), (0x0022, a.start & 0xFF), (0x0023, a.start >> 8), (0x0024, a.h & 0xFF), (0x0025, a.h >> 8)) + \
                (((0x0016, a.v016),) if a.v016 else ()):
            s.write(r, v)
        b.restart(); time.sleep(0.3)
        ln = lines(); print('after window: lines', ln, flush=True)
        end = a.rx or (min(ln) - 2)
        B.wr(WREG, (w0 & 0xFFFF0000) | end); time.sleep(0.1)
        if a.hcrop:
            full = (rx0 & 0xFFFF) * 12
            x0 = ((full - a.hcrop) // 2) // 12 * 12
            B.wr(0x3010000C, (x0 + a.hcrop) // 12 | (x0 // 12) << 16)
        if a.hmax:
            B.wr(0x30100004, (a.hmax - 1) | (a.hmax - 1) << 16)
        time.sleep(0.1)
        l7.rewindow(s, 0)
        ok = s.grab(out / 'probe')
        if ok:
            f, m = R.decode(out / 'probe')
            rows = f[0][:, 60:-60].mean(1)
            print('probe frame', f[0].shape, 'rx', hex(B.P().mem_get(0x3010000C)[0]), 'row means', [round(float(x)) for x in rows[::max(1, len(rows) // 16)]], flush=True)
        if a.probe or not ok:
            return
        s._trip = trip
        B.bus_on(st)
        g = a.gain
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, g & 0xFF), (0x003E, g >> 8), (0x003F, g & 0xFF), (0x0040, g >> 8)])
        B.P().sh('imager fixed_shutter 1 100')
        for vm in [int(x) for x in a.vmax.split(',') if x]:
            B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
            p = period(s, 1.0)
            d = out / f'v{vm}'
            ok = s.grab(d)
            row = dict(vmax=vm, ms=p and p * 1e3, frame=ok, lines=lines())
            if ok:
                f, m = R.decode(d)
                img = f[0][top:end]
                row['sig'] = float(img[:, 60:-60].mean())                       # image level (DCLP-clamped black ~256)
            res.append(row)
            print(f"VMAX {vm} period {row['ms'] or 0:.3f} ms fps {1000 / (row['ms'] or 1):.0f} sig {row.get('sig', 0):.1f} "
                  f"(lvl-256)/(VMAX-8)×1000 {1000 * (row.get('sig', 256) - 256) / (vm - 8):.1f} lines {row['lines']}", flush=True)
            (out / 'res.json').write_text(json.dumps(res, indent=1))
        for vm in [int(x) for x in a.burst.split(',') if x]:
            import hsburst, numpy as np
            from decode12 import decode12
            B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
            meta, raws = hsburst.burst(s, n=a.burstn)
            d = out / f'burst_v{vm}'; d.mkdir(exist_ok=True)
            t = [e[0] for e in meta['ents']]
            dt = np.diff(t)
            lv, tn = [], []
            for i, r in enumerate(raws):
                a2 = decode12(r, meta['h'], meta['words']).astype(np.float32)[top:end, 60:-60]
                lv.append(float(a2.mean()))
                if i:
                    tn.append(float(np.std(a2 - prev) / np.sqrt(2)))
                prev = a2
                (d / f'f{i:02d}.raw').write_bytes(r)
            meta.update(dt_us=dt.tolist(), levels=lv, tn=tn, vmax=vm, law_us=vm * (a.hmax or 330) / 72)
            (d / 'burst.json').write_text(json.dumps(meta, indent=1))
            print(f"BURST VMAX {vm}: {meta['done']} completions, interval µs median {np.median(dt):.1f} min {dt.min():.0f} max {dt.max():.0f} "
                  f"(law {vm * (a.hmax or 330) / 72:.1f}); >1.5x law: {int((dt > 1.5 * vm * (a.hmax or 330) / 72).sum())}; "
                  f"levels {min(lv):.1f}-{max(lv):.1f}; frame-to-frame noise {min(tn):.2f}-{max(tn):.2f}", flush=True)
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(WREG, w0); B.P().sh('imager fixed_shutter 0')
            B.wr(0x30100004, h0); B.wr(0x3010000C, rx0)
        finally:
            b.close()


if __name__ == '__main__':
    main()
