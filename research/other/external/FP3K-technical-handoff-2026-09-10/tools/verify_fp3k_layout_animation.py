"""Execute Sigma's animation parser through the installed record-copy hook.

Component registry/attachment is mocked. Native key creation, decoding and
string copying execute, proving that the temporary record is not retained by
those key objects.
"""
import json,struct
from pathlib import Path
from collections import deque
from unicorn import *
from unicorn.arm_const import *
from build_fp3k_native_menu import BASE,STATE,HOOKS,branch_word
from experimental_ui_record_compaction import animation
from inspect_uic_resources import load,POOL,START

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'prototype/development/native-ui'
main,strings,_=load();plan=json.loads((OUT/'layout-repair-plan.json').read_text());plan['aliases']={'FP3K_L':0xfffffff0,'FP3K_M':0xfffffff1,'FP3K_QS':0xfffffff2,'FP3K_SET':0xfffffff3,'FP3K_FONT':0xfffffff4}
manifest=json.loads((ROOT/'prototype/development/native-menu/resident-manifest.json').read_text())
payload=(ROOT/'prototype/development/native-menu/FP3KMENU.BIN').read_bytes()
u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0xc0000000,(len(main)+4095)&~4095);u.mem_write(0xc0000000,main)
u.mem_write(BASE,payload)
for address,label in HOOKS:u.mem_write(address,struct.pack('<I',branch_word(address,int(manifest['symbols'][label],16),label)))
u.mem_protect(0xc0000000,(len(main)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
u.mem_map(0x10000000,0x400000)
CTX=0x10000000;ALLOC=0x10001000;PARSER=0x10002000;SERVICE=0x10003000;SP=0x103ffff0
def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
def string(a):return bytes(u.mem_read(a,128)).split(b'\0',1)[0].decode()
put(ALLOC,0x10004000,0x10004004,0x10004008)
put(CTX+8,ALLOC);put(SERVICE+12,ALLOC)
put(STATE+36,CTX,1)
heap=[0x10100000];nodes={};curves=[];trace=deque(maxlen=16)
def allocate(n):
    assert 0<n<0x10000
    p=heap[0];heap[0]+=(n+15)&~15;assert heap[0]<0x10300000
    return p
def boundary(uc,a,n,d):
    r=[uc.reg_read(x) for x in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]];ret=0
    if a==0x10004000:ret=allocate(r[0])
    elif a==0xc05d9e80:
        assert string(r[1])=='animationClip';ret=0x10005000
    elif a==0xc05e5f10:ret=r[1]
    elif a==0xc05e82a0:ret=0x10006000
    elif a==0xc05d5968:
        out=get(uc.reg_read(UC_ARM_REG_SP)+4);put(out,allocate(0x80))
    elif a==0xc05e2738:
        curve=allocate(0x40);put(curve+8,r[1]);put(r[3],curve)
        curves.append(dict(pointer=curve,type=r[1],expected_count=r[2],keys=[]));nodes[curve]=curves[-1]
    elif a==0xc05e28c8:
        curve=nodes[r[0]];node=r[1]
        v=get(node+24)
        if curve['type']==2:assert 0x10100000<=v<0x10300000,hex(v)
        value=string(v) if curve['type']==2 else v
        curve['keys'].append(dict(time=get(node),flags=(get(node+48),get(node+44)),value=value))
    elif a==0xc05e1c28:
        curve=nodes[r[1]];curve.update(component=r[2],property=string(r[3]),dimension=get(uc.reg_read(UC_ARM_REG_SP)))
    uc.reg_write(UC_ARM_REG_R0,ret);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
mocks=[0x10004000,0x10004004,0x10004008,0xc05d9e80,0xc05e5f10,0xc05e82a0,0xc05d5968,0xc05d5db8,0xc05e1a58,0xc05e2738,0xc05e28c8,0xc05edb10,0xc05e1c28,0xc05e2798,0xc05d1490,0xc05d5d08]
for a in mocks:u.hook_add(UC_HOOK_CODE,boundary,begin=a,end=a)
u.hook_add(UC_HOOK_CODE,lambda uc,a,n,d:trace.append(hex(a)))
rows=[]
for p in plan['plans']:
    if int.from_bytes(bytes.fromhex(p['new'])[:4],'big')!=0x1000a:continue
    curves.clear();nodes.clear();heap[0]=0x10100000
    address=int(p['address'],16);position=address-0xc18c0460
    put(PARSER,0x01090000,position,CTX,SERVICE,START-POOL,0xc18c0474)
    put(PARSER+32,0xc2d8cef8-0xc18c0460,0xc18c0460)
    put(PARSER+52,0xc05e5d79,0xc05e5db9,0xc05e5e39,0xc05e5ea9)
    u.reg_write(UC_ARM_REG_FPEXC,0x40000000);u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000)
    u.reg_write(UC_ARM_REG_R0,PARSER);u.reg_write(UC_ARM_REG_SP,SP);u.reg_write(UC_ARM_REG_LR,0xc0000000)
    try:u.emu_start(0xc05e6401,0xc0000000,count=200000)
    except Exception:
        print(p['address'],list(trace));raise
    assert u.reg_read(UC_ARM_REG_PC)==0xc0000000 and u.reg_read(UC_ARM_REG_SP)==SP
    assert get(PARSER+4)==position+p['size'] and get(PARSER+36)==0xc18c0460
    expected=animation(bytes.fromhex(p['new']))
    assert len(curves)==len(expected),(p['address'],curves)
    for actual,(typ,component,name,dimension,keys) in zip(curves,expected):
        assert (actual['type'],actual['component'],actual['property'],actual['dimension'])==(typ,component,strings[name],dimension)
        assert len(actual['keys'])==len(keys)==actual['expected_count']
        for parsed,raw in zip(actual['keys'],keys):
            value=struct.unpack_from('>I',raw,6)[0]
            if typ==2:value=next((k for k,v in plan['aliases'].items() if v==value),strings.get(value))
            assert parsed==dict(time=struct.unpack_from('>I',raw,2)[0],flags=(raw[0],raw[1]),value=value),(p['address'],parsed,raw.hex())
    # Destroy the entire old temporary stack region after parsing; copied
    # strings and decoded key values remain in the bounded allocator region.
    u.mem_write(SP-0x1000,bytes([0xa5])*0x1000)
    rows.append(dict(address=p['address'],properties=len(curves),passed=True))
report=dict(cases=rows,payload_sha256=manifest['sha256'],
            limitations='Actual native animation parser, compact key reader, key constructor and string allocator execute. UI component registry, curve attachment and final GUI rendering are mocked.')
(OUT/'layout-animation-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(rows),'native animation-parser cases')
