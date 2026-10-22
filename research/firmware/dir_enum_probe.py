#!/usr/bin/env python3
"""List a directory on the camera through the firmware's own dir API.

    python3 research/firmware/dir_enum_probe.py '\\FPSUPUI' [drive]

Calls dir_ctor / dir_open / dir_next / dir_dtor one at a time through callfn,
the same four calls Loader v3's loader will make.  See notes/DIR_ENUM_API.md.
Buffers come from cave.claim; nothing is written to the card.
"""
import pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'fpSup' / 'fp_usb_shell'))
import cave
from callfn import call
from putfile import put, mem_get

DIR_CTOR, DIR_OPEN, DIR_NEXT, DIR_DTOR = 0xC0366918, 0xC0366990, 0xC03669F8, 0xC0366940
ENTRY = 0x238


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '\\'
    drive = int(sys.argv[2], 0) if len(sys.argv) > 2 else 1
    if not path.startswith('\\'):
        raise SystemExit('the firmware refuses a path that does not start with \\')
    b = cave.claim('dirprobe.buf', 0x280)
    holder, pth, ent = b, b + 8, b + 0x40
    pb = path.encode() + b'\0'
    pb += b'\0' * (-len(pb) % 4)
    if len(pb) > 0x38:
        raise SystemExit('path too long for the claim')
    put(pth, pb, 'path')
    put(holder, b'\0' * 8, 'holder')
    if not call(DIR_CTOR, holder, drive)[0]:
        raise SystemExit('dir_ctor did not return')
    try:
        ok, r = call(DIR_OPEN, holder, pth)
        if not (ok and r):
            print('open failed')
            return 1
        n = 0
        while n < 256:
            put(ent, b'\0' * ENTRY, 'entry')
            ok, r = call(DIR_NEXT, holder, ent, verbose=False)
            if not ok:
                raise SystemExit('dir_next did not return')
            if r == 0:
                break
            w = mem_get(ent, ENTRY // 4)
            if None in w:
                raise SystemExit('entry read came back incomplete')
            raw = b''.join(struct.pack('<I', x) for x in w)
            name = raw[:0x210].decode('utf-16le', 'replace').split('\0')[0]
            size = struct.unpack_from('<Q', raw, 0x210)[0]
            print(f'{n:3d}  attr=0x{raw[0x218]:02X}  {size:12d}  {name}')
            n += 1
        print(f'{n} entries')
        return 0
    finally:
        call(DIR_DTOR, holder, 2)


if __name__ == '__main__':
    sys.exit(main())
