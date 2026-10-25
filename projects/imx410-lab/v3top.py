#!/usr/bin/env python3
"""14v3 dark top rows (IMX410_RULES §72): in full_v1 the AE frame f/ of 14v3 / 14v3w2B windows (1136, 1358 rows) had its
first 12-14 image rows black (no noise at all), while the same config's frames at SHS = 4 started at the planned row.
Does it follow SHS? One config, the AE frame, then a fixed gain code and SHS from 4 up to near VMAX.

    v3top.py OUT [--key 14v3 --crop 6064x3408 --out 6064x1136 --shs 4,50,200,500,900,1200]
"""
import argparse, json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np
import readout_cfg as C, smc, smc_validate as V


def dead_rows(f, top, y_skip=0):
    """image rows at the top whose level is < 1/4 of the frame body above OB (unexposed)"""
    import numpy as np
    f = f.astype(float); ob = f[4:max(top - 4 - y_skip, 6), 16:-16].mean(); rm = f[:, 16:-16].mean(1) - ob
    if ob < 100 or f[top + 40:-4, 16:-16].std() < 1.0:    # no image (sensor sent nothing: 0007/0008 != 0 did this) --
        return -1                                         # a blank frame used to count as "0 dead rows"
    body = np.median(rm[top + 40:-4]); n = 0
    if body < 15:                                         # too little signal to tell a dark scene from no exposure
        return -2
    while n < 80 and rm[top + n] < 0.25 * body:
        n += 1
    return n


def bands(f, top, rows, y_skip=0):
    """(under-exposed rows anywhere in the image, content shift vs REF rows profile)"""
    import numpy as np
    f = f.astype(float); ob = f[4:max(top - 4 - y_skip, 6), 16:-16].mean(); rm = f[:, 16:-16].mean(1) - ob
    img = rm[top:top + rows]; body = np.median(img)
    low = int((img < 0.5 * body).sum())
    sh = None
    if REF is not None:
        seg = REF[60:rows - 60]
        cand = range(-40, 41)
        sh = min(cand, key=lambda s: np.mean((rm[60 + s:rows - 60 + s] - seg) ** 2) if 0 <= 60 + s and rows - 60 + s <= len(rm) else 1e18)
    return low, sh


REF = None


def first_row(f, top):
    rs = f[:, 16:-16].astype(float).std(1)
    return next((i for i in range(2, len(rs) - 1) if rs[i] > 3 and rs[i + 1] > 3), -1) - top


def top_levels(d, top):
    import resweep as R
    fr, _ = R.decode(d)
    f = fr[0].astype(float); ob = f[4:16, 16:-16].mean()
    return [round(float(x - ob), 1) for x in f[top:top + 18:2, 16:-16].mean(1)]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('out')
    ap.add_argument('--key', default='14v3'); ap.add_argument('--crop', default='6064x3408'); ap.add_argument('--outsz', default='6064x1136')
    ap.add_argument('--shs', default='4,50,200,500,900,1200'); ap.add_argument('--code', type=int, default=0x400)
    ap.add_argument('--fps', type=float, default=None)
    ap.add_argument('--hmax', type=int, default=None, help='plan HMAX (line length, 72 MHz clocks)')
    ap.add_argument('--vset', type=int, default=0, help='burst: SoC VMAX register to this (lines) after fixed_shutter')
    ap.add_argument('--subs', default='', help='burst: extra IMXB substitutions REG=VAL,... (hex) alongside --shsset')
    ap.add_argument('--shsset', type=int, default=-1, help='burst: SHS substituted to this')
    ap.add_argument('--fixed_val', default='100', help='imager fixed_shutter 1 <this>')
    ap.add_argument('--fixed', action='store_true', help='imager fixed_shutter 1 100 before the repeats (AE stops writing)')
    ap.add_argument('--burst', type=int, default=0, help='N consecutive frames (IMXB frame_cb) + the bus log -> which frames are dead vs when 005C was written')
    ap.add_argument('--poke', action='store_true', help='fixed shutter + our own 005C/005D write (stock 0x03FF) before each grab')
    ap.add_argument('--bus', action='store_true', help='log every sensor write during the repeats (IMXB) -> bus.json')
    ap.add_argument('--repeat', type=int, default=0, help='only AE frames, this many pairs')
    ap.add_argument('--ref', default='', help='a frame dir whose row profile is the unshifted reference')
    ap.add_argument('--add', default='', help='extra sensor writes in the mode table, REG=VAL,... (hex)')
    ap.add_argument('--wstart', type=int, default=None, help='override the window start (sensor rows, = 1 mod 4)')
    ap.add_argument('--vmax', default='', help='instead of the SHS sweep: AE frames at these VMAX values (SoC VMAX register)')
    a = ap.parse_args()
    import bufa_probe as B, resweep as R, vmode, fastsweep as F
    F.cached_assemble()
    global REF
    if a.ref:
        import numpy as np
        ff = R.decode(pathlib.Path(a.ref))[0][0].astype(float)
        REF = ff[:, 16:-16].mean(1) - ff[4:16, 16:-16].mean()
    crop = tuple(map(int, a.crop.split('x'))); outsz = tuple(map(int, a.outsz.split('x')))
    p = C.plan(a.key, *crop, *outsz, a.fps, hmax=a.hmax)
    if a.wstart is not None:                            # same H (same rows), window moved
        assert a.wstart % 4 == 1
        p['sensor'] = [(r, v) for r, v in p['sensor'] if r not in (0x0022, 0x0023)] + [(0x0022, a.wstart & 0xFF), (0x0023, a.wstart >> 8)]
    if a.add:
        add = [tuple(int(x, 16) for x in kv.split('=')) for kv in a.add.split(',')]
        p['sensor'] = [(r, v) for r, v in p['sensor'] if r not in dict(add)] + add
    at, rows, _ = smc.create(p)
    if a.wstart is not None:
        at['wstart'] = a.wstart
    rows = {t: bytes(v) for t, v in rows.items()}
    rows['R10'] = struct.pack('<II', V.R10[at['cls']], 10)
    out = pathlib.Path(a.out) / (p['id'].replace(':', '_').replace('>', '_') + (f'_ws{a.wstart}' if a.wstart is not None else '') + (f'_r' if a.repeat else '') + (f'_h{a.hmax}' if a.hmax else '') + ('_fx' if a.fixed else '') + ('_pk' if a.poke else '') + (f'_b{a.burst}' if a.burst else '') + (f'_f{a.fixed_val}' if a.fixed else '') + (f'_v{a.vset}' if a.vset else '') + (f'_s{a.shsset}' if a.shsset >= 0 else '') + (('_u' + a.subs.replace('=', '').replace(',', '_')) if a.subs else '') + (('_a' + a.add.replace('=', '').replace(',', '_')) if a.add else '')); out.mkdir(parents=True, exist_ok=True)
    vmode.KEEP_WINDOW = True
    b = R.Base(out, 'V2' if p['bits'] == 14 else 'V1', rows=rows)
    s = b.s; s.pair = True
    st = B.bus_state(); top = at['y0']; res = dict(id=p['id'], vmax=at['vmax'], frames={})

    def grab(name):
        if not s.grab(out / name):
            res['frames'][name] = None; return
        if p['bits'] == 14:
            m = json.loads((out / name / 'frame.json').read_text()); m['bits'] = 14; (out / name / 'frame.json').write_text(json.dumps(m))
        fr, _ = R.decode(out / name)
        res['frames'][name] = [dead_rows(f, top, at.get('y_skip', 0)) for f in fr]
        print(name, res['frames'][name], flush=True)
    try:
        time.sleep(1.0)
        if a.burst:
            import hsburst
            ln = min(B.P().mem_get(0x301005D8)[0] for _ in range(3))
            print('receiver lines', ln, 'planned', p['receiver_lines'], flush=True); res['lines'] = ln
            grab('ae')                                  # frame.json for the burst frames
            if a.fixed:
                B.P().sh(f'imager fixed_shutter 1 {a.fixed_val}'); time.sleep(0.8)
            B.bus_on(st)
            v0 = B.P().mem_get(V.VREG)[0]
            subs = [tuple(int(x, 16) for x in kv.split('=')) for kv in a.subs.split(',')] if a.subs else []
            if a.shsset >= 0:
                subs += [(0x0005, a.shsset & 0xFF), (0x0006, a.shsset >> 8)]
            if subs:
                B.bus_subs(st, subs)
            if a.vset:
                B.wr(V.VREG, ((a.vset - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.5)
            meta, raws = hsburst.burst(s, n=a.burst, enum=1 if p['bits'] == 14 else 0, store=True)
            log = B.bus_dump(st)
            B.bus_subs(st, []); B.wr(V.VREG, v0)
            fj = json.loads((out / 'ae' / 'frame.json').read_text())
            dead = []; bandv = []
            for k, raw in enumerate(raws):
                dk = out / f'b{k}'; dk.mkdir(exist_ok=True)
                (dk / 'frame.raw').write_bytes(raw); (dk / 'frame.json').write_text(json.dumps(fj))
                fr, _ = R.decode(dk)
                dead.append(dead_rows(fr[0], top, at.get('y_skip', 0))); bandv.append(bands(fr[0], top, at['height'], at.get('y_skip', 0)))
            bl = [t for t, r, v, c in log if r == 0x5C]
            fs = [t for t, r, v, c in log if r == 0x041F]
            res.update(burst_dead=dead, ents=meta['ents'], black_ticks=bl, f41f_ticks=fs, bus=log)
            print('burst dead', dead, 'bands/shift', bandv, flush=True)
            (out / 'burst.json').write_text(json.dumps(res, indent=1))
            return
        if a.repeat:
            if a.fixed:
                B.P().sh('imager fixed_shutter 1 100'); time.sleep(0.8)
            if a.bus:
                B.bus_on(st)
            for i in range(a.repeat):
                if a.poke:                              # does one mid-stream black-level write make the dead band?
                    from callfn import call
                    call(0xC0322C70, 0x5C, 0xFF); call(0xC0322C70, 0x5D, 0x03)
                grab(f'ae{i}')
            if a.bus:
                log = B.bus_dump(st)
                (out / 'bus.json').write_text(json.dumps(log))
                from collections import Counter
                print('bus writes', len(log), dict(Counter(hex(r) for _, r, _, _ in log).most_common(16)), flush=True)
            return
        grab('ae')
        if a.vmax:                                      # full_v1: 14v3 dark top rows at VMAX 1291 / 2761 (= 1 mod 3) only
            v0 = B.P().mem_get(V.VREG)[0]
            for vm in map(int, a.vmax.split(',')):
                B.wr(V.VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.6)
                grab(f'vmax{vm}')
                res.setdefault('rows', {})[vm] = top_levels(out / f'vmax{vm}', top)
                print('   rows 20.. mean-ob', res['rows'][vm], flush=True)
            B.wr(V.VREG, v0); time.sleep(0.5)
            grab('ae_back')
            return
        B.bus_on(st)
        for shs in map(int, a.shs.split(',')):
            if shs >= at['vmax'] - 8:
                continue
            B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, a.code & 0xFF), (0x003E, a.code >> 8),
                            (0x003F, a.code & 0xFF), (0x0040, a.code >> 8)])
            time.sleep(0.5)
            grab(f'shs{shs}')
        B.bus_subs(st, [])
        time.sleep(0.5)
        grab('ae2')
        B.P().sh('imager fixed_shutter 1 100'); time.sleep(0.5)
        grab('fixed')                                   # smc_validate's light branch grabs after this command
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0)]); time.sleep(0.5)
        grab('fixed_shs4')
        B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0'); time.sleep(0.5)
        grab('ae3')
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()
    (out / 'v3top.json').write_text(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
