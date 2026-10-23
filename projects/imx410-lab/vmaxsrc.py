#!/usr/bin/env python3
"""Where does the sensor's real frame length come from? Enter virtual modes built from donors 98 (77 fps) and 143
(18 fps) -- same REG rows, different timing-table VMAX -- dump SoC register blocks in each, diff them.

    vmaxsrc.py OUT
"""
import json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import vmode                                                          # noqa: E402
import fastsweep as F                                                 # noqa: E402

REGIONS = [(0x30100000, 0x1000), (0x30000000, 0x1000), (0x300E0000, 0x2000), (0x30182000, 0x400), (0x30002000, 0x200)]


def dump():
    out = {}
    for a, n in REGIONS:
        for o in range(0, n, 0x100):
            v = B.P().mem_get(a + o, 64)
            for i, x in enumerate(v):
                out[a + o + 4 * i] = x
    return out


def main():
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    B.not_recording()
    dumps = {}
    import struct
    for donor in (2094, 4188, 2094):              # donor 98 rows, only the timing-table VMAX changed (143 wedged)
        if ',0008,' not in B.P().sh('imager mode_now'):
            raise SystemExit('start from live view (mode 8)')
        rows = vmode.donor_rows(98)
        t = bytearray(rows['TIM']); struct.pack_into('<H', t, 8, donor); rows['TIM'] = bytes(t)
        b = R.Base(out, 'V1', rows=rows)
        try:
            time.sleep(0.5)
            d1 = dump(); time.sleep(0.3); d2 = dump()
            fc = B.P().sh('imager mode_now')
            dumps.setdefault(donor, []).append({hex(k): (v, d2.get(k)) for k, v in d1.items()})
            print(donor, [l for l in fc.splitlines() if 'frame_count' in l or ',0010,' in l], flush=True)
        finally:
            b.close()
        time.sleep(1.0)
    (out / 'dumps.json').write_text(json.dumps({str(k): v for k, v in dumps.items()}))
    a, c, a2 = dumps[2094][0], dumps[4188][0], dumps[2094][1]
    for k in a:
        v98, v98b, v143 = a[k], a2.get(k), c.get(k)
        stable = v98[0] == v98[1] and v143 and v143[0] == v143[1] and v98b and v98b[0] == v98b[1]
        if stable and v98[0] != v143[0] and v98[0] == v98b[0]:
            print('DIFF', k, f'2094 0x{v98[0]:08X}', f'4188 0x{v143[0]:08X}')


if __name__ == '__main__':
    main()
