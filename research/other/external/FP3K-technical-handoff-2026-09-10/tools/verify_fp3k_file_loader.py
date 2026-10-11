"""ARM-execute file loader and existing F1; mock filesystem/cache APIs only."""
from pathlib import Path
import json, struct
from unicorn import *
from unicorn.arm_const import *
from build_fp3k_file_loader import build,BASE,ROOT,DEST
from fullheight_candidate import plan
loader,payload,manifest=build()
main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
results=[]
for name in ['valid','missing','empty','short','bad_checksum','busy','wrong_stock','stale_valid_short']:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);n=(len(main)+4095)&~4095
 u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,main)
 u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
 entries=plan();base=0xc072de64;status=0xc072e800;echo=0xc0bac2f8
 for page in {base&~4095,BASE&~4095,status&~4095,echo&~4095,*[e['address']&~4095 for e in entries]}:u.mem_protect(page,4096,UC_PROT_ALL)
 for page in [0xc343b000,0xc3476000,0xc347e000,0xc358e000,0xc35a9000]:u.mem_map(page,4096)
 u.mem_map(0x10000000,0x10000)
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 u.mem_write(BASE,loader);put(echo,BASE);put(0xc343b58c,0 if name=='busy' else 8)
 if name=='wrong_stock':put(entries[0]['address'],0)
 if name=='stale_valid_short':u.mem_write(base,payload)
 before={e['address']:get(e['address']) for e in entries};events=[];entered=[]
 def hook(uc,a,n,d):
  r=[uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  assert get(echo)==0xc03d99a0
  events.append(hex(a));ret=0
  if a==0xc0365e90:assert r[1]==1
  elif a==0xc0365fb0:
   assert bytes(uc.mem_read(r[1],10))==b'\\FP3K.BIN\0';assert r[2]==1
   ret=int(name!='missing')
  elif a==0xc0366060:
   assert r[1]==base and r[2]==len(payload)
   data=payload
   if name=='empty':data=b''
   elif name in ('short','stale_valid_short'):data=payload[:100]
   elif name=='bad_checksum':data=payload[:-4]+bytes([payload[-4]^1])+payload[-3:]
   uc.mem_write(r[1],data);put(r[3],len(data));ret=1
  elif a==0xc0365ed0:assert r[1]==2
  uc.reg_write(UC_ARM_REG_R0,ret);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in [0xc0444658,0xc0444698,0xc0365e90,0xc0365fb0,0xc0366060,0xc0365ed0,0xc000e91c]:u.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
 u.hook_add(UC_HOOK_CODE,lambda uc,a,n,d:entered.append(a),begin=base,end=base)
 def writeguard(uc,access,a,n,v,d):
  assert 0x10000000<=a and a+n<=0x10010000 or status<=a and a+n<=status+16 or a==echo or a in before,hex(a)
 u.hook_add(UC_HOOK_MEM_WRITE,writeguard)
 regs=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8]
 for i,r in enumerate(regs):u.reg_write(r,0x5500+i)
 u.reg_write(UC_ARM_REG_SP,0x1000fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
 u.emu_start(BASE,0xc0000000,count=20000)
 assert u.reg_read(UC_ARM_REG_PC)==0xc0000000
 assert u.reg_read(UC_ARM_REG_SP)==0x1000fff0
 assert [u.reg_read(r) for r in regs]==list(range(0x5500,0x5505))
 expected={'valid':16,'missing':33,'empty':34,'short':34,'bad_checksum':35,'busy':3,'wrong_stock':4,'stale_valid_short':34}[name]
 assert get(status+4)==expected,(name,get(status+4))
 assert bool(entered)==(name in ('valid','busy','wrong_stock'))
 assert events.count(hex(0xc0365ed0))==1
 assert (hex(0xc000e91c) in events)==bool(entered)
 for e in entries:assert get(e['address'])==(e['replacement'] if name=='valid' else before[e['address']])
 results.append({'case':name,'status':expected,'payload_entered':bool(entered),'passed':True})
report={'cases':results,'loader_sha256':manifest['loader_sha256'],'mocked':'File manager, volume lookup, file object/open/read/destructor, cache synchronization. Actual F1 guard/application code executed.','limitations':'No real storage timing, filesystem readiness, cache hardware, camera boot, or menu integration tested.'}
(DEST/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
