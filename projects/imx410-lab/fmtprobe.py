#!/usr/bin/env python3
"""Unused 12-bit format words (0001) with a picture in the direct-write scan (captures/sweep0001: 1B 4177 wide x1.51,
15 3514 wide x2.37, 1C 3889 wide x4.28, 3D 6064 x0.90) set up properly: a class-12 plan whose format is the probed word
at the scanned width, so the receiver and BUFA match it. Fixed exposure (SHS 4, analog gain 0x400) for every word and for
the reference 2A, one frame pair each. Per word:
  width   real image columns (colscan_edge)      colour  R/G, B/G above black
  level   signal per exposure line vs 2A          noise   temporal (f1 - f2) / sqrt 2, and at matched level
  scale   horizontal scale of the scene vs 2A (column-profile match): 1 = no merge, 1/3 = 3:1 ...
Lens open, scene fixed. Nothing goes to the card or the settings area.

    fmtprobe.py OUT 2A:6064 1B:4177 15:3514 1C:3889 3D:6064
"""
import json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np
import readout_cfg as C, smc, smc_validate as V, colscan_edge as E


def one(code, width, out):
    import bufa_probe as B, resweep as R, vmode, fastsweep as F
    F.cached_assemble()
    key = f'x{code:02X}'
    r = dict(C.BY_KEY['12']); r.update(key=key, fmt={width: code}, name=f'probe 0001={code:02X}', cls=17)
    C.BY_KEY[key] = r; C.READOUTS.append(r)
    lw = C.line_width(r, width)
    cw = lw // 16 * 16
    p = C.plan(key, cw, 4040, cw, C.full_rows('12'))
    a, rows, _ = smc.create(p)
    rows = {t: bytes(v) for t, v in rows.items()}
    rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
    d = out / key; d.mkdir(parents=True, exist_ok=True)
    vmode.KEEP_WINDOW = True
    b = R.Base(d, 'V1', rows=rows); s = b.s; s.pair = True
    st = B.bus_state(); res = dict(code=f'{code:02X}', width=width, raster=p['raster_w'], vmax=a['vmax'], top=a['y0'])
    try:
        time.sleep(1.0)
        res['lines'] = min(B.P().mem_get(0x301005D8)[0] for _ in range(3))
        B.bus_on(st)
        B.P().sh('imager fixed_shutter 1 100')
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, 0x00), (0x003E, 0x04), (0x003F, 0x00), (0x0040, 0x04)])
        time.sleep(0.6)
        res['ok'] = bool(s.grab(d / 'f'))
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()
    if res['ok']:
        fr, _ = R.decode(d / 'f')
        top = a['y0']; f0, f1 = (x.astype(float) for x in fr[:2])
        ob = f0[4:max(top - 4, 6), 16:-16].mean()
        img = f0[top + 20:top + p['out_h'] - 20]
        l, rr, _ = E.edges(img)
        body = img[:, max(l, 32):img.shape[1] - max(rr, 32)] - ob
        ph = [body[i::2, j::2].mean() for i in (0, 1) for j in (0, 1)]; g = (ph[1] + ph[2]) / 2
        diff = (f0 - f1)[top + 20:top + p['out_h'] - 20, max(l, 32):img.shape[1] - max(rr, 32)]
        res.update(real_width=img.shape[1] - l - rr, pad=[l, rr], ob=ob, phases=ph, rg=ph[0] / g, bg=ph[3] / g,
                   level=g / (a['vmax'] - 4), noise=float(diff.std() / np.sqrt(2)), flat=float(body.std()))
        res['colprof'] = (body.mean(0)).tolist()
    (d / 'res.json').write_text(json.dumps(res))
    return res


def scale(ref, cand):
    """best horizontal scale + offset of cand's column profile against ref (both high-passed)"""
    def hp(x):
        x = np.asarray(x, float); k = np.ones(31) / 31
        return x - np.convolve(x, k, mode='same')
    rp, cp = hp(ref), hp(cand)
    best = (-2, None, None)
    for s in np.arange(0.30, 1.21, 0.01):
        xs = np.arange(len(cp)) / s                    # cand column i shows ref column i/s (+ offset)
        for off in range(0, max(1, int(len(rp) - xs[-1])), 8):
            idx = xs + off
            if idx[-1] >= len(rp) - 1:
                break
            v = np.interp(idx, np.arange(len(rp)), rp)
            c = np.corrcoef(v, cp)[0, 1]
            if c > best[0]:
                best = (c, round(float(s), 2), off)
    return dict(corr=round(float(best[0]), 3), scale=best[1], offset=best[2])


def main():
    """one word per process (a mode switch per process, like smc_validate); `summary` compares the saved results"""
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    if sys.argv[2] != 'summary':
        code, w = int(sys.argv[2].split(':')[0], 16), int(sys.argv[2].split(':')[1])
        r = one(code, w, out)
        print(r['code'], {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k not in ('colprof', 'phases')}, flush=True)
        return
    res = {json.loads(f.read_text())['code']: json.loads(f.read_text()) for f in out.glob('x*/res.json')}
    ref = res.get('2A')
    for k, r in sorted(res.items()):
        if ref and ref.get('ok') and r.get('ok') and k != '2A':
            r['vs2A'] = dict(level=round(r['level'] / ref['level'], 3), noise=round(r['noise'] / ref['noise'], 3),
                             **scale(ref['colprof'], r['colprof']))
        print(k, {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in r.items() if kk not in ('colprof', 'phases')}, flush=True)
    (out / 'summary.json').write_text(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'colprof'} for k, v in res.items()}, indent=1))


if __name__ == '__main__':
    main()
