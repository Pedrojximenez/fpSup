"""Offline tests for the RAM snapshot component; invoked by emulator verifier."""
import struct
import sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

def verify(profiles):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/'research/fpSup/fp_usb_shell'))
    from armasm import assemble, symbols
    source = root/'tools/raw_snapshot.S'
    code, syms = assemble(source), symbols(source)
    code_base, dest, stack, stop = 0x20000000, 0x41000100, 0x42000000, 0x20000ffc
    source_ptr = 0x43000100
    sensor, manager, settings, acquisition = 0xc343b588, 0xc375d840, 0xc31f869c, 0xc343a950
    profile = next(r for r in profiles['rows'] if 429 in r['profile_ids'])
    cases = [('valid',source_ptr), ('null',0), ('unaligned',source_ptr+1),
             ('mmio',0x30100000), ('outside_windows',0x60000000),
             ('end_overflow',0x4fffff00), ('wrong_parameter_pointer',source_ptr),
             ('source_changes',source_ptr), ('mode_changes',source_ptr), ('parameter_changes',source_ptr)]
    results=[]
    for name, pointer in cases:
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        for base,size in ((code_base,0x1000),(0x41000000,0x2000),(stack,0x4000),
                          (0x43000000,0x1000),(0xc343a000,0x2000),(0xc375d000,0x1000),
                          (0xc31f8000,0x1000),(0xc3476000,0x1000),(0xc347d000,0x2000)):
            u.mem_map(base,size)
        u.mem_write(code_base,code)
        u.mem_protect(code_base,0x1000,UC_PROT_READ|UC_PROT_EXEC)
        put=lambda address,value:u.mem_write(address,struct.pack('<I',value))
        u.mem_write(dest-16,bytes([0xa5])*0x360)
        put(sensor+4,151);put(manager+8,pointer)
        put(source_ptr,429);put(source_ptr+4,source_ptr+0x5c)
        u.mem_write(source_ptr+0x5c,struct.pack('<67I',*(profile['words']+[6064,4042])))
        expected_params=bytes(u.mem_read(source_ptr+0x5c,0x10c))
        if name=='wrong_parameter_pointer':put(source_ptr+4,0x30100000)
        put(settings,3840);put(settings+4,2160)
        put(acquisition+4,3856);put(acquisition+8,2170)
        put(0xc347d1d4,0);u.mem_write(0xc347e08f,b'\x01')
        def guard(engine,access,address,size,value,user):
            assert (dest<=address and address+size<=dest+0x340) or (stack<=address and address+size<=stack+0x4000),hex(address)
        u.hook_add(UC_HOOK_MEM_WRITE,guard)
        changed=[]
        def mutate(engine,address,size,user):
            if address==code_base+syms['finish'] and not changed:
                if name=='source_changes':put(manager+8,source_ptr+0x200)
                if name=='mode_changes':put(sensor+4,8)
                changed.append(True)
            # Change the parameter pointer after copying its contents, before
            # the component rechecks it. Find the ORR setting copied flag.
            if name=='parameter_changes' and bytes(engine.mem_read(address,4))==bytes.fromhex('01a08ae3'):
                put(source_ptr+4,source_ptr+0x60)
        u.hook_add(UC_HOOK_CODE,mutate)
        u.reg_write(UC_ARM_REG_R0,dest);u.reg_write(UC_ARM_REG_SP,stack+0x3ff0);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(code_base,stop,count=10000)
        assert u.reg_read(UC_ARM_REG_PC)==stop,name
        flags=u.reg_read(UC_ARM_REG_R0)
        expected={'valid':1,'source_changes':3,'mode_changes':5,'parameter_changes':3}.get(name,0)
        assert flags==expected,(name,flags,expected)
        assert bytes(u.mem_read(dest-16,16))==bytes([0xa5])*16,name
        assert bytes(u.mem_read(dest+0x340,16))==bytes([0xa5])*16,name
        assert struct.unpack('<2I',u.mem_read(dest+0x120,8))==(3840,2160)
        assert u.mem_read(dest+0x30c,1)==b'\x01'
        if flags&1:assert bytes(u.mem_read(dest+0x200,0x10c))==expected_params,name
        else:assert bytes(u.mem_read(dest+0x200,0x10c))==bytes(0x10c),name
        results.append({'case':name,'flags':flags,'passed':True})
    (root/'analysis/firmware/raw-snapshot.bin').write_bytes(code)
    return {'code_bytes':len(code),'record_bytes':0x340,'cases':results,
            'status':'Offline component only. No scheduler, allocation wrapper, loader, file writer or deployable AutoRun.',
            'limitations':'Concurrent mutation detection is best effort; parameter fields can change without pointer changes. No atomic snapshot claim.'}
