#!/usr/bin/env python3
"""Per-register, per-bit effect table from a `sweep.py judge` result (xor_bits plans).

    classify.py captures/sweep_table_bits [--k 4] [--md]

Each flipped bit gets one short label per mode:
  .      no effect above k x the ref-vs-ref floor, or under 3 % level change with no structure
  X      no frame (sensor stopped; from run.log)
  S      shape changed (frame size)
  Z      flat 256: the pixel signal is gone, output is the clamp target only
  W      flat 3327 / OB 4095: the conversion is broken (saturated constant)
  O+n    only the OB rows moved (by n DN); the active image is unchanged
  P+n    pedestal: every active phase moved by the same n DN
  L×r    signal (above black) changed by ratio r, all phases alike
  C      CFA phases changed unequally (ratios listed in --md)
  R / K  row / column structure changed (banding, line pattern)
Raw levels come from rawlv.py (rawlv.json beside judge.json).
"""
import argparse, json, pathlib, re
from collections import defaultdict


def label(p, k, raw, ref):
    """ref: raw levels of the point's reference."""
    if not p['hit']:
        return '.'
    v = raw[p['point']]
    act, ra = v['act'], ref['act']
    if v['std'] < 2 and abs(act[0] - 256) < 2:
        return 'Z'
    if v['std'] < 3 and act[0] > 3000:
        return 'W'
    sig = [a - ref['ob'] for a in act]
    rsig = [a - ref['ob'] for a in ra]
    r = [s / max(t, 1) for s, t in zip(sig, rsig)]
    d = [a - b for a, b in zip(act, ra)]
    out = []
    if abs(v['ob'] - ref['ob']) > 15 and max(abs(x - 1) for x in r) < 0.05:
        out.append(f'O{v["ob"] - ref["ob"]:+.0f}')
    elif max(d) - min(d) < 0.15 * max(abs(x) for x in d) and min(abs(x) for x in d) > 30:
        out.append(f'P{sum(d) / 4:+.0f}')
    elif max(r) - min(r) > 0.08:
        out.append('C')
    elif abs(sum(r) / 4 - 1) > 0.03:
        out.append(f'L×{sum(r) / 4:.2f}')
    if p['rows'] > k:
        out.append('R')
    if p['cols'] > k:
        out.append('K')
    return ''.join(out) or '.'



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--k', type=float, default=4.0)
    ap.add_argument('--md', action='store_true')
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    j = json.loads((out / 'judge.json').read_text())
    raw = json.loads((out / 'rawlv.json').read_text())
    tab = defaultdict(dict)                                    # reg -> (bit, mode) -> label
    detail = {}
    pat = re.compile(r'(0x[0-9A-F]+)_b(\d)_(0x[0-9A-F]+)_m(\d+)$')
    for p in j['points']:
        m = pat.match(p['point'])
        if m:
            ref = raw.get(p['ref']) or raw[f'ref_m{m[4]}_a']
            tab[m[1]][(int(m[2]), int(m[4]))] = label(p, a.k, raw, ref)
            detail[p['point']] = p
    for line in (out / 'run.log').read_text().splitlines():
        m = pat.search(line.split(' [')[0].split(' ok')[0])
        if m and 'no frame' in line:
            tab[m[1]][(int(m[2]), int(m[4]))] = 'X'
    shape = (out / 'shape.txt').read_text().split() if (out / 'shape.txt').exists() else []
    for s in shape:
        m = pat.match(s)
        if m:
            tab[m[1]][(int(m[2]), int(m[4]))] = 'S'
    regs = sorted(tab, key=lambda r: int(r, 16))
    live = [r for r in regs if any(v != '.' for v in tab[r].values())]
    print(f'{len(regs)} registers, {len(live)} with an effect')
    hdr = '| reg | ' + ' | '.join(f'b{b}' for b in range(8)) + ' |'
    print(hdr); print('|' + '---|' * 9)
    for r in live:
        cells = []
        for b in range(8):
            c10, c8 = tab[r].get((b, 10), '?'), tab[r].get((b, 8), '?')
            cells.append(f'{c10}/{c8}')
        print(f'| {int(r, 16):04X} | ' + ' | '.join(cells) + ' |')
    dead = [f'{int(r, 16):04X}' for r in regs if r not in live]
    print(f'\nno effect (either mode, all 8 bits): {len(dead)}\n' + ' '.join(dead))
    if a.md:
        print('\nratios R Gr Gb B of colour hits:')
        for n, p in detail.items():
            if tab[pat.match(n)[1]][(int(pat.match(n)[2]), int(pat.match(n)[4]))].startswith('C'):
                print(f'  {n}: {p["phase_ratio"]}')


if __name__ == '__main__':
    main()
