#!/usr/bin/env python3
"""Sweep sensor registers inside a synthesised merge (bins.py variants), looking for settings that change how
the merge combines pixels.  One register per call (the caller runs each under a time limit):

    binsweep.py OUT BASE REG [VALUES...]       BASE = a bins.V name (m98_2x2, vbin3, m139_3x3)

Opens the base readout once (mode 10 + batch), grabs a reference pair, then for every value: one direct write,
settle, grab a pair.  Nothing is restored by hand: closing the session switches back to mode 8 and the firmware
rewrites the whole mode table (bins.py §35 check); 0018/005D, the only extra registers, are written back.
A value that stops the frame ends this register (the rest are skipped and marked).
"""
import json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
import bins, l7                                                       # noqa: E402

DEFAULT = ['0x00', '0x01', '0x02', '0x03', '0x04', '0x05', '0x06', '0x08', '0x10', '0x20', '0x40', '0x80', '0xFF']


def main():
    out, base, reg = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3], 16)
    vals = [int(v, 16) for v in (sys.argv[4:] or DEFAULT)]
    regs, hmax, rx, yend, rx14 = bins.V[base]
    regs = [(r, v) for r, v in regs if r != 0x005D] + [(0x005D, 0x05)]
    cur = dict(regs).get(reg, int(bins.MODES['10'].get(f'reg_0x{reg:04x}', -1)))
    if cur < 0 and reg not in (0x0018,):
        cur = None                                                     # not a table register: value unknown
    d0 = out / base / f'{reg:04X}'
    todo = [v for v in vals if v != cur and not (d0 / f'{v:02X}' / 'frame2.raw').exists() and not (d0 / f'{v:02X}' / 'nofail').exists()]
    if not todo:
        return
    d0.mkdir(parents=True, exist_ok=True)
    (d0 / 'base.json').write_text(json.dumps(dict(base=base, reg=f'{reg:04X}', cur=cur)))
    F.cached_assemble()
    s = F.Session(out, yend, True, 10, min_alloc=24 << 20)
    clean = False
    try:
        B.startstop(100)
        l7.batch(regs)
        B.wr(0x30100004, (hmax - 1) | (hmax - 1) << 16)
        if rx:
            B.wr(0x3010000C, rx)
        time.sleep(0.3)
        l7.rewindow(s, 0)
        time.sleep(0.4)
        if not s.grab(d0 / 'ref'):
            raise SystemExit('base readout gave no frame')
        for v in todo:
            s.write(reg, v)
            time.sleep(0.15)
            ok = s.grab(d0 / f'{v:02X}')
            print(f'{base} {reg:04X}={v:02X} {"ok" if ok else "NO FRAME"}', flush=True)
            if not ok:
                (d0 / f'{v:02X}').mkdir(parents=True, exist_ok=True)
                (d0 / f'{v:02X}' / 'nofail').write_text('no frame\n')
                break
            if cur is not None:
                s.write(reg, cur)                                      # back to base before the next value
        s.write(0x0018, 0x00); s.write(0x005D, 0x03)
        clean = True
    finally:
        s.close()
        if not clean:
            import sweep
            sweep.KEEP = None
            sweep.fastreboot()


if __name__ == '__main__':
    main()
