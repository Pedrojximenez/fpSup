"""Single source of truth for the readout planner / generator / validator (DEV_PLAN D1).

Every readout the IMX410 can do on the fp, with the rules measured in IMX410_RULES §42-§58:
  mh, mv     sensor merge (horizontal, vertical); output rows = 2 * window H for every class
  fmt        sensor output width -> 0001 format code (the receiver then crops to the request, 12 px units)
  hmin       line-time floor (72 MHz cycles); hdef = the donor's own HMAX
  over       receiver lines on top of the image rows; centre = sensor row the window is centred on (2080 for every
             class; None: no window tested for this class -> full height only). start = centre - H*mv snapped to 1 mod 4
  v016       the donor's vertical blanking (0016); v016_min = smallest value tested good (None = not tested)
  fast_set   1x1 fast AD built on mode-10 rows: Family A fast values + TIM line length = width + 4 + DCLP width
  ev         where it was measured; 'est' = not measured with the standard method yet
"""
import json, math, pathlib

CLK = 72e6
HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / 'captures' / 'readout_validated.json'

READOUTS = [
    dict(key='14',       name='14-bit 1x1',       mh=1, mv=1, bits=14, ad='14',     donor=6,   fmt={6064: 0x29},
         hmin=870, hdef=911, over=52, centre=2080, v016=25, v016_min=None, ev='§42 §54'),
    dict(key='12',       name='12-bit 1x1',       mh=1, mv=1, bits=12, ad='normal', donor=10,  fmt={6064: 0x2A},
         hmin=445, hdef=445, over=52, centre=2080, v016=35, v016_min=2, ev='§45 §46'),
    dict(key='12fast',   name='12-bit fast 1x1',  mh=1, mv=1, bits=12, ad='fast',   donor=10,  fmt={4176: 0x2C},
         hmin=330, hdef=330, over=52, centre=2080, v016=35, v016_min=None, fast_set=True, ev='§49 (320 = broken frames, batch 10-22)'),
    dict(key='12fastW',  name='12-bit fast 1x1 wide', mh=1, mv=1, bits=12, ad='fast', donor=10, fmt={6064: 0x2A},
         hmin=400, hdef=400, over=52, centre=2080, v016=35, v016_min=None, fast_set=True, ev='§31 L2b (est)'),
    dict(key='2x2',      name='12-bit 2x2',       mh=2, mv=2, bits=12, ad='normal', donor=98,  fmt={3032: 0x39},
         hmin=445, hdef=445, over=30, centre=2080, v016=20, v016_min=None, ev='§21 (est)'),
    dict(key='2x2fast',  name='12-bit fast 2x2',  mh=2, mv=2, bits=12, ad='fast',   donor=11,  fmt={3032: 0x39},
         hmin=330, hdef=330, over=30, centre=2080, v016=7,  v016_min=7, ev='§47 §50 §52'),
    dict(key='3x3',      name='12-bit 3x3',       mh=3, mv=3, bits=12, ad='normal', donor=139, fmt={2016: 0x2F},
         hmin=445, hdef=445, over=26, centre=2080,  v016=50, v016_min=None, ev='mode 134 window (est)'),
    dict(key='3x3fast',  name='12-bit fast 3x3',  mh=3, mv=3, bits=12, ad='fast',   donor=8,   fmt={2016: 0x2F},
         hmin=330, hdef=330, over=26, centre=2080,  v016=50, v016_min=2, ev='§48 §58 (320 = broken frames, batch 10-22)'),
    dict(key='3x6',      name='12-bit 3x6',       mh=3, mv=6, bits=12, ad='normal', donor=140, fmt={2016: 0x30},
         hmin=445, hdef=445, over=19, centre=None, v016=35, v016_min=None, ev='M140 batch 10-22'),
    dict(key='3x6fast',  name='12-bit fast 3x6',  mh=3, mv=6, bits=12, ad='fast',   donor=12,  fmt={2016: 0x30},
         hmin=330, hdef=330, over=19, centre=None, v016=25, v016_min=None, ev='M12 batch 10-22: 287 fps linear, no drops'),
] 

# --- readout matrix (2026-10-22, IMX410_RULES §67): cells measured feasible or untested, built from register groups
# split off the stock tables. new=True: no stock class -> smc refuses them; layer-1 validation (direct writes) only.
# Vertical-only / horizontal-only and 14-bit vertical merges: §35 §37 §66, L7 T1. v6 without h3 and h2v3/h3v2: probes.
V2 = [(0x0005, 0x03), (0x001C, 0x03), (0x0717, 0x04), (0x071E, 0x05), (0x0720, 0x05), (0x0722, 0x02), (0x0723, 0x02),
      (0x0724, 0x02), (0x0725, 0x02), (0x0726, 0x01), (0x0728, 0x3D), (0x072A, 0xF0), (0x072B, 0x03), (0x072C, 0x04),
      (0x0734, 0x05), (0x0735, 0x05), (0x0737, 0x02), (0x0738, 0x02), (0x0739, 0x02), (0x073A, 0x02), (0x0792, 0x22),
      (0x0793, 0x02), (0x0794, 0x05), (0x079C, 0x3D)]                      # Z CAM MODE21 vertical 2:1 (L3)
V3 = [(0x0016, 0x32), (0x001C, 0x02), (0x0058, 0x70), (0x0717, 0x06), (0x071E, 0x03), (0x0722, 0x02), (0x0723, 0x02),
      (0x0724, 0x04), (0x0725, 0x04), (0x0728, 0x3F), (0x072A, 0xA0), (0x072B, 0x02), (0x072C, 0x06), (0x0734, 0x03),
      (0x0737, 0x02), (0x0738, 0x02), (0x0739, 0x04), (0x073A, 0x04), (0x0792, 0x30), (0x0793, 0x03), (0x079C, 0x3D)]   # mode 139 Family B (L4)
V6 = [(0x0005, 0x01), (0x001C, 0x02), (0x0058, 0x70), (0x0716, 0x00), (0x0717, 0x00), (0x071E, 0x00), (0x0720, 0x00),
      (0x0727, 0x00), (0x0728, 0x00), (0x072A, 0x00), (0x072B, 0x00), (0x072C, 0x00), (0x0734, 0x00), (0x0735, 0x00),
      (0x0790, 0x00), (0x0792, 0x00), (0x0793, 0x00), (0x0794, 0x00), (0x0795, 0x00), (0x0796, 0x00), (0x0797, 0x00),
      (0x0798, 0x00), (0x079A, 0x00), (0x079C, 0x00), (0x079E, 0x00), (0x079F, 0x00)]                       # mode 140 vertical set
PAIR = [(0x0242, 0x2C), (0x0278, 0x04), (0x0279, 0x01), (0x027B, 0x04), (0x08B6, 0x01), (0x08B7, 0x68)]   # same-colour pairing: h1 v2 only (§37)
BINNED = [(0x0058, 0x70)]
FULL = [(0x0003, 0x00)]          # no sensor window. (0018 = extra dark rows was on in matrix r1/r2 but is not among the
                                  # 161 REG-table registers, so a generated mode cannot carry it; stock binned modes do without)

_OVER = {(2, 1): 54, (3, 1): 34, (1, 2): 26, (3, 2): 26, (1, 3): 43, (2, 3): 43, (1, 6): 19, (2, 6): 19}
# receiver lines over the image rows, firmware switch WITHOUT 0018 (smc_m1 2026-10-23): every class sent exactly 36
# lines fewer than with 0018=0x12 on (matrix r1/r2: 90/70/62/60/79/79) -- 0x12 = 18 extra dark row pairs
_V016 = {1: 35, 2: 35, 3: 50, 6: 35}


_Y0 = {(1, 2): 20, (1, 3): 20, (2, 1): 40, (3, 1): 20, (2, 3): 20, (3, 2): 20}   # first COMPLETE row pair (full frames)   # first image row, even; h2 / h2v3 re-measured
# measured by the firmware switch without 0018 (smc_m1, 2026-10-23): first lit row 17/18 for every vertical or mixed
# merge, 40 for h2 (3B); h3 (2F, v1): rows 16-19 read below black (199), texture from row 20 (the 640 was a dark scene top)


def _cell(key, mh, mv, ad, fmt, extra, ev):
    bits = 14 if ad == '14' else 12
    h = {'14': 870, 'normal': 445, 'fast': 400 if min(fmt) > 4200 else 330}[ad]
    return dict(key=key, name=f'{bits}-bit{" fast" if ad == "fast" else ""} {mh}x{mv}', mh=mh, mv=mv, bits=bits, ad=ad,
                donor=6 if ad == '14' else 10, fmt=fmt, hmin=h, hdef=h, over=_OVER[(mh, mv)], centre=2080, v016=_V016[mv],
                v016_min=None, fast_set=ad == 'fast', extra=FULL + extra, new=True,
                y0=_Y0[(mh, mv)],
                cls=16 if ad == '14' else 17, ev=ev)


for _ad, _p in (('normal', ''), ('fast', 'f')):
    READOUTS += [
        _cell(f'{_p}12v2', 1, 2, _ad, {6064: 0x2A}, V2 + PAIR, '§35 §37 (12-bit normal)'),
        _cell(f'{_p}12v3', 1, 3, _ad, {6064: 0x2A}, V3, '§37'),
        _cell(f'{_p}12h2', 2, 1, _ad, {3032: 0x3B}, BINNED, '§35 (3B)'),
        _cell(f'{_p}12h3', 3, 1, _ad, {2016: 0x2F}, BINNED, 'probe'),
        _cell(f'{_p}12h2v3', 2, 3, _ad, {3032: 0x3B}, V3, 'matrix r2: 3B + V3 (39 + V3 put the colours 2 rows apart)'),
        _cell(f'{_p}12h3v2', 3, 2, _ad, {2016: 0x2F}, V2 + PAIR + BINNED, 'matrix r2: 2F + V2 + pairing set (without it 1.45 rows apart)'),
    ]
READOUTS += [
    _cell('14v2', 1, 2, '14', {6064: 0x29}, V2 + PAIR, 'L7 T1'),
    _cell('14v3', 1, 3, '14', {6064: 0x29}, V3, '§66'),
]
# matrix round 2 (§67): the format word decides whether the sensor pairs rows itself -- 39 (stock 2x2) does, so it
# cannot carry V3; 2F (h3) and 2A/3B (no h merge in v) do not, so v2 with them needs the pairing set
# measured NOT feasible (matrix round 1, §67): v/6 without the h3 format word 30 (12v6 sent 2272 lines, 12h2v6 2080 --
# the 07xx v6 set alone does not divide by 6); 14-bit with any non-stock 0001 word (only 29/2B carry a 14-bit image)
READOUTS += [
]
BY_KEY = {r['key']: r for r in READOUTS}
VMAX_MAX = 16384                                    # SoC 0x30100020 field is 14 bits: 16384 OK, 16385 wrapped and
                                                    # wedged the shell (longexp 2026-10-23) -- never write above
SENSOR_H = 4040                                     # active rows
WIN_TOP, WIN_BOTTOM = 56, 4104                      # readable sensor rows for a window (2x2 lit-row edges, SMC round 4)


def validated():
    try:
        return json.loads(RESULTS.read_text())
    except (OSError, ValueError):
        return {}


def config_id(key, cw, ch, ow, oh, fps):
    return f'{key}:{cw}x{ch}>{ow}x{oh}@{fps:g}'


def plan(key, cw, ch, ow, oh, fps=None, v016=None, hmax=None, hdr=0):
    """crop cw x ch (sensor px) -> output ow x oh at fps on readout `key`: everything needed to set it up, or
    raise ValueError if the rules say it cannot be done."""
    r = BY_KEY[key]
    sw, sh = cw / r['mh'], ch / r['mv']                 # crop on the sensor output grid
    fmt = min((w for w in r['fmt'] if w >= sw - 1e-6), default=None)
    if fmt is None and max(r['fmt']) >= sw * 0.995:     # within 0.5 %: trim the crop to the format (OG on 3x3)
        fmt = max(r['fmt']); sw = fmt
    if fmt is None:
        raise ValueError(f'crop {cw} wider than {key} formats')
    if ow > sw + 1e-6 or oh > sh + 1e-6:
        raise ValueError('RWZM cannot upscale')
    full_h = SENSOR_H / r['mv']
    windowed = sh < full_h - 2
    if windowed and r['centre'] is None:
        raise ValueError(f'{key}: vertical window not tested -- full height only')
    H = math.ceil(sh / 2)
    hm = hmax or r['hmin']
    if hm < r['hmin']:
        raise ValueError(f'HMAX {hm} below the floor {r["hmin"]}')
    rows_out = 2 * H if windowed else int(round(full_h))
    lines = rows_out + r['over']
    b = r['v016'] if v016 is None else v016
    if b < r['v016'] and (r['v016_min'] is None or b < r['v016_min']):
        raise ValueError(f'0016={b} below the tested minimum for {key}')
    vmin = lines + 2 * b + 12
    if fps:
        vmax = round(CLK / (hm * fps))
        if vmax < vmin and r['v016_min'] is not None and v016 is None:   # try the smaller tested blanking
            b = r['v016_min']; vmin = lines + 2 * b + 12
        if vmax < vmin:
            raise ValueError(f'{fps} fps needs VMAX {vmax} < minimum {vmin}')
        if vmax > VMAX_MAX:
            raise ValueError(f'{fps} fps needs VMAX {vmax} > {VMAX_MAX} (14-bit SoC field) -- multi-frame exposure (0007)')
    else:
        vmax = vmin
    rx_w = math.ceil(sw / 12) * 12
    raster_w = min(fmt, math.ceil(sw / 16) * 16)              # recorded raster (BUFA/ISP widths are multiples of 16)
    sensor = list(r.get('extra', [])) + [(0x0001, r['fmt'][fmt])]   # matrix classes: their register groups first
    if windowed:
        # window start is in SENSOR rows for every merge class and the window spans 2H output rows = 2H*mv sensor rows,
        # centred on row 2080 (stock 10/100/58/134/132 all fit); it must be = 1 mod 4 like every stock window -- an even
        # start mixes the colours (1x1, 3x3) or swaps the Bayer row phase (2x2) (SMC round 4, captures/winbound)
        raw = r['centre'] - H * r['mv']
        st = min((raw + k for k in range(-2, 3) if (raw + k) % 4 == 1), key=lambda x: (abs(x - raw), x))
        if st < WIN_TOP or st + 2 * H * r['mv'] > WIN_BOTTOM:
            raise ValueError(f'{key}: window rows {st}..{st + 2 * H * r["mv"]} outside the readable {WIN_TOP}..{WIN_BOTTOM}')
        sensor += [(0x0003, 1), (0x0022, st & 0xFF), (0x0023, st >> 8), (0x0024, H & 0xFF), (0x0025, H >> 8)]
    elif not any(a == 0x0003 for a, _ in sensor):
        sensor.append((0x0003, 0))                      # full height: switch the donor's window off (HDR r1: 12 / 14
                                                        # full-height plans read only the donor's 2076 rows)
    if b != r['v016']:
        sensor.append((0x0016, b))
    if hdr:
        # single-frame checkerboard HDR (§30): 0242 bit 0 + 0738 = attenuated row group; 1x1 and vertical merges only
        # [I, to be measured for every class]. The cells are 4 raw columns wide: crops stay 4-aligned because the
        # receiver works in 12-px units; an ISP-side x0 must be = 0 mod 4 as well.
        regs = dict(sensor)
        sensor = [(a, v) for a, v in sensor if a not in (0x0242, 0x0738)]
        sensor += [(0x0242, regs.get(0x0242, 0) | 1), (0x0738, hdr)]
    return dict(id=config_id(key, cw, ch, ow, oh, fps or 0) + (f'+hdr{hdr:02X}' if hdr else ''), key=key, hdr=hdr, name=r['name'], ev=r['ev'], donor=r['donor'], bits=r['bits'],
                merge=f"{r['mh']}x{r['mv']}", mv=r['mv'], new=bool(r.get('new')), crop=[cw, ch], out=[ow, oh], fmt_w=fmt, raster_w=raster_w, out_h=rows_out, receiver_lines=lines,
                rwzm=[sw / ow, sh / oh], sensor=sensor, fast_set=bool(r.get('fast_set')),
                rows=dict(TIM_line=(fmt + 4) if r.get('fast_set') and fmt < 6000 else None,
                          R38_words=(fmt // 12 + 1) if r.get('fast_set') and fmt < 6000 else None),
                soc=dict(hmax=hm, vmax=vmax, rx_width=rx_w, rx_end=lines - 2),
                fps=CLK / (hm * vmax), fps_max=CLK / (hm * vmin), rolling_ms=hm * lines / CLK * 1e3)
