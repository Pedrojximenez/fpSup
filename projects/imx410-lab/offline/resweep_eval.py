#!/usr/bin/env python3
"""Label every resweep point (resweep.py) against the reference of its base taken in the same boot.

    resweep_eval.py OUT [REG ...]

Floors come from the reference pairs themselves: the spread of the references of a base (taken one per boot)
gives the boot-to-boot noise of every metric; a metric counts when it exceeds max(3 x that spread, an absolute
step). Per point and capture (p = right after the restart, f10 = ~10 frames later, d = DCLP off):
  OB      black of the dark rows, per CFA phase                 lvl  image level per phase (block medians)
  tn      temporal noise per block (frame pair, p only)        rown / coln  OB row / column noise
  sat     99.99th percentile                                   geo  shift of the block-mean image (cells)
  st      receiver status (lines per frame, error flags)
Tags: 'transient' = seen in p but gone in f10 (the firmware wrote it back); 'dclp-only' = only with DCLP off.
"""
import pathlib, sys
import numpy as np

PH = ('00', '01', '10', '11')
ABS = dict(ob=3.0, lvl=0.02, tn=0.03, rown=0.1, coln=0.1, sat=8.0)


def load(d):
    p = d / 'stats.npz'
    return dict(np.load(p)) if p.exists() else None


def metrics(s):
    m = {}
    m['ob'] = np.array([s[f'ob{k}'][0] if f'ob{k}' in s else np.nan for k in PH])
    m['rown'] = np.array([s[f'ob{k}'][2] if f'ob{k}' in s else np.nan for k in PH])
    m['coln'] = np.array([s[f'ob{k}'][3] if f'ob{k}' in s else np.nan for k in PH])
    m['lvl'] = np.array([np.median(s[f'blk{k}']) for k in PH])
    m['tn'] = np.array([np.median(s[f'tn{k}']) if f'tn{k}' in s and np.median(s[f'tn{k}']) > 0 else np.nan for k in PH])
    m['sat'] = np.array([s['p999'][2]])
    return m


def geo(s, r):
    a, b = s['blk01'], r['blk01']
    if a.shape != b.shape:
        return None
    best = (-2, 0, 0)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            A = a[max(dy, 0):a.shape[0] + min(dy, 0), max(dx, 0):a.shape[1] + min(dx, 0)]
            Bq = b[max(-dy, 0):b.shape[0] + min(-dy, 0), max(-dx, 0):b.shape[1] + min(-dx, 0)]
            c = np.corrcoef(A.ravel(), Bq.ravel())[0, 1]
            if c > best[0]:
                best = (c, dy, dx)
    return best


def floors(refs):
    ms = [metrics(r) for r in refs]
    fl = {}
    for k in ABS:
        v = np.array([m[k] for m in ms])
        # robust: 90th percentile of the deviations, so one bad reference cannot raise the floor of a base
        if k in ('lvl', 'tn'):
            spread = np.nanpercentile(np.abs(v / np.nanmedian(v, 0) - 1), 90) if len(ms) > 1 else 0
        else:
            spread = np.nanpercentile(np.abs(v - np.nanmedian(v, 0)), 90) if len(ms) > 1 else 0
        fl[k] = max(3 * spread, ABS[k])
    return fl


def label(s, r, fl):
    if s is None:
        return 'missing'
    if tuple(s['shape']) != tuple(r['shape']):
        return f'shape {tuple(s["shape"])}'
    a, b = metrics(s), metrics(r)
    out = []
    d = a['ob'] - b['ob']
    if np.nanmax(np.abs(d)) > fl['ob']:
        out.append('OB' + ('/'.join(f'{x:+.0f}' for x in d) if np.nanmax(d) - np.nanmin(d) > fl['ob'] else f'{np.nanmean(d):+.0f}'))
    q = a['lvl'] / b['lvl']
    if np.nanmax(np.abs(q - 1)) > fl['lvl']:
        out.append('lvl×' + ('/'.join(f'{x:.2f}' for x in q) if np.ptp(q) > fl['lvl'] else f'{np.mean(q):.2f}'))
    if not np.all(np.isnan(a['tn'])):
        q = a['tn'] / b['tn']
        if np.nanmax(np.abs(q - 1)) > fl['tn']:
            out.append(f'tn×{np.nanmean(q):.2f}')
    for k, n in (('rown', 'rowN'), ('coln', 'colN')):
        dd = np.nanmax(np.abs(a[k] - b[k]))
        if dd > fl[k]:
            out.append(f'{n}{np.nanmean(a[k] - b[k]):+.1f}')
    if abs(a['sat'][0] - b['sat'][0]) > fl['sat']:
        out.append(f'sat{a["sat"][0] - b["sat"][0]:+.0f}')
    g = geo(s, r)
    if g and (g[1] or g[2] or g[0] < 0.98):
        out.append(f'geo({g[1]},{g[2]}) c{g[0]:.3f}')
    if (int(s['status'][1]) & ~1) != (int(r['status'][1]) & ~1) or abs(int(s['status'][0]) - int(r['status'][0])) > 4:   # bit 0 toggles by itself
        out.append(f'st{int(s["status"][0])}/{int(s["status"][1]):X}')
    return ' '.join(out) or '.'


def main():
    out = pathlib.Path(sys.argv[1]); want = set(sys.argv[2:])
    lines = []
    for bdir in sorted(p for p in out.iterdir() if p.is_dir()):
        refs = sorted(bdir.glob('ref_*'))
        R = {sub: [load(r / sub) for r in refs if load(r / sub)] for sub in ('p', 'f10', 'd')}
        if not R['p']:
            continue
        FL = {sub: floors(R[sub]) for sub in R if R[sub]}
        for rd in sorted(p for p in bdir.iterdir() if p.is_dir() and not p.name.startswith('ref_')):
            if want and rd.name not in want:
                continue
            for vd in sorted(p for p in rd.iterdir() if p.is_dir()):
                if (vd / 'nofail').exists():
                    lines.append(f'{bdir.name} {rd.name}={vd.name}  NO FRAME'); continue
                t = load(vd / 'p')['t'] if load(vd / 'p') else 0
                # the reference of the same boot: the latest one taken before this point
                idx = max([i for i, r in enumerate(refs) if load(r / 'p') and load(r / 'p')['t'] <= t] or [0])
                lab = {sub: label(load(vd / sub), load(refs[idx] / sub), FL[sub]) for sub in ('p', 'f10', 'd') if sub in FL}
                tag = []
                if lab.get('p') != '.' and lab.get('f10') == '.':
                    tag.append('TRANSIENT')
                if lab.get('p') == '.' and lab.get('d', '.') != '.':
                    tag.append('DCLP-ONLY')
                lines.append(f'{bdir.name} {rd.name}={vd.name}  p[{lab.get("p")}]  f10[{lab.get("f10")}]  d[{lab.get("d")}] {" ".join(tag)}')
    print('\n'.join(lines))
    (out / 'eval.txt').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
