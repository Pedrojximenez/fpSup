#!/usr/bin/env python3
"""Which rows / columns did a setting change?  For spatial-HDR hunting.

    rowmap.py captures/zaf            (every point against captures/zaf/ref)

Per point: the frame / ref ratio of every image row and column (black removed,
scene drift divided out by the median), the rows that deviate by more than
`--thr`, and the period of those rows if they repeat.
"""
import argparse, json, pathlib, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                        # noqa: E402


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = (m['window'] >> 16) if m.get('ystart') == 0 else 0
    black = img[1:max(top - 3, 2)].mean() if top else 0.0
    return img[top:] - black


def period(rows):
    if len(rows) < 3:
        return None
    d = np.diff(rows)
    vals, cnt = np.unique(d, return_counts=True)
    return int(vals[np.argmax(cnt)]), int(cnt.max()), len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sweep')
    ap.add_argument('--thr', type=float, default=0.05)
    a = ap.parse_args()
    root = pathlib.Path(a.sweep)
    ref = load(root / 'ref')
    for d in sorted(root.iterdir()):
        if d.name.startswith('ref') or not (d / 'frame.raw').exists():
            continue
        x = load(d)
        if x.shape != ref.shape:
            print(f'{d.name:10s} shape {x.shape} vs {ref.shape}')
            continue
        rr = x.mean(axis=1) / np.maximum(ref.mean(axis=1), 1)
        cr = x.mean(axis=0) / np.maximum(ref.mean(axis=0), 1)
        rr /= np.median(rr); cr /= np.median(cr)
        bad_r = np.where(np.abs(rr - 1) > a.thr)[0]
        bad_c = np.where(np.abs(cr - 1) > a.thr)[0]
        print(f'{d.name:10s} global {np.median(x.mean(axis=1) / np.maximum(ref.mean(axis=1), 1)):.3f}  '
              f'rows off {len(bad_r)} {bad_r[:12].tolist()} period {period(bad_r)} '
              f'(min {rr.min():.3f} max {rr.max():.3f})  cols off {len(bad_c)} {bad_c[:8].tolist()} period {period(bad_c)}')


if __name__ == '__main__':
    main()
