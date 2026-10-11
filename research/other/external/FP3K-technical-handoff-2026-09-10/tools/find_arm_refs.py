"""Find ARM MOVW/MOVT address constructions and aligned pointer literals."""
from pathlib import Path
import struct,argparse,json
p=argparse.ArgumentParser();p.add_argument('address',type=lambda s:int(s,0));a=p.parse_args();b=Path('analysis/firmware/MAIN_c0000000.bin').read_bytes();lo=a.address&65535;hi=a.address>>16
for i in range(0,len(b)-4,4):
 w=struct.unpack_from('<I',b,i)[0]
 if w==a.address:print('literal',hex(0xc0000000+i))
 if w&0x0ff00000==0x03000000 and (((w>>4)&0xf000)|(w&0xfff))==lo:
  rd=(w>>12)&15
  for j in range(i+4,min(i+44,len(b)-4),4):
   z=struct.unpack_from('<I',b,j)[0]
   if z&0x0ff00000==0x03400000 and (z>>12)&15==rd and (((z>>4)&0xf000)|(z&0xfff))==hi:print('movw/movt',hex(0xc0000000+i),hex(0xc0000000+j),'r'+str(rd))
