#!/usr/bin/env python3
"""0007 = long exposure across frames? (shs2.py found 0007 = 01/02/04/10 -> x1.5/2.1/3.2/6.0 or a black frame)
Per value: substitution on, then 12 single grabs back to back with the receiver frame counter, image level and OB.

    shs2seq.py OUT [--base V1] [--values 01,02,04,08,10]
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402


def frame_count():
    r = B.P().sh('imager mode_now')
    for line in r.splitlines():
        if line.startswith('frame_count'):
            return int(line.split(':')[1].split(',')[0])
    return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--base', default='V1'); ap.add_argument('--values', default='00,01,02,04,08,10')
    ap.add_argument('--pairs', action='store_true', help='consecutive frame pairs instead of single grabs (period check)')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / a.base; out.mkdir(parents=True, exist_ok=True)
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, a.base)
    s = b.s; s.pair = a.pairs
    st = B.bus_state()
    try:
        for v in [int(x, 16) for x in a.values.split(',')]:
            d = out / f'07_{v:02X}'
            B.bus_subs(st, [(0x0007, v), (0x0008, 0)]); time.sleep(0.3)
            seq = []
            for k in range(12):
                t = time.time(); fc = frame_count()
                ok = s.grab(d / f's{k:02d}')
                if not ok:
                    seq.append(dict(k=k, ok=False)); continue
                f, m = R.decode(d / f's{k:02d}')
                top = (m['window'] >> 16); top -= top % 2
                img, ob = f[0][top:], f[0][2:top - 2]
                rows = img[:, 100:-100].mean(1)
                seq.append(dict(k=k, t=round(t, 3), fc=fc, lvl=float(img.mean()), ob=float(ob.mean()),
                                top=float(rows[:200].mean()), bot=float(rows[-200:].mean()),
                                lvl2=float(f[1][top:].mean()) if len(f) > 1 else None))
                for q in (d / f's{k:02d}').glob('frame*.raw'):
                    q.unlink()                                         # levels are enough
            B.bus_subs(st, []); time.sleep(0.3)
            (d / 'seq.json').write_text(json.dumps(seq))
            print(f'07={v:02X}', ' '.join(f"{q.get('fc', 0) % 1000}:{q['lvl']:.0f}" + (f"+{q['lvl2']:.0f}" if q.get('lvl2') else f"/{q['ob']:.0f}") if q.get('ok', True) else 'X' for q in seq), flush=True)
    finally:
        try:
            B.bus_subs(st, [])
        finally:
            b.close()


if __name__ == '__main__':
    main()
