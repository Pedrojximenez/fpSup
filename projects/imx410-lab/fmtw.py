#!/usr/bin/env python3
"""Sensor-side width presets (format words 18 / 03 / 2C, readout_cfg.EXPERIMENTAL; user 2026-10-23: they are width
crops). Lens open, fixed scene. Per config: firmware switch to the generated full-height plan (receiver width = the
preset), a frame pair at AE. Reference: class 12 (2A, 6064). Analysis per frame:
  position   column offset of the preset inside the 6064 field (high-pass column-profile correlation with the ref)
  noise      temporal noise = std(frame1 - frame2)/sqrt(2) on the lit area
  valid      rows that are flat (std < 0.5) or alternate-row blanking (odd/even row mean ratio) -- the HMAX failure
             signatures of §45 ('whole frame constant', 'every other row blank')
Nothing is written to the settings area or the card.

    fmtw.py capture OUT KEY[@HMAX] ...      e.g. 12 12w18 f12w03@350
    fmtw.py report OUT
"""
import json, pathlib, struct, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np


def capture_one(spec, out):
    import resweep as R, vmode, smc, readout_cfg as C, smc_validate as V
    vmode.KEEP_WINDOW = True
    key, _, hm = spec.partition('@')
    r = C.BY_KEY[key]; w = max(r['fmt'])
    if hm:                                   # HMAX scan: below the class floor on purpose (this process only)
        r['hmin'] = min(r['hmin'], int(hm))
    p = C.plan(key, w * r['mh'], 4040, w // 16 * 16, C.full_rows(key), hmax=int(hm) if hm else None)
    a, rows, how = smc.create(p)
    rows = {t: bytes(v) for t, v in rows.items()}
    rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
    d = out / spec.replace('@', '_h'); d.mkdir(parents=True, exist_ok=True)
    b = R.Base(d, 'V1', rows=rows); s = b.s; s.pair = True
    try:
        time.sleep(1.0)
        ok = s.grab(d / 'f')
    finally:
        b.close()
    (d / 'meta.json').write_text(json.dumps(dict(spec=spec, key=key, hmax=p['soc']['hmax'], fmt_w=w, y0=a['y0'],
                                                 out_h=p['out_h'], ok=bool(ok)), indent=1))
    print(spec, 'ok' if ok else 'NO FRAME', flush=True)


def _prof(img):
    p = img.mean(0)
    return p - np.convolve(p, np.ones(31) / 31, 'same')


def report(out):
    import resweep as R
    metas = {json.loads((d / 'meta.json').read_text())['spec']: d for d in out.iterdir() if (d / 'meta.json').exists()}
    ref = None
    if '12' in metas:
        fr, _ = R.decode(metas['12'] / 'f'); m = json.loads((metas['12'] / 'meta.json').read_text())
        ref = _prof(np.mean(fr, 0)[m['y0'] + 100:m['y0'] + m['out_h'] - 100])
    for spec in sorted(metas):
        d = metas[spec]; m = json.loads((d / 'meta.json').read_text())
        if not m['ok']:
            print(f'{spec:14s} NO FRAME'); continue
        fr, _ = R.decode(d / 'f')
        f = np.mean(fr, 0)[m['y0'] + 4:m['y0'] + m['out_h'] - 4]
        rs = f[:, 16:-16].std(1)
        flat = float((rs < 0.5).mean())
        rm = f[:, 16:-16].mean(1)
        alt = float(np.median(rm[0::2][:len(rm) // 2 - 1]) / max(np.median(rm[1::2][:len(rm) // 2 - 1]), 1))
        noise = float(np.std((fr[0] - fr[1])[m['y0'] + 100:m['y0'] + 900, 100:-100]) / np.sqrt(2)) if len(fr) > 1 else None
        res = dict(width=int(f.shape[1]), flat_rows=round(flat, 3), even_odd=round(alt, 3), noise=None if noise is None else round(noise, 2))
        if ref is not None and spec != '12':
            p = _prof(f[96:-96])[40:-40]
            best = max(((off, float(np.corrcoef(p, ref[off + 40:off + 40 + len(p)])[0, 1]))
                        for off in range(0, len(ref) - len(p) - 80 + 1)), key=lambda t: t[1])
            res.update(x_in_6064=best[0], corr=round(best[1], 3),
                       centred_x=(6064 - m['fmt_w']) // 2)
        m['report'] = res
        (d / 'meta.json').write_text(json.dumps(m, indent=1))
        print(f'{spec:14s} hmax {m["hmax"]:4d} ' + ' '.join(f'{k} {v}' for k, v in res.items()), flush=True)


def main():
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == 'report':
        report(out); return
    for spec in sys.argv[3:]:
        r = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
        if r.returncode:
            print('camera did not come back -- stopping'); break
        r = subprocess.run([sys.executable, '-u', '-c', f'import fmtw, pathlib; fmtw.capture_one({spec!r}, pathlib.Path({str(out)!r}))'],
                           cwd=HERE, capture_output=True, text=True, timeout=300)
        print((r.stdout.strip().splitlines() or ['?'])[-1], ('ERR ' + (r.stderr.strip().splitlines() or ['?'])[-1][:200]) if r.returncode else '', flush=True)


if __name__ == '__main__':
    main()
