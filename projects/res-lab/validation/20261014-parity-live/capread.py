"""Read-only: the v22c capture (last virtual-profile record before/after ogc_canvas) vs the 9/29 reconstruction
(stock p13 column + the 25 archived 9/29 live pairs + canvas +0x30 = 239.76)."""
import json,re,struct,sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'20261012-m12-240-live'))
from common import *
import camera as C
C.live=live
REF=ROOT/'projects/res-lab/cards/20261014-cap/plain'
C.REFERENCE=REF;C.FACT=json.load(open(REF/'build.json'))['facts']
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'));import m12_240
img=open(ROOT/'out/MAIN_c0000000.bin','rb').read();iw=lambda a:struct.unpack_from('<I',img,a-0xC0000000)[0]
src=open(ROOT/'out/decomp/full/blk_c04.c').read();f=src[src.index('FUN_c0439d18(undefined4 *param_1,int param_2)'):];f=f[:f.index('\n}')]
cols=[int(x,16) for x in re.findall(r'DAT_(c0[0-9a-f]+) \+ param_2',f)]
ref=[iw(a+4*6) for a in cols]+[0x17B0,0xFCA]
for o,v in m12_240.ARCHIVED_PAIRS:ref[o//4]=v
ref[0x30//4]=0x436FC29F
name=sys.argv[1]
pf=live.putfile
r=C.snapshot();s=int(r['consumer_state'],16);cap=s-0x400
w=pf.mem_get(cap,4);raw=bytes(pf.read_bulk(cap,0x230))
before=list(struct.unpack_from('<67I',raw,0x10));after=list(struct.unpack_from('<67I',raw,0x120))
out={'hits':w[0],'pid':w[1],'canvas':hex(w[2]),'entry':r.get('picked_entry',{}).get('key'),
 'ours_vs_firmware':{hex(4*k):[before[k],after[k]] for k in range(67) if before[k]!=after[k]},
 'today_vs_0929':{hex(4*k):[after[k],ref[k]] for k in range(67) if after[k]!=ref[k]},
 'before':before,'after':after}
(HERE/f'cap-{name}.json').write_text(json.dumps(out,indent=1)+'\n')
print(json.dumps({k:out[k] for k in ('hits','pid','canvas','entry','ours_vs_firmware','today_vs_0929')},indent=1))
