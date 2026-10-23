#!/usr/bin/env python3
"""gainmap.py: per point read noise (OB rows, DN12), conversion gain g (DN12 per electron, photon transfer on 16x16
blocks of one green plane), read noise in electrons, ADC headroom, and DR = (ADC range) / read noise in stops."""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import resweep as R

out = pathlib.Path(sys.argv[1])
rows = []
for base in ('V1', 'V2'):
    log = json.loads((out / base / 'log.json').read_text())
    for e in log:
        d = out / base / f"h{e['hcg']}_g{e['gain_db']:02d}"
        fr, m = R.decode(d)
        top = e['top']
        a, b = fr[0], fr[1]
        ob = (a[4:top - 4, 100:-100], b[4:top - 4, 100:-100])
        black = float(np.median(ob[0]))
        rn = float(np.std(ob[0] - ob[1]) / np.sqrt(2))
        A = a[top + 40:-40, 100:-100][0::2, 1::2] - black      # one green plane
        Bq = b[top + 40:-40, 100:-100][0::2, 1::2] - black
        h, w = A.shape[0] // 16 * 16, A.shape[1] // 16 * 16
        blk = lambda x: x[:h, :w].reshape(h // 16, 16, w // 16, 16)
        mean = ((blk(A) + blk(Bq)) / 2).mean((1, 3)).ravel()
        var = (blk(A - Bq) ** 2).mean((1, 3)).ravel() / 2 - 0          # temporal variance per block (incl. read noise)
        sel = (mean > 5) & (mean < 0.8 * (4095 - black))
        if sel.sum() > 50:
            k, c = np.polyfit(mean[sel], var[sel], 1)
        else:
            k, c = np.nan, np.nan
        top_dn = 4095 - black
        rows.append(dict(base=base, hcg=e['hcg'], g=e['gain_db'], black=black, rn_dn=rn, dn_per_e=k, rn_e=rn / k if k > 0 else np.nan,
                         fw_adc_e=top_dn / k if k > 0 else np.nan, dr_stops=float(np.log2(top_dn / rn)), med=float(np.median(mean))))
for base in ('V1', 'V2'):
    print(f'== {base}  ({"12" if base == "V1" else "14"}-bit)   gain dB | HCG | read noise DN12 | DN/e- | read noise e- | ADC full scale e- | DR stops (ADC/RN)')
    for r in rows:
        if r['base'] == base:
            print(f"{r['g']:5d} | {r['hcg']} | {r['rn_dn']:6.2f} | {r['dn_per_e']:6.3f} | {r['rn_e']:6.2f} | {r['fw_adc_e']:8.0f} | {r['dr_stops']:5.2f}   (median sig {r['med']:.0f})")
json.dump(rows, open(out / 'eval.json', 'w'), indent=1, default=float)
