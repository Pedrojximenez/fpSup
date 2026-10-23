#!/usr/bin/env python3
"""Look for a two-row (Bayer-cell) grouping: per colour channel, the signal of even cells (raw rows 0-1, 4-5, ...)
against odd cells (raw rows 2-3, 6-7, ...), each relative to the nearest earlier reference.

    rowpair.py OUT_DIR [--min 0.05]

A register that groups rows in pairs makes R, Gr, Gb and B all split by the same factor between even and odd cells
(single-row grouping like 0738 instead splits Gr from Gb). Printed: per channel ratio(even cells)/ratio(odd cells),
and the single-row split Gb/Gr for comparison. Uses the mid-tone mask of OUT_DIR/masks.npz (rich.py).
"""
import json, pathlib, re, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rich                                                            # noqa: E402

PAT = re.compile(r'(0x[0-9A-F]+)_(0x[0-9A-F]+)_m\d+$')


def chans(d, mid):
    (img, *_), top = rich.frames(d)
    a = img[top:]
    black = img[1:top - 3].mean()
    out = {}
    for name, (i, j) in dict(R=(0, 0), Gr=(0, 1), Gb=(1, 0), B=(1, 1)).items():
        p = a[i::2, j::2] - black
        m = mid.copy()
        ev = np.zeros_like(m); ev[0::2] = True
        out[name] = (p[m & ev].mean(), p[m & ~ev].mean(), p[m].mean())
    return out


def main():
    out = pathlib.Path(sys.argv[1])
    thr = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    if not (out / 'masks.npz').exists():
        rich.make_masks(next(out.glob('ref_m*_a')), out / 'masks.npz')
    mid = np.load(out / 'masks.npz')['mid']
    pts = [d for d in out.iterdir() if (d / 'frame.raw').exists() and (d / 'frame.json').exists()]
    t = {d: json.loads((d / 'frame.json').read_text()).get('t', 0) for d in pts}
    refs = sorted([d for d in pts if d.name.startswith('ref_')], key=lambda d: t[d])
    C = {}
    for d in sorted(pts, key=lambda d: t[d]):
        C[d] = chans(d, mid)
    hits = []
    for d in sorted(pts, key=lambda d: t[d]):
        m = PAT.match(d.name)
        if not m:
            continue
        r = C[next(out.glob('ref_m*_a'))]                            # scene fixed: one reference (session refs can be broken)
        x = C[d]
        pair = {k: (x[k][0] / r[k][0]) / max(x[k][1] / r[k][1], 1e-6) for k in x}
        single = (x['Gb'][2] / r['Gb'][2]) / max(x['Gr'][2] / r['Gr'][2], 1e-6)
        level = np.mean([x[k][2] / r[k][2] for k in x])
        flag = all(abs(v - 1) > thr for v in pair.values()) and np.ptp(list(pair.values())) < 0.5 * max(abs(v - 1) for v in pair.values())
        line = (f'{d.name:16s} pair(even/odd cells) R {pair["R"]:.3f} Gr {pair["Gr"]:.3f} Gb {pair["Gb"]:.3f} B {pair["B"]:.3f}'
                f' | single Gb/Gr {single:.3f} | level {level:.3f}' + ('   <== two-row grouping' if flag else ''))
        if flag or any(abs(v - 1) > thr for v in pair.values()) or abs(single - 1) > thr:
            hits.append(line)
    print('\n'.join(hits) or 'no point moved even vs odd cells or Gr vs Gb by more than', thr)


if __name__ == '__main__':
    main()
