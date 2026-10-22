#!/usr/bin/env python3
"""arm / read / off — the live-view display-fit hook at 0xC0437ECC."""
import pathlib, struct, sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from armasm import assemble
from putfile import mem_set, mem_get, put

SRC   = pathlib.Path(__file__).resolve().parent / 'dispfit.S'
CODE  = 0xC072F900
DESC  = 0xC072FA20
SITE  = 0xC0437ECC
ORIG  = 0xE1A00002                      # mov r0, r2
BL    = 0xEB000000 | (((CODE - SITE - 8) >> 2) & 0xFFFFFF)


def setw(a, v):
    for _ in range(8):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'

if cmd == 'arm':
    code = assemble(SRC)
    if CODE + len(code) > DESC:
        raise SystemExit('payload would reach the descriptor buffer')
    cur = mem_get(SITE)[0]
    if cur != ORIG:
        raise SystemExit(f'site holds 0x{cur:08X}, expected 0x{ORIG:08X} — refusing')
    print('  現況(武裝前):')
    for name, obj in (('OBJ_A', 0xC375EB68), ('OBJ_B', 0xC375ED3C)):
        d = mem_get(obj)[0]
        print(f'    {name} 0x{obj:08X} → 描述子 0x{d:08X}', end='')
        if 0xC0000000 <= d < 0xC3900000:
            w = mem_get(d, 6)
            print(f'   {w[0]}x{w[1]}   +0x10/0x14 {w[4]}x{w[5]}')
        else:
            print('   (不像指標,武裝後這個物件會被守衛擋掉)')
    put(CODE, code, 'dispfit')
    for i in range(11):
        setw(DESC + i * 4, 0)
    if not setw(SITE, BL):
        raise SystemExit('could not arm')
    print(f'  armed 0x{SITE:08X} = 0x{BL:08X}  ({len(code)} bytes @ 0x{CODE:08X})')

elif cmd == 'off':
    setw(SITE, ORIG)
    print(f'  0x{SITE:08X} = 0x{mem_get(SITE)[0]:08X}  (原值 0x{ORIG:08X})')

else:
    w = mem_get(DESC, 11)
    if not any(w):
        print('  hook 還沒命中(描述子緩衝是空的)')
    else:
        print(f'  我們回傳的描述子 @0x{DESC:08X}:')
        print(f'    +0x00 {w[0]} x {w[1]}      ← 改過的幾何')
        print(f'    +0x10 {w[4]} x {w[5]}')
        print('    其餘: ' + '  '.join(f'+0x{i*4:02X}={v}' for i, v in enumerate(w)
                                       if i not in (0, 1, 4, 5)))
