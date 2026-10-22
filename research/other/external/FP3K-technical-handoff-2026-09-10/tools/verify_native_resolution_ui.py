"""Verify stock resolution-to-UI-variable message encoding, without a camera."""
from pathlib import Path
import struct,json,hashlib
from unicorn import *
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parents[1]
b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
rows=[]
for value,index in [(3,0),(2,1),(4,2)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);n=(len(b)+4095)&~4095
 u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,b);u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
 u.mem_map(0x10000000,0x10000)
 u.mem_write(0x10000100,struct.pack('<II',0xc2dee8f8,0x10000200))
 u.mem_write(0x10000200,b[0x2dead3c:0x2dead44])
 events=[]
 def hook(uc,a,n,d):
  r=[uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
  if a==0xc0015058:uc.mem_write(r[0],bytes([r[1]&255])*r[2]);ret=r[0]
  elif a==0xc055e0f0:ret=0x10000800
  else:
   data=bytes(uc.mem_read(r[1],56));kind,flags,name,idx=struct.unpack_from('<4I',data)
   assert kind==2 and flags==0 and idx==index
   assert bytes(uc.mem_read(name,14))==b'MV_Resolution\0'
   assert data[16:]==bytes(40)
   events.append(dict(variable='MV_Resolution',index=idx,kind=kind));ret=0
  uc.reg_write(UC_ARM_REG_R0,ret);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in (0xc0015058,0xc055e0f0,0xc055e1e8):u.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
 u.reg_write(UC_ARM_REG_R0,0x10000100);u.reg_write(UC_ARM_REG_R1,value)
 u.reg_write(UC_ARM_REG_SP,0x1000fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
 u.emu_start(0xc05931d0,0xc0000000,count=10000)
 assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and len(events)==1
 rows.append(dict(native_enum=value,events=events,passed=True))
report=dict(cases=rows,ui_method='0xc05931d0',message_builder='0xc055dd10',queue_boundary='0xc055e1e8',limitations='Memory fill, UI service singleton and queue delivery mocked. Proves message encoding only; does not add or draw a third menu choice.')
(ROOT/'analysis/firmware/menu-integration/native-resolution-ui-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
