"""Dump records of the NBV (app-variable) container at 0xC2D8CF40 that mention a name."""
import struct,sys
from collections import Counter
d=open('/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin','rb').read();B=0xC0000000
base=0xC2D8CF40-B; o=base+12; recs=[]
while True:
    tag,ln=struct.unpack_from('>II',d,o); recs.append((tag,o,ln)); o+=ln
    if tag==0xFFFFFFFF or len(recs)>200000: break
pool=recs[0][1]+8; psz=recs[0][2]-8
def s(x):
    if 0<=x<psz: a=pool+x; return d[a:d.index(b'\0',a)].decode('latin1')
print('records',len(recs),Counter(hex(t) for t,_,_ in recs).most_common(20))
names=sys.argv[1:]
offs={d.find(b'\0'+n.encode()+b'\0',pool)+1-pool:n for n in names}
print({hex(k):v for k,v in offs.items()})
for tag,o,ln in recs[1:]:
    if tag==0xFFFFFFFF: break
    n=(ln-8)//4; w=struct.unpack_from('>%dI'%n,d,o+8)
    # walk sub-records too (nested)
    if any(x in offs for x in w):
        print(hex(tag),ln,hex(B+o),[ (s(x) if s(x) else hex(x)) if x>3 and x<psz else hex(x) for x in w[:40]])
