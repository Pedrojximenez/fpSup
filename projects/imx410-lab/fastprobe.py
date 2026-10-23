#!/usr/bin/env python3
"""Why the synthesised fast class drops every other line (RULES §38): set up the failing state (bins.V['m8_rx200'],
mode 10 base, HMAX 330, sensor restarted), then for every register where the fast set differs from the normal set
(mode 8 vs mode 139 tables), write the normal value, restart the sensor (0011 0->1), read the receiver status
(0x301005D8 lines per frame, 0x30100588 flags) and the even/odd row levels of one frame, then put the fast value back.

    fastprobe.py OUT
"""
import json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
import bins, l7                                                       # noqa: E402
from decode12 import decode12                                         # noqa: E402


def status():
    v = B.P().mem_get(0x30100588, 1)[0], B.P().mem_get(0x301005D8, 1)[0]
    return v


def rows(s, d):
    if not s.grab(d):
        return None
    m = json.loads((d / 'frame.json').read_text())
    a = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(float)
    r = a[100:900, 20:1900].mean(1)
    return round(r[0::2].mean()), round(r[1::2].mean())


def main():
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    name = 'm8_rx200'
    regs, hmax, rx, yend, _ = bins.V[name]
    regs = [(r, v) for r, v in regs if r != 0x005D] + [(0x005D, 0x05)]
    fast = dict(regs)
    normal = dict(bins.diff('139', '8'))                             # mode 8 (fast) -> 139 (normal): Family A only
    cand = [(r, normal[r]) for r in sorted(normal) if r != 0x0018]
    log = open(out / 'probe.txt', 'a')
    say = lambda t: (print(t, flush=True), log.write(t + '\n'), log.flush())
    F.cached_assemble()
    s = F.Session(out, yend, False, 10, min_alloc=24 << 20)
    try:
        B.startstop(100)
        l7.batch(regs)
        B.wr(0x30100004, (hmax - 1) | (hmax - 1) << 16)
        s.write(0x0011, 0); time.sleep(0.03); s.write(0x0011, 1)
        B.wr(0x3010000C, rx)
        for ad, va in bins.SOC[name]:
            B.wr(ad, va)
        time.sleep(0.3)
        l7.rewindow(s, 0)
        time.sleep(0.4)
        say(f'base  status {status()}  rows {rows(s, out / "base")}')
        for r, v in cand:
            fv = fast.get(r, int(bins.MODES['8'][f'reg_0x{r:04x}']))
            s.write(r, v); s.write(0x0011, 0); time.sleep(0.03); s.write(0x0011, 1); time.sleep(0.15)
            st = status(); rw = rows(s, out / f'{r:04X}')
            say(f'{r:04X} {fv:02X}->{v:02X}  flags {st[0]:08X} lines {st[1]}  rows {rw}')
            s.write(r, fv); s.write(0x0011, 0); time.sleep(0.03); s.write(0x0011, 1); time.sleep(0.1)
        s.write(0x0018, 0); s.write(0x005D, 3)
    finally:
        s.close()


if __name__ == '__main__':
    main()
