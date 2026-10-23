#!/usr/bin/env python3
"""half14.py steps vs the HMAX 911 step: top code, blank/odd lines, temporal noise, OB black/noise, level, geometry."""
import pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import resweep as R
base = pathlib.Path(sys.argv[1])
ref = None
for d in ([base / 'ref'] if (base / 'ref').exists() else []) + sorted(base.glob('h*'), key=lambda p: -int(p.name[1:])):
    fr, m = R.decode(d / 'p')
    top = (m['window'] >> 16); top -= top % 2
    a = fr[0][top:]
    rows = a[:, 100:-100].mean(1)
    blank = int((a[:, 100:-100].std(1) < 1).sum())
    eo = rows[0::2].mean() / rows[1::2].mean()
    tn = np.std((fr[0][top:] - fr[1][top:])[200:1800:2, 200:4000:2]) / np.sqrt(2) if len(fr) > 1 else np.nan
    ob = fr[0][2:max(top - 2, 4), 40:-40]
    s = dict(top=a.max(), p9999=np.percentile(a, 99.99), lvl=np.median(a), tn=tn, ob=ob.mean(), obn=np.std(np.diff(ob[0::2, 0::2], axis=1)) / np.sqrt(2),
             blank=blank, eo=eo, rows=a.shape[0])
    if ref is None:
        ref = (s, a)
    c = np.corrcoef(a[::4, ::4].ravel(), ref[1][::4, ::4].ravel())[0, 1] if a.shape == ref[1].shape else np.nan
    print(f'{d.name}: max {s["top"]:.0f} p99.99 {s["p9999"]:.0f} median {s["lvl"]:.1f} tn {s["tn"]:.2f} OB {s["ob"]:.1f} OBnoise {s["obn"]:.2f} '
          f'blank rows {blank} even/odd {eo:.3f} rows {s["rows"]} corr {c:.4f}')
