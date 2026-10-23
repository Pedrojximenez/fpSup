#!/usr/bin/env python3
"""05A9 partner sweep: every point has 05A9 = 01 (even row group off) plus one register value.
For each point: even-row (Gr) and odd-row (Gb) signal against the nearest earlier stock reference,
and the OB level per row parity. Lists the points that leave the 05A9-only pattern (the median).

    a9partner.py captures/sweep_05a9_partner4 [--top 40]
"""
import argparse, json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402


def stats(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(float)
    top = m['window'] >> 16
    ob = img[2:top - 3, 100:-100]
    a = img[top:]
    return dict(gr=a[0::2, 1::2].mean(), gb=a[1::2, 0::2].mean(), r=a[0::2, 0::2].mean(), b=a[1::2, 1::2].mean(),
                ob0=ob[0::2].mean(), ob1=ob[1::2].mean(), std=float(a.std()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--top', type=int, default=40)
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    cache = out / 'a9stats.json'
    st = json.loads(cache.read_text()) if cache.exists() else {}
    dirs = sorted([d for d in out.iterdir() if (d / 'frame.raw').exists()], key=lambda d: d.stat().st_mtime)
    for d in dirs:
        if d.name not in st:
            st[d.name] = dict(stats(d), t=d.stat().st_mtime)
    cache.write_text(json.dumps(st))
    refs = [(v['t'], v) for k, v in st.items() if k.startswith('ref_')]
    rows = []
    for k, v in st.items():
        if k.startswith('ref_'):
            continue
        r = max([x for x in refs if x[0] < v['t']], key=lambda x: x[0], default=refs[0])[1]
        rb = (r['ob0'] + r['ob1']) / 2
        e = (v['gr'] - v['ob0']) / (r['gr'] - rb)
        o = (v['gb'] - v['ob1']) / (r['gb'] - rb)
        rows.append((k, e, o, v['ob0'] - r['ob0'], v['ob1'] - r['ob1'], v['std']))
    E = np.median([x[1] for x in rows]); O = np.median([x[2] for x in rows])
    print(f'{len(rows)} points; median even {E:.3f}  odd {O:.3f}  (05A9 = 01 alone)')
    score = lambda x: max(abs(x[1] - E) / 0.03, abs(np.log(max(x[2], 1e-3) / O)) / 0.05, abs(x[3]) / 10, abs(x[4]) / 10)
    for x in sorted(rows, key=score, reverse=True)[:a.top]:
        print(f'{x[0]:16s} even {x[1]:6.3f}  odd {x[2]:6.3f}  dOB even {x[3]:+7.1f} odd {x[4]:+7.1f}  std {x[5]:6.1f}')


if __name__ == '__main__':
    main()
