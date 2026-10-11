"""Build and exercise the guarded full-height3K candidate; no camera I/O."""
import hashlib,json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_PROT_READ,UC_PROT_EXEC,UC_PROT_ALL,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
from fullheight_candidate import plan
COUNT=len(plan())
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/firmware'
BASE,STATUS,ECHO=0xc072de64,0xc072e800,0xc0bac2f8
ORIGINAL_ECHO=0xc03d99a0
def build():
    sys.path.insert(0,str(ROOT/'research/fpSup/fp_usb_shell'))
    from armasm import assemble,symbols
    src=ROOT/'tools/three_k_fullheight.S'
    code=bytearray(assemble(src));syms=symbols(src)
    assert syms['payload_end']==len(code) and BASE+len(code)<STATUS
    struct.pack_into('<I',code,syms['checksum_word'],(-sum(struct.unpack('<'+'I'*(len(code)//4),code)))&0xffffffff)
    assert sum(struct.unpack('<'+'I'*(len(code)//4),code))&0xffffffff==0
    main=(OUT/'MAIN_c0000000.bin').read_bytes()
    assert hashlib.sha256(main).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
    assert main[BASE-0xc0000000:STATUS-0xc0000000+16]==bytes(STATUS-BASE+16)
    entries=[struct.unpack_from('<3I',code,syms['patch_table']+12*i) for i in range(COUNT)]
    assert entries==[(e['address'],e['expected'],e['replacement']) for e in plan()]
    for a,old,new in entries:assert struct.unpack_from('<I',main,a-0xc0000000)[0]==old
    assert struct.unpack_from('<I',main,ECHO-0xc0000000)[0]==ORIGINAL_ECHO
    (OUT/'three-k-fullheight.bin').write_bytes(code)
    return bytes(code),syms,entries,main

def verify():
    code,syms,entries,main=build()
    profiles=json.loads((OUT/'raw-profiles.json').read_text())
    results=[]
    busy_addresses=[0xc343b58c,0xc3476609,0xc347e08f,0xc358e140,0xc35a952c]
    specs=[('success',None),('corrupt_body',None),('rollback',None)]
    specs += [('wrong_stock',i) for i in range(COUNT)]
    specs += [('busy',i) for i in range(5)]
    specs += [('became_busy',None),('already_applied',None)]
    for name,index in specs:
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        n=(len(main)+4095)&~4095
        u.mem_map(0xc0000000,n);u.mem_write(0xc0000000,main)
        u.mem_protect(0xc0000000,n,UC_PROT_READ|UC_PROT_EXEC)
        for page in {BASE&~4095,STATUS&~4095,ECHO&~4095,*[a&~4095 for a,_,_ in entries]}:
            u.mem_protect(page,4096,UC_PROT_ALL)
        DATA,STACK,STOP=0x10000000,0x10010000,0xc0000000
        for a,n in [(DATA,4096),(STACK,0x4000),(0xc343b000,4096),(0xc3476000,4096),(0xc347e000,4096),(0xc358e000,4096),(0xc35a9000,4096)]:u.mem_map(a,n)
        put=lambda a,v:u.mem_write(a,struct.pack('<I',v))
        get=lambda a:struct.unpack('<I',u.mem_read(a,4))[0]
        blob=bytearray(code)
        if name=='corrupt_body':blob[syms['patch_table']+8]^=1
        u.mem_write(BASE,bytes(blob));put(ECHO,BASE);put(0xc343b58c,8)
        if name=='wrong_stock':put(entries[index][0],entries[index][1]^1)
        if name=='already_applied':
            for a,old,new in entries:put(a,new)
        if name=='busy':
            a=busy_addresses[index]
            if index in (0,3):put(a,151 if index==0 else 0x10000000)
            else:u.mem_write(a,b'\1')
        before={a:get(a) for a,_,_ in entries}
        writes=[];extra=[];idle_calls=[0]
        def guard(uc,access,a,n,v,data):
            assert any(lo<=a and a+n<=hi for lo,hi in [(STACK,STACK+0x4000),(STATUS,STATUS+16),(ECHO,ECHO+4),*[(x,x+4) for x,_,_ in entries],*extra]),hex(a)
            if a in before:writes.append([a,v])
        u.hook_add(UC_HOOK_MEM_WRITE,guard)
        def inject(uc,a,n,data):
            if a==BASE+syms['idle_check']:
                idle_calls[0]+=1
                if name=='became_busy' and idle_calls[0]==2:put(0xc343b58c,151)
            if name=='rollback' and a==BASE+syms['verify_readback']:put(entries[0][0],0)
        u.hook_add(UC_HOOK_CODE,inject)
        def run(addr,*args):
            u.reg_write(UC_ARM_REG_SP,STACK+0x3ff0);u.reg_write(UC_ARM_REG_LR,STOP)
            for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):u.reg_write(reg,v)
            u.emu_start(addr,STOP,count=30000)
            assert u.reg_read(UC_ARM_REG_PC)==STOP
        run(BASE)
        assert get(ECHO)==ORIGINAL_ECHO
        expected={'success':16,'corrupt_body':2,'rollback':5,'wrong_stock':4,'busy':3,'became_busy':3,'already_applied':4}[name]
        assert get(STATUS+4)==expected,(name,get(STATUS+4))
        if name=='success':
            assert len(writes)==COUNT
            # Follow actual patched firmware tables through all306 stock rows.
            extra[:]=[(DATA,DATA+4096)]
            for row in profiles['rows']:
                run(0xc0439d18,DATA,row['index'],0)
                actual=list(struct.unpack('<67I',u.mem_read(DATA,268)))
                want=row['words']+[6064,4042]
                if row['index']==286:
                    assert row['profile_ids']==[429]
                    for off,val in {0:3032,4:2020,0x24:3000,0x2c:2000,0xdc:3032,0xe4:2020,0x64:2048,0xd4:2048}.items():want[off//4]=val
                assert actual==want,row['index']
            run(0xc0439d18,DATA,286,0)
            put(DATA+0x200,429);put(DATA+0x204,DATA);put(DATA+0x258,0xc0bd04b0)
            run(0xc0438018,DATA+0x400,DATA+0x200,DATA+0x300)
            d=list(struct.unpack('<48I',u.mem_read(DATA+0x400,192)))
            assert d[:2]==[3032,2020] and d[6:8]==[16,10] and d[18:20]==[2048,2048]
            run(0xc03d9630,DATA+0x400)
            assert u.reg_read(UC_ARM_REG_R0)==9186968
        elif name=='rollback':
            assert len(writes)==2*COUNT and all(get(a)==old for a,old,_ in entries)
        else:
            assert not writes and all(get(a)==v for a,v in before.items())
        results.append(dict(case=name,index=index,status=expected,table_write_count=len(writes),passed=True))
    report=dict(payload_bytes=len(code),payload_sha256=hashlib.sha256(code).hexdigest(),cases=results,
        table_entries=[dict(address=hex(a),expected=old,replacement=new) for a,old,new in entries],
        scope='Full-height candidate: mode151 native full-height windows and geometry; stock true24 timing retained, RAW ratio2048. Hardware validation required.',
        validation='Guard/failure cases for every changed word and idle flag; all306 processing rows checked; descriptor and byte count checked. No firmware function stubs in these tests.',
        limitations='Hardware not tested. No DMA, sensor, image-quality, file I/O, power-loss or instruction-loading fault model. Bootstrap checksum cannot guarantee safety if bootstrap itself is corrupted.')
    (OUT/'three-k-fullheight-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':verify()
