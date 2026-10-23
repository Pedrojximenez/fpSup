#!/usr/bin/env python3
"""Readout-format register 0001, every value by direct write (looking for a DOL / multi-read / other output format).

    sweep0001.py OUT [--base V1] [--values 00-FF]

Virtual base (resweep.Base). Per value: write 0001, restart the sensor (0011 0->1), read the receiver status
(0x301005D8 = lines per frame, 0x30100588 = flags) twice 0.2 s apart, try one frame. Then the base value goes back
and one frame must come out again; if it does not, stop (the driver reboots and resumes: done values are skipped).
Direct writes only: no mode switch, so a value that stops the sensor cannot hang the shell (RESWEEP_DESIGN §9).
Raw frames are kept only when the line count or the frame stats differ from the base.
"""
import argparse, json, pathlib, sys, time
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import ramp14                                                         # noqa: E402

DONOR = {'V1': 10, 'V2': 6, 'V3': 98, 'V4': 8}


def status():
    return [B.P().mem_get(0x301005D8)[0] or 0, B.P().mem_get(0x30100588)[0] or 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--base', default='V1'); ap.add_argument('--values', default='00-FF')
    a = ap.parse_args()
    lo, hi = (int(x, 16) for x in a.values.split('-'))
    out = pathlib.Path(a.out) / a.base; out.mkdir(parents=True, exist_ok=True)
    stock = ramp14.table_value(DONOR[a.base], 0x0001)
    todo = [v for v in range(lo, hi + 1) if v != stock and not (out / f'{v:02X}' / 'res.json').exists()]
    if not todo:
        print('nothing to do'); return
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, a.base)
    s = b.s; s.pair = False
    try:
        b.restart()
        ref = out / f'ref_{time.strftime("%H%M%S")}'
        if not s.grab(ref):
            raise SystemExit('base gives no frame')
        rs = R.stats(ref); st0 = status()
        (out / 'base.json').write_text(json.dumps(dict(stock=f'{stock:02X}', status=st0)))
        print('base', f'0001={stock:02X}', 'status', st0, flush=True)
        for v in todo:
            d = out / f'{v:02X}'; d.mkdir(parents=True, exist_ok=True)
            s.write(0x0001, v); b.restart(); time.sleep(0.15)
            st = [status()]
            for _ in range(5):                      # 5 reads ~ one per frame: a format that alternates per frame
                time.sleep(0.017); st.append(status())  # shows up as alternating line counts / flags
            s.pair = True                           # two consecutive frames: alternating content or format
            try:
                ok = s.grab(d / 'p')
            except SystemExit as e:                 # DMA guard hit: a longer frame than the window
                ok = False; st.append(str(e))
            res = dict(value=f'{v:02X}', status=st, frame=ok)
            if ok:
                x = R.stats(d / 'p')
                res.update(shape=[int(q) for q in x['shape']], changed=bool(R.differs(x, rs)),
                           pair_same=float(x.get('pair_same', -1)))
                f = R.decode(d / 'p')[0]
                if len(f) > 1:                      # frame-to-frame difference beyond noise: alternating output
                    top = int(x['top'])
                    m1, m2 = f[0][top:].mean(), f[1][top:].mean()
                    res['f1f2'] = [float(m1), float(m2), float(np.corrcoef(f[0][top::8, ::8].ravel(), f[1][top::8, ::8].ravel())[0, 1])]
                    if abs(m1 - m2) > 0.03 * max(m1, 1) or res['f1f2'][2] < 0.98:
                        res['changed'] = True
                if not res['changed'] and all(isinstance(q, list) and q[0] == st0[0] for q in st):
                    R.drop_raw(d)
            s.pair = False
            s.write(0x0001, stock); b.restart(); time.sleep(0.15)
            back = s.grab(d / 'back')
            res['recovered'] = back
            for q in (d / 'back').glob('*'):
                q.unlink()
            (d / 'back').rmdir() if (d / 'back').exists() else None
            (d / 'res.json').write_text(json.dumps(res))
            print(f'{v:02X}', 'lines', [x[0] if isinstance(x, list) else x for x in st], 'frame', ok,
                  res.get('changed', ''), 'recovered' if back else 'NOT RECOVERED', flush=True)
            if not back:
                break
    finally:
        b.close()


if __name__ == '__main__':
    main()
