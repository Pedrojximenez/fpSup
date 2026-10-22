"""Disassemble Jose's layout at its own coordinates.  jdis.py 0xC0793C30 0x80 [-t]"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fmt_layout as F
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB

img = F.Image(F.load()[0])
a, n = int(sys.argv[1], 0), int(sys.argv[2], 0)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if '-t' in sys.argv else CS_MODE_ARM)
md.skipdata = True
for x in md.disasm(img.read(a, n) or b'', a):
    print(f'{x.address:08x} {x.bytes.hex():10s} {x.mnemonic} {x.op_str}')
