#!/usr/bin/env python3
"""BF phase-detect readout on the fp (user 2026-10-23; sigma_bf/AF_ANALYSIS.md §2.3). The SIGMA BF runs its live view
on two IMX410 modes named PDAF-6C / PDAF-7C. PDAF-6C = fp mode 139 (3x3, 12-bit) with 8 table registers changed, plus
23 registers the fp never writes (offline/bf_imx410_modes.csv, extracted again from seg02 and checked: 0 mismatches).
00E9 is left out: BF writes 80 in every mode, so it is not part of the phase readout, and 01/02/20/FF stop the sensor.

Steps, one frame pair each (lens open, fixed scene; SHS and gain held by IMXB substitution):
  ref1 ref2   mode 139 as the firmware sets it
  tbl         + the 8 table differences (vertical adders off, 0736 = 10, 0242 bit 0, 0728 +4, 0016 = 07)
  g_hcnt      + 0241 / 0246-0251 (horizontal counters; 0241 = 01 corrupted data in §17, 05 untested)
  g_misc      + 0073 / 0277
  g_ad        + 0442 / 04D0 / 04D4 / 0607 / 06C6
  g_vdrv      + 0704-0721 (vertical drive)  = the whole PDAF-6C set
The groups go in one at a time so a sensor stop names its group. Receiver lines are read before each grab and the
window is shrunk to what the sensor sends. Nothing is written to the settings area or the card.

    pdaf_bf.py OUT [--gain 0x400] [--upto g_vdrv]
"""
import argparse, json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import l7                                                             # noqa: E402

TABLE = [(0x0016, 0x07), (0x0242, 0x01), (0x0722, 0x00), (0x0723, 0x00), (0x0728, 0x43), (0x0736, 0x10),
         (0x0737, 0x00), (0x0738, 0x00)]
GROUPS = [
    ('g_hcnt', [(0x0241, 0x05), (0x0246, 0xC0), (0x0247, 0x17), (0x0248, 0x20), (0x0249, 0x20), (0x024E, 0xD8),
                (0x024F, 0x17), (0x0250, 0xD8), (0x0251, 0x17)]),
    ('g_misc', [(0x0073, 0x00), (0x0277, 0x01)]),
    ('g_ad', [(0x0442, 0x50), (0x04D0, 0x2C), (0x04D4, 0x69), (0x0607, 0x03), (0x06C6, 0x3C)]),
    ('g_vdrv', [(0x0704, 0x01), (0x0705, 0x02), (0x0706, 0x01), (0x0708, 0x06), (0x070F, 0x10), (0x0710, 0x03),
                (0x0721, 0x01)]),
]
DONOR = 139


def lines():
    return [B.P().mem_get(0x301005D8)[0] for _ in range(3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--gain', type=lambda x: int(x, 0), default=0x400)
    ap.add_argument('--upto', default='g_vdrv', choices=['tbl'] + [g for g, _ in GROUPS])
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    g = a.gain
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    import vmode
    vmode.KEEP_WINDOW = True                     # tool trap: without it full-height frames lose the bottom quarter
    rows = vmode.donor_rows(DONOR)                # the stock rows as the camera holds them (reads over USB)
    top = struct.unpack_from('<H', rows['TIM'], 0xE)[0]
    b = R.Base(out, 'V1', rows=rows); s = b.s; s.pair = True
    rx0, w0 = B.P().mem_get(0x3010000C)[0], B.P().mem_get(0x30100024)[0]
    st = B.bus_state()
    log = []

    def shot(name, writes=(), restart=True):
        for r, v in writes:
            s.write(r, v)
        if restart:
            b.restart(); time.sleep(0.3)
        ln = lines()
        if restart and min(ln) > 16:                 # the sensor may now send fewer lines: shrink the receiver window
            w = B.P().mem_get(0x30100024)[0]
            if min(ln) - 8 < (w & 0xFFFF):
                B.wr(0x30100024, (w & 0xFFFF0000) | (min(ln) - 8)); time.sleep(0.1)
                l7.rewindow(s, 0)
        ok = s.grab(out / name) if min(ln) > 16 else False
        e = dict(name=name, writes=[f'{r:04X}={v:02X}' for r, v in writes], lines=ln, ok=bool(ok))
        if ok:
            f, m = R.decode(out / name)
            im = f[0][top:]
            rr = im[:, 60:-60].mean(1)
            e.update(shape=list(im.shape), lvl=float(im[:, 60:-60].mean()),
                     eo=float(rr[0::2].mean() / max(rr[1::2].mean(), 1)),
                     tn=float(np.std((f[0] - f[1])[top + 100:-100:2, 100:-100:2]) / np.sqrt(2)) if len(f) > 1 else None)
        log.append(e)
        print(name, 'lines', ln, 'ok', ok, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in e.items()
                                            if k in ('shape', 'lvl', 'eo', 'tn') and v is not None}, flush=True)
        (out / 'log.json').write_text(json.dumps(log, indent=1))
        return ok

    try:
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, g & 0xFF), (0x003E, g >> 8), (0x003F, g & 0xFF), (0x0040, g >> 8)])
        time.sleep(0.3)
        shot('ref1', restart=False)
        shot('ref2', restart=False)
        if not shot('tbl', TABLE) or a.upto == 'tbl':
            return
        for name, regs in GROUPS:
            if not shot(name, regs) or a.upto == name:
                return
        shot(GROUPS[-1][0] + '_r', [], restart=False)            # repeatability
    finally:
        try:
            B.bus_subs(st, []); B.wr(0x3010000C, rx0); B.wr(0x30100024, w0)
        finally:
            b.close()


if __name__ == '__main__':
    main()
