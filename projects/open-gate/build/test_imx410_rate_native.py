#!/usr/bin/env python3
"""Execute native menu mappings and both gates, optionally from exact BIN words."""
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
import imx410_rate_native as N

ROOT=Path(__file__).resolve().parents[3]
IMG=(ROOT/'out/MAIN_c0000000.bin').read_bytes()
MEM=0x40000000
DONE=MEM+0xff00
STACK=MEM+0xe000
OBJ=MEM+0x100
VT=MEM+0x200
OUT=MEM+0x1000
CFG=MEM+0x1100
REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
      UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
      UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12)


def p32(x): return struct.pack('<I',x)


class Native:
 def __init__(self,words):
  self.mu=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  self.mu.mem_map(N.B,0x04000000)
  self.mu.mem_write(N.B,IMG)
  self.mu.mem_map(MEM,0x10000)
  for a,w in words.items(): self.mu.mem_write(a,p32(w))
  self.mu.mem_write(OBJ+4,p32(VT))
  self.mu.mem_write(VT+0x60,p32(0xC06BDB00))
  self.mu.mem_write(VT+0x4e0,p32(0xC06CB6D0))
  self.klass=0
  self.initialise=True
  self.trace=[]
  self.boundaries={}
  self.mu.hook_add(UC_HOOK_CODE,self._hook)
 def word(self,a): return struct.unpack('<I',self.mu.mem_read(a,4))[0]
 def _return(self,value=None):
  if value is not None:self.mu.reg_write(UC_ARM_REG_R0,value)
  self.mu.reg_write(UC_ARM_REG_PC,self.mu.reg_read(UC_ARM_REG_LR))
 def _hook(self,u,a,size,data):
  self.trace.append(a)
  if a in (0xC04A1220,0xC00A87E8,0xC049A78C,0xC05332AC):
   self.boundaries[a]=([u.reg_read(r) for r in REGS],u.reg_read(UC_ARM_REG_CPSR),u.reg_read(UC_ARM_REG_SP))
  if a in (DONE,0xC057A6FC,0xC05821BC):u.emu_stop();return
  if a==0xC0013090:self._return(int(self.initialise));return
  if a==0xC00131E4:self._return(1);return
  if a==0xC049EC58:self._return(OBJ);return
  if a==0xC049ED20:
   assert u.reg_read(UC_ARM_REG_R1)==0x19
   self._return(self.klass);return
  if a==0xC01F578C:
   dst,src,n=(u.reg_read(r) for r in REGS[:3])
   raw=bytes(u.mem_read(src,n)).split(b'\0')[0][:n]
   u.mem_write(dst,raw+b'\0'*(n-len(raw)))
   self._return(dst);return
  allowed=((0xC0063520,0xC0063714),(0xC00A8818,0xC00A8900),
           (0xC00A87E4,0xC00A8818),(0xC06BDA58,0xC06BDB28),
           (0xC06CCD70,0xC06CCDCC),(0xC06CF630,0xC06CF684),
           (0xC06CB678,0xC06CB6F8),(0xC06CF070,0xC06CF0CC),
           (0xC049A788,0xC049A890),(0xC05332A8,0xC05332D0),
           (0xC04A121C,0xC04A1224),(0xC043CAF0,0xC043CC54),
           (0xC0732A20,0xC0732C20))
  assert any(lo<=a<hi for lo,hi in allowed),f'unexpected native execution {a:#x}'
 def state(self,flag=1,fmt=0):
  self.mu.mem_write(N.FLAG,p32(flag));self.mu.mem_write(N.FMTLATCH,p32(fmt))
 def call(self,pc,values=None,stack=None):
  for i,r in enumerate(REGS):self.mu.reg_write(r,0xa1000000+i)
  for r,v in (values or {}).items():self.mu.reg_write(r,v)
  self.mu.reg_write(UC_ARM_REG_SP,STACK)
  self.mu.reg_write(UC_ARM_REG_LR,DONE)
  self.mu.reg_write(UC_ARM_REG_CPSR,0xa8000013)
  if stack:self.mu.mem_write(STACK,struct.pack('<'+'I'*len(stack),*stack))
  self.trace=[]
  self.boundaries={}
  self.mu.emu_start(pc,DONE+4,count=10000)
  assert self.mu.reg_read(UC_ARM_REG_PC)==DONE,'native function did not return'
  assert self.mu.reg_read(UC_ARM_REG_SP)==STACK+(len(stack)*4 if stack else 0),'stack not restored'
  return self.mu.reg_read(UC_ARM_REG_R0)
 def rate_class(self,k):
  return self.call(N.FRCLASS_HOOK,{UC_ARM_REG_R1:k},[0x14,0x15,0x16,DONE])
 def normalise(self,value,cap):
  return self.call(N.FRMAX_HOOK,{UC_ARM_REG_R4:cap,UC_ARM_REG_R6:value},
       [0,0,0,0x14,0x15,0x16,0x17,0x18,0x1a,0x1b,DONE])
 def listing(self,qs=False):
  self.call(0xC05332A8 if qs else 0xC049A788,{UC_ARM_REG_R0:OUT})
  ptr,n=self.word(OUT),self.word(OUT+4)
  return tuple(struct.unpack('<'+'I'*n,self.mu.mem_read(ptr,n*4)))
 def convert(self,value,to_row=False):
  return self.call(0xC06BDA58 if to_row else 0xC06BDAB0,
                   {UC_ARM_REG_R0:OBJ,UC_ARM_REG_R1:value})
 def summary(self,value):
  return self.call(0xC06CB678,{UC_ARM_REG_R0:OBJ,UC_ARM_REG_R1:value})
 def export(self,value):return self.call(0xC00636A8,{UC_ARM_REG_R0:value})
 def rank(self,value):return self.call(0xC0063548,{UC_ARM_REG_R0:value})
 def suffix(self,export):
  self.mu.mem_write(CFG+0x10,p32(export))
  self.call(0xC043CAF0,{UC_ARM_REG_R0:OBJ,UC_ARM_REG_R1:OUT,UC_ARM_REG_R2:CFG})
  return bytes(self.mu.mem_read(OUT,16)).split(b'\0')[0].decode('ascii')


def _role6(n,row,hook=5):
 """Run an MV_FrameRate pre-hook payload (HOOKS[5] or [6]) for a committed row; stop where stock resumes."""
 back={5:0xC057A6FC,6:0xC05821BC}[hook]
 var=MEM+0x300
 n.mu.mem_write(var+8,p32(row))
 for i,r in enumerate(REGS):n.mu.reg_write(r,0xa1000000+i)
 n.mu.reg_write(UC_ARM_REG_R0,var); n.mu.reg_write(UC_ARM_REG_SP,STACK)
 n.mu.reg_write(UC_ARM_REG_LR,0xa100000e); n.mu.reg_write(UC_ARM_REG_CPSR,0xa8000013)
 n.mu.emu_start(N.HOOKS[hook][1],back,count=200)
 assert n.mu.reg_read(UC_ARM_REG_PC)==back
 assert n.mu.reg_read(UC_ARM_REG_SP)==STACK-20                      # the displaced push {r4-r7,lr}
 assert n.mu.reg_read(UC_ARM_REG_R0)==var and n.mu.reg_read(UC_ARM_REG_R1)==0xa1000001
 assert n.mu.reg_read(UC_ARM_REG_CPSR)&0xf8000000==0xa8000000
 return n.word(N.RATE240)


def verify_installed(words):
 """Use caller-provided installed words, with no compilation/rebuild in this path."""
 for h in (5,6):
  assert words.get(N.HOOKS[h][0])==N._b(N.HOOKS[h][0],N.HOOKS[h][1]),'row-nine hook not armed'
 n=Native(words)
 n.state()
 # ⛔ SETTINGS_AREA_FIRST_RULE: internal 8 must not be reachable from any input.
 assert n.listing()==N.STOCK_ORDER and n.listing(qs=True)==N.STOCK_ORDER
 assert all(n.convert(row)!=N.INTERNAL for row in range(11))
 internal=n.convert(9)
 assert internal==N.ROW240_VALUE==7
 assert n.convert(10)==0 and n.convert(0,to_row=True)==10
 export=n.export(internal)
 assert export==10 and n.suffix(export)=='120'
 summary=None
 if 0xC06CB6DC in words:
  assert n.summary(10)==8 and n.summary(8)==6
 # Boot state: flag 0, value 7 shows row 8 (119.88).
 assert n.word(N.RATE240)==0 and n.convert(7,to_row=True)==8
 # Commit row nine (239.76): RAM flag, cursor and summary follow; stock still gets 7.
 assert _role6(n,9)==1
 assert n.convert(7,to_row=True)==9 and n.convert(9)==7 and n.convert(8)==7
 if 0xC06CB6DC in words:
  summary=n.summary(10)
  assert summary==9,('row-nine summary',summary)
 assert all(n.convert(row)!=N.INTERNAL for row in range(11))
 # Any other row clears it and restores stock order -- through either setter.
 for hook in (5,6):
  assert _role6(n,9,hook)==1 and n.convert(7,to_row=True)==9
  for row in (8,0,3,10):
   assert _role6(n,row,hook)==0
   assert n.convert(7,to_row=True)==8
   if 0xC06CB6DC in words: assert n.summary(10)==8
 assert n.call(0xC00A88B0,{UC_ARM_REG_R0:8})==11
 assert n.call(0xC00A8860,{UC_ARM_REG_R0:8})==8
 # AutoRun can run after this native lazy cache has already been populated.
 n.initialise=False
 n.mu.mem_write(0xC31CBBD4,struct.pack('<II',0xC0742250,9))
 assert n.call(0xC00A88B0,{UC_ARM_REG_R0:8})==11
 assert n.call(0xC00A8860,{UC_ARM_REG_R0:8})==8
 assert n.normalise(8,5)==8
 assert n.normalise(8,7)==8
 for internal,export,suffix in [(5,8,'60'),(7,10,'120')]:
  assert n.export(internal)==export
  assert n.suffix(export)==suffix
  assert n.normalise(internal,5)==internal
 for flag,fmt in [(0,0),(1,1),(1,0xffffffff),(2,0)]:
  n.state(flag,fmt)
  for klass in range(6):assert n.rate_class(klass)==klass
  assert n.normalise(7,5)==5
  assert n.normalise(5,7)==5
  n.klass=0
  assert n.listing()==N.STOCK_ORDER
  assert n.listing(qs=True)==N.STOCK_ORDER
  n.klass=3
  assert n.listing()==N.STOCK_ORDER[:7]
 n.state()
 for klass in range(6):assert n.rate_class(klass)==0
 n.rate_class(5)
 assert n.mu.reg_read(UC_ARM_REG_R1)==5
 assert n.mu.reg_read(UC_ARM_REG_R2)==0xa1000002
 assert n.mu.reg_read(UC_ARM_REG_R3)==0xa1000003
 assert n.mu.reg_read(UC_ARM_REG_R12)==0xa100000c
 assert n.mu.reg_read(UC_ARM_REG_CPSR)&0xf8000000==0xa8000000
 return {'row':9,'internal':N.ROW240_VALUE,'export':10,'suffix':'120','ram_flag':N.RATE240,'summary_state':summary,
         'native_checks':'no internal 8 from any row/list, row-nine RAM flag, cursor/summary order, cap, guards'}


def test_native_installed_roundtrip():
 assert verify_installed(N.installed_words(IMG))['internal']==7


def test_native_stock_guards():
 for a,_,_ in N.MAPPING_SITES + tuple((h[0],h[2],h[4]) for h in N.HOOKS):
  bad=bytearray(IMG);struct.pack_into('<I',bad,a-N.B,0)
  try:N.patches(bad)
  except ValueError:pass
  else:raise AssertionError(f'missing original-word guard {a:#x}')


def test_native_hook_abi():
 n=Native(N.installed_words(IMG))
 n.call(N.LEGAL_HOOK,{UC_ARM_REG_R5:0xC31CBBD4},[0x14,0x15,DONE])
 assert n.mu.reg_read(UC_ARM_REG_R0)==N.LEGAL_DESC
 assert n.mu.reg_read(UC_ARM_REG_CPSR)&0xf8000000==0xa8000000
 for i in (1,2,3,6,7,8,9,10,11,12):assert n.mu.reg_read(REGS[i])==0xa1000000+i
 for flag,fmt in [(1,0),(0,0),(1,1),(1,0xffffffff)]:
  n.state(flag,fmt)
  n.rate_class(5)
  regs,flags,sp=n.boundaries[0xC04A1220]
  assert regs[0]==(0 if (flag,fmt)==(1,0) else 5)
  assert regs[1:]==[5]+[0xa1000000+i for i in range(2,13)]
  assert flags&0xf8000000==0xa8000000 and sp==STACK
  n.normalise(8,5)
  regs,flags,sp=n.boundaries[0xC00A87E8]
  assert regs[1]==(8 if (flag,fmt)==(1,0) else 5)
  for i in (0,2,3,5,7,8,9,10,11,12):assert regs[i]==0xa1000000+i
  assert regs[4]==5 and regs[6]==8
  assert flags&0xf8000000==0xa8000000 and sp==STACK
  # Menu/QS list hooks are not armed (one-row-240): stock code in every state.
  for qs,back in [(False,0xC049A78C),(True,0xC05332AC)]:
   n.klass=0
   assert n.listing(qs)==N.STOCK_ORDER and back in n.boundaries


def test_native_mutants_are_detected():
 words=N.installed_words(IMG)
 site6,code6=N.HOOKS[5][0],N.HOOKS[5][1]
 site7=N.HOOKS[6][0]
 variants={
  'input row maps to 15':{N.INPUT_PAIR+9*8:0},
  'row nine hands stock internal 8':{N.INPUT_PAIR+9*8:N.INTERNAL},
  'normaliser gate absent':{N.FRMAX_HOOK:N.FRMAX_STOCK},
  'class gate absent':{N.FRCLASS_HOOK:N.FRCLASS_STOCK},
  'class guard removed':{N.HOOKS[0][1]+28:0xE320F000},
  'row-nine hook not armed':{site6:N.HOOKS[5][2]},
  'second MV_FrameRate setter not armed':{site7:N.HOOKS[6][2]},
  'RAM flag never stored':{code6+0x20:0xE320F000},
  'cursor order not swapped':{code6+0x38:0xE320F000},
 }
 for label,changes in variants.items():
  bad=dict(words);bad.update(changes)
  try:verify_installed(bad)
  except (AssertionError,ValueError):pass
  else:raise AssertionError(f'undetected mutant: {label}')


def _registered_names(fn):
 """GUI variable names registered with callback `fn`, read from the decompiled source
 (`FUN_c0560fb0/c0561080(obj, s_MV_..., FUN_xxx)`).  The ARM code loads the callbacks
 into r5/r6 up front, so register adjacency cannot pair them."""
 import re
 src=(ROOT/'out/decomp/full/blk_c05.c').read_text(errors='replace')
 return re.findall(rf's_(MV_\w+?)_c[0-9a-f]{{7}},FUN_{fn:08x}\)',src)


def test_row_nine_hook_is_the_frame_rate_setter():
 """2026-10-01 camera: r7 armed FUN_c057a750 (MV_Binning) and the flag never moved.
 The hook site must be the callback registered for GUI variable "MV_FrameRate"."""
 import re
 src=(ROOT/'out/decomp/full/blk_c05.c').read_text(errors='replace')
 setters={int(m,16) for m in re.findall(r's_MV_FrameRate_c[0-9a-f]{7},FUN_([0-9a-f]{8})\)',src)}
 assert setters=={N.HOOKS[5][0],N.HOOKS[6][0]},[hex(x) for x in setters]   # every setter hooked
 for h in (5,6):
  names=_registered_names(N.HOOKS[h][0])
  assert names and set(names)=={'MV_FrameRate'},names
 assert set(_registered_names(0xC057A750))=={'MV_Binning'}      # the wrong site, for contrast


def _run_rate_switch(words, fn, rate):
 """Execute a stock per-rate function with the frame-rate getter returning `rate`."""
 mu=Uc(UC_ARCH_ARM,UC_MODE_ARM)
 mu.mem_map(N.B,0x04000000); mu.mem_write(N.B,IMG)
 mu.mem_map(MEM,0x10000)
 for a,w in words.items(): mu.mem_write(a,p32(w))
 def hook(u,a,size,data):
  if a==DONE: u.emu_stop(); return
  if a in (0xC0057AE8,0xC005C0F0):
   u.reg_write(UC_ARM_REG_R0, OBJ if a==0xC0057AE8 else rate)
   u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 mu.hook_add(UC_HOOK_CODE,hook)
 mu.reg_write(UC_ARM_REG_SP,STACK); mu.reg_write(UC_ARM_REG_LR,DONE)
 mu.emu_start(fn,DONE,count=200)
 return mu.reg_read(UC_ARM_REG_R0)


def test_rate_switches_alias_240_to_11988():
 """Camera freeze 2026-10-01: stock value-string getter returned NULL for internal 8.
 Retired (SETTINGS_AREA_FIRST_RULE: do not alter the stock flow; internal 8 never
 reaches stock).  Off by default; the code is kept correct for the record."""
 assert N.WITH_SWITCH_ALIAS is False and N.switch_patches(IMG)==[]
 stock={}
 N.WITH_SWITCH_ALIAS=True
 try: patched={a:w for a,w,_ in N.switch_patches(IMG)}
 finally: N.WITH_SWITCH_ALIAS=False
 s7=_run_rate_switch(stock,0xC058F380,7)
 assert IMG[s7-N.B:s7-N.B+5]==b'0322\0'                  # "119.88 fps" string ID
 assert _run_rate_switch(stock,0xC058F380,8)==0           # the stock NULL
 assert _run_rate_switch(patched,0xC058F380,8)==s7        # aliased
 assert _run_rate_switch(patched,0xC058F380,9)==0         # 9..11 untouched
 for v in (1,2,3,4,5,6,7,12,13):
  assert _run_rate_switch(patched,0xC058F380,v)==_run_rate_switch(stock,0xC058F380,v), v
 for cmp,table in N.RATE_SWITCHES:
  word=patched
  at=cmp+20+N.INTERNAL
  got=struct.pack('<I',word[at&~3])[at&3]
  assert got==table[7] and table[8]!=table[7], hex(cmp)


if __name__=='__main__':
 for name,fn in sorted(globals().copy().items()):
  if name.startswith('test_') and callable(fn):fn();print(name,'PASS',flush=True)
 print('4/4 native rate tests passed',flush=True)
