#!/usr/bin/env python3
"""Readout generator (DEV_PLAN D1): a requested readout -> the sensor/SoC settings that produce it, from the rules
measured in IMX410_RULES §42-§58.

    readout_gen.py plan  --cls 12fast --merge 1 --w 4160 --h 2016 --fps 100
    readout_gen.py presets
    readout_gen.py validate PRESET OUT      (live: direct writes on the donor's virtual base, then the standard
                                             checks -- receiver lines, exposure linearity over 3 VMAX, 8-frame burst)

Output plan = donor mode (virtual base), table-row patches (TIM line length, DCLP width), sensor register writes
(class set, format, window, blanking), SoC writes (HMAX, VMAX, receiver crop) and the predicted fps / rolling shutter.
First stage only uses direct writes on the donor's base (proven safe); baking a plan into virtual rows comes after
each preset has passed validation (RESWEEP_DESIGN §9).
"""
import argparse, json, math, pathlib, sys

# per readout class: donor (virtual base), 0001 format, HMAX floor (measured) and default, output-row overhead the
# receiver sees on top of the image rows (lines - 2H), centre of the window (start + H, from stock modes), default 0016
CLASSES = {
    # name        merge donor  0001  hmax_min hmax  bits  overhead centre v016  v016_min  note
    '14':       dict(merge=1, donor=6,  word=0x29, hmin=860, hmax=911, bits=14, over=52, centre=2080, v016=25, v016_min=None, ref='§42'),
    '12':       dict(merge=1, donor=10, word=0x2A, hmin=445, hmax=445, bits=12, over=52, centre=2080, v016=35, v016_min=2, ref='§45 §46'),
    '12fast':   dict(merge=1, donor=10, word=0x2C, hmin=320, hmax=320, bits=12, over=52, centre=2080, v016=35, v016_min=None, ref='§49',
                     fast_set=True, width_fixed=4176),
    '2x2':      dict(merge=2, donor=98, word=0x39, hmin=445, hmax=445, bits=12, over=30, centre=1224, v016=20, v016_min=None, ref='§21'),
    '2x2fast':  dict(merge=2, donor=11, word=0x39, hmin=330, hmax=330, bits=12, over=30, centre=1224, v016=7, v016_min=7, ref='§47 §52'),
    '3x3fast':  dict(merge=3, donor=8,  word=0x2F, hmin=320, hmax=330, bits=12, over=26, centre=935, v016=50, v016_min=2, ref='§58'),
}
FULL_W = {1: 6064, 2: 3032, 3: 2016}
CLK = 72e6


def plan(cls, w, h, fps=None, v016=None, hmax=None, start=None):
    c = CLASSES[cls]
    hm = hmax or c['hmax']
    if hm < c['hmin']:
        raise SystemExit(f'HMAX {hm} below the measured floor {c["hmin"]} for {cls}')
    full = c.get('width_fixed') or FULL_W[c['merge']]
    if w > full:
        raise SystemExit(f'width {w} > {full} for {cls}')
    w12 = math.ceil(w / 12) * 12
    H = math.ceil(h / 2)                                  # window unit = 2 output rows (measured for 1x1/2x2/3x3)
    st = start if start is not None else c['centre'] - H
    b = c['v016'] if v016 is None else v016
    if c['v016_min'] is not None and b < c['v016_min']:
        raise SystemExit(f'0016={b} below the tested minimum {c["v016_min"]} for {cls}')
    lines = 2 * H + c['over']
    vmin = lines + 2 * b + 12                             # VMAX_min ~ lines + 2*0016 + ~6..10 (measured §47/§52/§58) + margin
    vmax = vmin if fps is None else max(vmin, round(CLK / (hm * fps)))
    p = dict(cls=cls, ref=c['ref'], donor=c['donor'], bits=c['bits'], merge=c['merge'],
             out_w=w12, out_h=2 * H, receiver_lines=lines,
             sensor=[(0x0001, c['word']), (0x0003, 1), (0x0022, st & 0xFF), (0x0023, st >> 8), (0x0024, H & 0xFF), (0x0025, H >> 8)]
             + ([(0x0016, b)] if b != c['v016'] else []),
             fast_set=bool(c.get('fast_set')),
             rows=dict(TIM_line=(w12 + 4) if c.get('fast_set') else None, R38_words=(w12 // 12 + 1) if c.get('fast_set') else None),
             soc=dict(hmax=hm, vmax=vmax, rx_width=w12, rx_end=lines - 2),
             fps=CLK / (hm * vmax), fps_max=CLK / (hm * vmin), vmax_min=vmin,
             rolling_ms=hm * lines / CLK * 1e3)
    return p


PRESETS = {
    'uhd-lowjello':   dict(cls='12fast', w=3840, h=2160, fps=None),
    '4176-lowjello':  dict(cls='12fast', w=4176, h=2016, fps=None),
    'fhd192':         dict(cls='2x2fast', w=1920, h=1080, fps=None),
    'fhd-full195':    dict(cls='3x3fast', w=1920, h=1080, fps=None, v016=2),
    'strip1000':      dict(cls='2x2fast', w=3032, h=160, fps=1000),
    'fhd120':         dict(cls='2x2fast', w=1920, h=1080, fps=120),
    '14bit-4k':       dict(cls='14', w=4176, h=2160, fps=None),
}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--cls', required=True, choices=sorted(CLASSES)); p.add_argument('--w', type=int, required=True)
    p.add_argument('--h', type=int, required=True); p.add_argument('--fps', type=float); p.add_argument('--v016', type=int)
    p.add_argument('--hmax', type=int); p.add_argument('--start', type=int)
    sub.add_parser('presets')
    v = sub.add_parser('validate'); v.add_argument('preset', choices=sorted(PRESETS)); v.add_argument('out')
    a = ap.parse_args()
    if a.cmd == 'plan':
        print(json.dumps(plan(a.cls, a.w, a.h, a.fps, a.v016, a.hmax, a.start), indent=1, default=str))
    elif a.cmd == 'presets':
        for k, q in PRESETS.items():
            r = plan(**q)
            print(f"{k:15s} {r['cls']:8s} {r['out_w']}x{r['out_h']} {r['bits']}-bit merge {r['merge']}  HMAX {r['soc']['hmax']} VMAX {r['soc']['vmax']}"
                  f"  -> {r['fps']:.1f} fps (max {r['fps_max']:.1f})  rolling {r['rolling_ms']:.2f} ms")
    else:
        import readout_validate
        readout_validate.run(plan(**PRESETS[a.preset]), pathlib.Path(a.out) / a.preset)


if __name__ == '__main__':
    main()
