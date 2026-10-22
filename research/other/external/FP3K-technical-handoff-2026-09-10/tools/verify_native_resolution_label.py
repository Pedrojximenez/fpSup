"""Execute native localized-text fallback; dictionary acquisition/lookup mocked."""
import json,struct
from unicorn import *
from unicorn.arm_const import *
from native_resolution_resource import stock,ROOT
main,_=stock();cases=[]
for case in ['no-dictionary','missing-key','translated-stock-key']:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0xc0000000,(len(main)+4095)&~4095);u.mem_write(0xc0000000,main)
 u.mem_map(0x10000000,0x10000)
 original=0x10000100;db=0x10000200;translated=0x10000300
 u.mem_write(original,b'3K 3000x2000\0' if case!='translated-stock-key' else b'0313\0')
 u.mem_write(translated,b'UHD 3840x2160\0');u.mem_write(db+4,struct.pack('<I',0 if case=='no-dictionary' else 1))
 def boundary(uc,a,n,d):
  if a==0xc05ebdb8:ret=db
  elif a==0xc05e9f28:
   assert uc.reg_read(UC_ARM_REG_R1)==original
   ret=3 if case=='missing-key' else 0
  else:
   assert case=='translated-stock-key';uc.mem_write(uc.reg_read(UC_ARM_REG_R1),struct.pack('<I',translated));ret=0
  uc.reg_write(UC_ARM_REG_R0,ret);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in [0xc05ebdb8,0xc05e9f28,0xc05e9ff0]:u.hook_add(UC_HOOK_CODE,boundary,begin=a,end=a)
 u.reg_write(UC_ARM_REG_R0,0x10000400);u.reg_write(UC_ARM_REG_R1,original)
 u.reg_write(UC_ARM_REG_SP,0x1000fff0);u.reg_write(UC_ARM_REG_LR,0xc0000000)
 u.emu_start(0xc05ebe59,0xc0000000,count=1000)
 assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and u.reg_read(UC_ARM_REG_SP)==0x1000fff0
 assert u.reg_read(UC_ARM_REG_R0)==(translated if case=='translated-stock-key' else original)
 cases.append(dict(case=case,passed=True))
(ROOT/'prototype/development/native-menu/label-verification.json').write_text(json.dumps(dict(cases=cases,limitations='Executes native localized-text fallback only. Dictionary acquisition/lookup are mocked; rendering and actual dictionary attachment are not tested.'),indent=2)+'\n')
print('PASS',len(cases),'native localized-label cases')
