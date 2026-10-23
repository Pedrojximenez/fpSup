#!/usr/bin/env python3
"""Raw levels (no black subtraction) of every hit point: OB rows mean and active mean per CFA phase.

    rawlv.py captures/sweep_table_bits      (reads judge.json, writes rawlv.json)
"""
import json, pathlib, sys
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                         # noqa: E402

out = pathlib.Path(sys.argv[1])
j = json.loads((out / 'judge.json').read_text())
res = {}
for p in [{'point': r.name} for r in sorted(out.glob('ref_m*')) if (r / 'frame.raw').exists()] + [p for p in j['points'] if p['hit']]:
    d = out / p['point']
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    a = img[top:]
    res[p['point']] = dict(ob=round(img[1:top - 3].mean(), 1),
                           act=[round(a[i::2, j::2].mean(), 1) for i in (0, 1) for j in (0, 1)],
                           sat=round(float((a >= 4090).mean()), 3), std=round(float(a.std()), 1))
(out / 'rawlv.json').write_text(json.dumps(res, indent=0))
for k, v in res.items():
    print(f'{k:24s} ob {v["ob"]:7.1f} act {v["act"]} sat {v["sat"]} std {v["std"]}')
