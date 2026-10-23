"""Read-only: vm0 clone rows vs the native row whose id word == donor (12), and vs row id 140."""
import fcntl,json,struct,sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'20261012-m12-240-live'))
from common import *
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'));import ogc_layout as L
pf=live.putfile
def W(a,n=1):
 v=pf.mem_get(a,n);assert len(v)==n and None not in v;return v
def rd(a,n):return bytes(pf.read_bulk(a,(n+3)&~3)[:n])
d=json.load(open(HERE/'rowdiff.json'));desc=int(d['desc'],16)
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for name,bf,cf,stride in L.TABLES:
  dd=L.REGDESC if name=='REG' else desc
  base,cnt=W(dd+bf)[0],W(dd+cf)[0];rows=rd(base,stride*cnt)
  ids=[struct.unpack_from('<I',rows,k*stride)[0] for k in range(cnt)]
  mine=rd(int(d['vm0']['tables'][name]['ptr'],16),stride)
  res={}
  for want in (12,140):
   if want not in ids:res[want]='absent';continue
   k=ids.index(want);nat=rows[k*stride:(k+1)*stride]
   res[want]=(k,[(o,mine[o:o+4].hex(),nat[o:o+4].hex()) for o in range(4,stride,4) if mine[o:o+4]!=nat[o:o+4]])
  print(name,'ids[:8]',ids[:8],'...');print(' ',res)
