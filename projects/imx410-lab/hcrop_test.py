#!/usr/bin/env python3
"""Horizontal crop on the SoC receiver (0x3010000C = width/12 | (x0/12) << 16, FUN_c0635ed8): full-width reference,
then 3000-px windows at several x0; the content shift is measured by cross-correlating column profiles.

    hcrop_test.py OUT
"""
import json, pathlib, sys, time
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
from l7 import rewindow                                               # noqa: E402
from decode12 import decode12                                         # noqa: E402


def colprof(d):
    m = json.loads((d / 'frame.json').read_text())
    a = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(float)
    top = m['window'] >> 16
    a = a[top:]
    return (a[0::2, 1::2] + a[1::2, 0::2]).mean(0) / 2, a.shape


def main():
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    s = F.Session(out, 0, False, 10, min_alloc=24 << 20)
    base = B.P().mem_get(0x3010000C)[0]
    try:
        s.grab(out / 'full')
        for x0 in (0, 1200, 2400, 3060):
            B.startstop(100)
            B.wr(0x3010000C, (x0 + 3000) // 12 | (x0 // 12) << 16)   # low half = END unit, high half = start
            rewindow(s, 0)
            time.sleep(0.15)
            print(f'x0 {x0}:', 'ok' if s.grab(out / f'x{x0}') else 'NO FRAME')
    finally:
        B.startstop(100)
        B.wr(0x3010000C, base)
        try:
            rewindow(s, 0)
        except SystemExit:
            pass
        s.close()
    ref, rs = colprof(out / 'full')
    print('full frame', rs)
    for x0 in (0, 1200, 2400, 3060):
        d = out / f'x{x0}'
        if not (d / 'frame.raw').exists():
            continue
        p, sh = colprof(d)
        n = len(p)
        g = lambda v: (v - v.mean()) / (v.std() + 1e-9)
        best = max(((np.mean(g(p[:n - 4]) * g(ref[k:k + n - 4])), k) for k in range(0, len(ref) - n + 4)), key=lambda t: t[0])
        print(f'x0 {x0}: frame {sh}, content found at full-frame cell column {best[1]} (= {2 * best[1]} px), corr {best[0]:.3f}')


if __name__ == '__main__':
    main()
