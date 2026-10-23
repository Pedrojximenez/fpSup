#!/usr/bin/env python3
"""SMC verification round (notes/SMC_VERIFY.md): generated 8-table mode -> virtual mode under host 10 -> the
firmware's own mode switch (magnify) -> checks. No direct sensor/SoC writes: everything comes from the tables.

    smc_validate.py OUT [--set core|sweep] [--dark]
Checks: G2 switch + receiver lines == plan; G5 live view (display transfer count grows); burst timing (8 frames);
--dark (lens capped): G4 black -- image black == OB black (+-3 DN), no row/column structure; otherwise G3 exposure
linearity (SHS held, VMAX +150/+400). Results -> captures/smc_validated.json (id -> checks).
"""
import argparse, json, pathlib, struct, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import readout_cfg as C
import smc

R10 = {16: 2, 17: 3, 18: 6, 19: 7, 20: 4, 21: 5, 22: 4, 23: 5}
DB = HERE / 'captures' / 'smc_validated.json'
VREG = 0x30100020
# image-minus-OB black of stock modes per readout class, dark, AE gain (captures/smc_r1/stock*): 8 -> 5.95, 11 -> 6.81, 58 -> 8.03, 12 -> 2.30;
# normal classes measured ~0 (round 1 PASS). 1x1 fast (no stock mode): the fast-class value.
FLICKER_HZ = 119.94          # mains 59.97 Hz here (IMX410_RULES §55)
BLACK_REF_FAST = 7.4        # 1x1 fast AD (12fast/12fastW): no stock mode; the fast-class value (round 1 used it)
BLACK_REF = {19: 7.4, 21: 6.0, 23: 2.3, 17: 0.0, 16: 0.0, 18: 0.0, 20: 0.0, 22: 0.0}

# Round 4 (SMC_VERIFY): image-minus-OB black of the donor-class stock mode at FIXED analog gain codes (0x400, 3900),
# measured the same way (captures/smc_r4_stock). AE-gain comparisons were unreliable (AE picks different gains per mode).
# The fast classes grow ~+2 DN at code 3900 from short (540 rows) to full height (dark shading), hence the wider tolerance.
STOCK_BLACK = {'14': (0.7, -1.3), '12': (1.9, 1.8), '12fast': (3.9, 5.2), '12fastW': (3.9, 5.2), '2x2': (6.1, 1.2),
               '2x2fast': (3.5, 7.3), '3x3': (1.9, 0.7), '3x3fast': (3.9, 5.2), '3x6': (1.1, 1.2), '3x6fast': (1.9, 2.2)}
BLACK_TOL = (2.0, 3.0)


MATRIX_BLACK_BOUND = (4.0, 10.0)   # matrix classes (§67) have no stock mode: until their own reference exists, bound the
                                   # offset at the widest stock class values (2x2 6.1 at 0x400, 2x2fast 7.3 at 3900) + tol


def black_judge(key, gains):
    if key not in STOCK_BLACK:
        got = (gains.get(1024, gains.get('1024')), gains.get(3900, gains.get('3900')))
        if None in got:
            return dict(PASS=False, why='missing gain frame')
        return dict(g1024=got[0], g3900=got[1], ref='bound', bound=list(MATRIX_BLACK_BOUND),
                    PASS=all(abs(g) <= b for g, b in zip(got, MATRIX_BLACK_BOUND)))
    ref = STOCK_BLACK[key]
    got = (gains.get(1024, gains.get('1024')), gains.get(3900, gains.get('3900')))
    if None in got:
        return dict(PASS=False, why='missing gain frame')
    dev = [g - r for g, r in zip(got, ref)]
    return dict(g1024=got[0], g3900=got[1], ref=list(ref), dev=dev, PASS=all(abs(d) <= t for d, t in zip(dev, BLACK_TOL)))


def rows_ok(img, ob):
    """every image row must be a real row: no saturated / far-off rows (round 4: tall 2x2/3x3 windows ran past the
    readable area and the last ~50 rows read 4095, invisible to the receiver line count)"""
    rp = img.mean(1)
    bad = int((np.abs(rp - ob) > 60).sum())
    return dict(bad_rows=bad, PASS=bad == 0)


CORE = [('12', (6060, 3408), (3840, 2160)), ('12', (3840, 2160), (3840, 2160)), ('14', (4152, 2160), (3840, 2160)),
        ('12fast', (4176, 2016), (4160, 2016)), ('12fastW', (6060, 3408), (3840, 2160)), ('2x2', (6060, 3408), (1920, 1080)),
        ('2x2fast', (3840, 2160), (1920, 1080)), ('3x3', (6060, 3408), (1920, 1080)), ('3x3fast', (5760, 3240), (1920, 1080)),
        ('3x6', (6060, 4040), (1008, 662)), ('3x6fast', (6060, 4040), (1008, 662))]


def lin_check(pts, base=None):
    """with a measured zero-exposure baseline (round 3b): (signal - base)/(VMAX-8) must be constant within 6 % or 1 DN;
    without one, the old line fit (kept for re-checking stored data)."""
    if base is not None and len(pts) == 3:
        k = [(p[1] * (p[0] - 8) - base) / (p[0] - 8) for p in pts]
        sig = [p[1] * (p[0] - 8) - base for p in pts]
        dev = max(k) - min(k)
        ok = min(k) > 0 and (dev / max(k) < 0.06 or dev * (pts[0][0] - 8) < 1.0)
        return dict(points=pts, base=base, k=k, signal=sig, PASS=bool(ok))
    return lin_fit(pts)


def lin_fit(pts):
    """signal = a + b*(VMAX-8): a constant image-vs-OB black offset (fast/2x2 classes, amplified by the gain) makes
    signal/(VMAX-8) drift with VMAX although the exposure is linear (round 3). Fit a line through the 3 points
    (signal = ratio*(VMAX-8)) and require the residual < 2 % of the signal span and a positive slope."""
    if len(pts) != 3:
        return dict(points=pts, PASS=False)
    x = np.array([p[0] - 8 for p in pts], float); y = np.array([p[1] * (p[0] - 8) for p in pts], float)
    b, a = np.polyfit(x, y, 1)
    resid = float(np.max(np.abs(a + b * x - y)))
    span = float(y.max() - y.min()) or 1.0
    return dict(points=pts, slope=float(b), offset=float(a), resid_rel=resid / span, resid=resid,
                PASS=bool(b > 0 and (resid / span < 0.02 or resid < 1.0)))   # < 1 DN: low-signal configs (short frames, dim room)


def sweep_set():
    """many geometries per readout: crop heights / widths spread over the sensor"""
    out = []
    for key in ('12', '14', '12fast', '2x2', '2x2fast', '3x3', '3x3fast'):
        r = C.BY_KEY[key]
        m = r['mh']
        for ch in (4000, 3240, 2160, 1600, 1080, 720, 480, 240):
            for cw in (6048, 4800, 3840, 2400, 1920):
                if key == '12fast' and cw > 4176:
                    continue
                ow = (cw // m) // 16 * 16
                oh = (ch // r['mv']) // 2 * 2
                if ow < 256 or oh < 120:
                    continue
                try:
                    C.plan(key, cw, ch, ow, oh)
                except ValueError:
                    continue
                out.append((key, (cw, ch), (ow, oh)))
    return out


def fps_set():
    """common frame rates (VMAX above the minimum, the sweep ran everything at max fps): every readout x 3 crop heights
    x 23.976/29.97/59.94/119.88 where the plan allows it"""
    out = []
    for key in ('12', '14', '12fast', '12fastW', '2x2', '2x2fast', '3x3', '3x3fast', '3x6', '3x6fast'):
        r = C.BY_KEY[key]
        cw = 4176 if key == '12fast' else 6048
        hs = (4040,) if r['centre'] is None else (3408, 2160, 1080)
        for ch in hs:
            ow = (cw // r['mh']) // 16 * 16
            oh = (ch // r['mv']) // 2 * 2
            for fps in (23.976, 29.97, 59.94, 119.88):
                try:
                    C.plan(key, cw, ch, ow, oh, fps)
                except ValueError:
                    continue
                out.append((key, (cw, ch), (ow, oh), fps))
    return out


def matrix_set():
    """matrix classes (readout_cfg new=True, §67): full height at full width + two receiver crops, two vertical windows
    (3408 / 2160 sensor rows), all at max fps; full frame at 23.976 / 29.97 / 59.94 where the plan allows it"""
    out = []
    for r in C.READOUTS:
        if not r.get('new'):
            continue
        w = max(r['fmt'])
        cw_full = w * r['mh'] if r['mh'] > 1 else w
        for frac in (1.0, 0.75, 0.5):
            cw = int(cw_full * frac) // (12 * r['mh']) * (12 * r['mh'])
            ow = (cw // r['mh']) // 16 * 16
            oh = int(4040 / r['mv']) // 2 * 2
            out.append((r['key'], (cw, 4040), (ow, oh), None))
        for ch in (3408, 2160):                     # vertical windows (§64 rule; not yet measured for these classes)
            ow = (cw_full // r['mh']) // 16 * 16
            try:
                C.plan(r['key'], cw_full, ch, ow, int(ch / r['mv']) // 2 * 2)
            except ValueError:
                continue
            out.append((r['key'], (cw_full, ch), (ow, int(ch / r['mv']) // 2 * 2), None))
        for fps in (23.976, 29.97, 59.94):
            ow = (cw_full // r['mh']) // 16 * 16
            try:
                C.plan(r['key'], cw_full, 4040, ow, int(4040 / r['mv']) // 2 * 2, fps)
            except ValueError:
                continue
            out.append((r['key'], (cw_full, 4040), (ow, int(4040 / r['mv']) // 2 * 2), fps))
    return out


def run_one(key, crop, outsz, base_out, dark, fps=None):
    import bufa_probe as B, resweep as R, vmode, hsburst
    p = C.plan(key, *crop, *outsz, fps)
    a, rows, how = smc.create(p)
    rows = {t: bytes(v) for t, v in rows.items()}
    rows['R10'] = struct.pack('<II', R10[a['cls']], 10)
    d = base_out / p['id'].replace(':', '_').replace('>', '_')
    d.mkdir(parents=True, exist_ok=True)
    res = dict(id=p['id'], attrs=a, checks={})
    vmode.KEEP_WINDOW = True
    b = R.Base(d, 'V2' if p['bits'] == 14 else 'V1', rows=rows)
    s = b.s; s.pair = True
    import fastsweep as F

    def trip(timeout=1.0):                  # >400 fps: the DMA rewrites the tail before a verified write reads back
        for i in range(4):
            B.wr(s.tail + 4 * i, F.SENT, verify=False)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if B.P().mem_get(s.tail)[0] != F.SENT:
                return True
        return False
    s._trip = trip
    st = B.bus_state()
    top = a['y0']
    try:
        ln = min(B.P().mem_get(0x301005D8)[0] for _ in range(3))
        res['checks']['switch_lines'] = dict(measured=ln, planned=p['receiver_lines'], PASS=abs(ln - p['receiver_lines']) <= 8)
        def counts():
            for line in B.P().sh('imager mode_now').splitlines():
                if line.startswith('frame_count'):
                    return [int(x.split(':')[1]) for x in line.split(',')]
        c0 = counts(); time.sleep(1.0); c1 = counts()
        res['checks']['live_view'] = dict(frames=c1[0] - c0[0], transfers=c1[1] - c0[1], PASS=(c1[1] - c0[1]) > 5)
        ok = s.grab(d / 'f')
        res['checks']['frame'] = dict(PASS=bool(ok))   # smc_m1: 10 configs never completed a frame and still "passed"
        if ok and p['bits'] == 14:
            m = json.loads((d / 'f' / 'frame.json').read_text()); m['bits'] = 14; (d / 'f' / 'frame.json').write_text(json.dumps(m))
        if ok:
            fr, m = R.decode(d / 'f')
            img = fr[0][top + 2:top + p['out_h'] - 2, 16:-16]; ob = fr[0][4:max(top - 4, 6), 16:-16]
            if not dark:                            # matrix classes: y0 was measured with 0018 (dark rows) on, which the
                rs_ = fr[0][:, 16:-16].std(1)      # REG table cannot carry. Texture, not level (h3 had a dark scene
                thr = 2 * float(np.median(rs_[1:6])) + 3.0   # top); and the first COMPLETE row pair: in f12v2 row 18 was
                lit = next((r for r in range(2, len(rs_) - 1) if rs_[r] > thr and rs_[r + 1] > thr), -1)  # lit, 19 dark
                lit += lit % 2
                # a dark scene top looks exactly like the dark rows (f12v3 windows: rows 20-33 at black, std 2), so a
                # later first textured pair is only a warning; an image starting BEFORE y0 (rows lost) is a failure
                # 12v3 / 12h2v3 (normal AD): rows 18-19 are a complete pair in some runs and not in others (same
                # config) -- y0 = 20 skips that unstable pair, so first_pair = y0 - 2 is expected, not a failure
                res['checks']['top'] = dict(first_pair=lit, y0=top, warn=bool(lit > top),
                                            PASS=(lit >= top - 2) if p.get('new') else True)
            if dark:
                rowp = img.mean(1); colp = img.mean(0)
                # image - OB black depends on the AD class (stock fast modes: +6..8 DN, others ~0..2; SMC_VERIFY round 1):
                # compare with the stock reference of the same class, not with zero
                ref = BLACK_REF_FAST if p['fast_set'] else BLACK_REF.get(a['cls'], 0.0)   # 1x1 fast is class 17 + fast AD (round 4)
                diff = float(img.mean() - ob.mean())
                res['checks']['black'] = dict(image=float(img.mean()), ob=float(ob.mean()), diff=diff, ref=ref, row_std=float(rowp.std()), col_std=float(colp.std()),
                                              even_odd=float(rowp[0::2].mean() - rowp[1::2].mean()),
                                              PASS=abs(diff - ref) < 3 and rowp.std() < 1.5 and abs(rowp[0::2].mean() - rowp[1::2].mean()) < 1.5)
                # round 4: image-vs-OB offset at forced analog gain codes (light rounds saw ~98 / ~138 DN at high gain);
                # recorded only -- judged against stock modes of the same class measured the same way (smc_stockblack.py)
                B.bus_on(st)
                hg = {}
                for code in (0x400, 3900):
                    B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, code & 0xFF), (0x003E, code >> 8), (0x003F, code & 0xFF), (0x0040, code >> 8)])
                    time.sleep(0.4)
                    if s.grab(d / f'g{code}'):
                        if p['bits'] == 14:
                            m2 = json.loads((d / f'g{code}' / 'frame.json').read_text()); m2['bits'] = 14
                            (d / f'g{code}' / 'frame.json').write_text(json.dumps(m2))
                        f2, _ = R.decode(d / f'g{code}')
                        hg[code] = float(np.mean([f[top + 2:top + p['out_h'] - 2, 16:-16].mean() - f[4:max(top - 4, 6), 16:-16].mean() for f in f2]))
                B.bus_subs(st, [])
                res['gain_offsets'] = hg
                res['checks']['black_gain'] = black_judge(key, hg)
                res['checks']['rows'] = rows_ok(img, float(ob.mean()))
                # the AE-gain check stays for structure only (row/column/even-odd); its level is judged by black_gain
                res['checks']['black']['PASS'] = rowp.std() < 1.5 and abs(rowp[0::2].mean() - rowp[1::2].mean()) < 1.5
            else:
                B.bus_on(st)
                B.P().sh('imager fixed_shutter 1 100')
                v0 = B.P().mem_get(VREG)[0]; vp = (v0 >> 16) + 1

                clipmask = {}

                def sig(dd):
                    if p['bits'] == 14:
                        m2 = json.loads((dd / 'frame.json').read_text()); m2['bits'] = 14; (dd / 'frame.json').write_text(json.dumps(m2))
                    f2, _ = R.decode(dd)                 # both frames of the pair (round 3d: one frame was too noisy at ~10 DN)
                    out_ = []
                    for f in f2:
                        img_ = f[top + 2:top + p['out_h'] - 2, 16:-16]
                        if 'mask' not in clipmask:       # smc_m1 h3: highlights clip at the longest exposure even at the
                            clipmask['mask'] = img_ < 1500   # lowest gain code -> one fixed mask from the first (longest) frame;
                            # 1500 not 3600: a merged h3 value can be far below 4095 while one of its 3 pixels clipped
                        mk = clipmask['mask'][:img_.shape[0], :img_.shape[1]]
                        out_.append(img_[mk[:img_.shape[0]]].mean() - f[4:max(top - 4, 6), 16:-16].mean())
                    return float(np.mean(out_))
                # adaptive gain (round 3: a dimmed room left ~7 DN of signal and the 6 % test failed on noise):
                # raise the analog gain code until the full-frame signal is >= ~120 DN, or the code tops out
                code = 0x400
                for _ in range(4):
                    B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, code & 0xFF), (0x003E, code >> 8), (0x003F, code & 0xFF), (0x0040, code >> 8)])
                    time.sleep(0.3)
                    if not s.grab(d / 'gainprobe'):
                        break
                    sg = sig(d / 'gainprobe')
                    if sg >= 120 or code >= 3900:
                        break
                    g = 4095 / (4095 - code) * min(8.0, 160 / max(sg, 2))
                    code = min(3900, int(4095 - 4095 / g))
                res['gain_code'] = code
                clipmask.clear()                         # the mask comes from the first VMAX point (the longest exposure)
                pts = []
                # VMAX at exposures of n, n+1, n+2 lamp periods (120 Hz): a dimmed (PWM) room flickers and short
                # exposures then wander by ~1 DN (round 3c); whole periods average the flicker out (IMX410_RULES §55)
                hw = B.P().mem_get(0x30100004)[0]; hm = min(hw & 0x3FFF, (hw >> 16) & 0x3FFF) + 1
                per = 72e6 / hm / FLICKER_HZ
                n0 = max(1, int(np.ceil((vp - 8) / per)))
                vms = [int(np.ceil(n * per)) + 8 for n in (n0 + 2, n0 + 1, n0)]
                for vm in vms:
                    B.wr(VREG, ((vm - 1) << 16) | (v0 & 0xFFFF)); time.sleep(0.3)
                    if s.grab(d / f'v{vm}'):
                        pts.append((vm, sig(d / f'v{vm}') / (vm - 8)))
                # zero-exposure baseline: SHS just below VMAX/2 (exposure ~4 lines) -> the image-vs-OB offset itself
                vb_ = vms[-1]
                B.wr(VREG, ((vb_ - 1) << 16) | (v0 & 0xFFFF))
                shs0 = vb_ // 2 - 2
                B.bus_subs(st, [(0x0005, shs0 & 0xFF), (0x0006, shs0 >> 8), (0x003D, code & 0xFF), (0x003E, code >> 8), (0x003F, code & 0xFF), (0x0040, code >> 8)])
                time.sleep(0.3)
                b1 = sig(d / 'base') if s.grab(d / 'base') else None
                b2 = sig(d / 'base2') if s.grab(d / 'base2') else None
                base = None if b1 is None or b2 is None else (b1 + b2) / 2
                res['checks']['linearity'] = lin_check(pts, base)
                # Bayer phase (round 4: an even window start mixed the colours or swapped the row phase and every other
                # check still passed): every stock mode reads [R/B, G, G, B/R] -- the two greens equal and the brightest
                fb, _ = R.decode(d / f'v{vms[0]}')
                fb = fb[0].astype(float)[top + 10:top + p['out_h'] - 10, 32:-32]
                ph = [float(fb[i::2, j::2].mean()) for i in (0, 1) for j in (0, 1)]
                g = (ph[1] + ph[2]) / 2
                res['checks']['bayer'] = dict(phases=ph, PASS=abs(ph[1] - ph[2]) < 0.02 * g and g > max(ph[0], ph[3]) + 0.05 * g)
                # row phase (Julien Acquaviva, sigma-fp-raw: OG3K/M98 G2 rows 0.5 px off): even vertical bins put the
                # second row of each pair 1 sensor row off -- must equal the stock value for the class (§65)
                import rowphase
                res['checks']['rowphase'] = rowphase.judge(fb, C.BY_KEY[key]['mv'])
                B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0'); B.wr(VREG, v0)
        meta, raws = hsburst.burst(s, n=8, enum=1 if p['bits'] == 14 else 0)
        dt = np.diff([e[0] for e in meta['ents']])[1:]
        law = np.median(dt)
        res['checks']['burst'] = dict(median_us=float(law), drops=int((dt > 1.5 * law).sum()), PASS=int((dt > 1.5 * law).sum()) == 0)
    finally:
        try:
            B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()
    res['PASS'] = all(c['PASS'] for c in res['checks'].values())
    (d / 'result.json').write_text(json.dumps(res, indent=1, default=float))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--set', default='core'); ap.add_argument('--dark', action='store_true')
    ap.add_argument('--only', default='')
    ap.add_argument('--fresh', action='store_true'); ap.add_argument('--force', action='store_true')   # poff before every config (matrix r2: wedges at configs 3 and 7)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cfgs = {'core': CORE, 'sweep': sweep_set, 'fps': fps_set, 'matrix': matrix_set,
            'matrixfull': lambda: [c for c in matrix_set() if c[1][1] == 4040 and c[3] is None and c[2][0] >= (max(C.BY_KEY[c[0]]['fmt']) // 16 * 16) - 16]}[a.set]
    cfgs = cfgs() if callable(cfgs) else cfgs
    cfgs = [c if len(c) == 4 else (*c, None) for c in cfgs]
    if a.only:
        cfgs = [c for c in cfgs if c[0] in a.only.split(',')]
    db = json.loads(DB.read_text()) if DB.exists() else {}
    tag = 'dark' if a.dark else 'light'
    print(f'{len(cfgs)} configs ({tag})', flush=True)

    def focus():                                    # user rule: AF after every (re)boot and at the start of a run
        subprocess.run([sys.executable, 'bufa_probe.py', 'focus', '--hold', '1.0'], cwd=HERE, capture_output=True, timeout=90)
    focus()
    for key, crop, outsz, fps in cfgs:
        if (out / 'STOP').exists():
            print('STOP file: stopping cleanly after the last config', flush=True); break
        pid = C.plan(key, *crop, *outsz, fps)['id']
        if db.get(pid, {}).get(tag, {}).get('PASS') and not a.force:
            continue
        chk = subprocess.run([sys.executable, '-c', 'import vmode, bufa_probe as B; vmode.check_stock(); print("HEAP", B.P().sh("memmgr heapmem").strip())'],
                             cwd=HERE, capture_output=True, text=True, timeout=120)
        hl = next((l for l in chk.stdout.splitlines() if l.startswith('HEAP')), '')
        if hl:
            print('  ' + hl, flush=True)                # round 5: the shell died after 55-90 configs twice -- watch for a leak
        if chk.returncode or a.fresh:
            print('  not stock -> fastreboot' if chk.returncode else '  fresh boot', flush=True)
            rb = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE,
                                capture_output=True, timeout=300)
            if rb.returncode:                       # round 4: a failed restart used to fall through and fail every later config
                print('camera did not come back -- stopping (needs a manual reboot)', flush=True); break
            focus()
        try:                                           # sensor temperature before every config (user 10-23: runs hot)
            import thermal
            _t = thermal.wait_cool(); thermal.log(out / 'thermal.jsonl', pid)
            print(f"  temp {_t.get('C')}", flush=True)
        except Exception as _e:                        # noqa: BLE001
            print('  temp read failed', _e, flush=True)
        r = subprocess.run([sys.executable, '-u', '-c',
                            f'import json,pathlib,smc_validate as V; print("RES", json.dumps(V.run_one({key!r}, {crop!r}, {outsz!r}, pathlib.Path({str(out)!r}), {a.dark!r}, {fps!r}), default=float))'],
                           cwd=HERE, capture_output=True, text=True, timeout=600)
        line = next((l for l in r.stdout.splitlines() if l.startswith('RES ')), None)
        if line:
            res = json.loads(line[4:])
            db.setdefault(pid, {})[tag] = res
            fails = [k for k, c in res['checks'].items() if not c['PASS']]
            if res['PASS']:                         # disk: ~70 MB of raw frames per config; keep them only for failures
                for f in (out / pid.replace(':', '_').replace('>', '_')).rglob('frame*.raw'):
                    f.unlink()
            print(f"{'PASS' if res['PASS'] else 'FAIL'} {pid}  " + ' '.join(f"{k}={'ok' if c['PASS'] else json.dumps({x: y for x, y in c.items() if x not in ('PASS', 'points')}, default=float)[:120]}" for k, c in res['checks'].items()), flush=True)
            if res.get('gain_offsets'):
                print('   gain offsets', {k: round(v, 1) for k, v in res['gain_offsets'].items()}, flush=True)
        else:
            (out / f"{pid.replace(':', '_').replace('>', '_')}.stderr").write_text(r.stdout + '\n----\n' + r.stderr)   # full trace for the post-mortem
            db.setdefault(pid, {})[tag] = dict(PASS=False, error=(r.stderr.strip().splitlines() or ['?'])[-1][:200])
            print(f'ERROR {pid}: {db[pid][tag]["error"]}', flush=True)
        DB.write_text(json.dumps(db, indent=1, default=float))


if __name__ == '__main__':
    main()
