"""Live validation of one readout_gen plan (DEV_PLAN D1 milestone 2): direct writes on the donor's virtual base,
then the standard checks of SUMMARY_2026-10-21 §3:
  1. receiver lines == plan['receiver_lines'] and the frame completes;
  2. exposure linearity: smc_validate.lin_check (lamp-period VMAX, pair average, zero-exposure baseline);
  3. Bayer phase of the lit frame: greens equal, green above R and B; row phase = the class value (rowphase, §65);
  4. frame_cb burst (8 frames) at the plan's VMAX: completion intervals == law, no drops, frames distinct.
Writes result.json with PASS/FAIL per check. Nothing is written to the settings area or the card.
"""
import json, struct, time
import numpy as np
import bufa_probe as B
import resweep as R
import fastsweep as F
import vmode, l7, hsburst
from decode12 import decode12
from decode14 import decode14

VREG, WREG, HREG, RXREG = 0x30100020, 0x30100024, 0x30100004, 0x3010000C


def hdr_check(img, black):
    """checkerboard HDR (§30): within every colour plane the cell columns alternate full / attenuated (cells are 4 raw
    columns: plane columns k even = raw cols 0-1 mod 4, k odd = 2-3 mod 4). Per colour: attenuated/full ratio and side;
    the two planes of a Bayer row share a side and the other row has the other side. Per row (green, both planes):
    the ratio along the frame -- rows at the bottom whose ratio is off by > 30 % are counted (the attenuated group is
    read 0738 rows further down, §30: a window can cut it off)."""
    img = img[:img.shape[0] // 2 * 2].astype(np.float64) - black
    out, sides = {}, []
    for i in (0, 1):
        for j in (0, 1):
            pl = img[i::2, j::2]
            a, b = pl[:, 0::2], pl[:, 1::2]
            n = min(a.shape[1], b.shape[1]); a, b = a[:, :n], b[:, :n]
            ma, mb = float(a.mean()), float(b.mean())
            side = 'a' if ma < mb else 'b'
            sides.append(side)
            out[f'{i}{j}'] = dict(ratio=round(min(ma, mb) / max(ma, mb, 1e-6), 4), att=side)
    g = []                                           # green per-row ratio: plane 01 and 10
    for i, j in ((0, 1), (1, 0)):
        pl = img[i::2, j::2]; n = pl.shape[1] // 2 * 2
        a, b = pl[:, 0:n:2].mean(1), pl[:, 1:n:2].mean(1)
        g.append(np.minimum(a, b) / np.maximum(np.maximum(a, b), 1e-6))
    rr = np.minimum(*[x[:min(len(g[0]), len(g[1]))] for x in g])
    med = float(np.median(rr))
    off = np.abs(rr - med) > 0.3 * med
    bot = 0
    for v in off[::-1]:
        if not v:
            break
        bot += 1
    ok_side = sides[0] == sides[1] and sides[2] == sides[3] and sides[0] != sides[2]
    ok_ratio = all(0.01 < v['ratio'] < 0.3 for v in out.values())
    return dict(planes=out, row_ratio_median=round(med, 4), bottom_bad_rows=2 * bot, rows_off=int(off.sum()) * 2,
                PASS=bool(ok_side and ok_ratio and off.sum() - bot < 0.02 * len(off)))


def hdr_linearity(s, st, out, top, p, vp, v0, mark14):
    """HDR: exposure stepped by SHS at a fixed VMAX (exposure lines = VMAX - SHS), level of the full-gain and the
    attenuated cells separately (black from the OB rows), plus the clipped fraction. Each group must fit a line
    through its 3 points (smc_validate.lin_fit) unless it is clipped."""
    from smc_validate import lin_fit
    B.wr(VREG, ((vp - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
    pts_f, pts_a, clip = [], [], []
    for shs in (vp // 2, vp // 4, 8):
        B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, 0x00), (0x003E, 0x04), (0x003F, 0x00), (0x0040, 0x04)])
        time.sleep(0.3)
        d = out / f'hshs{shs}'
        if not s.grab(d):
            continue
        mark14(d)
        f = R.decode(d)[0][0].astype(np.float64)
        blk = float(f[4:max(top - 4, 6), 60:-60].mean())
        img = f[top + 10:top + p['out_h'] - 10, 60:-60]; img = img[:img.shape[0] // 2 * 2, :img.shape[1] // 4 * 4] - blk
        att = np.zeros(img.shape, bool)                # rows 0 mod 2: attenuated in cols 0-1 mod 4; rows 1: 2-3 mod 4
        att[0::2, :] = (np.arange(img.shape[1]) % 4 < 2)[None, :]
        att[1::2, :] = (np.arange(img.shape[1]) % 4 >= 2)[None, :]
        e = vp - shs
        pts_f.append((e + 8, float(img[~att].mean()) / e)); pts_a.append((e + 8, float(img[att].mean()) / e))
        clip.append(float((img[~att] + blk > 4000).mean()))
        for q in d.glob('frame*.raw'):
            q.unlink()
    lf, la = lin_fit(pts_f), lin_fit(pts_a)
    clipped = max(clip) > 0.02 if clip else True
    return dict(full=lf, attenuated=la, clip_frac=clip, PASS=bool(la['PASS'] and (lf['PASS'] or clipped)))


def C_mv(p):
    import readout_cfg
    return readout_cfg.BY_KEY[p['key']]['mv']


def run(p, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'plan.json').write_text(json.dumps(p, indent=1, default=str))
    F.cached_assemble(); B.not_recording()
    for _ in range(15):                                # matrix round 2: 5 configs in a row found the camera off mode 8
        if ',0008,' in B.P().sh('imager mode_now'):    # right after the previous config -- give the switch back time
            break
        time.sleep(1.0)
    else:
        raise SystemExit('start from live view (mode 8): ' + B.P().sh('imager mode_now').strip().splitlines()[2][:60])
    vmode.KEEP_WINDOW = True
    rows = vmode.donor_rows(p['donor'])
    if p['rows']['TIM_line']:
        t = bytearray(rows['TIM']); struct.pack_into('<H', t, 0xC, p['rows']['TIM_line']); rows['TIM'] = bytes(t)
    if p['rows']['R38_words']:
        r = bytearray(rows['R38']); struct.pack_into('<H', r, 8, p['rows']['R38_words']); rows['R38'] = bytes(r)
    b = R.Base(out, 'V2' if p['bits'] == 14 else 'V1', rows=rows); s = b.s; s.pair = False
    v0, w0, h0, rx0 = (B.P().mem_get(a)[0] for a in (VREG, WREG, HREG, RXREG))
    top = struct.unpack_from('<H', rows['TIM'], 0xE)[0]
    st = B.bus_state(); res = dict(checks={})

    def lines():
        return min(B.P().mem_get(0x301005D8)[0] for _ in range(3))

    def mark14(d):
        if p['bits'] == 14 and (d / 'frame.json').exists():
            m = json.loads((d / 'frame.json').read_text()); m['bits'] = 14
            (d / 'frame.json').write_text(json.dumps(m))

    def level(d):
        mark14(d)
        f, m = R.decode(d)
        return float(f[0][top:top + p['out_h'], 60:-60].mean())

    try:
        if p['fast_set']:
            import bins
            for r, v in bins.diff('8', '139'):
                s.write(r, v)
        for r, v in p['sensor']:
            s.write(r, v)
        b.restart(); time.sleep(0.3)
        hm = p['soc']['hmax']
        B.wr(HREG, (hm - 1) | (hm - 1) << 16)
        B.wr(VREG, ((p['soc']['vmax'] + 400 - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.2)   # room for every line
        full = (rx0 & 0xFFFF) * 12
        wid = min(p['soc']['rx_width'], full)
        x0 = ((full - wid) // 2) // 12 * 12
        if p.get('new') and p['fmt_w'] < full - 12:   # matrix class narrower than the donor line: the sensor's
            x0 = 0                                     # pixels sit at the left of the receiver line (matrix round 1)
        B.wr(RXREG, (x0 + wid) // 12 | (x0 // 12) << 16)
        ln = lines()
        B.wr(WREG, (w0 & 0xFFFF0000) | (ln - 2)); time.sleep(0.1)
        l7.rewindow(s, 1 if p['bits'] == 14 else 0)
        ok = s.grab(out / 'probe')
        res['checks']['lines'] = dict(measured=ln, planned=p['receiver_lines'], frame=ok,
                                      PASS=bool(ok and abs(ln - p['receiver_lines']) <= 8))
        print('lines', res['checks']['lines'], flush=True)
        if not ok:
            return
        mark14(out / 'probe')
        f0 = R.decode(out / 'probe')[0][0].astype(float)
        if p.get('new'):                               # matrix class: no stock y0 -- the OB/dark rows change with the
            rp = f0[:, 60:-60].mean(1)                 # vertical merge (vbin2: 40 -> 5); take the first lit row
            lit = int(np.argmax(rp > np.median(rp[1:4]) + 25))     # decode() gives 14-bit in 12-bit units
            top = lit + lit % 2                        # Bayer rows start on an even row (stock y0 all even; 12v3 lit at 53)
            res['top'], res['first_lit'] = top, lit
        # Bayer phase on the lit AE frame (round 4b: an even window start mixes colours)
        fb = f0[top + 10:top + p['out_h'] - 10, 60:-60]
        if p.get('hdr'):
            obl = float(f0[4:max(top - 4, 6), 60:-60].mean())
            res['checks']['hdr'] = hdr_check(f0[top:top + p['out_h'], 60:-60], obl)   # replaces Bayer / row phase
            print('hdr', res['checks']['hdr'], flush=True)
        else:
            ph = [float(fb[i::2, j::2].mean()) for i in (0, 1) for j in (0, 1)]
            g = (ph[1] + ph[2]) / 2
            res['checks']['bayer'] = dict(phases=ph, PASS=bool(abs(ph[1] - ph[2]) < 0.02 * g and g > max(ph[0], ph[3]) + 0.05 * g))
            print('bayer', res['checks']['bayer'], flush=True)
            import rowphase                            # even vertical merges: -1/mv rows (§65)
            fr_ = fb[:fb.shape[0] // 2 * 2]
            res['checks']['rowphase'] = rowphase.judge(fr_, p.get('mv') or C_mv(p))
            print('rowphase', res['checks']['rowphase'], flush=True)
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, 0x00), (0x003E, 0x04), (0x003F, 0x00), (0x0040, 0x04)])
        B.P().sh('imager fixed_shutter 1 100')
        vp = p['soc']['vmax']
        # same linearity test as smc_validate (rounds 3b-3d): VMAX at whole lamp periods (a PWM-dimmed room flickers),
        # frame-pair averages, and a measured zero-exposure baseline (image-vs-OB offset) subtracted
        from smc_validate import lin_check, FLICKER_HZ
        s.pair = True

        def sig(d):
            mark14(d)
            f2, _ = R.decode(d)
            return float(np.mean([f[top + 2:top + p['out_h'] - 2, 60:-60].mean() - f[4:max(top - 4, 6), 60:-60].mean() for f in f2]))
        if p.get('hdr'):                               # HDR r1: the VMAX steps left the level at ~1848 every time
            res['checks']['linearity'] = hdr_linearity(s, st, out, top, p, vp, v0, mark14)   # -> SHS steps, per group
            print('linearity', res['checks']['linearity'], flush=True)
        per = 72e6 / hm / FLICKER_HZ
        n0 = max(1, int(np.ceil((vp - 8) / per)))
        vms = [int(np.ceil(n * per)) + 8 for n in (n0 + 2, n0 + 1, n0)] if not p.get('hdr') else []
        pts = []
        for vm in vms:
            B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
            if s.grab(out / f'v{vm}'):
                pts.append((vm, sig(out / f'v{vm}') / (vm - 8)))
        if not p.get('hdr'):
            vb_ = vms[-1]
            B.wr(VREG, ((vb_ - 1) << 16) | (v0 & 0xFFFF))
            shs0 = vb_ // 2 - 2
            B.bus_subs(st, [(0x0005, shs0 & 0xFF), (0x0006, shs0 >> 8), (0x003D, 0x00), (0x003E, 0x04), (0x003F, 0x00), (0x0040, 0x04)])
            time.sleep(0.3)
            b1 = sig(out / 'base') if s.grab(out / 'base') else None
            b2 = sig(out / 'base2') if s.grab(out / 'base2') else None
            res['checks']['linearity'] = lin_check(pts, None if b1 is None or b2 is None else (b1 + b2) / 2)
        for q in [q for d_ in ('v*', 'base*') for q in out.glob(f'{d_}/frame*.raw')]:   # keep the probe frame
            q.unlink()
        s.pair = False
        if not p.get('hdr'):
            print('linearity', res['checks']['linearity'], flush=True)
        B.wr(VREG, ((vp - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
        # burst only times the frames: receive the top ~500 rows (matrix round 2: 9 full-height 12h2 buffers of 19 MB
        # hung the allocator and wedged the shell); the frame period is VMAX's, whatever the receiver keeps
        y0w = w0 >> 16
        B.wr(WREG, (w0 & 0xFFFF0000) | min(ln - 2, y0w + top + 400)); time.sleep(0.1)
        # dt[0] spans the VMAX change from the linearity step (smc_validate drops it too)
        meta, raws = hsburst.burst(s, n=8, enum=1 if p['bits'] == 14 else 0)
        dt = np.diff([e[0] for e in meta['ents']])[1:]; law = vp * hm / 72
        dec = decode14 if p['bits'] == 14 else decode12
        fr = [dec(r, meta['h'], meta['words']).astype(np.float32)[top:top + p['out_h'], 60:-60] for r in raws]
        tn = [float(np.std(fr[i] - fr[i - 1]) / np.sqrt(2)) for i in range(1, len(fr))]
        drops = int((dt > 1.5 * law).sum())
        res['checks']['burst'] = dict(median_us=float(np.median(dt)), law_us=law, drops=drops, drop_at=[int(i) for i in np.nonzero(dt > 1.5 * law)[0]],
                                      dt=[int(x) for x in dt], frame_noise=[min(tn), max(tn)],
                                      PASS=bool(drops == 0 and abs(np.median(dt) - law) < 0.01 * law and min(tn) > 0.3 and max(tn) < 30))
        print('burst', res['checks']['burst'], flush=True)
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0')
            for a, v in ((VREG, v0), (WREG, w0), (HREG, h0), (RXREG, rx0)):
                B.wr(a, v)
        finally:
            b.close()
            res['PASS'] = all(c.get('PASS') for c in res['checks'].values()) and len(res['checks']) == (4 if p.get('hdr') else 5)
            (out / 'result.json').write_text(json.dumps(res, indent=1, default=float))
            if p.get('id'):                                # shared record the planner reads (readout_cfg.validated)
                import readout_cfg
                db = readout_cfg.validated()
                db[p['id']] = dict(PASS=res['PASS'], checks=res['checks'], when=time.strftime('%Y-%m-%d %H:%M'))
                readout_cfg.RESULTS.write_text(json.dumps(db, indent=1, default=float))
            print('RESULT', 'PASS' if res['PASS'] else 'FAIL', flush=True)
