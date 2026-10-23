#!/usr/bin/env python3
"""Capture a two-frame colour-HDR pair as close together as the host allows (§29), plus a stock frame:
stock, then 0738 = V with 023A = 01 (odd rows attenuated) -> A, 023A = 00 (even rows attenuated) -> B.
Leaves 0738 = 00, 023A = 01 (behaves as stock).

    swap_pair.py OUT_DIR [--v 0x10]
"""
import argparse, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--v', default='0x10')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    F.cached_assemble()
    s = F.Session(out, 0, False, 10)
    try:
        s.write(0x0738, 0); s.write(0x023A, 1); time.sleep(0.15)
        s.grab(out / 'stock')
        s.write(0x0738, int(a.v, 16)); time.sleep(0.15)
        t0 = time.time(); s.grab(out / 'A')
        s.write(0x023A, 0); time.sleep(0.05)
        s.grab(out / 'B'); print(f'A -> B {time.time() - t0:.2f} s')
    finally:
        s.write(0x0738, 0); s.write(0x023A, 1)
        s.close()


if __name__ == '__main__':
    main()
