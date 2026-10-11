"""Offline only: execute the exact r78 panel and recipe from the frozen VBIN.

The panel entry 0x1a8b and state offsets below are verified from its Thumb
instructions, not today's struct. GUI posting, settings and lookup are stubs;
geometry, table writes and recipe calculation are the original instructions.
No old loader or historical fixed addresses are used on a physical camera.
"""
from pathlib import Path
import struct,json,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_INVALID
from unicorn.arm_const import *
R=Path(__file__).resolve().parents[4]
p=R/'projects/res-lab/cards/20261004-b25-menu-r78-isopreview/fast-debug/fpSup.BIN';b=p.read_bytes()
assert hashlib.sha256(b).hexdigest()=='4c39061502bfe82f3e43347488464fb942b588aeb366925399b519b97e239543'
n=struct.unpack_from('<I',b,4)[0];at=16+8*n;rec=[]
for i in range(n):
 a,z=struct.unpack_from('<II',b,16+8*i);rec.append((a,b[at:at+z]));at+=(z+3)&~3
menu=next(d for a,d in rec if not a and len(d)==23120)
image=(R/'out/MAIN_c0000000.bin').read_bytes();u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
for a,z in ((0xc0000000,0x4000000),(0x10000000,0x100000),(0x40000000,0x40000)):u.mem_map(a,z)
u.mem_write(0xc0000000,image)
for a,d in rec:
 if a>=0xc0000000:u.mem_write(a,d)
u.mem_write(0x10000000,menu)
def w(a,v):u.mem_write(a,struct.pack('<I',v))
def r(a):return struct.unpack('<I',u.mem_read(a,4))[0]
w(0xc343b588,0xc2f1e654);w(0xc2f1e654,0xc0b59500);w(0xc2f1e654+4,70);w(0xc2f1e654+8,0xc0b59dc0);w(0xc2f1e654+12,70)
w(0xc37b7048,0x40010000)
m=0x40000000
w(m+4,0x40010000)
for off,v in {0x41c:1,0x434:1,0x490:992,0x494:662,0x498:1,0x49c:1,0x4ac:0,0x4b0:2016,0x4b4:672,0x4bc:3,0x4c0:6}.items():w(m+off,v)
u.mem_write(m+0x440,b'\x0c')
stubs={0xc0593f30:0,0xc0593fe0:0,0xc0057ae8:0x40020000,0xc005c0f0:3,0xc005bf28:0,0xc002b920:1000,0xc05db418:0}
for a in stubs:u.mem_write(a,struct.pack('<I',0xe12fff1e))
calls=[]
def step(u,a,z,d):
 if a in stubs:
  if a==0xc05db418:w(u.reg_read(UC_ARM_REG_R2),0)
  u.reg_write(UC_ARM_REG_R0,stubs[a]);calls.append(hex(a));u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
 if 0x10000170<=a<0x10000000+len(menu) or 0xc0730c20<=a<0xc0731600:return
 raise AssertionError('unmodelled code '+hex(a))
u.hook_add(UC_HOOK_CODE,step)
u.hook_add(UC_HOOK_MEM_INVALID,lambda u,access,a,z,v,d: print("invalid",hex(a),"pc",hex(u.reg_read(UC_ARM_REG_PC))) or False)
def call(a):
 u.reg_write(UC_ARM_REG_R0,m);u.reg_write(UC_ARM_REG_SP,0x4002fff8);u.reg_write(UC_ARM_REG_LR,0x40030000)
 u.emu_start(a,0x40030000,count=2_000_000)
 assert u.reg_read(UC_ARM_REG_PC)==0x40030000
call(0x10001a8b)
row=r(0xc0bd0730);cols=[r(0xc0732670+4*i) for i in range(29)]
offs=[0,4,12,16,28,32,36,40,44,56,88,92,96,100,136,144,192,196,200,208,212,216,220,224,228,244,248,252,256]
canvas={hex(o):r(c+row*4) for o,c in zip(offs,cols)}
profiles=json.loads((R/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
full=[r(c['table']+row*4) if isinstance(c['table'],int) else r(int(c['table'],0)+row*4) for c in profiles['columns']]
report={'sha256':hashlib.sha256(b).hexdigest(),'panel_entry_offset':'0x1a8b','mapping_row':row,'canvas':canvas,'row':full,'standby':[r(m+0x438),r(m+0x43c)],'axis':list(struct.unpack('<9I',u.mem_read(0xc0732490,36))),'calls':sorted(set(calls))}
call(0xc0730c20)
report['recipe']=list(struct.unpack('<27I',u.mem_read(0xc07324c0,108)));count=r(0xc0732560)
report['recipe_canvas']=dict((hex(a),v) for a,v in struct.iter_unpack('<2I',u.mem_read(0xc0732564,count*8)))
print(json.dumps(report,indent=2));(R/'projects/res-lab/validation/20261009-recording-formula/frozen-r78.json').write_text(json.dumps(report,indent=2)+'\n')
