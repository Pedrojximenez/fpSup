"""Execute installed UI hooks; keep each mocked native boundary explicit."""
import json,struct,hashlib
from verify_fp3k_native_menu import Camera,BASE,STATE,HOOKS,code,syms,main
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm_const import *
from build_fp3k_ui_resources import OUT,ALIAS

plan=json.loads((OUT/'layout-repair-plan.json').read_text());plan['plans'] += [p for p in json.loads((OUT/'ui-resource-plan.json').read_text())['plans'] if p['kind']=='QS-limit'];ALIAS={k:v for k,v in ALIAS.items() if k!='FP3K_LH'};ALIAS.update({'FP3K_FONT':0xfffffff4,'3K':0xfffffff6});results=[]
c=Camera();c.install();u=c.u
parser=0x10000800
seen=[]
c.put(parser+8,0x10000700);c.put(STATE+36,0x10000700)
u.hook_add(UC_HOOK_MEM_INVALID,lambda uc,access,a,n,v,d:print('Invalid',hex(a),'PC',hex(uc.reg_read(UC_ARM_REG_PC)),'SP',hex(uc.reg_read(UC_ARM_REG_SP))))
def parser_boundary(uc,address,size,data):
    p=uc.reg_read(UC_ARM_REG_R0);position=c.get(p+4);source=c.get(p+36)+position
    n=struct.unpack('>I',uc.mem_read(source+4,4))[0]
    seen.append(bytes(uc.mem_read(source,n)))
    c.put(p+4,position+n)
    # Displaced Thumb push.w {r4-r11,lr} has executed.
    sp=uc.reg_read(UC_ARM_REG_SP);saved=struct.unpack('<9I',uc.mem_read(sp,36))
    for reg,value in zip(range(UC_ARM_REG_R4,UC_ARM_REG_R11+1),saved[:8]):uc.reg_write(reg,value)
    uc.reg_write(UC_ARM_REG_SP,sp+36);uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,saved[8])
h=u.hook_add(UC_HOOK_CODE,parser_boundary,begin=0xc05e6404,end=0xc05e6404)
for p in plan['plans']:
    address=int(p['address'],16);c.put(STATE+40,1)
    c.put(parser+4,address-0xc18c0460);c.put(parser+20,0xc18c0474);c.put(parser+36,0xc18c0460)
    c.run(0xc05e6401,parser)
    assert seen[-1]==bytes.fromhex(p['new']),p['address']
    assert c.get(parser+36)==0xc18c0460 and c.get(parser+4)==address-0xc18c0460+p['size']
    results.append(dict(case='parser-copy-'+p['address'],passed=True))
assert c.get(STATE+48)==15 and c.get(STATE+52)==15
results.append(dict(case='qs-both-screens-seen-and-extended',passed=True))
qs_record=next(p for p in plan['plans'] if p['address']=='0xc237249f')
address=int(qs_record['address'],16)
for case in ('pack-unavailable','source-mismatch'):
    c.put(STATE+48,0);c.put(STATE+52,0)
    c.put(STATE+40,3 if case=='pack-unavailable' else 1)
    c.put(parser+4,address-0xc18c0460);c.put(parser+36,0xc18c0460)
    if case=='source-mismatch':
        old=bytes.fromhex(qs_record['old']);u.mem_write(address+24,bytes([old[24]^1]))
    c.run(0xc05e6401,parser)
    assert c.get(STATE+48)==1 and c.get(STATE+52)==0
    if case=='source-mismatch':u.mem_write(address,bytes.fromhex(qs_record['old']))
    results.append(dict(case='qs-diagnostic-'+case,passed=True))
for case in ['pack-failed','different-buffer','changed-record']:
    p=plan['plans'][0];address=int(p['address'],16);old=bytes.fromhex(p['old'])
    c.put(STATE+40,3 if case=='pack-failed' else 1);c.put(parser+20,0xc18c0474)
    c.put(parser+4,address-0xc18c0460);c.put(parser+36,0xc18c0460)
    if case=='different-buffer':
        # Another in-memory pack at the same relative position must be untouched.
        c.put(parser+4,0);c.put(parser+36,0x10001000);u.mem_write(0x10001000,old)
    if case=='changed-record':
        u.mem_write(address+24,bytes([old[24]^1]));old=old[:24]+bytes([old[24]^1])+old[25:]
    c.run(0xc05e6401,parser)
    assert seen[-1]==old,case
    if case=='changed-record':u.mem_write(address,bytes.fromhex(p['old']))
    results.append(dict(case=case,passed=True))
u.hook_del(h)
for alias,index in ALIAS.items():
    c.put(parser+16,0x2b018);c.put(parser+20,0xc18c0474)
    result=c.run(0xc05e5b59,parser,index)
    assert bytes(u.mem_read(result,len(alias)+1))==alias.encode()+b'\0'
    c.put(parser+20,0x10001000)
    assert c.run(0xc05e5b59,parser,index)==0
    results.append(dict(case='bounded-alias-'+alias,passed=True))
c.put(parser+20,0xc18c0474)
assert c.run(0xc05e5b59,parser,0xffffffff)==0
assert c.run(0xc05e5b59,parser,0x235c4)==0xc18c0474+0x235c4
results.append(dict(case='stock-string-lookup-preserved',passed=True))

calls=[];returns=[0,0]
def load_boundary(uc,address,size,data):
    args=[uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
    calls.append(args)
    if args[1]==BASE+syms['ui_pack']:
        assert bytes(uc.mem_read(args[1],args[2]))==(OUT/'FP3KUI.NBR').read_bytes()
    sp=uc.reg_read(UC_ARM_REG_SP);lr=c.get(sp+24)
    uc.reg_write(UC_ARM_REG_SP,sp+28);uc.reg_write(UC_ARM_REG_R0,returns[min(len(calls)-1,len(returns)-1)]);uc.reg_write(UC_ARM_REG_PC,lr)
h=u.hook_add(UC_HOOK_CODE,load_boundary,begin=0xc05e84dc,end=0xc05e84dc)
for case,native_result,private_result in [('pack-ok',0,0),('pack-failed',0,2),('stock-failed',2,0)]:
    calls.clear();returns[:]=[native_result,private_result];c.put(STATE+36,0);c.put(STATE+40,0)
    assert c.run(0xc05e84d9,0x10000400,0xc0d22400,123,0)==native_result
    assert len(calls)==(1 if native_result else 2)
    assert c.get(STATE+40)==(0 if native_result else 3 if private_result else 1)
    if case=='pack-ok':
        calls.clear();c.run(0xc05e84d9,0x10000400,0xc0d22400,123,0);assert len(calls)==1
    results.append(dict(case=case,passed=True))
# A normal NBU parse can register the pack when stock NBR was loaded earlier.
calls.clear();returns[:]=[0];c.put(STATE+36,0);c.put(STATE+40,0)
p=plan['plans'][0];address=int(p['address'],16)
c.put(parser+4,address-0xc18c0460);c.put(parser+36,0xc18c0460)
ph=u.hook_add(UC_HOOK_CODE,parser_boundary,begin=0xc05e6404,end=0xc05e6404)
c.run(0xc05e6401,parser)
assert len(calls)==1 and calls[0][1]==BASE+syms['ui_pack']
assert seen[-1]==bytes.fromhex(p['new']) and c.get(STATE+40)==1
u.hook_del(ph);u.hook_del(h)
results.append(dict(case='late-resource-pack-registration',passed=True))

# Real native enum mapping in both HUD publishers; only the UI queue is mocked.
events=[];setter_args=[]
def queue(uc,address,size,data):
    ptr=uc.reg_read(UC_ARM_REG_R1);name=bytes(uc.mem_read(ptr,14)).split(b'\0',1)[0].decode()
    events.append((name,uc.reg_read(UC_ARM_REG_R2)))
    uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
# Camera's existing queue hook returns first, so replace its callback behavior.
original_boundary=c.boundary
def replacement(uc,a,n,d):
    if a==0xc0593f30:queue(uc,a,n,d)
    else:original_boundary(uc,a,n,d)
# Existing bound-method hook cannot be replaced; a fresh fixture subclass owns it.
class DisplayCamera(Camera):
    def boundary(self,uc,a,n,d):
        if a==0xc0593f30:return queue(uc,a,n,d)
        if a==0xc005c024:setter_args.append(uc.reg_read(UC_ARM_REG_R2))
        return super().boundary(uc,a,n,d)
d=DisplayCamera();d.install()
assert d.get(STATE+28)==d.get(STATE+32)==0
d.select(2);d.assert_3k();assert events[-2:]==[('LV_Resolution',3),('MV_Resolution',2)]
d.select(0);d.assert_stock();assert events[-2:]==[('LV_Resolution',0),('MV_Resolution',0)]
results.append(dict(case='HUD-refresh-without-startup-observers',passed=True))
for address in [0xc059c640,0xc059c9f0]:
    d.run(address,0x10000100,3);assert events[-1]==('LV_Resolution',0)
d.select(2);d.assert_3k();assert events[-3:]==[('MV_Resolution',2),('LV_Resolution',3),('LV_Resolution',3)]
d.select(0);d.assert_stock();assert events[-3:]==[('MV_Resolution',0),('LV_Resolution',0),('LV_Resolution',0)]
results.append(dict(case='HUD-select-and-UHD-restore',passed=True))
d.put(0x10000408,2);d.run(0xc05824d0,0x10000400,0);d.assert_3k();assert setter_args[-1]==1
d.put(0x10000408,1);d.run(0xc05824d0,0x10000400,0);d.assert_stock();assert setter_args[-1]==1
assert events[-3:]==[('MV_Resolution',1),('LV_Resolution',1),('LV_Resolution',1)]
results.append(dict(case='QS-selection-preserves-apply-flag',passed=True))
report=dict(cases=results,payload_sha256=hashlib.sha256(code).hexdigest(),
            limitations='Native parser-copy trampoline, alias resolver, loader dispatch, HUD enum mapping, QS/capture transitions executed. Parser record consumption, pack registration, UI queue and settings service are mocked here. Separate pack/decoder tests exercise native parsing. Full GUI rendering remains untested.')
(OUT/'layout-ui-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(results),'native UI hook cases')
