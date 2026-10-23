#!/usr/bin/env python3
"""Vertical window bounds per merge class (SMC round 4: the 2x2 / 3x3 window centres were estimates and tall crops
ran past the bottom of the readable area -- 50 rows of 4095 under the lens cap).

    winbound.py OUT KEY CROP_H START [START ...]     lens OFF, lit scene
For each START (0x0022/23 window start) the generated mode (smc.create, window start replaced) is switched in by the
firmware and one frame is grabbed. Row classes over the whole frame: OB-like (within 3 DN of the OB black: rows that
do not respond to light), lit, saturated (>= 4000). Reports the image rows' first/last lit row relative to y0 -- a
window start too small shows dark rows at the image top, too large shows dark/saturated rows at the bottom.
"""
import json, pathlib, struct, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np


def one(key, crop_h, start, out):
    import readout_cfg as C, smc, smc_validate as V, resweep as R, vmode
    r = C.BY_KEY[key]
    cw = 6048 if r['mh'] < 3 else 6048
    p = C.plan(key, cw, crop_h, int(cw / r['mh']) // 16 * 16, int(crop_h / r['mv']) // 2 * 2)
    sens = dict(p['sensor'])
    if 0x0022 not in sens:
        raise SystemExit('not windowed')
    sens[0x0022], sens[0x0023] = start & 0xFF, start >> 8
    p['sensor'] = sorted(sens.items())
    a, rows, how = smc.create(p)
    rows = {t: bytes(v) for t, v in rows.items()}
    rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
    d = out / f'{key}_{crop_h}_{start}'; d.mkdir(parents=True, exist_ok=True)
    vmode.KEEP_WINDOW = True
    b = R.Base(d, 'V1', rows=rows); s = b.s; s.pair = False
    try:
        if not s.grab(d / 'f'):
            return dict(start=start, error='no frame')
        fr, m = R.decode(d / 'f')
        f = fr[0].astype(float)[:, 16:-16]
        top, h = a['y0'], p['out_h']
        ob = f[4:max(top - 4, 6)].mean()
        rp = f.mean(1)
        cls = np.where(rp >= 4000, 'S', np.where(np.abs(rp - ob) < 3, 'D', 'L'))
        img = cls[top:top + h]
        lit = np.nonzero(img == 'L')[0]
        runs, cur, n = [], None, 0                              # run-length of the row classes over the image rows
        for c in img:
            if c == cur:
                n += 1
            else:
                if cur:
                    runs.append(f'{cur}{n}')
                cur, n = c, 1
        runs.append(f'{cur}{n}')
        return dict(start=start, H=dict(p['sensor'])[0x0024] | dict(p['sensor'])[0x0025] << 8, y0=top, out_h=h, frame_h=int(f.shape[0]),
                    ob=float(ob), img_mean=float(f[top:top + h].mean()), first_lit=int(lit[0]) if len(lit) else None,
                    last_lit=int(lit[-1]) if len(lit) else None, runs=' '.join(runs),
                    phases=[round(float(f[top + 10:top + h - 10][i::2, j::2].mean()), 1) for i in (0, 1) for j in (0, 1)])
    finally:
        b.close()


def main():
    out = pathlib.Path(sys.argv[1]); key = sys.argv[2]; crop_h = int(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    db_p = out / 'winbound.json'
    db = json.loads(db_p.read_text()) if db_p.exists() else {}
    for st in map(int, sys.argv[4:]):
        chk = subprocess.run([sys.executable, '-c', 'import vmode; vmode.check_stock()'], cwd=HERE, capture_output=True, timeout=120)
        if chk.returncode:
            print('not stock -> fastreboot', flush=True)
            rb = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
            if rb.returncode:
                print('camera did not come back -- stopping'); break
        r = subprocess.run([sys.executable, '-u', '-c', f'import json,pathlib,winbound as W; print("RES", json.dumps(W.one({key!r}, {crop_h}, {st}, pathlib.Path({str(out)!r}))))'],
                           cwd=HERE, capture_output=True, text=True, timeout=600)
        line = next((l for l in r.stdout.splitlines() if l.startswith('RES ')), None)
        if line:
            res = json.loads(line[4:]); db[f'{key}:{crop_h}:{st}'] = res
            print(key, crop_h, st, {k: (round(v, 1) if isinstance(v, float) else v) for k, v in res.items() if k != 'start'}, flush=True)
        else:
            print('ERROR', key, st, (r.stderr.strip().splitlines() or ['?'])[-1][:200], flush=True)
        db_p.write_text(json.dumps(db, indent=1))


if __name__ == '__main__':
    main()
