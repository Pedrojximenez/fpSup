"""Trace fp 5.02 RAW reduction setup; peripherals are RAM, NOT pixel models."""
from pathlib import Path
import hashlib, json, struct
from unicorn import *
from unicorn.arm_const import *
from fullheight_candidate import plan as capture_plan
from preview_candidate import plan as preview_plan
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/reduction-method';OUT.mkdir(exist_ok=True)
main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
dat=(ROOT/'analysis/firmware/DAT1_c2ef6e00.bin').read_bytes()
sha=hashlib.sha256(main).hexdigest()
assert sha=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
profiles=json.loads((ROOT/'analysis/firmware/raw-profiles.json').read_text())
BASE=0x10000000; STACK=0x10010000; STOP=0xc0000000
PARAM,SOURCE,DESC,CTX,OBJ,RESULT=[BASE+i for i in (0x100,0x300,0x600,0x800,0x900,0xb00)]
reports=[]
for label,profile,patched in [('stock_UHD24',429,False),('current_3K24',429,True),('stock_UHD24_DC_crop',432,False)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 end=(0xc2ef6e00+len(dat)+4095)&~4095
 u.mem_map(0xc0000000,end-0xc0000000);u.mem_write(0xc0000000,main);u.mem_write(0xc2ef6e00,dat)
 if patched:
  for e in capture_plan()+preview_plan():u.mem_write(e['address'],struct.pack('<I',e['replacement']))
 u.mem_protect(0xc0000000,end-0xc0000000,UC_PROT_READ|UC_PROT_EXEC)
 u.mem_map(BASE,0x4000);u.mem_map(STACK,0x4000)
 mmio=[(0x300f0000,0x300f3000),(0x30100000,0x30101000),(0x30001000,0x30002000)]
 for lo,hi in mmio:u.mem_map(lo,hi-lo)
 def put(a,ws):u.mem_write(a,struct.pack('<'+'I'*len(ws),*ws))
 def words(a,n):return list(struct.unpack('<'+'I'*n,u.mem_read(a,4*n)))
 allowed=[];writes=[];calls=[]
 def guard(uc,access,a,n,v,data):
  assert any(lo<=a and a+n<=hi for lo,hi in allowed),hex(a)
  if any(lo<=a<a+n<=hi for lo,hi in mmio):writes.append({'address':hex(a),'size':n,'value':hex(v)})
 u.hook_add(UC_HOOK_MEM_WRITE,guard)
 def run(a,*args,stop=STOP,extra=()):
  allowed[:]=[(STACK,STACK+0x4000),*extra]
  u.reg_write(UC_ARM_REG_CPSR,0x13);u.reg_write(UC_ARM_REG_SP,STACK+0x3ff0);u.reg_write(UC_ARM_REG_LR,STOP)
  for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,v)
  u.emu_start(a,stop,count=100000);assert u.reg_read(UC_ARM_REG_PC)==stop,hex(u.reg_read(UC_ARM_REG_PC))
 row=next(r for r in profiles['rows'] if profile in r['profile_ids'])
 # Read the actual patched column values, not a manually substituted descriptor.
 p=[words(c['table']+row['index']*4,1)[0] for c in profiles['columns']]
 assert len(p)==65
 p += [6064 if profile==429 else 4176,4042 if patched else 3412 if profile==429 else 2174]
 put(PARAM,p);put(SOURCE,[profile,PARAM]);put(SOURCE+0x58,[0xc0bd04b0]);put(CTX,[0,0])
 run(0xc0438018,DESC,SOURCE,CTX,extra=[(DESC,DESC+0xc0)])
 desc=words(DESC,48)
 put(OBJ,[0xc2f1e654]);put(OBJ+0xd0,[0xc0b5fcc0])
 def mock(uc,a,n,data):
  if a==0xc0436590:rv=0x10002000
  elif a==0xc04370e8:put(uc.reg_read(UC_ARM_REG_R1),[DESC]);rv=0
  elif a==0xc0322e48:rv=OBJ
  else:raise AssertionError(hex(a))
  uc.reg_write(UC_ARM_REG_R0,rv);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in [0xc0436590,0xc04370e8,0xc0322e48]:u.hook_add(UC_HOOK_CODE,mock,begin=a,end=a)
 def observe(uc,a,n,data):
  ptr=uc.reg_read(UC_ARM_REG_R1)
  count=6 if a in (0xc0635de0,0xc0635df8) else 44
  calls.append({'entry':hex(a),'enabled':uc.reg_read(UC_ARM_REG_R0),'arguments':bytes(uc.mem_read(ptr,count)).hex()})
 for a in [0xc0635de0,0xc0635df8,0xc0635db0,0xc0635dc8]:u.hook_add(UC_HOOK_CODE,observe,begin=a,end=a)
 run(0xc031d988,RESULT,stop=0xc031dca0,extra=[(RESULT,RESULT+0x20),*mmio])
 addresses=sorted({int(x['address'],16) for x in writes})
 regs={hex(a):hex(words(a,1)[0]) for a in addresses}
 r={'case':label,'profile':profile,'descriptor_words':desc,'route_bytes':list(u.mem_read(RESULT,3)),
    'route_words':words(RESULT,8),'driver_calls':calls,'register_writes':writes,'final_registers':regs}
 reports.append(r)
 print(label,'route',r['route_bytes'],'zoom',desc[18:20], 'ratio MMIO', {k:v for k,v in regs.items() if k in ['0x300f0900','0x300f0908','0x300f090c','0x300f2900']})
a,b,c=reports
assert a['route_bytes']==b['route_bytes']==[0,0,1]
assert b['descriptor_words'][:2]==[3032,2020]
assert b['descriptor_words'][18:22]==[2048,2048,0,0]
assert b['driver_calls'][0]['arguments']=='010000080008'
assert b['final_registers']['0x300f0908']==b['final_registers']['0x300f090c']=='0x800'
assert b['final_registers']['0x300f0900']=='0x1'
assert b['final_registers']['0x300f2900']=='0x0'
assert c['descriptor_words'][18:22]==[1023,1023,0,0]
assert c['route_bytes']==[1,0,0]
assert c['route_words'][1]==1  # CrctCrmfToBufA, before the RAW zoom output.
# Both sensor reduction records have mode bit 1; this must not be named an
# interpolation selector without evidence. Ratio 2048 produces zero upper phase.
records=[main[0xb5f770+56*i:0xb5f770+56*(i+1)].hex() for i in range(2)]
report={'firmware_sha256':sha,'cases':reports,'sensor_reduction_records':records,
 'mocked':['descriptor acquisition and manager lookup','sensor singleton lookup','MMIO as ordinary RAM'],
 'executed':'Native descriptor construction, routing, ratio and binning configuration drivers; no pixel transformation is emulated.',
 'conclusion':'3K uses CrctRwzmToBufA with 2048/2048 ratios, zero programmed upper phases and separate RAW reduction factors 1/1. This does not identify the hardware kernel.',
 'limitations':['No pixel arithmetic or live register readback','Does not prove all photosites contribute','DC crop control is statically traced, not newly camera-tested']}
(OUT/'native-trace.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: three native paths, bounded writes, current 3K ratio and unity-ratio control checks')
