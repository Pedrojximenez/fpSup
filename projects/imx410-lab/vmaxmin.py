#!/usr/bin/env python3
"""FAST_READOUT / HIGH_SPEED_SENSING: the shortest frame (VMAX) per row count, and whether frames really arrive that
fast (IMX410_RULES §15 open question: mode 8 at VMAX 1300 < 1358 rows still looked intact).

    vmaxmin.py OUT [--rows 2022,1010,506,254,126] [--fr 1.3,1.15,1.05,1.0,0.95,0.9,0.8,0.7,0.6,0.5]

Virtual V1 (mode 10 rows: 1x1, 12-bit normal AD, HMAX 445; magnify window start 1069, 1011 pairs). Per row count N:
sensor window centred (0022/23 start, 0024/25 = N/2), receiver window end = first image row + N, BUFA0 re-windowed;
SHS held at 4 by IMXB substitution (the firmware's SHS is computed for its own VMAX and would blank short frames).
Then VMAX = round(fr * (top + N)) for each fr: write, measure the delivered frame period over 15 BUFA0 completions
(polling the tail sentinel), grab one frame and compare it with the frame at the first VMAX of that N.
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import l7                                                             # noqa: E402
import fastsweep as F                                                 # noqa: E402

VREG, WREG = 0x30100020, 0x30100024
START0, PAIRS0 = 1069, 1011


def counts():
    r = B.P().sh('imager mode_now')
    for line in r.splitlines():
        if line.startswith('frame_count'):
            fc, tc = (int(x.split(':')[1]) for x in line.split(','))
            return time.time(), fc, tc
    return None


def period(s, secs=1.5):
    """seconds per frame from the firmware's frame counter (SoC sync) -- the polled BUFA0 sentinel was too slow
    (one round trip ~50 ms); BUFA0 completions are checked by the grab itself"""
    a = counts(); time.sleep(secs); b = counts()
    if not a or not b or b[1] == a[1]:
        return None
    period.tc = (b[0] - a[0]) / max(b[2] - a[2], 1)
    return (b[0] - a[0]) / (b[1] - a[1])


def window(s, top, n):
    start = START0 + PAIRS0 - n // 2
    for r, v in ((0x0022, start & 0xFF), (0x0023, start >> 8), (0x0024, (n // 2) & 0xFF), (0x0025, (n // 2) >> 8)):
        s.write(r, v)
    B.wr(WREG, (B.P().mem_get(WREG)[0] & 0xFFFF0000) | (top + n))
    s.write(0x0011, 0); time.sleep(0.03); s.write(0x0011, 1); time.sleep(0.2)
    l7.rewindow(s, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--rows', default='2022,1010,506,254,126')
    ap.add_argument('--fr', default='1.3,1.15,1.05,1.0,0.95,0.9,0.8,0.7,0.6,0.5')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, 'V1')
    s = b.s; s.pair = False
    v0, w0, h0 = B.P().mem_get(VREG)[0], B.P().mem_get(WREG)[0], B.P().mem_get(0x30100004)[0]
    hmax = (h0 & 0xFFFF) + 1
    top = s.base_window >> 16
    st = B.bus_state()
    res = dict(vmax0=f'0x{v0:08X}', window0=f'0x{w0:08X}', hmax=hmax, top=top, runs=[])
    try:
        B.bus_on(st); B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, 0), (0x003E, 0), (0x003F, 0), (0x0040, 0)])   # SHS 4, gain 0 dB: AE cannot level it out
        for n in [int(x) for x in a.rows.split(',')]:
            window(s, top, n)
            ref = None
            for fr in [float(x) for x in a.fr.split(',')]:
                vm = max(8, round(fr * (top + n)))
                B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.15)
                p = period(s)
                held = (B.P().mem_get(VREG)[0] >> 16) + 1
                d = out / f'n{n:04d}' / f'v{vm:05d}'
                ok = s.grab(d)
                row = dict(rows=n, vmax=vm, fr=fr, law_ms=(vm - 1) * hmax / 72e3 + hmax / 72e3,
                           meas_ms=None if p is None else p * 1e3, frame=ok, held=held)
                if ok:
                    f, m = R.decode(d)
                    img = f[0][top:top + n]
                    rows = img[:, 100:-100].mean(1)
                    row.update(lvl=float(img.mean()), blank=int((img[:, 100:-100].std(1) < 1).sum()),
                               rowstd=float(np.std(np.diff(rows))))
                    if ref is None:
                        ref = img
                    else:
                        row['corr'] = float(np.corrcoef(img[::4, ::8].ravel(), ref[::4, ::8].ravel())[0, 1])
                    for q in d.glob('frame*.raw'):
                        if ref is not img:
                            q.unlink()
                res['runs'].append(row)
                print(f"N {n} VMAX {vm} ({fr}) law {row['law_ms']:.2f} ms meas {row['meas_ms'] or 0:.2f} ms frame {ok} "
                      f"held {held} tc {period.tc * 1e3:.2f} ms corr {row.get('corr', 1):.3f} blank {row.get('blank', '')} lvl {row.get('lvl', 0):.0f}", flush=True)
                (out / 'res.json').write_text(json.dumps(res, indent=1))
                if not ok or p is None:
                    break
            B.wr(VREG, v0)
    finally:
        try:
            B.bus_subs(st, []); B.wr(VREG, v0); B.wr(WREG, w0)
        finally:
            b.close()


if __name__ == '__main__':
    main()
