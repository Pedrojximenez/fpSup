"""Execute the display-fit trampoline and native rectangle calculation.

Device/environment selectors use explicit fixtures. Native aspect fitting,
descriptor reads/writes and floating-point helpers execute without mocks.
This cannot establish which branch the physical camera uses.
"""
import hashlib,json,struct
from pathlib import Path
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from verify_fp3k_native_menu import Camera,BASE,STATE,code,syms

ROOT=Path(__file__).resolve().parents[1]
cases=[]
OBJ,DEVICE,DESC=0x10002000,0x10002100,0x10002200
for active in (0,1,2):
 for device in (1,4,5,29):
  for flags in (0x13,0xf80000d3):
   c=Camera();c.install();u=c.u;c.put(STATE+16,active)
   c.put(OBJ,DEVICE);c.put(DEVICE+8,device)
   regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_LR]
   vals=list(range(0x5500,0x5500+len(regs)));vals[4]=OBJ;vals[5]=DESC
   for r,v in zip(regs,vals):u.reg_write(r,v)
   u.reg_write(UC_ARM_REG_SP,0x1001fff0);u.reg_write(UC_ARM_REG_CPSR,flags)
   u.emu_start(0xc0306ea0,0xc0306ea4,count=200)
   yes=active==1 and device==1
   assert u.reg_read(UC_ARM_REG_PC)==0xc0306ea4
   assert u.reg_read(UC_ARM_REG_R0)==(2 if yes else 3)
   assert [u.reg_read(r) for r in regs[1:]]==vals[1:]
   assert u.reg_read(UC_ARM_REG_SP)==0x1001fff0
   assert u.reg_read(UC_ARM_REG_CPSR)==flags
   assert c.get(STATE+56)==(3 if yes else 1) and c.get(STATE+60)==DESC
   cases.append(dict(case=f'trampoline-active{active}-device{device}-flags{flags:x}',passed=True))

# Native top-level display method, with two environment predicates determining
# whether its movie-fit branch is selected. No mock replaces rectangle math.
for active,device,branch in [(0,1,True),(1,1,True),(1,5,True),(1,1,False)]:
 c=Camera();c.install();u=c.u;c.put(STATE+16,active)
 c.put(OBJ,DEVICE);c.put(DEVICE+8,device)
 u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
 # Full native output rectangle in a 3:2 display raster.
 u.mem_write(DESC+0x60,struct.pack('<6H',1620,1080,1620,1080,0,0))
 u.mem_write(DESC+0x78,struct.pack('<6H',1620,1080,1620,1080,0,0))
 before=bytes(u.mem_read(DESC,0xa0))
 environment={0xc02e9e00:2,0xc0307280:0,0xc0307408:int(branch),0xc0307520:0,0xc0021c00:0x10003000,0xc0021c40:0x10003000}
 def boundary(uc,a,n,d):
  uc.reg_write(UC_ARM_REG_R0,environment[a]);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in environment:u.hook_add(UC_HOOK_CODE,boundary,begin=a,end=a)
 writes=[]
 def bounded(uc,access,a,n,v,d):
  assert (0x10010000<=a and a+n<=0x1001fff0) or (DESC<=a and a+n<=DESC+0xa0) or (STATE+56<=a and a+n<=STATE+64),hex(a)
  if DESC<=a<DESC+0xa0:writes.append((a-DESC,n))
 u.hook_add(UC_HOOK_MEM_WRITE,bounded)
 try:c.run(0xc0306df8,OBJ,DESC)
 except Exception:
  print("native case",active,device,branch,"pc",hex(u.reg_read(UC_ARM_REG_PC)))
  raise
 rect=struct.unpack('<4H',u.mem_read(DESC+0x7c,8))
 expected=(1620,1080,0,0) if (active==1 and device==1) or not branch else (1620,911,0,84)
 assert rect==expected,(active,device,branch,rect,expected)
 assert bytes(u.mem_read(DESC,0x7c))==before[:0x7c]
 assert c.get(STATE+56)==(3 if active==1 and device==1 else 1) if branch else c.get(STATE+56)==0
 cases.append(dict(case=f'native-fit-active{active}-device{device}-branch{branch}',rectangle=list(rect),writes=writes,passed=True))
report=dict(payload_sha256=hashlib.sha256(code).hexdigest(),cases=cases,
 limitations='Selector fixtures are not camera observations. Executes native display-fit math and bounded descriptor writes, not LCD rendering, refresh, overlay composition, or sensor coverage.')
out=ROOT/'prototype/development/native-menu/preview-layout-verification.json'
out.write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(cases),'preview layout cases')
