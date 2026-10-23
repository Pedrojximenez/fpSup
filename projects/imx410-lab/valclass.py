#!/usr/bin/env python3
"""Label every point of an absolute-value sweep (plan items with `values`, dirs REG_VAL_mM) from the summaries.

    valclass.py captures/sweep_sony_bits [--reg 0x5D]

Against the nearest earlier reference of the same mode (summary.npz, see sweep.summarize):
  X no frame · W flat saturated · Z flat 256 · B±n black (OB) moved · P±n pedestal · L×r level · C colour
  E/O×r even/odd row group (Gr vs Gb) · R/K row/column structure · N×r OB noise · '.' nothing
"""
import argparse, json, pathlib, re, sys
from collections import defaultdict
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sweep                                                             # noqa: E402

PAT = re.compile(r'(0x[0-9A-F]+)_(0x[0-9A-F]+)_m(\d+)$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--reg')
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    dirs = [d for d in out.iterdir() if sweep.captured(d)]
    Z = {d: np.load(d / 'summary.npz') if (d / 'summary.npz').exists() else (sweep.summarize(d) or np.load(d / 'summary.npz'))
         for d in dirs}
    refs = sorted([d for d in dirs if d.name.startswith('ref_m')], key=lambda d: float(Z[d]['t']))
    fl = {}
    for m in {int(d.name.split('_')[1][1:]) for d in refs}:
        r = [d for d in refs if d.name.startswith(f'ref_m{m}_')][:2]
        c = sweep.compare(sweep.load_summary(r[0])[0], sweep.load_summary(r[1])[0])
        fl[m] = (max(c['rows'], 0.01), max(c['cols'], 0.01))
    tab = defaultdict(list)
    for d in dirs:
        mm = PAT.match(d.name)
        if not mm or (a.reg and int(mm[1], 16) != int(a.reg, 16)):
            continue
        reg, val, m = mm[1], mm[2], int(mm[3])
        x = Z[d]
        rc = [r for r in refs if r.name.startswith(f'ref_m{m}_') and float(Z[r]['t']) < float(x['t'])] or refs[:1]
        r = Z[max(rc, key=lambda q: float(Z[q]['t']))]
        act, ra, ob, rob = x['act'], r['act'], x['ob'].mean(), r['ob'].mean()
        lab = []
        if x['std'] < 3 and act[0] > 3000:
            lab.append('W')
        elif x['std'] < 3 and abs(act[0] - 256) < 4:
            lab.append('Z')
        else:
            sig = (act - ob) / np.maximum(ra - rob, 1)
            d_ = act - ra
            if abs(ob - rob) > 4:
                lab.append(f'B{ob - rob:+.0f}')
            if np.ptp(d_) < 0.15 * np.abs(d_).max() and np.abs(d_).min() > 25 and abs(ob - rob) < 4:
                lab.append(f'P{d_.mean():+.0f}')
            elif np.ptp(sig) > 0.08:
                e, o = sig[1], sig[2]
                lab.append(f'E×{e:.2f}O×{o:.2f}' if abs(e - o) > 0.08 and abs(sig[0] - e) < 0.08 else 'C' + '/'.join(f'{v:.2f}' for v in sig))
            elif abs(sig.mean() - 1) > 0.04:
                lab.append(f'L×{sig.mean():.2f}')
            c = sweep.compare(sweep.load_summary(d)[0], {k: v for k, v in zip(('means', 'tex', 'rows', 'cols'),
                              (r['means'], r['tex'], [r[f'rows{i}'] for i in range(4)], [r[f'cols{i}'] for i in range(4)]))})
            if c['rows'] > 4 * fl[m][0]:
                lab.append('R')
            if c['cols'] > 4 * fl[m][1]:
                lab.append('K')
            nz = x['obnoise'].mean() / max(r['obnoise'].mean(), 1e-3)
            if abs(nz - 1) > 0.25:
                lab.append(f'N×{nz:.1f}')
        tab[reg].append((int(val, 16), ''.join(lab) or '.'))
    for line in (out / 'run.log').read_text().splitlines():
        mm = PAT.search(line.split(' [')[0].split(' ok')[0])
        if mm and 'no frame' in line and (not a.reg or int(mm[1], 16) == int(a.reg, 16)):
            tab[mm[1]].append((int(mm[2], 16), 'X'))
    for reg in sorted(tab, key=lambda q: int(q, 16)):
        cells = sorted(set(tab[reg]))
        if all(c == '.' for _, c in cells):
            print(f'{int(reg, 16):04X}  -- no effect'); continue
        print(f'{int(reg, 16):04X}  ' + '  '.join(f'{v:02X}:{c}' for v, c in cells))


if __name__ == '__main__':
    main()
