#!/usr/bin/env python3
"""Single-frame colour HDR capture (§30): 0242 = 01 alternates the attenuated row group every two columns, 0738 = V
sets the attenuation -> a 2x2-cell checkerboard where every colour has a full and an attenuated sample.
Captures stock, then one frame per V. Leaves 0738 = 00, 0242 = 00.

    checker_capture.py OUT [--v 0x10 --v 0x20 --v 0x40]
"""
import argparse, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--v', action='append', default=[])
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    s = F.Session(out, 0, True, 10)
    try:
        s.write(0x0738, 0); s.write(0x0242, 0); time.sleep(0.15)
        s.grab(out / 'stock')
        s.write(0x0242, 1)
        for v in a.v or ['0x10', '0x20', '0x40']:
            s.write(0x0738, int(v, 16)); time.sleep(0.15)
            s.grab(out / f'checker_{v}')
    finally:
        s.write(0x0738, 0); s.write(0x0242, 0)
        s.close()


if __name__ == '__main__':
    main()
