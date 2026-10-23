#!/usr/bin/env python3
"""Constant-register scan points against the reference taken most recently before each.
    const_cmp.py [first_index]          (captures/const)"""
import json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402
from override_cmp import metrics                                      # noqa: E402

root = HERE / 'captures' / 'const'


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    return decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64), m['window'] >> 16


def main():
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    refs = sorted([d for d in root.glob('ref_*') if (d / 'frame.raw').exists()], key=lambda d: d.stat().st_mtime)
    for d in sorted(root.glob('p*')):
        if int(d.name[1:4]) < first:
            continue
        if not (d / 'frame.raw').exists():
            print('   ', d.name, 'NO FRAME'); continue
        ref = max([r for r in refs if r.stat().st_mtime < d.stat().st_mtime], key=lambda r: r.stat().st_mtime)
        x, top = load(d); r, rtop = load(ref)
        mx, mr = metrics(x, top), metrics(r, rtop)
        bx, br = x[1:top - 3].mean(), r[1:rtop - 3].mean()
        xa, ra = x[top:] - bx, r[rtop:] - br
        rr = xa.mean(1) / np.maximum(ra.mean(1), 1); rr /= np.median(rr)
        cr = xa.mean(0) / np.maximum(ra.mean(0), 1); cr /= np.median(cr)
        ph = [round(float((a - bx) / (b - br)), 3) for a, b in zip(mx['phases'], mr['phases'])]
        flag = (abs(mx['black'] - mr['black']) > 2 or max(abs(p - 1) for p in ph) > 0.05 or abs(mx['dx'] - mr['dx']) > 0.4
                or abs(mx['dy'] - mr['dy']) > 0.4 or np.abs(rr - 1).max() > 0.08 or np.abs(cr - 1).max() > 0.08)
        tail = (f' black {mx["black"]} vs {mr["black"]}  phase {ph}  dx {mx["dx"]}/{mr["dx"]}  dy {mx["dy"]}/{mr["dy"]}'
                f'  rowdev {np.abs(rr - 1).max():.3f}  coldev {np.abs(cr - 1).max():.3f}') if flag else ''
        print(('** ' if flag else '   ') + d.name + tail)


if __name__ == '__main__':
    main()
