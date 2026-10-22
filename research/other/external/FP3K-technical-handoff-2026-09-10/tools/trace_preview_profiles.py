"""Execute stock descriptor builder for every known processing profile.
Read-only firmware; no peripheral or allocator simulation and no camera writes.
"""
import struct,json,hashlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'analysis/firmware/preview'
b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
profiles=json.loads((ROOT/'analysis/firmware/raw-profiles.json').read_text())
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0xc0000000,(len(b)+4095)&~4095);u.mem_write(0xc0000000,b);u.mem_protect(0xc0000000,(len(b)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
u.mem_map(0x10000000,0x10000)
PARAM,SOURCE,DESC,CTX,SP=0x10000100,0x10000300,0x10000600,0x10000800,0x1000fff0
u.hook_add(UC_HOOK_MEM_WRITE,lambda uc,ac,a,n,v,d: check(a,n))
def check(a,n):assert DESC<=a and a+n<=DESC+0xc0 or 0x10008000<=a and a+n<=SP,hex(a)
def put(a,v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
rows=[]
for row in profiles['rows']:
 put(PARAM,row['words']+[6064,4042]);u.mem_write(SOURCE,bytes(0x60));put(SOURCE,[row['profile_ids'][0],PARAM]);put(SOURCE+0x58,[0xc0bd04b0]);put(CTX,[0,0]);u.mem_write(DESC,bytes(0xc0))
 for reg,v in [(UC_ARM_REG_R0,DESC),(UC_ARM_REG_R1,SOURCE),(UC_ARM_REG_R2,CTX),(UC_ARM_REG_SP,SP),(UC_ARM_REG_LR,0xc0000000)]:u.reg_write(reg,v)
 u.emu_start(0xc0438018,0xc0000000,count=20000)
 assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and u.reg_read(UC_ARM_REG_SP)==SP
 d=list(struct.unpack('<48I',u.mem_read(DESC,0xc0)))
 rows.append(dict(row=row['index'],ids=row['profile_ids'],raw=d[:2],preview=d[22:24],preview_target=d[26:28],preview_zoom=d[40:42],preview_reduction_enums=d[42:44],descriptor=d))
OUT.mkdir(exist_ok=True);(OUT/'stock-descriptors.json').write_text(json.dumps(dict(rows=rows,limitations='Native descriptor construction only. Profile IDs do not establish live sensor/display routing.'),indent=2)+'\n')
for r in rows:
 if any(x in [1,2,3,17,41,42,81,82,429] for x in r['ids']):print({k:v for k,v in r.items() if k!='descriptor'})
print('Preview groups:',sorted(set(tuple(r['preview']) for r in rows)))
