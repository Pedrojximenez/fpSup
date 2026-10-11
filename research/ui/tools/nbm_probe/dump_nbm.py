"""Dump the stock NBM container at 0xC2DE3D20: machines, states, transitions (with conditions)."""
import struct, sys
d=open('/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin','rb').read();B=0xC0000000
base=0xC2DE3D20-B
o=base+12
recs=[]
while True:
    tag,ln=struct.unpack_from('>II',d,o)
    recs.append((tag,o,ln)); o+=ln
    if tag==0xFFFFFFFF or len(recs)>5000: break
pool_off=recs[0][1]+8
def s(x):
    a=pool_off+x; return d[a:d.index(b'\0',a)].decode('latin1')
from collections import Counter
print('tags',Counter(hex(t) for t,_,_ in recs))
want=sys.argv[1:] 
cur=None
for tag,o,ln in recs[1:]:
    w=struct.unpack_from('>%dI'%((ln-8)//4),d,o+8)
    if tag==0x50002:
        cur=s(w[-1]); show=(not want) or cur in want
        if show: print('MACHINE',cur,'states',w[0],'trans',w[7], 'raw',w)
    elif tag==0x50003 and show: print('  S',s(w[0]),w[1:])
    elif tag==0x50004 and show: print('  T',s(w[0]),'->',s(w[1]),'ev=%r cond=%r'%(s(w[2]),s(w[3])))
    elif tag not in (0x50001,0x50002,0x50003,0x50004,0xFFFFFFFF): print('REC',hex(tag),ln,w[:8])
