#!/usr/bin/env python3
"""Odd-row against even-row signal inside each frame, by brightness (cancels scene/AF changes between frames).

    rowgroup.py captures/sweep_table_bits3 0x738_b1_0x02_m10 [...]     (ref: the dir's ref_m10_a)

Gb (odd rows) over Gr (even rows) on 32x32-pixel blocks, normalised by the same ratio in the reference,
in five brightness bins. A flat row = a linear per-row-group factor; the OB noise per row parity tells a
gain after the pixel (noise scales) from less charge (noise unchanged).
"""
import json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(float)
    top = m['window'] >> 16
    return img[top:] - img[2:top - 3].mean(), img[2:top - 3, 100:-100]


def blk(p, b=32):
    h, w = (p.shape[0] // b) * b, (p.shape[1] // b) * b
    return p[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3)).ravel()


def main():
    root = pathlib.Path(sys.argv[1])
    ref, _ = load(root / 'ref_m10_a')
    kref = np.median(blk(ref[1::2, 0::2]) / np.maximum(blk(ref[0::2, 1::2]), 1))
    for n in sys.argv[2:]:
        x, ob = load(root / n)
        e, o = blk(x[0::2, 1::2]), blk(x[1::2, 0::2])
        bins = np.percentile(e, [2, 25, 50, 75, 98, 100])
        s = [f'{e[k].mean():5.0f}:{o[k].mean() / e[k].mean() / kref:.3f}'
             for lo, hi in zip(bins[:-1], bins[1:]) for k in [(e >= lo) & (e <= hi)]]
        nz = [np.std(np.diff(ob[p::2], axis=1)) / np.sqrt(2) for p in (0, 1)]
        print(f'{n:22s} odd/even by level {" ".join(s)}   OB noise even {nz[0]:.2f} odd {nz[1]:.2f}')


if __name__ == '__main__':
    main()
