#!/usr/bin/env python3
"""Region-wise measurements of a frame pair, for a fixed scene with clipped, dark and mid-tone areas.

    rich.py OUT_DIR                 label every point against its nearest earlier reference

The regions come from the run's first reference (`ref_m10_a`), on the 2x2 CFA-cell grid, and are kept in
OUT_DIR/masks.npz:  clip  = G at the ADC ceiling,  dark = G within 30 DN of black,  mid = 200..3000 DN above black.
Per point (`rich.npz`, written by fastsweep with two consecutive frames frame.raw / frame2.raw):
  black      OB mean                      white  mean raw level inside `clip` (the clip point) per phase
  dark_mean  dark-area level above black  dark_sp / dark_tmp  spatial / temporal (frame pair) noise in `dark`
  mid        mid-area level above black per phase           row_n / col_n  row / column noise in `dark`
The noise floor of every feature is the ref a / ref b difference; a feature counts above max(3x that, a small
absolute step). This answers what sweep.judge could not: clip point, dark noise, temporal noise, black.
"""
import json, pathlib, re, sys
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                          # noqa: E402

PH = ((0, 0), (0, 1), (1, 0), (1, 1))


def frames(d):
    m = json.loads((d / 'frame.json').read_text())
    out = []
    for name in ('frame.raw', 'frame2.raw'):
        if (d / name).exists():
            img = decode12((d / name).read_bytes(), m['height'], m['line_words']).astype(np.float64)
            out.append(img)
    return out, m['window'] >> 16


def make_masks(ref_dir, path):
    (img, *_), top = frames(ref_dir)
    a = img[top:]
    black = img[1:top - 3].mean()
    g = (a[0::2, 1::2] + a[1::2, 0::2]) / 2 - black
    clip = (a[0::2, 1::2] >= 4090) & (a[1::2, 0::2] >= 4090)
    np.savez_compressed(path, clip=clip, dark=g < 30, mid=(g > 200) & (g < 3000))


def measure(d, masks):
    imgs, top = frames(d)
    a = [im[top:] for im in imgs]
    black = imgs[0][1:top - 3].mean()
    clip, dark, mid = masks['clip'], masks['dark'], masks['mid']
    f = dict(black=black)
    f['white'] = np.array([a[0][i::2, j::2][clip].mean() if clip.any() else np.nan for i, j in PH])
    f['mid'] = np.array([(a[0][i::2, j::2][mid] - black).mean() for i, j in PH])
    g0 = (a[0][0::2, 1::2] + a[0][1::2, 0::2]) / 2 - black
    f['dark_mean'] = g0[dark].mean()
    d0 = a[0][0::2, 1::2] - black                                       # one phase, dark area
    f['dark_sp'] = np.std(np.diff(np.where(dark, d0, np.nan), axis=1)[~np.isnan(np.diff(np.where(dark, d0, np.nan), axis=1))]) / np.sqrt(2)
    if len(a) > 1:
        diff = (a[0][0::2, 1::2] - a[1][0::2, 1::2])[dark]
        f['dark_tmp'] = diff.std() / np.sqrt(2)
    rows = np.array([d0[r][dark[r]].mean() for r in range(d0.shape[0]) if dark[r].sum() > 50])
    cols = np.array([d0[:, c][dark[:, c]].mean() for c in range(d0.shape[1]) if dark[:, c].sum() > 50])
    f['row_n'] = np.std(np.diff(rows)) / np.sqrt(2) if len(rows) > 2 else np.nan
    f['col_n'] = np.std(np.diff(cols)) / np.sqrt(2) if len(cols) > 2 else np.nan
    return f


def ensure(d, out):
    p = d / 'rich.npz'
    if not p.exists():
        mp = out / 'masks.npz'
        if not mp.exists():
            make_masks(out / 'ref_m10_a', mp)
        np.savez_compressed(p, **measure(d, np.load(mp)))
    return dict(np.load(p))


PAT = re.compile(r'(0x[0-9A-F]+)_(0x[0-9A-F]+)_m10$')
ABS = dict(black=3.0, white=15.0, mid=0.02, dark_mean=2.0, dark_sp=0.1, dark_tmp=0.1, row_n=0.1, col_n=0.1)


def label(x, r, fl):
    """Short label of what moved, against reference r with floor fl (ref a vs b)."""
    out = []
    def dev(k):
        return np.nanmax(np.abs(np.atleast_1d(x[k]) - np.atleast_1d(r[k])))
    def big(k, rel=False):
        thr = max(3 * fl[k], ABS[k] * (np.nanmean(np.abs(np.atleast_1d(r[k]))) if rel else 1))
        return dev(k) > thr
    if big('black'):
        out.append(f'black{x["black"] - r["black"]:+.0f}')
    if big('white'):
        out.append(f'white{np.nanmean(x["white"] - r["white"]):+.0f}')
    if big('mid', rel=True):
        rat = x['mid'] / np.maximum(r['mid'], 1e-3)
        out.append('mid×' + ('/'.join(f'{v:.2f}' for v in rat) if np.ptp(rat) > 0.05 else f'{rat.mean():.2f}'))
    if big('dark_mean'):
        out.append(f'dark{x["dark_mean"] - r["dark_mean"]:+.1f}')
    for k, n in (('dark_sp', 'nSp'), ('dark_tmp', 'nT'), ('row_n', 'nRow'), ('col_n', 'nCol')):
        if k in x and k in r and big(k):
            out.append(f'{n}×{x[k] / max(r[k], 1e-3):.2f}')
    return ' '.join(out) or '.'


def main():
    out = pathlib.Path(sys.argv[1])
    pts = [d for d in out.iterdir() if (d / 'frame.json').exists() and (d / 'frame.raw').exists()]
    t = {d: json.loads((d / 'frame.json').read_text()).get('t', d.stat().st_mtime) for d in pts}
    F = {d: ensure(d, out) for d in sorted(pts, key=lambda d: t[d])}
    refs = sorted([d for d in pts if d.name.startswith('ref_')], key=lambda d: t[d])
    ra, rb = F[out / 'ref_m10_a'], F[out / 'ref_m10_b']
    fl = {k: float(np.nanmax(np.abs(np.atleast_1d(ra[k]) - np.atleast_1d(rb[k])))) for k in ra}
    print('floor (ref a vs b):', {k: round(v, 3) for k, v in fl.items()})
    res = {}
    for d in sorted(pts, key=lambda d: t[d]):
        m = PAT.match(d.name)
        if not m:
            continue
        r = F[max([q for q in refs if t[q] < t[d]] or refs[:1], key=lambda q: t[q])]
        res.setdefault(m[1], []).append((int(m[2], 16), label(F[d], r, fl)))
    for reg in sorted(res, key=lambda q: int(q, 16)):
        cells = res[reg]
        if all(c == '.' for _, c in cells):
            print(f'{int(reg, 16):04X}  -- no effect')
        else:
            print(f'{int(reg, 16):04X}  ' + '  '.join(f'{v:02X}:{c}' for v, c in cells))


if __name__ == '__main__':
    main()
