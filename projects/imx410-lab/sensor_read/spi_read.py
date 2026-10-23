#!/usr/bin/env python3
"""Try to read an IMX410 register back over serial ch1 (notes/SENSOR_BUS_READ.md, step 2).

    spi_read.py 0x0016 --chip 0x82 [--chip 0x83 ...]

Runs asm/spi_read.S once per chip-ID through callfn (echo borrowed, IRQs masked inside).
Also does one control transaction: a real write (chip 0x81) of the register's current stock value, so the RX
seen during a write is known. Only use registers that are harmless to clobber (0016 has no effect on any bit, §20).
Pause the sweep first (touch captures/PAUSE): both borrow the echo slot.
"""
import argparse, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[2] / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))
from armasm import assemble                                            # noqa: E402
from callfn import call                                                # noqa: E402
from putfile import put, mem_get                                       # noqa: E402
import cave                                                            # noqa: E402

F_DCACHE = 0xC000E91C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reg', type=lambda x: int(x, 0))
    ap.add_argument('--chip', action='append', type=lambda x: int(x, 0), default=[])
    ap.add_argument('--control', type=lambda x: int(x, 0), help='stock value: also do one real write of it (chip 0x81)')
    ap.add_argument('--v2', type=lambda x: int(x, 0), metavar='MODE',
                    help='use spi_read2.S (driver-A completion) with this r3 mode (bit0 framing, bits 15:8 divider)')
    a = ap.parse_args()
    code = assemble(HERE / ('spi_read2.S' if a.v2 is not None else 'spi_read.S'))
    at = cave.claim('imxl.spiread2' if a.v2 is not None else 'imxl.spiread', 320 if a.v2 is not None else 192)
    res = cave.claim('imxl.spiread2.res' if a.v2 is not None else 'imxl.spiread.res', 128 if a.v2 is not None else 16)
    put(at, code + bytes(-len(code) % 4), 'spird ')
    ok, _ = call(F_DCACHE, verbose=False)
    hi, lo = a.reg >> 8, a.reg & 0xFF
    tries = [(c, 0) for c in a.chip] + ([(0x81, a.control)] if a.control is not None else [])
    for chip, tx in tries:
        if a.v2 is None:
            put(res, bytes(12), 'res   ')
            ok, v = call(at, chip | hi << 8 | lo << 16, tx, res, verbose=False)
            rx, st, left = mem_get(res, 3)
            print(f'chip 0x{chip:02X} reg 0x{a.reg:04X} tx 0x{tx:02X}: returned {ok}, RX 0x{rx:08X}  status 0x{st:02X}  polls left {left}')
            continue
        put(res, bytes(116) + bytes(12), 'res   ')
        ok, v = call(at, chip | hi << 8 | lo << 16, tx, res, a.v2, verbose=False)
        w = mem_get(res, 29)
        pairs = ' '.join(f'{w[5 + 2 * i]:08X}/{w[6 + 2 * i]:02X}' for i in range(min(w[4] or 0, 12)))
        print(f'chip 0x{chip:02X} reg 0x{a.reg:04X} tx 0x{tx:02X} mode 0x{a.v2:X}: returned {ok}, last RX 0x{w[0]:08X} '
              f'status 0x{w[1]:02X} polls left {w[2]} before 0x{w[3]:02X}  pairs {pairs}')


if __name__ == '__main__':
    main()
