"""Bounded read-only FPS object snapshot; synthetic RAM, no camera."""
import struct,unittest
from pathlib import Path
import experiment as E
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
P,CODE,STACK,STOP=0x45000000,0x46000000,0x47008000,0x46001000
APP,SCREEN,ROOT,CHILD,ARR,COMPS,COMP,DESC=[0x45100000+0x1000*i for i in range(8)]
class SnapshotTests(unittest.TestCase):
 def run_case(self,change=None):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  for a,n in [(0xc37b0000,0x10000),(P,0x200000),(CODE,0x2000),(STACK-0x8000,0x10000)]:u.mem_map(a,n)
  def put(a,*words):u.mem_write(a,struct.pack('<'+'I'*len(words),*words))
  put(0xc37b7048,APP);put(APP+0x84c,SCREEN);put(SCREEN+12,ROOT)
  put(ROOT+0x18,1);put(ROOT+0x54,1);put(ROOT+0x60,ARR);put(ARR,CHILD)
  put(CHILD+0x18,926);put(CHILD+0x40,1);put(CHILD+0x4c,COMPS);put(COMPS,COMP)
  put(COMP+8,3);put(COMP+0x10,DESC);put(DESC+12,0xc05fe2b1);put(COMP+0x1c,COMP+0x200);put(COMP+0x20,COMP+0x400)
  for index,value in [(14,0xff),(15,0x40000000),(16,1)]:
   u.mem_write(COMP+0x200+2*index,struct.pack('<H',index*2));put(COMP+0x400+8*index,0,value)
  if change:change(u,put)
  blob=E.assemble(Path(__file__).with_name('fps_outline_snapshot.S'),[f'P={P}','TARGET=926'])
  u.mem_write(CODE,blob)
  regs=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
  for i,r in enumerate(regs):u.reg_write(r,0x11220000+i)
  u.reg_write(UC_ARM_REG_SP,STACK);u.reg_write(UC_ARM_REG_LR,STOP)
  def check_write(mu,access,address,size,value,user):
   self.assertTrue(P<=address and address+size<=P+224 or STACK-168<=address and address+size<=STACK,(hex(address),size))
  u.hook_add(UC_HOOK_MEM_WRITE,check_write)
  u.emu_start(CODE,STOP,count=100000)
  self.assertEqual(u.reg_read(UC_ARM_REG_PC),STOP)
  self.assertEqual(u.reg_read(UC_ARM_REG_SP),STACK)
  self.assertEqual([u.reg_read(r) for r in regs],[0x11220000+i for i in range(8)])
  return struct.unpack('<56I',u.mem_read(P,224))
 def test_owned_component_capture(self):
  w=self.run_case();self.assertEqual(w[:8],(1,APP,SCREEN,ROOT,CHILD,926,1,2));self.assertEqual(w[8:12],(3,0xff,0x40000000,1))
 def test_missing_object(self):self.assertEqual(self.run_case(lambda u,p:p(CHILD+0x18,927))[0],0)
 def test_invalid_root(self):self.assertEqual(self.run_case(lambda u,p:p(SCREEN+12,0))[0],0)
 def test_unaligned_app(self):self.assertEqual(self.run_case(lambda u,p:p(0xc37b7048,APP+1))[0],0)
 def test_child_count_bound(self):self.assertEqual(self.run_case(lambda u,p:p(ROOT+0x54,65))[0],0)
 def test_component_count_bound(self):self.assertEqual(self.run_case(lambda u,p:p(CHILD+0x40,13))[0],0)
 def test_cycle_depth_bound(self):
  self.assertEqual(self.run_case(lambda u,p:(p(ARR,ROOT),p(ROOT+0x18,1)))[0],0)
if __name__=='__main__':unittest.main(verbosity=2)
