"""Read-only: each virtual mode's cloned rows vs the closest native row in the stock descriptor tables."""
import fcntl,json,struct,sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'20261012-m12-240-live'))
from common import *
import camera as C
C.live=live
REF=ROOT/'projects/res-lab/cards/20261014-hookcnt/plain'
C.REFERENCE=REF;C.FACT=json.load(open(REF/'build.json'))['facts']
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'));import ogc_layout as L
pf=live.putfile
def W(a,n=1):
 v=pf.mem_get(a,n);assert len(v)==n and None not in v,(hex(a),n);return v
def rd(a,n):
 b=pf.read_bulk(a,(n+3)&~3);assert len(b)>=n;return bytes(b[:n])
out={}
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 r=C.snapshot();s=int(r['consumer_state'],16)
 nvm=r['state']['NVM'];vms=s+r['state']['VMS']
 desc=W(L.IMAGER)[0];regd=L.REGDESC
 out['desc']=hex(desc)
 for i in range(nvm):
  vm=vms+i*L.VM['SIZE'];h=W(vm,0x50//4)
  v={'id':h[0],'donor':h[1],'filled':h[2],'regfilled':h[3],'zfilled':h[4],'tw0':hex(h[5]),'tw1':hex(h[6]),'nom':h[7],
     'clamp':h[0x3C//4],'r10':h[0x40//4],'r10ok':h[0x44//4],'novr':h[0x4C//4]}
  if v['novr']:v['ovr']=[W(s+h[0x48//4]+12*k,3) for k in range(v['novr'])]
  tabs={}
  for t,(name,bf,cf,stride) in enumerate(L.TABLES):
   ptr=h[0x20//4+t]
   if not ptr:tabs[name]='no clone';continue
   d=regd if name=='REG' else desc
   base,cnt=W(d+bf)[0],W(d+cf)[0]
   mine=rd(ptr,stride);rows=rd(base,stride*cnt)
   best=min(range(cnt),key=lambda k:sum(a!=b for a,b in zip(mine,rows[k*stride:(k+1)*stride])))
   nat=rows[best*stride:(best+1)*stride]
   diffs=[(o,mine[o:o+4].hex(),nat[o:o+4].hex()) for o in range(0,stride,4) if mine[o:o+4]!=nat[o:o+4]]
   tabs[name]={'ptr':hex(ptr),'best_native_row':best,'count':cnt,'diff_words':diffs}
  v['tables']=tabs;out[f'vm{i}']=v
 (HERE/'rowdiff.json').write_text(json.dumps(out,indent=1)+'\n');print(json.dumps(out,indent=1))
