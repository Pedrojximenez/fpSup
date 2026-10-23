"""Explicit per-field rules for the IMX410 per-mode tables (META / R14 / R28 / R38 / R68).

Each rule is a formula over generator-level attributes (geometry, binning, bits, fps, purpose) plus three pieces of
fixed camera data that are NOT per-mode tables:
  DEFECT_DIR  factory defect-table directory (flash; one table per calibrated output geometry)   -> R68 +0x04
  V33_IDS     mode ids hard-coded in v33 0xC0324FD8 (cmp #0x66/#0x6C/#0x7C/#0x98)               -> R38 +0x0A/C, R68 +0x08/+0x0C
  REP_ADJ     SensorAdjustment parameters of the 11 calibration ("representative") modes         -> R68 +0x30..+0x64
Values a formula cannot give are listed in HAND with a reason; they are counted separately, never as 'exact'.
Notes/evidence: notes/MODE_TABLE_RULES.md.
"""

# ---------------------------------------------------------------- fixed camera data
# (hbin, vbin, width, height) -> defect table id. The id is the mode number of the mode that was calibrated for it.
DEFECT_DIR = {(1, 1, 6064, 4042): 97, (1, 1, 4176, 2174): 6, (1, 1, 6064, 3412): 7, (1, 1, 3968, 2640): 130,
              (2, 2, 1984, 1320): 131, (2, 2, 2088, 1174): 88, (2, 2, 3032, 1708): 27, (2, 2, 3032, 2012): 98,
              (3, 3, 2016, 1136): 134, (3, 3, 2016, 1344): 139, (3, 6, 2016, 672): 140}
DEFECT_FALLBACK = {(1, 1): 97, (2, 2): 98, (3, 3): 139, (3, 6): 140}   # geometry without its own table
V33_IDS = {102, 108, 124, 152}
ZOOM_IDS = {10, 3}        # zoom table 0xC0B5F7E0 (descriptor +0x128, 2 rows): FUN_c030e2a0 takes FUN_c030fd68 for these
# R68 +0x38 of each calibration mode (SensorAdjustment only: getter c032cbb0 -> 'imager view_wdd'); 97 is the
# long-exposure (30 s) calibration and differs in +0x30/+0x34/+0x58/+0x5C too.
REP_ADJ38 = {97: 14000, 6: 4000, 7: 3000, 130: 4000, 131: 1000, 88: 2000, 27: 2000, 98: 2000, 134: 1000, 139: 2000,
             140: 1000}

# R28 grid: 16x16 cells covering ~95 % of the frame, cell sizes even. Constants fitted (see notes for the intervals).
K_EVAL_W, K_EVAL_H, K_AF_W, K_AF_H = 0.949, 0.9541, 0.949, 0.9437


def derive(a, mode):
    """attributes the rules use, all computable for a new mode"""
    d = dict(a)
    hb, vb, W, H = a['hbin'], a['vbin'], a['width'], a['height']
    r = (W * hb) / (H * vb)
    d['hd'] = int(1.7 < r < 2.0)                         # 16:9-class output (META +0x54 = 1)
    d['fullw'] = int(W * hb >= 6048)                     # whole sensor width
    d['v33'] = int(mode in V33_IDS)
    d['inzoom'] = int(mode in ZOOM_IDS)
    key = (hb, vb, W, H)
    d['dtab'] = DEFECT_DIR.get(key, DEFECT_FALLBACK.get((hb, vb), 97))   # matrix binnings: no own table -> cut from 97 (G7)
    d['dtab_own'] = int(key in DEFECT_DIR)
    d['rep'] = int(DEFECT_DIR.get(key) == mode)
    d['full1x1'] = int(hb == 1 and vb == 1 and W == 6064 and H == 4042)
    return d


def _even_round(x):
    return 2 * int(x / 2 + 0.5)


def _even_floor(x):
    return 2 * int(x // 2)


def _r28(a):
    W, H = a['width'], a['height']
    cw = _even_round(W * K_EVAL_W / 16)
    ch = _even_floor(H * K_EVAL_H / 16)
    aw = _even_round(W / 2 * K_AF_W / 16)
    ah = _even_round(H / 2 * K_AF_H / 16)
    return dict(cw=cw, ch=ch, x0=(W - 16 * cw) // 2, y0=_even_floor((H - 16 * ch) / 2),
                aw=aw, ah=ah, ax0=_even_floor((W // 2 - 16 * aw) / 2), ay0=_even_floor((H // 2 - 16 * ah) / 2))


def _r68_flag(a):
    # 1 = the defect map is cut out of table +0x0C with window +0x10.. (FUN_c0310740 / FUN_c0310410)
    return int(a['v33'] or (a['acq'] and not a['full1x1']) or (not a['dtab_own'] and not a['inzoom']))


def _r68_crop(a):
    if not _r68_flag(a):
        return (0, 0, 0, 0)
    hb, vb = a['hbin'], a['vbin']
    if a['v33']:                                         # cut from table 7 (6064x3412, origin x=8 y=354)
        return (a['x0'] - 8, a['y0'] - 354, a['width'], a['height'])
    x = hb * a['x0'] - 8                                 # cut from table 97 (origin x=8 y=40, 1x1 coordinates)
    if vb == 1:
        y = a['y0'] - 40 + (a['wstart'] - 59 if a['win'] else 0)   # 59 = zoom-table row base (+0x1C)
    else:
        y = vb * a['y0'] - 32
    h = 4042 if (a['fullw'] and vb > 1) else vb * a['height']     # full-width binned readout = whole table
    return (x, y, hb * a['width'], h)


def _r38_vshift(a):
    # receiver-row DCLP window = [y0-2, y1+2] shifted down by d rows
    if a['v33']:
        return 4
    return 2 if (a['hd'] and a['vbin'] > 1) else 0


def _r38_ob(a, group):
    # vertical OB band [s, s + 2**n) used for the clamp average, n = shift nibble
    vb = a['vbin']
    s = {1: 24, 2: 10, 3: 8, 6: 6}[vb]
    n = {1: 3, 2: 3, 3: 2, 6: 1}[vb]
    if group == 1 and vb == 1 and a['acq']:
        s = 30
    return s, s + (1 << n), n


def _lo(v):
    return v & 0xFFFF


def _hi(v):
    return v >> 16


EXACT = {
    # ---- TIM tg_mode_param and the REG sensor window: these ARE the generator inputs (identity rules)
    ('TIM', 0x04): lambda a: a['hmax'], ('TIM', 0x06): lambda a: a['tail'], ('TIM', 0x08): lambda a: a['vmax'],
    ('TIM', 0x0A): lambda a: a['x0'], ('TIM', 0x0C): lambda a: a['x1'],
    ('TIM', 0x0E): lambda a: a['y0'], ('TIM', 0x10): lambda a: a['y1'],
    ('REG', 0x0003): lambda a: a['win'],
    ('REG', 0x0022): lambda a: a['wstart'] & 0xFF, ('REG', 0x0023): lambda a: a['wstart'] >> 8,
    ('REG', 0x0024): lambda a: a['wh'] & 0xFF, ('REG', 0x0025): lambda a: a['wh'] >> 8,
    # ---- META raw_info_param
    ('META', 0x04): lambda a: a['width'], ('META', 0x08): lambda a: a['height'],
    ('META', 0x14): lambda a: a['width'], ('META', 0x18): lambda a: a['height'],
    ('META', 0x24): lambda a: a['width'], ('META', 0x28): lambda a: a['height'],
    ('META', 0x2C): lambda a: 6000 // a['hbin'] if a['acq'] and a['fullw'] else 0,
    ('META', 0x30): lambda a: 4000 // a['vbin'] if a['acq'] and a['fullw'] else 0,
    ('META', 0x34): lambda a: (a['width'] - 6000 // a['hbin']) // 2 if a['acq'] and a['fullw'] else 0,
    ('META', 0x38): lambda a: (a['height'] - 4000 // a['vbin']) // 2 if a['acq'] and a['fullw'] else 0,
    ('META', 0x3C): lambda a: {12: 0, 14: 1}[a['bits']],
    ('META', 0x40): lambda a: a['fpsn'],
    ('META', 0x44): lambda a: a['hbin'], ('META', 0x48): lambda a: a['vadd'],
    ('META', 0x4C): lambda a: a['hbin'], ('META', 0x50): lambda a: a['vbin'],
    ('META', 0x54): lambda a: 1 if a['hd'] else 2,
    ('META', 0x58): lambda a: 0 if a['fullw'] else 1,
    ('META', 0x5C): lambda a: a['f5c'],
    ('META', 0x60): lambda a: a['cls'],
    # ---- R14 cmos_ctrl_info_tbl: +0x0C shutter margins (byte) | +0x0D line unit 1
    ('R14', 0x0C): lambda a: 0x100 | {1: 0x22, 2: 0x33, 3: 0x22, 6: 0x11}[a['vbin']],   # stock pairs (1,1)(2,2)(3,3)(3,6); vbin decides [I]
    # ---- R28 eval_mode_param (AE/AWB grid 0x30058010.., AF grid 0x30050010..)
    ('R28', 0x04): lambda a: _r28(a)['x0'], ('R28', 0x06): lambda a: _r28(a)['y0'],
    ('R28', 0x08): lambda a: _r28(a)['cw'], ('R28', 0x0A): lambda a: _r28(a)['ch'],
    ('R28', 0x0E): lambda a: _r28(a)['ax0'], ('R28', 0x10): lambda a: _r28(a)['ay0'],
    ('R28', 0x12): lambda a: _r28(a)['aw'], ('R28', 0x14): lambda a: _r28(a)['ah'],
    # ---- R38 dclp_mode_param (0x300F02xx); horizontal in 12-px receiver words, vertical in receiver rows
    ('R38', 0x04): lambda a: 8 if a['hd'] else 0,
    ('R38', 0x06): lambda a: max(0, a['x0'] // 12 - 1),
    ('R38', 0x08): lambda a: a['x0'] // 12 + -(-a['width'] // 12) + 1,
    ('R38', 0x0A): lambda a: a['y0'] - 2 + _r38_vshift(a),
    ('R38', 0x0C): lambda a: a['y1'] + 2 + _r38_vshift(a),
    ('R38', 0x10): lambda a: max(0, a['x0'] // 12 - 1) + 4,
    ('R38', 0x12): lambda a: a['x1'] // 12 - 3,
    ('R38', 0x14): lambda a: _r38_ob(a, 1)[0], ('R38', 0x16): lambda a: _r38_ob(a, 1)[1],
    ('R38', 0x18): lambda a: _r38_ob(a, 1)[2] | (0xC000 if a['hd'] else 0),
    ('R38', 0x1A): lambda a: max(0, a['x0'] // 12 - 1) + 4,
    ('R38', 0x1C): lambda a: a['x1'] // 12 - 3,
    ('R38', 0x1E): lambda a: _r38_ob(a, 2)[0], ('R38', 0x20): lambda a: _r38_ob(a, 2)[1],
    ('R38', 0x22): lambda a: _r38_ob(a, 2)[2],
    # ---- R68 cmos_defect_mode_adj_info
    ('R68', 0x04): lambda a: a['dtab'],
    ('R68', 0x08): _r68_flag,
    ('R68', 0x0C): lambda a: 7 if a['v33'] else 97,
    ('R68', 0x10): lambda a: _r68_crop(a)[0], ('R68', 0x14): lambda a: _r68_crop(a)[1],
    ('R68', 0x18): lambda a: _r68_crop(a)[2], ('R68', 0x1C): lambda a: _r68_crop(a)[3],
    ('R68', 0x20): lambda a: {1: 0, 2: 7, 3: 2}[a['hbin']],
    ('R68', 0x24): lambda a: {1: 0, 2: 7, 3: 1, 6: 3}[a['vbin']],
    ('R68', 0x2C): lambda a: a.get('dyo') or (2 if a['vbin'] == 2 and a['acq'] else 0),
    ('R68', 0x30): lambda a: (_lo(30000000) if a['mode'] == 97 else _lo(1000000)) if a['rep'] else 0,
    ('R68', 0x32): lambda a: (_hi(30000000) if a['mode'] == 97 else _hi(1000000)) if a['rep'] else 0,
    ('R68', 0x34): lambda a: (117 if a['mode'] == 97 else 3200) if a['rep'] else 0,
    ('R68', 0x38): lambda a: REP_ADJ38[a['mode']] if a['rep'] else 0,
    ('R68', 0x3C): lambda a: 1 if a['rep'] else 0,
    ('R68', 0x40): lambda a: 100 if a['rep'] else 0,
    ('R68', 0x44): lambda a: 50 if a['rep'] else 0,
    ('R68', 0x48): lambda a: a['width'] - 16 if a['rep'] else 0,
    ('R68', 0x4C): lambda a: a['height'] - 16 if a['rep'] else 0,
    ('R68', 0x50): lambda a: 8 if a['rep'] else 0,
    ('R68', 0x54): lambda a: 8 if a['rep'] else 0,
    ('R68', 0x58): lambda a: (_lo(6000000) if a['mode'] == 97 else _lo(500000)) if a['rep'] else 0,
    ('R68', 0x5A): lambda a: (_hi(6000000) if a['mode'] == 97 else _hi(500000)) if a['rep'] else 0,
    ('R68', 0x5C): lambda a: (585 if a['mode'] == 97 else 3200) if a['rep'] else 0,
    ('R68', 0x60): lambda a: 450 if a['rep'] else 0,
    ('R68', 0x64): lambda a: 3 if a['rep'] else 0,
}

# fields whose value depends on the defect-calibration identity (rep / mode 97) rather than on geometry: these
# are factory SensorAdjustment parameters, not mode design -- reported as 'adj' instead of 'exact'
ADJ_FIELDS = {('R68', o) for o in range(0x30, 0x66, 2)}

# per-mode values no formula gives: {(table, off): {mode: (value, live?, reason)}}
# live = the value reaches a register/consumer in live view or video for that mode (else only stills / unread)
HAND = {
    ('META', 0x24): {100: (3032, 0, 'typo (3rd width copy); META +0x0C..+0x30 have no reader')},
    ('META', 0x34): {10: (32, 1, 'zoom LV base: 1x1 full-frame effective offset, read by AF/zoom coords c031b3a0 path')},
    ('META', 0x38): {10: (21, 1, 'same as +0x34')},
    ('META', 0x58): {134: (1, 1, 'crop flag set although 3x3 reads full width; read by c0312468 (AE/AF tuning)')},
    ('R38', 0x08): {m: (v, 1, 'newest 2x2 modes: DCLP word end +1 (= x1//12 + 2)') for m, v in ((218, 255), (219, 215), (220, 255), (221, 215))},
    ('R38', 0x0A): {m: (18, 1, '2x2 HD windowed 120/100p: no +2 row shift') for m in (132, 133)},
    ('R38', 0x0C): {m: (1196, 1, 'same as +0x0A') for m in (132, 133)},
    ('R38', 0x14): {8: (12, 1, 'OB band 12..13 hand-tuned'), 98: (14, 1, 'OB band 14..15 hand-tuned'),
                    132: (8, 1, 'OB band 8..16'), 133: (8, 1, 'OB band 8..16')},
    ('R38', 0x16): {8: (13, 1, ''), 98: (15, 1, ''), 132: (16, 1, ''), 133: (16, 1, '')},
    ('R38', 0x18): {8: (1, 1, 'shift 1 for a 1-row band')},
    ('R38', 0x1C): {m: (419, 0, 'group-2 x end = +0x08-1; type 0 selects group 0 only [I]') for m in (129, 144)},
    ('R38', 0x1E): {8: (12, 1, ''), 98: (14, 0, 'type 0: group 2 unused [I]'), 132: (8, 1, ''), 133: (8, 1, '')},
    ('R38', 0x20): {8: (13, 1, ''), 98: (15, 0, ''), 132: (16, 1, ''), 133: (16, 1, '')},
    ('R38', 0x22): {8: (1, 1, '')},
    ('R68', 0x10): {m: (10, 0, 'stale crop window, flag +0x08 = 0 -> never read') for m in (8, 56, 139, 147, 148, 149, 150)},
    ('R68', 0x14): {m: (4, 0, '') for m in (8, 56, 139, 147, 148, 149, 150)},
    ('R68', 0x18): {**{m: (6064, 0, '') for m in (8, 56, 139, 147, 148, 149, 150)},
                    **{m: (4716, 1, 'typo of 4176; used by v33 path FUN_c0310410 in LV') for m in V33_IDS}},
    ('R68', 0x1C): {m: (4042, 0, '') for m in (8, 56, 139, 147, 148, 149, 150)},
    ('R68', 0x24): {140: (1, 0, 'y map type 1 (3x3) on a 3x6 mode; flag 0 -> unread')},
}


EXPLICIT_KEYS = set(EXACT)


def predict(field, mode, attrs):
    """value of field for a mode with attributes attrs (dict as reconstruct.load gives) -> (value, how)
    how = 'exact' | 'adj' | 'hand' ; None if the field has no explicit rule"""
    f = EXACT.get(field)
    if f is None:
        return None, None
    h = HAND.get(field, {}).get(mode)
    if h is not None:
        return h[0], 'hand'
    a = derive(dict(attrs, mode=mode), mode)
    return f(a), ('adj' if field in ADJ_FIELDS else 'exact')


def fit_k(points, rnd, div):
    """feasible interval of k for value = rnd(dim*k/div) over points [(dim, value)]; None if empty"""
    lo, hi = None, None
    for i in range(92000, 98001):
        k = i / 100000
        if all(rnd(d * k / div) == v for d, v in points):
            lo = k if lo is None else lo
            hi = k
    return (lo, hi) if lo is not None else None
