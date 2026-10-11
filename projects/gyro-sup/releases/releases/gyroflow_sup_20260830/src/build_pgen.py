#!/usr/bin/env python3
"""Wrap the profile generator as \\PGEN.BIN for the camera to load at boot.

    ./gyro/build_pgen.py            -> writes it to the card over USB

    "PGEN" | u32 entry offset | u32 length | the code

The generator lives in the pool, whose address is only known at run time, so it
cannot be a section of VSHL.BIN like the logger is.  It goes on the card as a
file instead and pgenload.S reads it in at boot -- the same shape the lens table
already uses.  The header carries the entry offset so the loader never has to
know anything about the code it is placing.
"""
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL = HERE.parent / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))

from armasm import assemble, symbols                           # noqa: E402


def build():
    code = assemble(HERE / 'profilegen.S')
    entry = symbols(HERE / 'profilegen.S')['pg_build']
    return struct.pack('<4sII', b'PGEN', entry, len(code)) + code, entry, len(code)


if __name__ == '__main__':
    blob, entry, n = build()
    local = HERE / '.pgen.bin'
    local.write_bytes(blob)
    print(f'  generator     {n} bytes, entry +0x{entry:X}, {len(blob)} on the card')
    if '--local' not in sys.argv:
        r = subprocess.run([sys.executable, str(SHELL / 'putfile.py'),
                            str(local), r'\PGEN.BIN'], capture_output=True, text=True)
        sys.stdout.write('\n'.join(l for l in (r.stdout + r.stderr).splitlines()
                                   if 'written' in l or 'dir' in l or 'ERR' in l))
        print()
