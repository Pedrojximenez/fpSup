"""Test bounded capture wrapper with simulated clock and filesystem calls."""
import struct
import hashlib
import sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

def build():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'research/fpSup/fp_usb_shell'))
    from armasm import assemble,symbols
    source=root/'tools/raw_capture.S'
    code=bytearray(assemble(source)); syms=symbols(source)
    checksum=(-sum(struct.unpack(f'<{len(code)//4}I',code)))&0xffffffff
    struct.pack_into('<I',code,syms['checksum_word'],checksum)
    assert sum(struct.unpack(f'<{len(code)//4}I',code))&0xffffffff==0
    assert 0xc072de64+len(code)<0xc072f000
    (root/'analysis/firmware/raw-capture.bin').write_bytes(code)
    return bytes(code),syms

def verify(profiles):
    code,syms=build()
    code_base,pool,source_ptr,stack,stop=0xc072de64,0x41000100,0x43000100,0x42000000,0xc072fff0
    profile=next(r for r in profiles['rows'] if 429 in r['profile_ids'])
    results=[]
    for case in ('short_take','late_stop','no_take','always_recording','finalizing','bad_pool','small_pool','corrupt_body'):
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        for base,size in ((0xc072d000,0x3000),(0x41000000,0x22000),(stack,0x4000),(0x43000000,0x1000),
                          (0xc343a000,0x2000),(0xc3757000,0x1000),(0xc375d000,0x1000),(0xc31f8000,0x1000),
                          (0xc3476000,0x1000),(0xc347d000,0x2000),(0xc358e000,0x1000),(0xc35a9000,0x1000),
                          (0xc0bac000,0x1000),(0xc0421000,0x1000),(0xc03fa000,0x1000)):
            u.mem_map(base,size)
        blob=bytearray(code)
        if case=='corrupt_body':blob[syms['raw_snapshot']+4]^=1
        u.mem_write(code_base,bytes(blob));u.mem_protect(0xc072d000,0x3000,UC_PROT_READ|UC_PROT_EXEC)
        put=lambda address,value:u.mem_write(address,struct.pack('<I',value))
        get=lambda address:struct.unpack('<I',u.mem_read(address,4))[0]
        put(0xc3757a7c,0x30100000 if case=='bad_pool' else pool)
        put(0xc3757a80,64 if case=='small_pool' else 0x20000)
        put(0xc375d848,source_ptr)
        put(source_ptr,429);put(source_ptr+4,source_ptr+0x5c)
        u.mem_write(source_ptr+0x5c,struct.pack('<67I',*(profile['words']+[6064,4042])))
        put(0xc31f869c,3840);put(0xc31f86a0,2160)
        u.mem_write(pool-16,b'\xa5'*16);u.mem_write(pool+0x20000,b'\xa5'*16)
        clock=[0];saved=[];sleeps=[]
        def states():
            t=clock[0]
            active=case=='always_recording' or (case in ('short_take','late_stop') and 1000<=t<(4000 if case=='short_take' else 35000))
            pending=active or case=='finalizing' or (case=='short_take' and 4000<=t<6000)
            put(0xc343b58c,151 if active else 8)
            u.mem_write(0xc347e08f,bytes([int(active)]))
            put(0xc358e140,0x43000000 if pending else 0)
        states()
        def guard(engine,access,address,size,value,user):
            assert (pool<=address and address+size<=pool+0x20000) or (stack<=address and address+size<=stack+0x4000) or (address==0xc0bac2f8 and size==4),hex(address)
        u.hook_add(UC_HOOK_MEM_WRITE,guard)
        def cstring(address):return bytes(u.mem_read(address,64)).split(b'\0',1)[0].decode('ascii')
        def call_hook(engine,address,size,user):
            if address==0xc0421770:
                delay=u.reg_read(UC_ARM_REG_R0);assert delay==250
                clock[0]+=delay;sleeps.append(delay);states()
                u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
            elif address==0xc03fa0e0:
                assert get(0xc343b58c)==8 and get(0xc358e140)==0
                assert u.mem_read(0xc347e08f,1)==b'\0'
                assert u.reg_read(UC_ARM_REG_R0)==0x12345678
                assert u.reg_read(UC_ARM_REG_R1)==3
                argv=u.reg_read(UC_ARM_REG_R2)
                args=[cstring(get(argv+i*4)) for i in range(3)]
                assert args==['save','\\FPD003\\STATE.BIN',f'0x{pool:08X},,99904'],args
                assert get(pool)==0x33525046 and get(pool+12)==120
                assert get(pool+0x20)==99904 and get(pool+0x1c)==1
                assert clock[0]>=33000
                from read_raw_capture import analyze
                parsed=analyze(bytes(u.mem_read(pool,99904)),profiles)
                assert parsed['profile_ids']==[429] and parsed['copied_profiles']==120
                if case=='short_take':assert parsed['sensor_modes']==[8,151]
                saved.append(clock[0]);u.reg_write(UC_ARM_REG_R0,1)
                u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,call_hook,begin=0xc0421770,end=0xc0421770)
        u.hook_add(UC_HOOK_CODE,call_hook,begin=0xc03fa0e0,end=0xc03fa0e0)
        u.reg_write(UC_ARM_REG_R0,0x12345678);u.reg_write(UC_ARM_REG_SP,stack+0x3ff0);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(code_base,stop,count=1000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop,case
        assert get(0xc0bac2f8)==0xc03d99a0
        assert bytes(u.mem_read(pool-16,16))==b'\xa5'*16
        assert bytes(u.mem_read(pool+0x20000,16))==b'\xa5'*16
        expected_save=case in ('short_take','late_stop','no_take')
        assert len(saved)==int(expected_save),(case,saved)
        assert clock[0]<=90000
        if case in ('bad_pool','small_pool','corrupt_body'):assert not sleeps
        if expected_save:
            for i in range(120):assert get(pool+64+i*832)==i
        results.append({'case':case,'passed':True,'simulated_ms':clock[0],'file_calls':len(saved)})
    return {'code_bytes':len(code),'code_sha256':hashlib.sha256(code).hexdigest(),'capture_bytes':99904,'allocation_bytes':131072,'cases':results,
            'limitations':'Sleep and file handlers are stubs. No physical camera, flash, filesystem or media contention is modeled. Bootstrap integrity cannot be guaranteed by its own checksum.'}
