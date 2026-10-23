#!/usr/bin/env python3
"""Two-frame colour HDR from the row groups (§29): frame A = 0738 attenuates the odd rows (Gb, B),
frame B = the same 0738 with 023A bit 0 = 0 attenuates the even rows (R, Gr). Every colour then has a
full-sensitivity sample (one frame) and an attenuated one (the other frame): no channel is estimated.

    hdr_swap.py FRAME_A FRAME_B STOCK --out PNG

Per colour plane: full below 85 % of the clip, attenuated/k above (k per colour from the mid tones), smooth blend.
Cells demosaiced as (R, (Gr+Gb)/2, B); white balance grey-world on the stock frame's mid tones; same log curve.
"""
import argparse, json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

PH = dict(R=(0, 0), Gr=(0, 1), Gb=(1, 0), B=(1, 1))


def planes(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    a, b = img[top:], img[1:top - 3].mean()
    return {k: a[i::2, j::2] - b for k, (i, j) in PH.items()}, 4090 - b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a'); ap.add_argument('b'); ap.add_argument('stock'); ap.add_argument('--out', required=True)
    o = ap.parse_args()
    A, ca = planes(pathlib.Path(o.a)); Bf, cb = planes(pathlib.Path(o.b)); S, cs = planes(pathlib.Path(o.stock))
    full = dict(R=(A['R'], ca), Gr=(A['Gr'], ca), Gb=(Bf['Gb'], cb), B=(Bf['B'], cb))
    att = dict(R=Bf['R'], Gr=Bf['Gr'], Gb=A['Gb'], B=A['B'])
    out = {}
    for c in PH:
        f, clip = full[c]
        ok = (f > 150) & (f < 0.8 * clip) & (att[c] > 10)
        k = np.median(att[c][ok] / f[ok])
        w = np.clip((f - 0.8 * clip) / (0.12 * clip), 0, 1)
        out[c] = (1 - w) * f + w * att[c] / k
        print(f'{c}: k = {k:.4f} ({np.log2(1 / k):.2f} EV), {(w > 0.5).mean() * 100:.1f}% of cells from the attenuated frame')
    hdr = np.stack([out['R'], (out['Gr'] + out['Gb']) / 2, out['B']], -1)
    ref = np.stack([S['R'], (S['Gr'] + S['Gb']) / 2, S['B']], -1)
    mid = (S['Gr'] > 200) & (S['Gr'] < 3000)
    wb = ref[mid].mean(0); wb = wb[1] / wb
    hdr, ref = hdr * wb, ref * wb
    hi = np.percentile(hdr, 99.9)
    tone = lambda v: (np.clip(np.log2(1 + np.maximum(v, 0)) / np.log2(1 + hi), 0, 1) ** 1.6 * 255).astype(np.uint8)
    from PIL import Image
    Image.fromarray(np.concatenate([tone(ref), tone(hdr)], 0)[::2, ::2]).save(o.out)
    print('saved', o.out)


if __name__ == '__main__':
    main()
