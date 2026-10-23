#!/usr/bin/env python3
"""Sweep -> table.  Each point directory holds frame.raw/.json (bufa_probe.py
frame --ystart 0 --bus) and bus.json.  Per point: the steady value of every
register the firmware writes per frame (the last 20 writes of each), and the
RAW statistics (OB rows 1-10, active phase means above black, noise).

    analyze.py captures/sweep_shutter [--csv out.csv]
"""
import argparse, collections, csv, json, pathlib, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                  # noqa: E402


def regs(bus):
    last = collections.defaultdict(list)
    for e in bus:
        last[int(e['reg'], 16)].append(int(e['val'], 16))
    steady = {}
    for r, vs in last.items():
        tail = vs[-20:]
        v, n = collections.Counter(tail).most_common(1)[0]
        steady[r] = v if n == len(tail) else None          # None: changing at the end
    return steady


def w16(s, lo, hi, mask=0xFFFF):
    a, b = s.get(lo), s.get(hi)
    return None if a is None or b is None else ((b << 8) | a) & mask


def stats(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = 14 if m.get('ystart') == 0 else 0
    ob = img[1:11] if top else None
    act = img[top:]
    black = ob.mean() if top else np.nan
    ph = {k: act[i::2, j::2] for k, (i, j) in zip(('R', 'Gr', 'Gb', 'B'), ((0, 0), (0, 1), (1, 0), (1, 1)))}
    noise = lambda x: np.diff(x[:, ::2], axis=1).std() / np.sqrt(2)
    out = dict(black=round(black, 2), ob_noise=round(noise(ob), 3) if top else None,
               ob11_13=round(img[11:14].mean(), 2) if top else None, sat=int(act.max()))
    for k, x in ph.items():
        out[k] = round(x.mean() - (black if top else 0), 2)
    out['G_noise'] = round(noise(ph['Gr']), 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sweep')
    ap.add_argument('--csv')
    a = ap.parse_args()
    rows = []
    for d in sorted(pathlib.Path(a.sweep).iterdir(), key=lambda p: (len(p.name), p.name)):
        if not (d / 'frame.raw').exists():
            continue
        s = regs(json.loads((d / 'bus.json').read_text())) if (d / 'bus.json').exists() else {}
        row = dict(point=d.name)
        row.update(shs=w16(s, 0x05, 0x06, 0x3FFF), r07_08=w16(s, 0x07, 0x08),
                   again=w16(s, 0x3D, 0x3E, 0xFFF), again2=w16(s, 0x3F, 0x40, 0xFFF),
                   r05E1=s.get(0x5E1), r05E2=s.get(0x5E2), r041F=s.get(0x41F),
                   r05A6=s.get(0x5A6), r05A8=s.get(0x5A8))
        others = {f'0x{r:04X}': v for r, v in s.items()
                  if r not in (0x05, 0x06, 0x07, 0x08, 0x3D, 0x3E, 0x3F, 0x40, 0x5E1, 0x5E2, 0x41F, 0x5A6, 0x5A8)}
        row.update(stats(d))
        row['other_regs'] = len(others)
        rows.append(row)
        print(row)
    if a.csv and rows:
        with open(a.csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    main()
