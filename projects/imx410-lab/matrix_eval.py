#!/usr/bin/env python3
"""Evaluate a matrix.py capture directory: per cell the lit width / rows, Bayer phases at the first lit row, row
phase (v1), temporal noise (frame pair) and same-colour neighbour roughness, against the m10_1x1 control.

    matrix_eval.py DIR [--bits14 PREFIX]
"""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
from decode12 import decode12
from decode14 import decode14
import rowphase


def load(d, bits):
    m = json.loads((d / 'frame.json').read_text())
    dec, sc = (decode14, 0.25) if bits == 14 else (decode12, 1.0)
    out = []
    for n in ('frame.raw', 'frame2.raw'):
        q = d / n
        if q.exists():
            out.append(dec(q.read_bytes(), m['height'], m['line_words']).astype(np.float64) * sc)
    return out


def main():
    base = pathlib.Path(sys.argv[1])
    rows = {}
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        if not (d / 'frame.json').exists():
            continue
        bits = 14 if d.name.startswith('w14') else 12
        fr = load(d, bits)
        if not fr:
            print(d.name, 'no frame'); continue
        f = fr[0]
        # image rows / columns = textured ones (OB and padding are flat; with the 005D pedestal the OB can sit ABOVE a
        # dim scene, so a level threshold fails)
        rs = f[:, 40:-40].std(1); cs = f[60:-10].std(0)
        r0 = float(np.median(rs[2:6])) + 1.0; c0 = float(np.median(np.sort(cs)[:50])) + 1.0
        lit_r = np.nonzero(rs > 4 * r0)[0]; lit_c = np.nonzero(cs > 4 * c0)[0]
        if len(lit_r) < 50 or len(lit_c) < 50 or f[60:-10].std() < 3:
            print(f'{d.name:9s} FLAT  median {np.median(f):.0f} std {f.std():.1f}'); rows[d.name] = dict(ok=False); continue
        top = int(lit_r[0]); top += top % 2
        x0, x1 = int(lit_c[0]), int(lit_c[-1])
        x0 += x0 % 2
        img = f[top + 10:int(lit_r[-1]) - 10, x0 + 8:x1 - 8]
        img = img[:img.shape[0] // 2 * 2, :img.shape[1] // 2 * 2]
        ph = [float(img[i::2, j::2].mean()) for i in (0, 1) for j in (0, 1)]
        g = (ph[1] + ph[2]) / 2
        bayer = abs(ph[1] - ph[2]) < 0.02 * g and g > max(ph[0], ph[3]) + 0.05 * g
        rpj = rowphase.judge(img, 1)
        tn = float(np.std(fr[0][top:top + 300, x0:x0 + 1000] - fr[1][top:top + 300, x0:x0 + 1000]) / np.sqrt(2)) if len(fr) > 1 else None
        rough = float(np.median(np.abs(img[:, 0:-2:2] - img[:, 2::2])))
        rows[d.name] = dict(ok=True, lit_rows=[top, int(lit_r[-1])], lit_cols=[x0, x1], width=x1 - x0 + 1, phases=ph, bayer=bool(bayer),
                            rowphase=rpj['dy'], rowphase_ok=rpj['PASS'], temporal_noise=tn, roughness=rough)
        print(f"{d.name:9s} rows {top}-{int(lit_r[-1])} cols {x0}-{x1} (w {x1 - x0 + 1}) bayer {'ok' if bayer else 'BAD'} "
              f"{[round(x) for x in ph]} rowphase {rpj['dy']} noise {tn if tn is None else round(tn, 1)} rough {rough:.0f}", flush=True)
    (base / 'eval.json').write_text(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
