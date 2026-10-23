#!/usr/bin/env python3
"""G7 (SMC_VERIFY): do generated modes get the right defect table? Lens capped.

The BUFA0 tap sits BEFORE the defect correction (DEFECT_CORRECTION.md), so hot pixels are visible in our raw grabs.
Per mode: firmware switch (stock donor rows or smc-generated rows under host 10), long frame (VMAX 16000) at analog
code 3965 (30 dB), SHS 4; two frames; stable hot pixels = > median + 12 robust sigma in both. Predicted defects = the
flash table the mode would use, translated with the firmware's own rules (offline/defect_tables.translate):
  stock 10 -> table 97 as is; stock 98 -> its own table 98; generated class -> table 97 with the class's coordinate
  types (h/v merge -> 0/7/2 and 0/7/1/3). The unknown is the coordinate origin: the best integer offset (dx, dy) of
  the predicted set onto the measured set is searched in +-120 px; reported: coverage at that offset (fraction of
  hot pixels with a predicted defect within 1 px) and the offset itself, to compare with the stock modes.

    g7_probe.py capture OUT MODE...      MODE = stock:<id> | gen:<readout key>   (full frame; use full-height stock
                                         modes 97 / 98 / 139 as references -- windowed ones sit ~1000 rows off)
    g7_probe.py eval OUT BUF.bin         BUF = captures/defect/flashbuf.bin
"""
import json, pathlib, struct, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np

VREG = 0x30100020
CODE = 3965


def hot(a):
    med = np.median(a); mad = 1.4826 * np.median(np.abs(a - med)) + 1e-6
    ys, xs = np.nonzero(a > med + 12 * mad)
    return set(zip(ys.tolist(), xs.tolist()))


def capture_one(spec, out):
    import bufa_probe as B, resweep as R, vmode, smc, readout_cfg as C, smc_validate as V
    kind, name = spec.split(':')
    d = out / spec.replace(':', '_'); d.mkdir(parents=True, exist_ok=True)
    vmode.KEEP_WINDOW = True
    if kind == 'stock':
        mode = int(name)
        rows = vmode.donor_rows(mode)
        top = struct.unpack_from('<H', rows['TIM'], 0xE)[0]
        import reconstruct as RC
        bits = RC.load()[1][mode]['bits']
        meta = dict(kind='stock', mode=mode, top=top)
    else:
        r = C.BY_KEY[name]; w = max(r['fmt'])
        p = C.plan(name, w * r['mh'] if r['mh'] > 1 else w, 4040, (w // 16) * 16, C.full_rows(r['key']))
        a, rows, how = smc.create(p)
        rows = {t: bytes(v) for t, v in rows.items()}
        rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
        top, bits = a['y0'], p['bits']
        meta = dict(kind='gen', key=name, top=top, x0=a['x0'], hbin=r['mh'], vbin=r['mv'], width=a['width'], height=a['height'])
    b = R.Base(d, 'V2' if bits == 14 else 'V1', rows=rows); s = b.s; s.pair = True
    st = B.bus_state(); v0 = B.P().mem_get(VREG)[0]
    try:
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, CODE & 0xFF), (0x003E, CODE >> 8), (0x003F, CODE & 0xFF), (0x0040, CODE >> 8)])
        B.P().sh('imager fixed_shutter 1 100')
        B.wr(VREG, ((16000 - 1) << 16) | (v0 & 0xFFFF)); time.sleep(1.0)
        ok = s.grab(d / 'dark')
        if ok and bits == 14:
            m = json.loads((d / 'dark' / 'frame.json').read_text()); m['bits'] = 14; (d / 'dark' / 'frame.json').write_text(json.dumps(m))
        meta['ok'] = bool(ok)
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0'); B.wr(VREG, v0)
        finally:
            b.close()
    (d / 'meta.json').write_text(json.dumps(meta, indent=1))
    print(spec, 'ok' if meta.get('ok') else 'NO FRAME', flush=True)


def evaluate(out, bufp):
    import resweep as R, defect_tables as D, reconstruct as RC
    buf = pathlib.Path(bufp).read_bytes()
    attrs = RC.load()[1]
    src97, _ = D.table(buf, 97)
    for d in sorted(p for p in out.iterdir() if (p / 'meta.json').exists()):
        m = json.loads((d / 'meta.json').read_text())
        if not m.get('ok'):
            continue
        f2, _ = R.decode(d / 'dark')
        top = m['top']
        meas = hot(f2[0][top:, 8:-8]) & hot(f2[1][top:, 8:-8])
        if m['kind'] == 'stock':
            a = attrs[m['mode']]
            if m['mode'] in (97, 10, 3):
                pred = D.points(src97)
            else:
                own, _ = D.table(buf, m['mode']) if m['mode'] in D.parse(buf)['tables'] else D.table(buf, 98)
                pred = D.points(own)
        else:
            xt = {1: 0, 2: 7, 3: 2}[m['hbin']]; yt = {1: 0, 2: 7, 3: 1, 6: 3}[m['vbin']]
            stream, _ = D.translate(src97, (0, 0, 6064, 4042), (xt, yt), (0, 0), m['width'] + 64, m['height'] + 64)
            pred = D.points(stream)
        P = np.zeros((max(y for _, y in pred) + 400, max(x for x, _ in pred) + 400), bool) if pred else None
        best = (0, 0, 0.0)
        if pred and meas:
            for x, y in pred:
                P[y + 150, x + 150] = True
            P1 = P.copy()                                             # 3x3 dilation without scipy
            for ddy in (-1, 0, 1):
                for ddx in (-1, 0, 1):
                    P1 |= np.roll(np.roll(P, ddy, 0), ddx, 1)
            M = np.array(sorted(meas))                                # (row, col) in the frame (col offset 8)
            for dy in range(-120, 121):
                for dx in range(-120, 121, 1):
                    yy = M[:, 0] + dy + 150; xx = M[:, 1] + 8 + dx + 150
                    okm = (yy >= 0) & (yy < P1.shape[0]) & (xx >= 0) & (xx < P1.shape[1])
                    cov = float(P1[yy[okm], xx[okm]].mean()) if okm.any() else 0.0
                    if cov > best[2]:
                        best = (dx, dy, cov)
        print(f"{d.name:14s} hot {len(meas):5d} predicted {len(pred):6d}  best offset dx {best[0]:+d} dy {best[1]:+d}  coverage {best[2]:.3f}", flush=True)
        m['g7'] = dict(hot=len(meas), predicted=len(pred), dx=best[0], dy=best[1], coverage=best[2])
        (d / 'meta.json').write_text(json.dumps(m, indent=1))


def main():
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == 'capture':
        for spec in sys.argv[3:]:
            r = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
            if r.returncode:
                print('camera did not come back -- stopping'); break
            r = subprocess.run([sys.executable, '-u', '-c', f'import g7_probe, pathlib; g7_probe.capture_one({spec!r}, pathlib.Path({str(out)!r}))'],
                               cwd=HERE, capture_output=True, text=True, timeout=300)
            print((r.stdout.strip().splitlines() or ['?'])[-1], ('ERR ' + (r.stderr.strip().splitlines() or ['?'])[-1][:160]) if r.returncode else '', flush=True)
    elif sys.argv[1] == 'eval':
        evaluate(out, sys.argv[3])


if __name__ == '__main__':
    main()
