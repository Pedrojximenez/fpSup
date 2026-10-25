#!/usr/bin/env python3
"""Right / left edge column check of stored validator frames (offline). full_v1 found the w03 preset (format word 3,
"4016 wide") delivering 3992 real columns: the last 24 were pad (normal AD: flat 256) or garbage (fast AD), and no check
looked at columns. A real column has texture in a lit frame; a pad column is flat (std < 2) or far off its
neighbours' level.

    colscan_edge.py captures/full_v1 --db captures/full_v1.json   -> per config: real width, pad columns at each edge
"""
import argparse, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np
import resweep as R


def edges(img):
    cs = img.std(0); cm = img.mean(0)
    W = img.shape[1]; mid = slice(W // 4, 3 * W // 4)
    s_ref = float(np.median(cs[mid])); m_ref = float(np.median(cm[mid]))
    good = (cs > max(2.0, 0.25 * s_ref)) & (cs < 4 * s_ref + 20) & (np.abs(cm - m_ref) < max(150, 4 * s_ref))
    left = int(np.argmax(good)); right = int(np.argmax(good[::-1]))
    return left, right, s_ref


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cap'); ap.add_argument('--db', required=True)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    db = json.loads(pathlib.Path(a.db).read_text()); res = {}
    for pid, e in sorted(db.items()):
        lt = e.get('light')
        if not lt or 'attrs' not in lt:
            continue
        d = pathlib.Path(a.cap) / pid.replace(':', '_').replace('>', '_') / 'f'
        if not (d / 'frame.raw.zst').exists():
            continue
        at = lt['attrs']
        fr, _ = R.decode(d)
        img = fr[0].astype(float)[at['y0'] + 2:at['y0'] + at['height'] - 2]
        l, r, s = edges(img)
        res[pid] = dict(width=img.shape[1], left_pad=l, right_pad=r, real=img.shape[1] - l - r, tex=round(s, 1))
        if l or r:
            print(f'{pid:44s} width {img.shape[1]:5d}  pad left {l:3d} right {r:3d}  -> real {img.shape[1] - l - r}', flush=True)
    bad = sum(1 for v in res.values() if v['left_pad'] or v['right_pad'])
    print(f'{len(res)} configs, {bad} with pad columns')
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
