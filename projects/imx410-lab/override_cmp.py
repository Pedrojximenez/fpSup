#!/usr/bin/env python3
"""Override sweep -> what each register did.

For every captures/override/<name> (bufa_probe.py frame ... --pre "imager mode_reg_add 0 R V"):
  - was the override really written, after the table (bus.json, the consumer C03234E0 region)?
  - frame against `ref`: geometry, OB black, image level per CFA phase, sharpness (same-colour
    neighbour difference along x / y), row and column banding.

    override_cmp.py captures/override
    override_cmp.py captures/override57 0x57 [captures/override/ref]   # v0x.. names, another reference
"""
import json, pathlib, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decode12 import decode12                                        # noqa: E402


def load(d):
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = (m['window'] >> 16) if m.get('ystart') == 0 else 0
    return m, img, top


def metrics(img, top):
    ob = img[1:max(top - 3, 2)] if top else img[:0]
    a = img[top:]
    ph = [a[i::2, j::2].mean() for i in (0, 1) for j in (0, 1)]
    g = a[0::2, 1::2]
    return dict(h=img.shape[0], w=img.shape[1],
                black=round(ob.mean(), 2) if ob.size else None,
                ob_noise=round(np.diff(ob[:, ::2], axis=1).std() / np.sqrt(2), 2) if ob.size else None,
                phases=[round(p, 1) for p in ph],
                dx=round(np.abs(np.diff(g, axis=1)).mean(), 2), dy=round(np.abs(np.diff(g, axis=0)).mean(), 2),
                rowband=round(a.mean(axis=1).std(), 2), colband=round(a.mean(axis=0).std(), 2),
                sat=int(a.max()), zero_rows=int((a.max(axis=1) == 0).sum()))


def written(d, name):
    """(reg, val) the override wrote, or None."""
    if name.startswith('r') and '_v' in name:
        reg, val = (int(x, 16) for x in name[1:].split('_v'))
    elif name.startswith('v0x') and len(sys.argv) > 2:          # bit tests: register on the command line
        reg, val = int(sys.argv[2], 16), int(name[1:], 16)
    else:
        return None
    bus = json.loads((d / 'bus.json').read_text())
    hits = [e for e in bus if int(e['reg'], 16) == reg and int(e['val'], 16) == val]
    return (f'0x{reg:04X}', f'0x{val:02X}', len(hits), sorted({e['lr'] for e in hits}))


def main():
    root = pathlib.Path(sys.argv[1])
    m0, ref, top0 = load(pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else root / 'ref')
    r = metrics(ref, top0)
    print('ref', r)
    for d in sorted(root.iterdir()):
        if d.name.startswith('ref') or not (d / 'frame.raw').exists():
            continue
        m, img, top = load(d)
        x = metrics(img, top)
        diff = {k: (r[k], v) for k, v in x.items() if v != r[k]}
        print(f'{d.name:14s} written={written(d, d.name)}')
        print(f'{"":14s} {x}')


if __name__ == '__main__':
    main()
