"""Execute complete loader -> resident -> native selection path offline."""
import json,struct
from verify_fp3k_native_menu import Camera,BASE,STATE,HOOKS,entries,code,syms
from build_fp3k_menu_package import build,BOOT,BOOT_STATE,OUT
from unicorn import *
from unicorn.arm_const import *
loader,payload,manifest=build();results=[];ECHO=0xc0bac2f8
class BootCamera(Camera):
 def guard(self,u,access,a,n,v,d):
  if BOOT_STATE<=a and a+n<=BOOT_STATE+16 or a==ECHO:return
  super().guard(u,access,a,n,v,d)
 def boot(self,case):
  self.u.mem_protect(ECHO&~4095,4096,UC_PROT_ALL)
  self.u.mem_write(BOOT,loader);self.put(ECHO,BOOT)
  self.files=[];self.installs=[]
  def filesystem(u,a,n,d):
   r=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
   assert self.get(ECHO)==0xc03d99a0
   self.files.append(a);ret=0
   if a==0xc0365e90:assert r[1]==1
   elif a==0xc0365fb0:
    assert bytes(u.mem_read(r[1],14))==b'\\FP3KMENU.BIN\0' and r[2]==1
    ret=int(case!='missing')
   elif a==0xc0366060:
    assert r[1]==BASE and r[2]==len(payload)
    data=payload
    if case=='short':data=payload[:100]
    if case=='empty':data=b''
    if case=='corrupt':data=payload[:-1]+bytes([payload[-1]^1])
    u.mem_write(r[1],data);self.put(r[3],len(data));ret=1
   elif a==0xc0365ed0:assert r[1]==2
   u.reg_write(UC_ARM_REG_R0,ret);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  handles=[self.u.hook_add(UC_HOOK_CODE,filesystem,begin=a,end=a) for a in [0xc0365e90,0xc0365fb0,0xc0366060,0xc0365ed0]]
  handles.append(self.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:self.installs.append(a),begin=BASE,end=BASE))
  self.run(BOOT)
  for h in handles:self.u.hook_del(h)
  assert self.get(ECHO)==0xc03d99a0
for case in ['cold','busy-boot','missing','short','empty','corrupt','stock-table-mismatch','warm-idle','warm-active','warm-corrupt','mixed-hooks','foreign-hook','warm-bad-state']:
 c=BootCamera()
 if case.startswith('warm'):
  c.install()
  if case=='warm-active':c.select(2)
  if case=='warm-corrupt':c.u.mem_write(BASE+syms['csv_new'],b'X')
  if case=='warm-bad-state':c.put(STATE,0)
 if case=='mixed-hooks':c.install();c.put(HOOKS[0][0],0xe92d40f0)
 if case=='foreign-hook':c.put(HOOKS[0][0],0xea000001)
 if case=='stock-table-mismatch':c.put(entries[0]['address'],0)
 if case=='busy-boot':c.put(0xc343b58c,151)
 before=c.tables();active=c.active();resident_before=bytes(c.u.mem_read(BASE,len(payload)))
 c.boot(case)
 expected={'cold':16,'busy-boot':16,'missing':33,'empty':34,'short':34,'corrupt':35,'stock-table-mismatch':49,'warm-idle':17,'warm-active':17,'warm-corrupt':36,'mixed-hooks':36,'foreign-hook':36,'warm-bad-state':36}[case]
 assert c.get(BOOT_STATE+4)==expected,(case,c.get(BOOT_STATE+4))
 assert c.tables()==before and c.active()==active
 if case.startswith('warm') or case in ['mixed-hooks','foreign-hook']:
  assert not c.files and not c.installs
  assert bytes(c.u.mem_read(BASE,len(payload)))==resident_before
 else:assert c.files.count(0xc0365ed0)==1
 if case=='cold':
  c.run(0xc05931d0,0x10000100,3);c.select(2);c.assert_3k();assert c.events[-1]==('display',2)
  c.select(0);c.assert_stock();assert c.events[-1]==('display',0)
 results.append(dict(case=case,status=expected,passed=True))
report=dict(cases=results,files=manifest['files'],limitations='Actual assembled bootstrap, resident installer and installed menu hooks executed. Filesystem, hardware cache synchronization, settings backing service, volume routing and UI queue mocked. Camera timing, rendering and physical media behavior require hardware validation.')
(OUT/'package-verification.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS',len(results),'integrated boot cases')
