"""Read-only: every word of the live firmware image that differs from out/MAIN_c0000000.bin, in 64 KiB chunks."""
import fcntl,json,struct,sys,time
from common import *
pf=live.putfile
img=open(ROOT/'out/MAIN_c0000000.bin','rb').read()
lo=int(sys.argv[1],16) if len(sys.argv)>1 else 0xC0000000
hi=int(sys.argv[2],16) if len(sys.argv)>2 else 0xC0000000+len(img)
CH=0x10000;diffs=[];t=time.monotonic()
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 B.idle()
 for a in range(lo,hi,CH):
  n=min(CH,hi-a);got=bytes(pf.read_bulk(a,n,'      '))
  assert len(got)==n,(hex(a),len(got))
  ref=img[a-0xC0000000:a-0xC0000000+n]
  if got!=ref:
   for o in range(0,n,4):
    if got[o:o+4]!=ref[o:o+4]:diffs.append((hex(a+o),ref[o:o+4][::-1].hex(),got[o:o+4][::-1].hex()))
print('read',hex(lo),hex(hi),round(time.monotonic()-t,1),'s; words differ:',len(diffs),file=sys.stderr)
(HERE/f'codediff-{lo:08x}-{hi:08x}.json').write_text(json.dumps(diffs,indent=0)+'\n')
