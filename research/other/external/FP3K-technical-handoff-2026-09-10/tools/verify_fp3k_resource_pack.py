"""Exercise native NBR parsing and file lookup; mock the UI registry only."""
from pathlib import Path
from collections import deque
import json,struct,hashlib
from unicorn import *
from unicorn.arm_const import *

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'prototype/development/native-ui'
main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
pack=(OUT/'FP3KUI.NBR').read_bytes()
u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
u.mem_map(0xc0000000,(len(main)+4095)&~4095);u.mem_write(0xc0000000,main)
u.mem_protect(0xc0000000,(len(main)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
u.mem_map(0x10000000,0x400000)
CTX=0x10000000;ALLOC=0x10001000;PACK=0x10010000;SP=0x103ffff0
heap=[0x10100000];blocks=[];registered=[];variants=[];trace=deque(maxlen=16)
def put(a,*v):u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
def string(a):return bytes(u.mem_read(a,128)).split(b'\0',1)[0].decode()
def allocate(n):
    assert 0<n<0x10000,n
    a=heap[0];heap[0]+=(n+15)&~15;assert heap[0]<0x10200000
    blocks.append((a,n));return a
put(CTX+8,ALLOC);put(CTX+0x888,0x10002000)
put(ALLOC,0x10003000,0x10003004,0x10003008)
u.mem_write(PACK,pack)
def boundary(uc,a,n,d):
    r=[uc.reg_read(x) for x in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
    ret=0
    if a==0x10003000:ret=allocate(r[0])
    elif a==0x10003008:
        ret=allocate(r[1]);old=next(n for p,n in blocks if p==r[0]);uc.mem_write(ret,bytes(uc.mem_read(r[0],min(old,r[1]))))
    elif a==0xc05d8618:
        ret=allocate(0x60);registered.append(dict(pointer=ret,name=string(r[1]),plugin=string(r[2]),variants=r[3]))
    elif a==0xc05d87c8:
        variants.append((r[0],struct.unpack('<4I',uc.mem_read(r[1],16))))
    elif a==0xc05dae48:
        put(0x10004000,r[1])
    uc.reg_write(UC_ARM_REG_R0,ret);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
for a in [0x10003000,0x10003004,0x10003008,0xc05dfe88,0xc05d8618,0xc05e0aa8,0xc05d87c8,0xc05d8a90,0xc05e0940,0xc05dae48]:
    u.hook_add(UC_HOOK_CODE,boundary,begin=a,end=a)
u.hook_add(UC_HOOK_CODE,lambda uc,a,n,d:trace.append(hex(a)))
def call(address,*args):
    u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
    u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000)
    for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
    u.reg_write(UC_ARM_REG_SP,SP);u.reg_write(UC_ARM_REG_LR,0xc0000000)
    try:u.emu_start(address,0xc0000000,count=1000000)
    except UcError:
        print('Last native instructions:',list(trace));raise
    assert u.reg_read(UC_ARM_REG_PC)==0xc0000000,list(trace)
    assert u.reg_read(UC_ARM_REG_SP)==SP
    return u.reg_read(UC_ARM_REG_R0)
assert call(0xc05e84d9,CTX,PACK,len(pack),0x10004004)==0
parser=get(0x10004000)
assert parser==get(0x10004004)
assert [r['name'] for r in registered]==['FP3K_L','FP3K_M','FP3K_QS','FP3K_SET','FP3K_FONT'],registered
assert all(r['plugin']=='xcimage' and r['variants']==1 for r in registered)
assert len(variants)==5
for resource,(pointer,variant) in zip(registered,variants):
    assert pointer==resource['pointer'] and variant[:2]==(0xffffffff,0xffffffff)
    assert variant[2]==parser
    config=PACK+variant[3]
    assert struct.unpack('>4I',u.mem_read(config,16))==(0x20002,48,5,31)
    file_offset=struct.unpack('>I',u.mem_read(config+16,4))[0]
    assert string(PACK+20+file_offset)==resource['name']+'.xci'
    name=0x10005000;u.mem_write(name,(resource['name']+'.xci\0').encode())
    assert call(0xc05e5bb9,0x10006000,name,parser)==1
    size=get(0x10006000);data=get(0x10006004)
    assert bytes(u.mem_read(data,size))==(OUT/(resource['name']+'.xci')).read_bytes()
report=dict(passed=True,pack_sha256=hashlib.sha256(pack).hexdigest(),registered=registered,files_resolved=5,
            mocked=['bounded allocation','resource registry and deferred property attachment'],
            limitations='Native pack parsing, names, variants, and file resolution exercised. Renderer/resource instantiation remains untested.')
(OUT/'resource-pack-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS native NBR parser and all 5 private resource lookups')
