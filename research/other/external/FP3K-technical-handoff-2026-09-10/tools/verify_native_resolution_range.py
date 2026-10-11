"""Execute native controlValue initialization and range wrapping from stock NBU values."""
import struct,json
from unicorn import *
from unicorn.arm_const import *
from native_resolution_resource import stock,ROOT
main,_=stock();ADDR=0xc1a7099c
record=main[ADDR-0xc0000000:ADDR-0xc0000000+40]
assert struct.unpack('>8I',record[:32])==(0x1000e,40,0x24fe0,5,0xffffffff,0x10a3,3,0xa)
# Descriptor at C2E027C8 identifies slots0..4 as min,max,value,loop,terminal-type.
names=[]
for i in range(5):
 p=struct.unpack_from('<I',main,0x2e027cc+i*12)[0]-0xc0000000
 names.append(main[p:].split(b'\0',1)[0].decode())
assert names==['min-value','max-value','value','is-value-loop','terminal-type']
rows=[]
for maxvalue,terminal in [(1.,0),(2.,0),(1.,1),(2.,1)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0xc0000000,(len(main)+4095)&~4095);u.mem_write(0xc0000000,main);u.mem_map(0x10000000,0x10000)
 u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
 state=0x10000200;plugin=0x10000100;value=0x10000300;flag=0x10000400
 properties=[0.,maxvalue,0.,1,terminal]
 def boundary(uc,a,n,d):
  r=[uc.reg_read(x) for x in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2]]
  if a==0xc06011f0:
   v=struct.unpack('<f',uc.mem_read(r[0],4))[0];assert v in [-1.,0.,1.,2.,3.]
   uc.mem_write(r[1],(str(v)+'\0').encode())
  elif a==0xc05d7148:uc.mem_write(r[1],struct.pack('<I',state))
  elif a in [0xc05d68d0,0xc05d6400]:
   assert 0<=r[1]<5;uc.mem_write(r[2],struct.pack('<f' if a==0xc05d68d0 else '<I',properties[r[1]]))
  uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in [0xc05d5e30,0xc05d7148,0xc05d68d0,0xc05d6400,0xc05e90a8,0xc0601140,0xc05fa998,0xc06011f0]:u.hook_add(UC_HOOK_CODE,boundary,begin=a,end=a)
 def run(a,args):
  for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
  u.reg_write(UC_ARM_REG_SP,0x1000fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
  try:u.emu_start(a|1,0xc0000000,count=20000)
  except UcError:
   print('Fault',hex(u.reg_read(UC_ARM_REG_PC)),[hex(u.reg_read(r)) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4]])
   raise
  assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and u.reg_read(UC_ARM_REG_SP)==0x1000fff0
 run(0xc05fab70,[plugin]);assert struct.unpack('<3f',u.mem_read(state+0x14,12))==(0.,maxvalue,0.)
 outputs=[]
 for requested in [0.,1.,2.,3.,-1.]:
  u.mem_write(value,struct.pack('<f',requested));u.mem_write(flag,struct.pack('<I',1))
  run(0xc05fad48,[plugin,2,value,flag]);outputs.append(struct.unpack('<f',u.mem_read(state+0x1c,4))[0])
 expected=[0.,1.,1.,1.,0.] if maxvalue==1 else [0.,1.,2.,1.,1.]
 if terminal:expected=[0.,1.,0.,1.,1.] if maxvalue==1 else [0.,1.,2.,0.,2.]
 assert outputs==expected,(maxvalue,terminal,outputs)
 rows.append(dict(maximum=maxvalue,terminal=terminal,requested=[0,1,2,3,-1],result=outputs,passed=True))
out=ROOT/'prototype/development/native-menu/range-verification.json';out.write_text(json.dumps(dict(resource=hex(ADDR),maximum_address=hex(ADDR+32),original_maximum=struct.unpack('>f',record[32:36])[0],cases=rows,limitations='Native constructor and property range/wrap code execute. Generic property access, event publication and numeric text formatting mocked; native integer-valued float comparisons execute. Properties supplied from verified NBU mask/descriptor layout. Does not emulate physical dial input or the full GUI.'),indent=2)+'\n');print(json.dumps(rows,indent=2))
