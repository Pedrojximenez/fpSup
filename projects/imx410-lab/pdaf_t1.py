#!/usr/bin/env python3
"""PDAF T1 (notes/PDAF_A7III_DIFF.md): V1 + Sony column 16 format (0001=1A, 4177 wide), 001C=00, the ZAF group with
sane values, then a ZAF-shutter / selector / ZAF-gain bracket with the main SHS and gain held by IMXB substitution.
Pixels driven by the ZAF path would change between bracket frames while normal pixels stay put.

    pdaf_t1.py OUT [--gain 0x400]
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import l7                                                             # noqa: E402


def lines():
    return [B.P().mem_get(0x301005D8)[0] for _ in range(3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--gain', type=lambda x: int(x, 0), default=0x400)
    ap.add_argument('--donor', type=int, help='virtual base from this donor (own window) instead of V1 + 0001=1A/4176')
    ap.add_argument('--word', type=lambda x: int(x, 16), help='with --donor: format code written first (window refit)')
    ap.add_argument('--extra', default='', help='with --donor: table writes REG=VAL,... after the format (hex)')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    g = a.gain
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    rows = None
    if a.donor:
        import vmode
        vmode.KEEP_WINDOW = True
        rows = vmode.donor_rows(a.donor)
    b = R.Base(out, 'V1', rows=rows); s = b.s; s.pair = True
    rx0, w0 = B.P().mem_get(0x3010000C)[0], B.P().mem_get(0x30100024)[0]
    st = B.bus_state(); log = []
    top = s.base_window >> 16
    if a.donor:
        import struct, vmode
        top = struct.unpack_from('<H', vmode.donor_rows(a.donor)['TIM'], 0xE)[0]

    def shot(name, writes=(), restart=True, fixwin=False):
        for r, v in writes:
            s.write(r, v)
        if restart:
            b.restart(); time.sleep(0.2)
        ln = lines()
        if fixwin:                                   # the sensor now sends fewer lines: shrink the receiver window
            w = B.P().mem_get(0x30100024)[0]
            B.wr(0x30100024, (w & 0xFFFF0000) | (min(ln) - 8)); time.sleep(0.1)
            l7.rewindow(s, 0)
        ok = s.grab(out / name)
        e = dict(name=name, writes=[f'{r:04X}={v:02X}' for r, v in writes], lines=ln, ok=ok)
        if ok:
            f, m = R.decode(out / name)
            im = f[0][top:]
            rr = im[:, 60:-60].mean(1)
            e.update(lvl=float(im[:, 60:-60].mean()), eo=float(rr[0::2].mean() / max(rr[1::2].mean(), 1)),
                     tn=float(np.std((f[0] - f[1])[top + 100:-100:2, 100:-100:2]) / np.sqrt(2)) if len(f) > 1 else None)
        log.append(e)
        print(name, 'lines', ln, 'ok', ok, {k: round(v, 3) for k, v in e.items() if k in ('lvl', 'eo', 'tn') and v is not None}, flush=True)
        (out / 'log.json').write_text(json.dumps(log, indent=1))
        return ok

    try:
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, g & 0xFF), (0x003E, g >> 8), (0x003F, g & 0xFF), (0x0040, g >> 8)])
        time.sleep(0.3)
        if not a.donor:
            s.write(0x0001, 0x1A)
            B.wr(0x3010000C, (rx0 & 0xFFFF0000) | (4176 // 12))
            b.restart(); time.sleep(0.3)
            l7.rewindow(s, 0)
            shot('ref1', restart=False)
            shot('ref2', restart=False)
            if not shot('c1c00', [(0x001C, 0x00)], fixwin=True):
                return
        else:
            shot('ref1', restart=False)
            shot('ref2', restart=False)
            ex = [tuple(int(q, 16) for q in e.split('=')) for e in a.extra.split(',') if e]
            if not shot('fmt', [(0x0001, a.word), (0x001C, 0x00)] + ex, fixwin=True):
                return
        zaf = [(0x000D, 0), (0x000E, 0), (0x000F, 0), (0x0010, 0), (0x0036, 0x01),
               (0x0047, g & 0xFF), (0x0048, g >> 8), (0x0049, g & 0xFF), (0x004A, g >> 8)]
        shot('zaf_shd0004', zaf + [(0x000B, 0x04), (0x000C, 0x00)])
        shot('zaf_shd0542', [(0x000B, 0x42), (0x000C, 0x05)])
        shot('zaf_shd0542_r', [], restart=False)
        shot('sel_ff_shd0542', [(0x0036, 0xFF)])
        shot('sel_ff_shd0004', [(0x000B, 0x04), (0x000C, 0x00)])
        shot('sel_ff_zg0000', [(0x0047, 0), (0x0048, 0), (0x0049, 0), (0x004A, 0)])
        shot('sel_ff_zg0d00', [(0x0047, 0x00), (0x0048, 0x0D), (0x0049, 0x00), (0x004A, 0x0D)])
    finally:
        try:
            B.bus_subs(st, []); B.wr(0x3010000C, rx0); B.wr(0x30100024, w0)
        finally:
            b.close()


if __name__ == '__main__':
    main()
