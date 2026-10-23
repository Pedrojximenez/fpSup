#!/usr/bin/env python3
"""Stock reference for SMC round 4 (notes/SMC_VERIFY.md): image-minus-OB black of STOCK modes, measured exactly like
smc_validate --dark (stock rows as a virtual mode under host 10 -> firmware switch), at AE gain and at forced analog
gain codes 0x400 / 3900. Lens capped.

    smc_stockblack.py OUT MODE [MODE ...]       one subprocess per mode, results -> OUT/stockblack.json
"""
import json, pathlib, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np

CODES = (0x400, 3900)
LIGHT = False                 # set by --light: AE frame + Bayer phase only


def one(mode, out):
    import bufa_probe as B, resweep as R, vmode
    import reconstruct as RC
    modes, attrs, fields = RC.load()
    a = attrs[mode]
    top, h = a['y0'], a['height']
    d = out / f'stock{mode}'; d.mkdir(parents=True, exist_ok=True)
    vmode.KEEP_WINDOW = True
    b = R.Base(d, 'V2' if a['bits'] == 14 else 'V1', rows=vmode.donor_rows(mode))
    s = b.s; s.pair = True
    st = B.bus_state()
    res = dict(mode=mode, cls=a['cls'], width=a['width'], height=h, y0=top, offsets={})

    def diff(dd):
        if a['bits'] == 14:
            m = json.loads((dd / 'frame.json').read_text()); m['bits'] = 14; (dd / 'frame.json').write_text(json.dumps(m))
        f2, _ = R.decode(dd)
        return float(np.mean([f[top + 2:top + h - 2, 16:-16].mean() - f[4:max(top - 4, 6), 16:-16].mean() for f in f2]))
    try:
        if s.grab(d / 'ae'):
            res['offsets']['ae'] = diff(d / 'ae')
            f2, _ = R.decode(d / 'ae'); f = f2[0].astype(float)[top + 10:top + h - 10, 32:-32]
            res['phases'] = [float(f[i::2, j::2].mean()) for i in (0, 1) for j in (0, 1)]   # Bayer phase (lit scene)
            if LIGHT:
                return res
        B.bus_on(st)
        for code in CODES:
            B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, code & 0xFF), (0x003E, code >> 8), (0x003F, code & 0xFF), (0x0040, code >> 8)])
            time.sleep(0.4)
            if s.grab(d / f'g{code}'):
                res['offsets'][code] = diff(d / f'g{code}')
    finally:
        try:
            B.bus_subs(st, [])
        finally:
            b.close()
    return res


def main():
    global LIGHT
    if '--light' in sys.argv:
        sys.argv.remove('--light'); LIGHT = True
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    db_p = out / 'stockblack.json'
    db = json.loads(db_p.read_text()) if db_p.exists() else {}
    for m in map(int, sys.argv[2:]):
        chk = subprocess.run([sys.executable, '-c', 'import vmode; vmode.check_stock()'], cwd=HERE, capture_output=True, timeout=120)
        if chk.returncode:
            print('not stock -> fastreboot', flush=True)
            subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
        r = subprocess.run([sys.executable, '-u', '-c', f'import json,pathlib,smc_stockblack as S; S.LIGHT={LIGHT}; print("RES", json.dumps(S.one({m}, pathlib.Path({str(out)!r}))))'],
                           cwd=HERE, capture_output=True, text=True, timeout=600)
        line = next((l for l in r.stdout.splitlines() if l.startswith('RES ')), None)
        if line:
            res = json.loads(line[4:]); db[str(m)] = res
            print(m, 'cls', res['cls'], f"{res['width']}x{res['height']}", {k: round(v, 1) for k, v in res['offsets'].items()}, [round(x) for x in res.get('phases', [])], flush=True)
        else:
            print('ERROR', m, (r.stderr.strip().splitlines() or ['?'])[-1][:200], flush=True)
        db_p.write_text(json.dumps(db, indent=1))


if __name__ == '__main__':
    main()
