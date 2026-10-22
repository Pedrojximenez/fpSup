"""Exercise installed ARM hooks and reversible 3K tables in a bounded emulator.
Settings backing service and UI queue are mocks; stock enum-to-UI mapping runs.
"""
import struct,json
from unicorn import *
from unicorn.arm_const import *
from build_fp3k_native_menu import build,BASE,STATE,OUT,HOOKS,CONFIG,UI_RANGE
from native_resolution_resource import CSV,RESOURCE
code,syms,entries,main,manifest=build()
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
SAVED=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10]
class Camera:
 def __init__(self):
  u=self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);n=(len(main)+4095)&~4095
  u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,main);u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
  for page in {BASE&~4095,STATE&~4095,*[a&~4095 for a,l in HOOKS],*[e['address']&~4095 for e in entries],RESOURCE&~4095,UI_RANGE&~4095}:u.mem_protect(page,4096,UC_PROT_ALL)
  for page in [0xc343b000,0xc3476000,0xc347e000,0xc358e000,0xc35a9000,0xc31ac000]:u.mem_map(page,4096)
  u.mem_map(0x10000000,0x20000);u.mem_write(BASE,code)
  self.values={'resolution':3,'format':0,'quality':0,'rate':12,'crop':0,'media':5};self.events=[];self.table_writes=[];self.injection=None
  self.put(0xc343b58c,8)
  for offset,v in CONFIG:
   self.put(0xc31ac59c+offset+0x14,v);u.mem_write(0xc31ac59c+offset+5,b'\1')
  self.put(0x10000100,0xc2dee8f8,0x10000200);u.mem_write(0x10000200,main[0x2dead3c:0x2dead44])
  self.put(STATE+20,0x10000100)
  self.setters={a+4:l[4:] for a,l in HOOKS if l.startswith('set_')}
  self.getters={0xc005c058:'resolution',0xc005be90:'format',0xc005bf28:'quality',0xc005c0f0:'rate',0xc005bb98:'crop'}
  addresses=[0xc000e91c,0xc0057ae8,0xc0444658,0xc0444698,0xc0593f30,*self.setters,*self.getters]
  for a in addresses:u.hook_add(UC_HOOK_CODE,self.boundary,begin=a,end=a)
  u.hook_add(UC_HOOK_MEM_WRITE,self.guard)
  u.hook_add(UC_HOOK_CODE,self.inject)
 def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
 def get(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def tables(self):return [self.get(e['address']) for e in entries]
 def active(self):return self.get(STATE+16)
 def guard(self,u,access,a,n,v,d):
  allowed=(a==UI_RANGE and n==4) or 0x10000000<=a and a+n<=0x10020000 or STATE<=a and a+n<=STATE+64 or RESOURCE<=a and a+n<=RESOURCE+89 or any(a==x and n==4 for x,l in HOOKS) or any(a==e['address'] and n==4 for e in entries)
  assert allowed,hex(a)
  critical=a==UI_RANGE or RESOURCE<=a<RESOURCE+89 or any(a==x for x,l in HOOKS) or any(a==e['address'] and n==4 for e in entries)
  if critical:assert u.reg_read(UC_ARM_REG_CPSR)&0xc0==0xc0,hex(a)
  if any(a==e['address'] for e in entries):self.table_writes.append((a,v))
 def inject(self,u,a,n,d):
  if self.injection:self.injection(self,a)
 def boundary(self,u,a,n,d):
  r=[u.reg_read(x) for x in REGS];ret=0
  if a in self.setters:
   name=self.setters[a]
   # Only the callback's own native resolution write may retain active tables.
   internal=self.get(STATE+24)
   if self.active():assert internal and name=='resolution'
   self.events.append(('setting',name,r[1],self.active()))
   self.values[name]=r[1]
   if name in ['crop','format','quality','rate']:
    i=['crop','format','quality','rate'].index(name);self.put(0xc31ac59c+CONFIG[i][0]+0x14,r[1])
   # Trampoline has executed the displaced push; return using that frame.
   sp=u.reg_read(UC_ARM_REG_SP);v=struct.unpack('<4I',u.mem_read(sp,16))
   for reg,val in zip(SAVED[:3],v[:3]):u.reg_write(reg,val)
   u.reg_write(UC_ARM_REG_SP,sp+16);u.reg_write(UC_ARM_REG_R0,0xabc);u.reg_write(UC_ARM_REG_PC,v[3]);return
  elif a in self.getters:ret=self.values[self.getters[a]]
  elif a==0xc0057ae8:ret=0x10000600
  elif a==0xc0444698:ret=self.values['media']
  elif a==0xc0593f30:
   assert u.reg_read(UC_ARM_REG_CPSR)&0xc0==self.irq
   name=bytes(u.mem_read(r[1],14))
   assert name in (b'MV_Resolution\0',b'LV_Resolution\0')
   if name==b'MV_Resolution\0':self.events.append(('display',r[2]))
  u.reg_write(UC_ARM_REG_R0,ret);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def run(self,address,*args,irq=0):
  u=self.u;self.irq=irq
  u.reg_write(UC_ARM_REG_CPSR,0x13|irq)
  for i,r in enumerate(SAVED):u.reg_write(r,0x5510+i)
  for r,v in zip(REGS,args):u.reg_write(r,v)
  u.reg_write(UC_ARM_REG_SP,0x1001fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
  u.emu_start(address,0xc0000000,count=100000)
  assert u.reg_read(UC_ARM_REG_PC)==0xc0000000,hex(u.reg_read(UC_ARM_REG_PC))
  assert u.reg_read(UC_ARM_REG_SP)==0x1001fff0
  assert [u.reg_read(r) for r in SAVED]==list(range(0x5510,0x5517))
  assert u.reg_read(UC_ARM_REG_CPSR)&0xc0==irq
  return u.reg_read(UC_ARM_REG_R0)
 def install(self):
  self.run(BASE)
  assert self.get(STATE+4)==16 and not self.active()
  assert bytes(self.u.mem_read(RESOURCE,89))==CSV
  assert self.get(UI_RANGE)==0x40
  self.run(0xc05931d0,0x10000100,3)
 def select(self,index):
  self.put(0x10000408,index);self.run(0xc057a6a0,0x10000400,0)
 def assert_stock(self):assert self.tables()==[e['expected'] for e in entries] and not self.active()
 def assert_3k(self):assert self.tables()==[e['replacement'] for e in entries] and self.active()==1
results=[]
def passed(name,**extra):results.append(dict(case=name,passed=True,**extra))
# Real installed branch targets, repeated selection, both stock exits, UI indices.
for exit_index in (0,1):
 c=Camera();c.install();c.assert_stock();c.select(2);c.assert_3k()
 assert c.events[-1]==('display',2)
 assert [x for x in c.events if x[0]=='setting'][-1][2]==3
 writes=len(c.table_writes);c.select(2);assert len(c.table_writes)==writes
 c.select(exit_index);c.assert_stock();assert c.values['resolution']==(3 if exit_index==0 else 2)
 assert c.events[-1]==('display',exit_index)
 passed('select3K-and-exit-'+str(exit_index))
# Guard each live busy signal before touching tables or settings.
for a,size,value in [(0xc343b58c,4,151),(0xc3476609,1,1),(0xc347e08f,1,1),(0xc358e140,4,1),(0xc35a952c,4,1)]:
 c=Camera();c.install();c.u.mem_write(a,value.to_bytes(size,'little'));c.select(2);c.assert_stock();assert not c.table_writes
 passed('busy-'+hex(a))
for name,value in [('format',1),('quality',3),('rate',1),('crop',1),('media',1)]:
 c=Camera();c.install();c.values[name]=value;c.select(2);c.assert_stock();assert not c.table_writes
 passed('unsupported-'+name)
for i in (3,0xffffffff):
 c=Camera();c.install();c.select(i);c.assert_stock();assert not [e for e in c.events if e[0]=='setting']
 passed('invalid-index-'+str(i))
for a,name in HOOKS:
 if not name.startswith('set_'):continue
 c=Camera();c.install();c.select(2);c.assert_3k();c.run(a,0x10000600,1,0);c.assert_stock()
 assert c.events[-1][0]=='display';passed('setting-restores-'+name)
 c=Camera();c.install();c.select(2);c.put(0xc343b58c,151);before=len([x for x in c.events if x[0]=='setting'])
 c.run(a,0x10000600,1,0);c.assert_3k();assert len([x for x in c.events if x[0]=='setting'])==before
 passed('busy-blocks-'+name)
# Every table word is verified before either direction writes anything.
for i,e in enumerate(entries):
 for active in (False,True):
  c=Camera();c.install()
  if active:c.select(2)
  c.put(e['address'],0xbad00000+i);before=c.tables();writes=len(c.table_writes)
  c.select(0 if active else 2)
  assert c.tables()==before and c.active()==int(active) and len(c.table_writes)==writes
  passed('table-mismatch-'+str(i)+'-'+str(active))
# Cache changed after getter validation, including invalid cache: reject.
for i,(offset,v) in enumerate(CONFIG):
 for valid in (False,True):
  c=Camera();c.install()
  def race(cam,a):
   if a==BASE+syms['transition']:
    if valid:cam.put(0xc31ac59c+offset+0x14,v^1)
    else:cam.u.mem_write(0xc31ac59c+offset+5,b'\0')
  c.injection=race;c.select(2);c.assert_stock();assert not c.table_writes
  passed('cache-race-'+str(i)+'-'+str(valid))
# Readback rollback and preservation of incoming IRQ/FIQ bits.
for active in (False,True):
 for irq in (0,0x80,0xc0):
  c=Camera();c.install()
  if active:c.select(2)
  fired=[False]
  def fault(cam,a):
   if a==BASE+syms['verify_transition'] and not fired[0]:cam.put(entries[0]['address'],0);fired[0]=True
  c.injection=fault;c.run(BASE+syms['transition'],int(not active),irq=irq)
  (c.assert_3k if active else c.assert_stock)()
  passed('rollback-'+str(active)+'-'+hex(irq))
# Installer does not alter resources/hooks when preflight is wrong.
for address in [a for a,l in HOOKS]+[RESOURCE,UI_RANGE]+[e['address'] for e in entries]:
 c=Camera();c.put(address,c.get(address)^1);old_resource=bytes(c.u.mem_read(RESOURCE,89));old_hooks=[c.get(a) for a,l in HOOKS]
 c.run(BASE);assert c.get(STATE+4)==0x31
 assert bytes(c.u.mem_read(RESOURCE,89))==old_resource and [c.get(a) for a,l in HOOKS]==old_hooks
 passed('install-preflight-'+hex(address))
c=Camera();c.u.mem_write(BASE+syms['csv_new'],b'X');c.run(BASE);assert c.get(STATE+4)==0x32;passed('install-checksum')
c=Camera();fired=[False]
def install_fault(cam,a):
 if a==BASE+syms['verify_install'] and not fired[0]:cam.put(HOOKS[0][0],0);fired[0]=True
c.injection=install_fault;c.run(BASE);assert c.get(STATE+4)==0x33
assert bytes(c.u.mem_read(RESOURCE,89))==main[RESOURCE-0xc0000000:RESOURCE-0xc0000000+89]
assert [c.get(a) for a,l in HOOKS]==[struct.unpack_from('<I',main,a-0xc0000000)[0] for a,l in HOOKS]
assert c.get(UI_RANGE)==0x803f
passed('install-rollback')
c=Camera();fired=[False]
def range_fault(cam,a):
 if a==BASE+syms['verify_install'] and not fired[0]:cam.put(UI_RANGE,0);fired[0]=True
c.injection=range_fault;c.run(BASE);assert c.get(STATE+4)==0x33 and c.get(UI_RANGE)==0x803f
assert bytes(c.u.mem_read(RESOURCE,89))==main[RESOURCE-0xc0000000:RESOURCE-0xc0000000+89]
assert [c.get(a) for a,l in HOOKS]==[struct.unpack_from('<I',main,a-0xc0000000)[0] for a,l in HOOKS]
passed('install-range-rollback')
report=dict(payload_sha256=manifest['sha256'],cases=results,limitations='Native entry branches, trampolines, interrupt masking, UI enum mapping, table transactions and rollback executed. Settings backing operations, filesystem/media routing and UI queue delivery mocked. No real camera timing, DMA, cross-core execution, resource caching or on-screen rendering verified.')
(OUT/'resident-verification.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS',len(results),'cases;',manifest['bytes'],'bytes;',manifest['sha256'])
