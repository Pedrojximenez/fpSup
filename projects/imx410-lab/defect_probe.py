#!/usr/bin/env python3
"""Dark-frame defect-correction probe (notes/DEFECT_CORRECTION.md, step 2/3). Lens capped.

    defect_probe.py OUT [--donor N]
Virtual base (donor rows, own window), long frame (VMAX 16000) at max analog gain (SHS 4, code 3965 = 30 dB) so hot
pixels stand out; grab two frames with the stock defect correction, two with `imager defect_collect_off 1`.
Hot pixel = > median + 12 x robust sigma. Saves the hot pixel lists (on / off / removed-by-correction).
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import vmode                                                          # noqa: E402

VREG = 0x30100020


def hot(a):
    med = np.median(a); mad = 1.4826 * np.median(np.abs(a - med)) + 1e-6
    ys, xs = np.nonzero(a > med + 12 * mad)
    return set(zip(ys.tolist(), xs.tolist())), float(med), float(mad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--donor', type=int, default=10); ap.add_argument('--vmax', type=int, default=16000)
    a = ap.parse_args()
    out = pathlib.Path(a.out) / f'd{a.donor}'; out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    vmode.KEEP_WINDOW = True
    rows = vmode.donor_rows(a.donor)
    b = R.Base(out, 'V1', rows=rows); s = b.s; s.pair = True
    v0 = B.P().mem_get(VREG)[0]
    import struct
    top = struct.unpack_from('<H', rows['TIM'], 0xE)[0] if a.donor != 10 else (s.base_window >> 16)
    st = B.bus_state(); res = {}
    try:
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, 3965 & 0xFF), (0x003E, 3965 >> 8), (0x003F, 3965 & 0xFF), (0x0040, 3965 >> 8)])
        B.P().sh('imager fixed_shutter 1 100')
        B.wr(VREG, ((a.vmax - 1) << 16) | (v0 & 0xFFFF)); time.sleep(1.0)
        sets = {}
        for tag, cmd in (('on', 'imager defect_collect_off 0'), ('off', 'imager defect_collect_off 1'), ('on2', 'imager defect_collect_off 0')):
            print(tag, B.P().sh(cmd).strip()[-60:], flush=True)
            time.sleep(1.0)
            d = out / tag
            if not s.grab(d):
                print(tag, 'NO FRAME'); continue
            f, m = R.decode(d)
            img = f[0][top + 4:, 8:-8]
            h1, med, mad = hot(img)
            h2, _, _ = hot(f[1][top + 4:, 8:-8]) if len(f) > 1 else (set(), 0, 0)
            sets[tag] = h1 & h2                                  # hot in both frames = stable hot pixels
            res[tag] = dict(n_hot=len(sets[tag]), median=med, mad=mad, shape=list(img.shape))
            print(tag, res[tag], flush=True)
        if 'on' in sets and 'off' in sets:
            removed = sets['off'] - sets['on']
            res['removed_by_correction'] = len(removed)
            res['still_hot_with_correction'] = len(sets['on'])
            (out / 'hot.json').write_text(json.dumps({k: sorted(v) for k, v in sets.items()}))
            print('removed by correction', len(removed), 'still hot', len(sets['on']), 'on/on2 agree', len(sets.get('on', set()) ^ sets.get('on2', set())), flush=True)
        (out / 'res.json').write_text(json.dumps(res, indent=1))
    finally:
        try:
            B.P().sh('imager defect_collect_off 0')
            B.bus_subs(st, []); B.wr(VREG, v0); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()


if __name__ == '__main__':
    main()
