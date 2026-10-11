"""Conservative aligned ARM call/immediate index for local reverse engineering.
Candidate matches can be data or Thumb; callers require disassembly validation.
"""
from pathlib import Path
import struct,json,argparse
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--target',type=lambda s:int(s,0));p.add_argument('--immediate',type=lambda s:int(s,0));a=p.parse_args();b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
for off in range(0,min(len(b),0x730000),4):
 w=struct.unpack_from('<I',b,off)[0];pc=0xc0000000+off
 if a.target is not None and w&0x0e000000==0x0a000000:
  disp=w&0xffffff
  if disp&0x800000:disp-=0x1000000
  target=(pc+8+(disp<<2))&0xffffffff
  if w>>28==15:target+=((w>>24)&1)*2
  if target==a.target:print(hex(pc),'branch/call',hex(w))
 if a.immediate is not None:
  match=False
  if w&0x0ff00000==0x03000000:match=(((w>>4)&0xf000)|(w&0xfff))==a.immediate
  elif w&0x0e000000==0x02000000 and (w>>21)&15 not in (8,9,10,11) or (w&0x0e000000==0x02000000 and w&(1<<20)):
   k=((w>>8)&15)*2;imm=w&255;val=((imm>>k)|(imm<<(32-k)))&0xffffffff if k else imm
   match=val==a.immediate
  if match:print(hex(pc),'immediate',hex(w))
