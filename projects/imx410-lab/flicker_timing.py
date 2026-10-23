#!/usr/bin/env python3
"""Test 1 (§32): WHEN is the attenuated group read? Under a flickering light, short exposures show horizontal bands
whose row position is the read time. The ratio of two frames (different flicker phase) cancels the scene and keeps
the bands; the band profile of the full rows (Gr) is cross-correlated with that of the attenuated rows (Gb).
  shift 0      -> the attenuated sample in output row y is read at row y's time
  shift V/2    -> it is read at the time of physical row y + V (its own slot), cell rows = raw rows / 2

    flicker_timing.py OUT [--v 0x20] [--lines 300]
"""
import argparse, json, pathlib, sys, time
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
from decode12 import decode12                                         # noqa: E402


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    return img[top:] - img[1:top - 3].mean()


def profiles(a, b):
    """Per cell row: median over columns of a/b, for the Gr (even rows) and Gb (odd rows) planes."""
    out = []
    for i, j in ((0, 1), (1, 0)):
        pa, pb = a[i::2, j::2], b[i::2, j::2]
        m = (pb > 80) & (pb < 3500) & (pa > 80) & (pa < 3500)
        r = np.where(m, pa / np.maximum(pb, 1), np.nan)
        out.append(np.nanmedian(r, axis=1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--v', default='0x20'); ap.add_argument('--lines', type=int, default=300)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    s = F.Session(out, 0, False, 10)
    st = B.bus_state()
    shs = (2700 - a.lines) // 2
    try:
        B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8)])
        for v in (0, int(a.v, 16)):
            s.write(0x0738, v); time.sleep(0.25)
            for k in range(6):
                s.grab(out / f'v{v:02X}_{k}'); time.sleep(0.037)       # a few ms off the flicker phase each time
    finally:
        B.bus_subs(st, []); s.write(0x0738, 0)
        s.close()
    for v in (0, int(a.v, 16)):
        fr = [load(out / f'v{v:02X}_{k}') for k in range(3)]
        for x, y in ((0, 1), (1, 2)):
            gr, gb = profiles(fr[x], fr[y])
            ok = ~np.isnan(gr) & ~np.isnan(gb)
            g1 = gr - np.nanmean(gr); g2 = gb - np.nanmean(gb)
            amp = np.nanstd(gr) * 100
            best = []
            for sh in range(-80, 81):
                u = np.roll(g2, -sh)
                q = ok & np.roll(ok, -sh)
                q[:90] = False; q[-90:] = False
                best.append((np.corrcoef(g1[q], u[q])[0, 1], sh))
            best.sort(reverse=True)
            print(f'0738={v:#04x} frames {x}/{y}: band amplitude {amp:.1f}%  Gb-vs-Gr best shift {best[0][1]:+d} cell rows '
                  f'(corr {best[0][0]:.3f}; next {best[1][1]:+d} {best[1][0]:.3f})')


if __name__ == '__main__':
    main()
