#!/usr/bin/env python3
"""Table of the 0001 sweep: per value line counts (receiver), frame yes/no, changes, frame-pair alternation, and for
kept frames: content rows/columns, row-parity ratio, mean level against the base frame."""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import resweep as R
base = pathlib.Path(sys.argv[1])
b = json.loads((base / 'base.json').read_text())
refd = sorted(base.glob('ref_*'))[-1]
rf, _ = R.decode(refd)
top = 40
rl = rf[0][top:].mean()
print('base', b)
groups = {}
for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith('ref')):
    if not (d / 'res.json').exists():
        continue
    r = json.loads((d / 'res.json').read_text())
    lines = sorted({q[0] for q in r['status'] if isinstance(q, list)})
    flags = sorted({q[1] for q in r['status'] if isinstance(q, list)})
    extra = ''
    if (d / 'p' / 'frame.raw').exists():
        f, m = R.decode(d / 'p')
        a = f[0][top:]
        cr = int((a[:, 50:-50].std(1) > 1).sum()); cc = int((a.std(0) > 1).sum())
        eo = a[0::2].mean() / max(a[1::2].mean(), 1e-3)
        extra = f'content {cr}x{cc} lvl×{a.mean() / rl:.2f} even/odd {eo:.2f}'
    key = (tuple(lines), tuple(flags), r['frame'], r.get('changed'))
    print(f"{r['value']} lines {lines} flags {[hex(x) for x in flags]} frame {r['frame']} changed {r.get('changed', '')} "
          f"f1f2 {np.round(r.get('f1f2', []), 3).tolist()} {'' if r['recovered'] else 'NOT RECOVERED'} {extra}")
