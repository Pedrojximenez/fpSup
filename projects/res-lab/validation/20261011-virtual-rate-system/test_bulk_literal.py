"""Execute native CinemaDNG bulk setup; no camera, timing or DMA model."""
import pathlib,struct,unittest
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
ROOT=pathlib.Path(__file__).resolve().parents[4]
ROM=(ROOT/'out/MAIN_c0000000.bin').read_bytes()
START,END,LITERAL=0xc03a5050,0xc03a518c,0xc0b9e5d8
OBJ,CFG,BUFFER,RET,SP=0x45000000,0x45001000,0x45002000,0x45003000,0x45010000
class BulkTests(unittest.TestCase):
 def run_native(self,size,enabled=1):
  mu=Uc(UC_ARCH_ARM,UC_MODE_ARM);mu.mem_map(0xc0000000,0x3000000);mu.mem_write(0xc0000000,ROM)
  mu.mem_map(0x45000000,0x20000)
  def word(a,v):mu.mem_write(a,struct.pack('<I',v))
  def get(a,n=1):return list(struct.unpack('<'+'I'*n,mu.mem_read(a,4*n)))
  word(OBJ,BUFFER);mu.mem_write(CFG+0x9c,bytes([enabled]));word(LITERAL,size)
  stubs={0xc0019dc0:0,0xc001a048:0,0xc0444658:0,0xc0444698:1,0xc0021c00:CFG,0xc0021c40:CFG,0xc0365e90:0,0xc0365ed0:0}
  calls=[]
  def step(mu,a,n,_):
   if a==RET:mu.emu_stop();return
   if START<=a<END:return
   if a==0xc0366790:
    calls.append(get(mu.reg_read(UC_ARM_REG_R1),4));value=1
   elif a in stubs:value=stubs[a]
   else:raise AssertionError(f'unmodeled execution {a:#x}')
   mu.reg_write(UC_ARM_REG_R0,value);mu.reg_write(UC_ARM_REG_PC,mu.reg_read(UC_ARM_REG_LR))
  mu.hook_add(UC_HOOK_CODE,step)
  mu.reg_write(UC_ARM_REG_R0,OBJ);mu.reg_write(UC_ARM_REG_LR,RET);mu.reg_write(UC_ARM_REG_SP,SP);mu.reg_write(UC_ARM_REG_R4,0xa4a4a4a4)
  mu.emu_start(START,RET+4,count=10000)
  self.assertEqual(mu.reg_read(UC_ARM_REG_R0),1);self.assertEqual(mu.reg_read(UC_ARM_REG_R4),0xa4a4a4a4);self.assertEqual(mu.reg_read(UC_ARM_REG_SP),SP)
  self.assertEqual(get(OBJ+0x10),[1]);self.assertEqual(mu.mem_read(OBJ+0xc,2),bytes([1,enabled]))
  return calls
 def test_native_uses_actual_batch_limit_and_preserves_buffer_callback(self):
  self.assertEqual(struct.unpack_from('<4I',ROM,LITERAL-0xc0000000),(0x4000000,0,0x40000,0xc03a55d0))
  for n in (0x4000000,0x1000000,0x100000):
   self.assertEqual(self.run_native(n),[[n,BUFFER,0x40000,0xc03a55d0]])
 def test_non_bulk_path_does_not_submit_limit(self):
  self.assertEqual(self.run_native(0x1000000,0),[])
if __name__=='__main__':unittest.main(verbosity=2)
