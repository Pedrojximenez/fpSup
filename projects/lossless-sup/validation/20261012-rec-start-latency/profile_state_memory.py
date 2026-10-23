"""Offline ARM transaction comparison; not camera timing."""
from pathlib import Path
import sys,tempfile,subprocess,json
from collections import Counter
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'fpSup/lossless'),str(ROOT/'research/ui/tools/arm_text')]
import build_card as B
import elf_text
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
SOURCE='''#include "native/frame_hold.h"
#include "native/state_memory.h"
uint32_t hold_bytes(void) { return sizeof(struct fpl_frame_hold); }
void old_clear(void *v, uint32_t n) { unsigned char *p=v; for(uint32_t i=0;i<n;++i) p[i]=0; }
uint32_t old_check(const void *v, uint32_t n) { const unsigned char *p=v; for(uint32_t i=0;i<n;++i) if(p[i]) return 0; return 1; }
void new_clear(void *v, uint32_t n) { fpl_state_clear(v,n); }
uint32_t new_check(const void *v, uint32_t n) { return fpl_state_is_zero(v,n); }
'''
HERE=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='fpl-state-arm-') as td:
 t=Path(td);src=t/'profile.c';src.write_text(SOURCE);obj=t/'profile.o'
 subprocess.run(['clang',*B.CFLAGS,'-DFPL_HOLD_COMMITS=1016u','-I',str(ROOT/'fpSup/lossless'),'-c',str(src),'-o',str(obj)],check=True)
 img=elf_text.load_text(obj)
 mu=Uc(UC_ARCH_ARM,UC_MODE_ARM);code,data,stack,done=0x100000,0x200000,0x800000,0x101000
 mu.mem_map(code,0x2000);mu.mem_map(data,0x200000);mu.mem_map(stack,0x10000);mu.mem_write(code,img.code)
 hist=Counter()
 def access(uc,typ,addr,size,value,ctx): hist[(typ,size)]+=1
 hook=mu.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=data,end=data+0x200000-1)
 def call(name,n=0):
  hist.clear();mu.reg_write(UC_ARM_REG_R0,data);mu.reg_write(UC_ARM_REG_R1,n);mu.reg_write(UC_ARM_REG_SP,stack+0x10000-8);mu.reg_write(UC_ARM_REG_LR,done)
  mu.emu_start(code+img.functions[name],done,count=15000000)
  assert mu.reg_read(UC_ARM_REG_PC)==done
  return mu.reg_read(UC_ARM_REG_R0)
 n=call('hold_bytes'); result={'hold_bytes':n,'two_lane_bytes':2*n,'source':'same production CFLAGS and state_memory.h; firmware scheduling/cache latency not simulated','operations':{}}
 for name in ['old_clear','old_check','new_clear','new_check']:
  if name.endswith('clear'):mu.mem_write(data,b'\xa5'*n)
  else:mu.mem_write(data,bytes(n))
  r=call(name,n)
  if name.endswith('clear'):assert bytes(mu.mem_read(data,n))==bytes(n)
  else:assert r==1
  result['operations'][name]={'transactions':sum(hist.values()),'widths':{str(k):v for k,v in hist.items()}}
 assert result['operations']['new_clear']['transactions']<=result['operations']['old_clear']['transactions']/4
 assert result['operations']['new_check']['transactions']<=result['operations']['old_check']['transactions']/4
 (HERE/'state-memory-arm.json').write_text(json.dumps(result,indent=2)+'\n')
 dis=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
 (HERE/'state-memory-arm.asm').write_text('\n'.join(f'{i.address:08x} {i.mnemonic} {i.op_str}' for i in dis.disasm(img.code,0)))
 print(json.dumps(result,indent=2))
