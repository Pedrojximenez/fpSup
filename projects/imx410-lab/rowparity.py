#!/usr/bin/env python3
"""Even (R/G) and odd (G/B) image rows against a reference, per CFA phase.

    rowparity.py captures/r05a9            (each point against <dir>/ref)

Prints signal above black for each phase and its ratio to the reference, plus
whether the ratio repeats with a longer row period (2 / 4 / 8) -- a row-
interleaved exposure would show as two levels alternating by row pair.
"""
import json, pathlib, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    return img[top:] - img[1:top - 3].mean(), img[1:top - 3].mean()


def main():
    root = pathlib.Path(sys.argv[1])
    ref, rb = load(root / 'ref')
    rows_ref = ref.mean(axis=1)
    print(f'ref black {rb:.1f}  phases R {ref[0::2, 0::2].mean():.1f}  Gr {ref[0::2, 1::2].mean():.1f}  '
          f'Gb {ref[1::2, 0::2].mean():.1f}  B {ref[1::2, 1::2].mean():.1f}')
    for d in sorted(root.iterdir()):
        if d.name.startswith('ref') or not (d / 'frame.raw').exists():
            continue
        x, xb = load(d)
        ph = {k: x[i::2, j::2].mean() / max(ref[i::2, j::2].mean(), 1e-6)
              for k, (i, j) in dict(R=(0, 0), Gr=(0, 1), Gb=(1, 0), B=(1, 1)).items()}
        rr = x.mean(axis=1) / np.maximum(rows_ref, 1e-6)
        per = {p: [round(float(rr[k::p].mean()), 3) for k in range(p)] for p in (2, 4, 8)}
        print(f'{d.name:8s} black {xb:6.1f}  ratio R {ph["R"]:.3f} Gr {ph["Gr"]:.3f} | Gb {ph["Gb"]:.3f} B {ph["B"]:.3f}  '
              f'rows mod 4 {per[4]}  mod 8 {per[8]}')


if __name__ == '__main__':
    main()
