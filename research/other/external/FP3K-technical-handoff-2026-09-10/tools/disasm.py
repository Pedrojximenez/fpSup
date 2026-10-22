from pathlib import Path
import argparse
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM,CS_MODE_THUMB
p=argparse.ArgumentParser();p.add_argument('address',type=lambda s:int(s,0));p.add_argument('length',type=lambda s:int(s,0),nargs='?',default=0x100);p.add_argument('--thumb',action='store_true');a=p.parse_args()
b=Path('analysis/firmware/MAIN_c0000000.bin').read_bytes();md=Cs(CS_ARCH_ARM,CS_MODE_THUMB if a.thumb else CS_MODE_ARM);md.skipdata=True
for x in md.disasm(b[a.address-0xc0000000:a.address-0xc0000000+a.length],a.address):print(f'{x.address:08x}  {x.bytes.hex():10s} {x.mnemonic:8s} {x.op_str}')
