"""Exercise native movie resolution setting path using captured screen state.
Mocks service lookup, backing setting storage, logging and notification delivery;
not a camera pipeline or persistence test.
"""
from pathlib import Path
import struct,json,hashlib
from unicorn import *
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parents[1];b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
screen=(ROOT/'diagnostics/menu-native-v1-return/SSD/FP3KMN/SCREEN2.BIN').read_bytes();assert struct.unpack_from('<I',screen,0x24)[0]==0xc3768d84
cases=[]
for label,index,old,busy,expected in [('UHD-to-FHD',1,3,False,2),('FHD-to-UHD',0,2,False,3),('same-UHD',0,3,False,3),('third-value',2,3,False,4),('invalid-index',3,3,False,0),('reentrant-guard',1,3,True,3)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);size=(len(b)+4095)&~4095;u.mem_map(0xc0000000,size);u.mem_write(0xc0000000,b);u.mem_protect(0xc0000000,size,UC_PROT_READ|UC_PROT_EXEC)
 for page in [0xc3785000,0xc37b7000,0xc3768000,0xc31ac000,0xc31ca000]:u.mem_map(page,4096)
 u.mem_map(0x10000000,0x10000)
 def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 u.mem_write(0xc3785308,screen);put(0xc37b7538,0xc3785308);u.mem_write(0xc37b7724,b[0x2dead3c:0x2dead44]);u.mem_write(0xc3768d84,b[0xcde030:0xcde034]);put(0xc31ac5a0,0xc07397d8)
 put(0x10000c00,0xc31ac59c);prop=0xc31acc1c;put(prop,0x69,0,0,0xc07421bc,0,0,0);u.mem_write(prop+0x10,bytes([int(busy)]));put(0x10000d00,old);put(0x10000308,index)
 notified=[];writes=[]
 def hook(uc,a,n,d):
  regs=[uc.reg_read(x) for x in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
  if a==0xc0057ae8:ret=0x10000c00
  elif a==0xc00b5c28:ret=0x10000d00
  elif a==0xc00911a0:notified.append(regs);ret=0
  else:ret=0
  uc.reg_write(UC_ARM_REG_R0,ret);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in [0xc0057ae8,0xc00b5c28,0xc0019dc0,0xc001a048,0xc00911a0]:u.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
 def guard(uc,access,a,n,v,d):
  assert prop<=a and a+n<=prop+28 or 0x10000000<=a and a+n<=0x10010000,hex(a)
  if a==0x10000d00:writes.append(v)
 u.hook_add(UC_HOOK_MEM_WRITE,guard)
 u.reg_write(UC_ARM_REG_R0,0x10000300);u.reg_write(UC_ARM_REG_R1,0);u.reg_write(UC_ARM_REG_SP,0x1000fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
 u.emu_start(0xc057a6a0,0xc0000000,count=30000);assert u.reg_read(UC_ARM_REG_PC)==0xc0000000
 assert get(0x10000d00)==expected,(label,get(0x10000d00));assert bool(notified)==(not busy and old!=expected),(label,notified)
 cases.append({'case':label,'selection_index':index,'before':old,'after':expected,'backing_storage_writes':writes,'notifications':notified,'passed':True})
report={'cases':cases,'captured_receiver':'0xc3768d84','receiver_constructor':'0xc04acda8','receiver_vtable':'0xc0cde064','receiver_resolution_setter':'0xc04aae70','setting_setter':'0xc005c020','property_address_from_stock_factory':'0xc31acc1c','property_id':105,'notification_boundary':'0xc00911a0','mocked':['settings service singleton','backing setting location','logging','notification delivery'],'limitations':'No pipeline restart, event delivery, display update, persistence, electrical hardware or inter-thread synchronization emulated. Reentrant property flag is not a recording lock. Third/invalid values being accepted here does not make them safe capture modes.'}
(ROOT/'analysis/firmware/menu-integration/native-setter-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
