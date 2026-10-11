#!/usr/bin/env python3
"""Dev-only: install / read the RAM logger on the frame-rate table getter (diag/getter_log.S).

    python3 diag/getter_log.py          read-only preflight + plan
    python3 diag/getter_log.py --go     write logger, sync, arm C06BDB00, sync
    python3 diag/getter_log.py --read   dump the ring (newest last)
    python3 diag/getter_log.py --off    restore C06BDB00 (stock word), sync
    python3 diag/getter_log.py --go --reload   disarm, clear ring, rewrite code, re-arm
"""
import struct, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[3] / 'fpSup/fp_usb_shell')]
from armasm import assemble
from imx410_load import CameraIO

CODE, LOG, SITE, STOCK = 0xC0732D00, 0xC0732E00, 0xC06BDB00, 0xE52D4004


def blob():
    return assemble(str(HERE / 'getter_log.S'), defines=[f'LOG={LOG:#x}', 'RATE240=0xC0731C48', 'PAIRROW=0xC0730204'])


def hook():
    return 0xEA000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)


def main():
    io = CameraIO()
    words = struct.unpack(f'<{len(blob())//4}I', blob())
    if '--read' in sys.argv:
        n = io.read(LOG)
        print('calls', n)
        for k in range(max(0, n - 8), n):
            e = [io.read(LOG + 0x10 + (k % 8) * 128 + 4*i) for i in range(32)]
            print(f'#{k:5d} lr={e[0]:08x} r6={e[1]:#x} sp={e[2]:08x} RATE240={e[3]} first7row={e[4]} caller={e[5]:08x}')
            print('       stk ' + ' '.join(f'{w:08x}' for w in e[5:]))
        return
    site = io.read(SITE)
    if '--off' in sys.argv:
        if site == hook():
            io.write(SITE, STOCK); io.sync()
        print('C06BDB00', hex(io.read(SITE)))
        return
    free = [io.read(a) for a in range(CODE, LOG + 0x410, 4)]
    print('C06BDB00', hex(site), '(stock)' if site == STOCK else '(ARMED)' if site == hook() else '(UNKNOWN)')
    print('area free', not any(free), f'| plan: {len(words)} words at {CODE:#x}, ring at {LOG:#x}, then {SITE:#x}={hook():#010x}')
    if '--go' not in sys.argv:
        return
    if '--reload' in sys.argv and site == hook():
        io.write(SITE, STOCK); io.sync()                      # disarm before rewriting code
        for a in range(LOG, LOG + 0x410, 4): io.write(a, 0)
        site = io.read(SITE); free = [0]
        print('disarmed for reload; ring cleared')
    if site != STOCK or any(free):
        raise SystemExit('preflight failed: not writing')
    for i, w in enumerate(words):
        io.write(CODE + 4*i, w)
    if [io.read(CODE + 4*i) for i in range(len(words))] != list(words):
        raise SystemExit('code read-back mismatch: NOT armed')
    io.sync()
    io.write(SITE, hook())
    io.sync()
    print('armed', hex(io.read(SITE)))


if __name__ == '__main__':
    main()
