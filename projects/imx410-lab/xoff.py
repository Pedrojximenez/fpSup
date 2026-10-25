#!/usr/bin/env python3
"""Where do the 24 pad columns come from (IMX410_RULES §72)? Every width preset at its widest format width (x0 = 8)
ends in 24 columns that are not image. One config, the SoC capture start x0 moved (the virtual mode's x0 / x1, nothing
else changed), one lit frame each: if the pad moves with x0 the line simply ends early; if it stays, the sensor sends it.

    xoff.py OUT [--key 14w2B --crop 4176x4040 --outsz 4176x4040 --x0 8,0,32]
"""
import argparse, json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import readout_cfg as C, smc, smc_validate as V, colscan_edge as E


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('out')
    ap.add_argument('--key', default='14w2B'); ap.add_argument('--crop', default='4176x4040'); ap.add_argument('--outsz', default='4176x4040')
    ap.add_argument('--x0', default='8,0,32')
    a = ap.parse_args()
    import bufa_probe as B, resweep as R, vmode, fastsweep as F
    F.cached_assemble()
    crop = tuple(map(int, a.crop.split('x'))); outsz = tuple(map(int, a.outsz.split('x')))
    p = C.plan(a.key, *crop, *outsz, None)
    orig = smc.attrs_from_plan
    res = {}
    for x0 in map(int, a.x0.split(',')):
        def patched(pp, x0=x0):
            at = orig(pp); at['x1'] = x0 + (at['x1'] - at['x0']); at['x0'] = x0
            return at
        smc.attrs_from_plan = patched
        at, rows, _ = smc.create(p)
        smc.attrs_from_plan = orig
        rows = {t: bytes(v) for t, v in rows.items()}
        rows['R10'] = struct.pack('<II', V.R10[at['cls']], 10)
        out = pathlib.Path(a.out) / f"{p['id'].replace(':', '_').replace('>', '_')}_x{x0}"; out.mkdir(parents=True, exist_ok=True)
        vmode.KEEP_WINDOW = True
        b = R.Base(out, 'V2' if p['bits'] == 14 else 'V1', rows=rows)
        s = b.s; s.pair = True
        try:
            time.sleep(1.0)
            ok = s.grab(out / 'f')
            if ok and p['bits'] == 14:
                m = json.loads((out / 'f' / 'frame.json').read_text()); m['bits'] = 14; (out / 'f' / 'frame.json').write_text(json.dumps(m))
            if ok:
                fr, _ = R.decode(out / 'f')
                img = fr[0].astype(float)[at['y0'] + 2:at['y0'] + at['height'] - 2]
                l, r, t = E.edges(img)
                cs = img.std(0)
                res[x0] = dict(width=img.shape[1], left_pad=l, right_pad=r, tail_std=[round(float(x), 1) for x in cs[-32:]])
            else:
                res[x0] = dict(grab=False)
            print('x0', x0, res[x0].get('width'), 'pad', res[x0].get('left_pad'), res[x0].get('right_pad'), flush=True)
        finally:
            b.close()
    (pathlib.Path(a.out) / f"{p['id'].replace(':', '_').replace('>', '_')}.json").write_text(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
