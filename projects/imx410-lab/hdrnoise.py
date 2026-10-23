#!/usr/bin/env python3
"""HDR wrap-up (RESEARCH_DIRECTION #7): shadow noise of 12-bit vs 14-bit 1x1, 14-bit + checkerboard HDR, vertical 2:1
and vertical 2:1 + checkerboard, at 0 dB and at ISO-3200-like analog gain (26.4 dB), with the same exposure time.

    hdrnoise.py OUT CONFIG GAIN_DB      CONFIG = A (V1 12-bit) | B (V2 14-bit) | C (B + 0242=01 0738=20)
                                                 | D (V1 + vertical 2:1) | E (D + 0242=2D 0738=20)
Main SHS, gain and HCG (05E1 = 0) held by IMXB substitution; fixed shutter so AE stays out. Two frame pairs per point;
analysis offline (offline/hdrnoise_eval.py).
"""
import json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import fastsweep as F                                                 # noqa: E402
import vmode, l7                                                      # noqa: E402

T_US = {0.0: 16600.0, 26.4: 790.0}                 # exposure time: near-full frame at 0 dB, 1/21 of it at 26.4 dB
CHECK = {'C': [(0x0242, 0x01), (0x0738, 0x20)], 'E': [(0x0242, 0x2D), (0x0738, 0x20)]}


def main():
    out, cfg, gdb = pathlib.Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
    d = out / f'{cfg}_{gdb:g}dB'; d.mkdir(parents=True, exist_ok=True)
    code = round(4095 - 4095 / 10 ** (gdb / 20))
    F.cached_assemble(); B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    base = 'V2' if cfg in 'BC' else 'V1'
    if base == 'V2':
        vmode.KEEP_WINDOW = True
    b = R.Base(d, base); s = b.s; s.pair = True
    w0 = B.P().mem_get(0x30100024)[0]
    st = B.bus_state()
    try:
        if cfg in 'DE':
            geom = [(r, v) for r, v in l7.VBIN2 if not (cfg == 'E' and r in (0x0242, 0x0738))] + CHECK.get(cfg, [])
            for r, v in geom:
                s.write(r, v)
            b.restart(); time.sleep(0.3)
            ln = min(B.P().mem_get(0x301005D8)[0] for _ in range(3))
            B.wr(0x30100024, (w0 & 0xFFFF0000) | (ln - 8)); time.sleep(0.1)
            l7.rewindow(s, 0)
        elif cfg == 'C':
            for r, v in CHECK['C']:
                s.write(r, v)
            b.restart(); time.sleep(0.3)
        vmax = (B.P().mem_get(0x30100020)[0] >> 16) + 1
        hw = B.P().mem_get(0x30100004)[0]           # line length and tail halves (mode 6: 911 / 1915): the shorter is HMAX
        hmax = min(hw & 0x3FFF, (hw >> 16) & 0x3FFF) + 1
        lines = T_US[gdb] * 72 / hmax
        shs = max(4, round((vmax - lines) / 2))
        B.bus_on(st)
        B.bus_subs(st, [(0x0005, shs & 0xFF), (0x0006, shs >> 8), (0x003D, code & 0xFF), (0x003E, code >> 8),
                        (0x003F, code & 0xFF), (0x0040, code >> 8), (0x05E1, 0)])
        B.P().sh('imager fixed_shutter 1 100')
        time.sleep(0.5)
        meta = dict(cfg=cfg, gain_db=gdb, code=code, vmax=vmax, hmax=hmax, shs=shs, exposure_us=(vmax - 2 * shs) * hmax / 72,
                    bits=b.bits, top=s.base_window >> 16, lines=B.P().mem_get(0x301005D8)[0])
        for k in range(2):
            ok = b.grab_set(d / f'g{k}')           # p = frame pair, f10, d = DCLP off
            meta[f'g{k}'] = ok
        (d / 'meta.json').write_text(json.dumps(meta, indent=1))
        print(cfg, f'{gdb:g} dB', meta, flush=True)
    finally:
        try:
            B.bus_subs(st, []); B.wr(0x30100024, w0); B.P().sh('imager fixed_shutter 0')
        finally:
            b.close()


if __name__ == '__main__':
    main()
