#!/usr/bin/env python3
"""反組譯我們這份映像的一段。  ./dis.py 0xC0435150 0x60 [--thumb]"""
import sys, pathlib
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
ROOT = pathlib.Path(__file__).resolve().parents[3]
b = (ROOT / "out" / "MAIN_c0000000.bin").read_bytes()
a = int(sys.argv[1], 0)
n = int(sys.argv[2], 0) if len(sys.argv) > 2 and not sys.argv[2].startswith('-') else 0x80
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if '--thumb' in sys.argv else CS_MODE_ARM)
md.skipdata = True
for x in md.disasm(b[a-0xC0000000:a-0xC0000000+n], a):
    print(f"{x.address:08x}  {x.bytes.hex():10s} {x.mnemonic:8s} {x.op_str}")
