"""Execute stock movie UI mapping/callback; mock only the unknown settings sink."""
from pathlib import Path
import struct,json,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_PROT_READ,UC_PROT_EXEC
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parents[1];b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);n=(len(b)+4095)&~4095;u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,b);u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
u.mem_map(0xc37b7000,4096);u.mem_map(0x10000000,0x10000)
def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
# Stock constructor seeds the two-word enum provider from this ROM template.
u.mem_write(0xc37b7724,b[0x2dead3c:0x2dead44]);put(0xc37b7538,0x10000100)
put(0x10000100,0xc0d19654);put(0x10000124,0x10000200);put(0x10000134,0xc37b7724)
put(0x10000200,0x10000400);put(0x10000400+0x13c,0x10000800)
seen=[]
def sink(uc,a,n,d):
 seen.append([uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)])
 uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,sink,begin=0x10000800,end=0x10000800)
cases=[]
for index,expected in [(0,3),(1,2),(2,4),(3,0),(0xffffffff,0)]:
 put(0x10000308,index);u.reg_write(UC_ARM_REG_R0,0x10000300);u.reg_write(UC_ARM_REG_R1,0);u.reg_write(UC_ARM_REG_SP,0x1000fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
 seen.clear();u.emu_start(0xc057a6a0,0xc0000000,count=1000)
 assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and seen==[[0x10000200,expected,0]],seen
 cases.append({'index':index,'dispatched_value':expected,'passed':True})
report={'cases':cases,'provider_template':'0xc2dead3c','provider_vtable':'0xc2dead7c','slot_0x5c':'0xc06bda30','pairs_address':'0xc2e4020c','pairs':[[3,0],[2,1],[4,2]],'scope':'Native callback, stock screen getter, native enum provider and reverse lookup executed. Screen and event constructed in mock RAM; settings receiver sink mocked. Does not validate live object identity, rendering, persistence, transition or new third-item semantics.'}
(ROOT/'analysis/firmware/menu-integration/native-callback-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
