"""Execute F1's native timing/window/receiver setup against captured sensor state.
Only receiver I/O, timing I/O and the singleton getter are mocked. This verifies
arguments reaching hardware drivers, not actual sensor/electrical behavior.
"""
import struct,json,hashlib
from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
from fullheight_candidate import plan
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'analysis/firmware'
main=(OUT/'MAIN_c0000000.bin').read_bytes();dat=(OUT/'DAT1_c2ef6e00.bin').read_bytes()
assert hashlib.sha256(main).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
state=(ROOT/'diagnostics/v003-uhd24-retry/SSD/FPD003/STATE.BIN').read_bytes()
assert hashlib.sha256(state).hexdigest()=='6c10b388be9b5c2695b627b7524ccc57fbd60bb4f02953e5e6d4a74f970838e7'
OBJ=0xc343b588;STACK=0x10010000;STOP=0xc0000000
reports=[]
for label,mode,patched in [('stock151',151,False),('native3',3,False),('native121',121,False),('fullheight151',151,True)]:
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);n=(len(main)+4095)&~4095
 u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,main)
 # DAT1 begins inside the last MAIN page; map only the extension.
 end=(0xc2ef6e00+len(dat)+4095)&~4095
 if end>0xc0000000+n:u.mem_map(0xc0000000+n,end-(0xc0000000+n))
 u.mem_write(0xc2ef6e00,dat)
 if patched:
  for e in plan():u.mem_write(e['address'],struct.pack('<I',e['replacement']))
 u.mem_protect(0xc0000000,end-0xc0000000,UC_PROT_READ|UC_PROT_EXEC)
 u.mem_map(OBJ&~4095,4096);u.mem_map(STACK,0x4000)
 u.mem_write(OBJ,state[64+8*832+0x20:64+8*832+0x20+256]);u.mem_write(OBJ+4,struct.pack('<I',mode))
 calls=[]
 specs={0xc0635ed8:('input_window_a',0,12),0xc0636048:('input_window_b',0,12),0xc0635d40:('receiver_a',1,68),0xc0635d58:('receiver_b',1,68),0xc01265c0:('hmax_vmax',None,0),0xc0126128:('tail_cycles',None,0)}
 def hook(uc,a,n,d):
  regs=[uc.reg_read(x) for x in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
  if a==0xc0322e48:result=OBJ
  elif a in specs:
   name,ptr,count=specs[a];calls.append(dict(name=name,args=regs[:3],data=bytes(uc.mem_read(regs[ptr],count)).hex() if ptr is not None else None));result=0
  else:raise AssertionError(hex(a))
  uc.reg_write(UC_ARM_REG_R0,result);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 for a in [*specs,0xc0322e48]:u.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
 def guard(uc,access,a,n,v,d):assert STACK<=a and a+n<=STACK+0x4000 or OBJ<=a and a+n<=OBJ+256,hex(a)
 u.hook_add(UC_HOOK_MEM_WRITE,guard)
 def run(a,*args):
  u.reg_write(UC_ARM_REG_SP,STACK+0x3ff0);u.reg_write(UC_ARM_REG_LR,STOP)
  for reg,val in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(reg,val)
  u.emu_start(a,STOP,count=50000);assert u.reg_read(UC_ARM_REG_PC)==STOP,hex(u.reg_read(UC_ARM_REG_PC))
 run(0xc0321290,OBJ,mode)
 run(0xc0320740,OBJ)
 run(0xc0320008,OBJ,mode)
 run(0xc0320ab0,OBJ,mode,0,0)
 reports.append(dict(case=label,mode=mode,calls=calls))
f1=reports[-1]['calls'];stock=reports[0]['calls'];native=reports[1]['calls']
assert [c['name'] for c in f1]==['hmax_vmax','tail_cycles','input_window_a','input_window_b','receiver_a','receiver_b']
assert f1[0]['args']==stock[0]['args']==[445,6740,0]
assert f1[1]['args'][0]==stock[1]['args'][0]==1145
for i in range(2,6):assert f1[i]['data']==native[i]['data'],(i,f1[i],native[i])
assert struct.unpack('<I4H',bytes.fromhex(f1[2]['data']))==(3,8,6072,40,4082)
# All table-fed sensor-register values remain identical to native full-height modes.
r={x['mode_id']:x for x in json.loads((OUT/'sensor-registers.json').read_text())['rows']}
assert r[151]['words'][1:]==r[3]['words'][1:]==r[121]['words'][1:]
report=dict(cases=reports,frame_cycles=445*(6740-1)+1145,estimated_fps_at_72MHz=72000000/(445*(6740-1)+1145),input_raster=[6064,4042],mocked=['singleton lookup',*list(specs.values())],limitations='No hardware or mode-transition concurrency emulated. Preview remains stock16:9; hardware RAW filtering at ratio2048 still unverified.')
(OUT/'fullheight-capture-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: native mode3 input/receiver arguments matched; stock true24 timing preserved. Four cases.')
