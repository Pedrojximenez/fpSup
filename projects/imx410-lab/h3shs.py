#!/usr/bin/env python3
"""h3 (3x1, format 2F, no vertical merge) linearity (SMC_VERIFY round 16): the validator's VMAX steps gave signal ~
0.052 * (VMAX - ~1480) at max fps instead of VMAX - 8. Hypothesis: in format 2F the SHS register counts 3-row units
(stock 3x3 lines are 3 sensor rows), so the firmware's SHS takes ~3x the lines it meant. Test: firmware switch to the
generated full-height plan, fixed analog gain, fixed VMAX, SHS held by IMXB substitution at several values; the slope of
signal vs SHS relative to the slope vs VMAX gives the SHS unit. 12h2 (format 3B) is the control. Lens open.
Nothing is written to the settings area or the card.

    h3shs.py OUT KEY...          (KEY = 12h3, 12h2, f12h3 ...)
"""
import json, pathlib, struct, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np

VREG = 0x30100020
SHS = (4, 500, 1000, 1500)
GAINCODE = 0x400     # analog gain code (round 16 r3: h3 linearity failed only where the validator raised it to ~3700+)
OVR = []             # extra sensor writes appended to the plan (round 16 r5: V3 subsets on h3 / mode-10 values on 3x3)
OVR_TAG = ''
REG58 = None         # override 0058 (pedestal/clamp; 1x1 stock 0x20, binned 0x70) -- round 16 r4
VSTEPS = False      # True: VMAX x1..x4 at SHS 4, each twice (repeatability; round 16 r2)


def one(key, out):
    import bufa_probe as B, resweep as R, vmode, smc, readout_cfg as C, smc_validate as V
    vmode.KEEP_WINDOW = True
    r = C.BY_KEY[key]; w = max(r['fmt'])
    p = C.plan(key, w * r['mh'], 4040, w // 16 * 16, C.full_rows(key))
    if REG58 is not None:
        p['sensor'] = [(ad, v) for ad, v in p['sensor'] if ad != 0x0058] + [(0x0058, REG58)]
    if OVR:
        drop = {ad for ad, _ in OVR}
        p['sensor'] = [(ad, v) for ad, v in p['sensor'] if ad not in drop] + list(OVR)
    a, rows, how = smc.create(p)
    rows = {t: bytes(v) for t, v in rows.items()}
    if r.get('new'):
        rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
    d = out / (f'{key}_g{GAINCODE}' + (f'_58_{REG58:02X}' if REG58 is not None else '') + (f'_{OVR_TAG}' if OVR_TAG else '')); d.mkdir(parents=True, exist_ok=True)
    b = R.Base(d, 'V1', rows=rows); s = b.s; s.pair = True
    top = a['y0']
    st = B.bus_state(); v0 = B.P().mem_get(VREG)[0]; vbase = (v0 >> 16) + 1
    GAIN = [(0x003D, GAINCODE & 0xFF), (0x003E, GAINCODE >> 8), (0x003F, GAINCODE & 0xFF), (0x0040, GAINCODE >> 8)]
    res = dict(key=key, vmax=vbase, gain=GAINCODE, points=[])

    def level(dd):
        fr, _ = R.decode(dd)
        return float(np.mean([f[top + 4:top + p['out_h'] - 4, 60:-60].mean() - f[4:max(top - 4, 6), 60:-60].mean() for f in fr]))
    try:
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        plan_ = ([(m * vbase, 4) for m in (1, 2, 3, 4) for _ in range(2)] if VSTEPS else [(vbase, x) for x in SHS] + [(2 * vbase, 4)])
        plan_ = [(vm, x) for vm, x in plan_ if vm <= C.VMAX_MAX]   # r2 asked 4 x 4156 = 16624 > 16384 (refused, readback)
        for i_, (vm, shs) in enumerate(plan_):
            B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF))
            B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8)] + GAIN); time.sleep(0.6)
            dd = d / f'v{vm}_s{shs}_{i_}'
            lv = level(dd) if s.grab(dd) else None
            res['points'].append((vm, shs, lv))
            print(key, 'vmax', vm, 'shs', shs, 'level', None if lv is None else round(lv, 1), flush=True)
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0'); B.wr(VREG, v0)
        finally:
            b.close()
    pts = [q for q in res['points'] if q[2] is not None]
    if VSTEPS:
        k = [q[2] / (q[0] - 8) for q in pts]
        x = np.array([q[0] - 8 for q in pts], float); y = np.array([q[2] for q in pts])
        b_, a_ = np.polyfit(x, y, 1)
        res.update(k=k, slope=float(b_), offset=float(a_), offset_lines=float(a_ / b_))
        print(key, 'k per point', [round(v * 1e3, 3) for v in k], 'fit offset', round(a_, 2), 'DN =', round(a_ / b_), 'lines', flush=True)
        (d / 'result.json').write_text(json.dumps(res, indent=1)); return
    sv = [(q[1], q[2]) for q in pts if q[0] == vbase]
    if len(sv) >= 2 and len(pts) == len(res['points']):
        ks = -np.polyfit([x for x, _ in sv], [y for _, y in sv], 1)[0]      # DN lost per SHS step
        kv = (pts[-1][2] - pts[0][2]) / vbase                                # DN gained per VMAX line
        res.update(dn_per_shs=float(ks), dn_per_line=float(kv), shs_unit=float(ks / kv))
        print(key, 'SHS unit (lines per SHS step):', round(ks / kv, 2), flush=True)
    (d / 'result.json').write_text(json.dumps(res, indent=1))


def main():
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    gains = [int(x.split('=')[1]) for x in sys.argv[2:] if x.startswith('--gain=')] or [0x400]
    r58 = next((int(x.split('=')[1], 16) for x in sys.argv[2:] if x.startswith('--r58=')), None)
    args = [x for x in sys.argv[2:] if not x.startswith('--')]
    for key, gc in [(k, g) for k in args for g in gains]:
        r = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
        if r.returncode:
            print('camera did not come back -- stopping'); break
        r = subprocess.run([sys.executable, '-u', '-c', f'import h3shs, pathlib; h3shs.VSTEPS = {"--vsteps" in sys.argv}; h3shs.GAINCODE = {gc}; h3shs.REG58 = {r58!r}; h3shs.one({key!r}, pathlib.Path({str(out)!r}))'],
                           cwd=HERE, capture_output=True, text=True, timeout=400)
        print(r.stdout.strip())
        if r.returncode:
            print('ERR', (r.stderr.strip().splitlines() or ['?'])[-1][:200])


if __name__ == '__main__':
    main()
