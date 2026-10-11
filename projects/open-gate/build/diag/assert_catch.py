#!/usr/bin/env python3
"""Dev-only: install / read the RAM assert catcher (diag/assert_catch.S).

    python3 diag/assert_catch.py            read-only: preflight + plan, writes nothing
    python3 diag/assert_catch.py --go       write code, sync caches, then arm C0011100
    python3 diag/assert_catch.py --read     read RECORD (after a 'freeze')

RAM only; a battery pull removes it.  A power-switch restart that keeps the
image keeps it too (C0011100 is not in the loader journal).
"""
import struct, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[3] / 'fpSup/fp_usb_shell')]
from armasm import assemble
from imx410_load import CameraIO

CODE, RECORD, SITE, STOCK = 0xC0732D00, 0xC0732E00, 0xC0011100, 0xE92D4030
AXIS_RATE = 0xC0732494


def blob():
    return assemble(str(HERE / 'assert_catch.S'), defines=[f'RECORD={RECORD:#x}'])


def hook():
    return 0xEA000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)


def main():
    io = CameraIO()
    words = struct.unpack(f'<{len(blob())//4}I', blob())
    if '--read' in sys.argv:
        r = [io.read(RECORD + 4*i) for i in range(23)]
        print('magic', hex(r[0]), 'hits', r[1])
        if r[0] == 0x54525352:
            name = b''
            for i in range(32):
                name += struct.pack('<I', io.read((r[2] & ~3) + 4*i))
            name = name[r[2] & 3:].split(b'\0')[0]
            print('file', name.decode(errors='replace'), 'line', r[3])
            print('caller lr', hex(r[4]), 'site', hex(r[4]-4), 'sp', hex(r[5]), 'cpsr', hex(r[6]))
            print('stack', ' '.join(f'{w:08x}' for w in r[7:23]))
        return
    site = io.read(SITE)
    free = [io.read(a) for a in range(CODE, RECORD + 0x60, 4)]
    print('C0011100', hex(site), '(stock)' if site == STOCK else '(ARMED)' if site == hook() else '(UNKNOWN)')
    print('cave free', not any(free), '| AXIS[1]', io.read(AXIS_RATE), '| FLAG', io.read(0xC0731C08))
    print(f'plan: {len(words)} code words at {CODE:#x}, sync, then {SITE:#x} = {hook():#010x}')
    if '--go' not in sys.argv:
        return
    if site != STOCK or any(free):
        raise SystemExit('preflight failed: not writing')
    for i, w in enumerate(words):
        io.write(CODE + 4*i, w)
    if [io.read(CODE + 4*i) for i in range(len(words))] != list(words):
        raise SystemExit('code read-back mismatch: hook NOT armed')
    io.sync()
    io.write(SITE, hook())
    io.sync()
    print('armed:', hex(io.read(SITE)))


if __name__ == '__main__':
    main()
