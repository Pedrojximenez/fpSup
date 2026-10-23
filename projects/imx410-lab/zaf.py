#!/usr/bin/env python3
"""PDAF gate test: Sony's ZAF register path written as a set (notes/CAPABILITY_MAP.md P0-PDAF).

    zaf.py OUT [--base V1]

Sony's a7 III IMX410 driver has SetExposure_ZAF (000B-0010, 0036) and SetRead_ZAF (0047-004A, 0424, 05E2 bit 1)
that the fp never writes (sony_a7iii_v404_imx410_pdaf_reverse_comparison.md §4). R1 wrote them one at a time:
nothing. Here they go in cumulatively, the way Sony's driver writes them, with the fp's PdafCorrect and DCLP off,
raw frames kept for a sparse/periodic pixel search (offline/zaf_eval.py). One boot; fastreboot afterwards
(registers outside the mode table persist).
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402

STEPS = [
    ('ref1', []),
    ('ref2', []),
    ('exp', [(0x000B, 0x00), (0x000C, 0x07), (0x000D, 0x00), (0x000E, 0x01), (0x000F, 0x00), (0x0010, 0x01),
             (0x0036, 0xFF)]),
    ('read', [(0x0047, 0x00), (0x0048, 0x01), (0x0049, 0x00), (0x004A, 0x01)]),
    ('gate', [(0x0424, 0x0E), (0x05E2, 0x03)]),
    ('sel1', [(0x0036, 0x01)]),
    ('gate2', [(0x0424, 0x1B)]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--base', default='V1')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / a.base; out.mkdir(parents=True, exist_ok=True)
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, a.base)
    log = []
    try:
        B.P().sh('imager pdaf_cor_off 1')
        for name, writes in STEPS:
            for r, v in writes:
                b.s.write(r, v)
            b.restart(); time.sleep(0.05)
            d = out / name
            ok = b.grab_set(d)
            if ok:
                for sub in ('p', 'f10', 'd'):
                    if (d / sub / 'frame.json').exists():
                        R.stats(d / sub)
            log.append(dict(step=name, writes=[f'{r:04X}={v:02X}' for r, v in writes], ok=ok))
            print(name, 'ok' if ok else 'NO FRAME', flush=True)
            if not ok:
                break
    finally:
        try:
            B.P().sh('imager pdaf_cor_off 0')
        finally:
            b.close()
        (out / 'steps.json').write_text(json.dumps(log, indent=1))


if __name__ == '__main__':
    main()
