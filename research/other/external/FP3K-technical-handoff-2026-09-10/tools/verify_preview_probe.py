"""Exercise preview trace bounds, capture identities, and delayed file saving.
Sleep/filesystem are mocked. No camera access.
"""
import hashlib
import json
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from build_preview_probe import build, ROOT, OUT, BASE, COUNT, STRIDE, TOTAL, INTERVAL, STATE_BYTES

code, syms, manifest = build()
profiles = json.loads((ROOT / 'analysis/firmware/raw-profiles.json').read_text())
results = []
for case in ('mode_transitions', 'late_stop', 'idle', 'always_recording', 'finalizing', 'bad_pool', 'small_pool', 'corrupt_body', 'bad_source'):
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    pool, source, stack, stop = 0x41000100, 0x43000100, 0x42000000, 0xc0000000
    ranges = [(0xc0731000,0x2000), (pool&~4095,0x22000),(source&~4095,4096),(stack,0x4000),
              (0xc343a000,0x2000),(0xc3757000,4096),(0xc375d000,4096),(0xc31f8000,4096),
              (0xc3476000,4096),(0xc347d000,0x2000),(0xc358e000,4096),(0xc35a9000,4096),
              (0xc0bac000,4096),(0xc0421000,4096),(0xc03fa000,4096),(0xc31df000,4096),(0xc31d2000,4096)]
    for address, size in ranges:
        u.mem_map(address, size)
    blob = bytearray(code)
    if case == 'corrupt_body':
        blob[syms['raw_snapshot']+4] ^= 1
    u.mem_write(BASE, bytes(blob))
    # Canary around the probe catches overlaps with the resident and its state.
    u.mem_write(BASE-16, b'\xa5'*16)
    u.mem_write(BASE+len(code), b'\xa5'*16)
    u.mem_protect(0xc0731000,0x2000,UC_PROT_READ|UC_PROT_EXEC)
    def put(address, value):
        u.mem_write(address, struct.pack('<I', value))
    def get(address):
        return struct.unpack('<I', u.mem_read(address,4))[0]
    put(0xc3757a7c, 0x30100000 if case=='bad_pool' else pool)
    put(0xc3757a80, 64 if case=='small_pool' else 0x20000)
    put(0xc375d848, 0x30100000 if case=='bad_source' else source)
    put(source+4,source+0x5c)
    u.mem_write(pool-16,b'\xa5'*16)
    u.mem_write(pool+0x20000,b'\xa5'*16)
    u.mem_write(0xc31df564, bytes((i*7)%256 for i in range(0x360)))
    u.mem_write(0xc31d2800, bytes(range(256)))
    put(0xc0732030,10)
    put(0xc0732034,2)
    put(0xc0732038,3)
    put(0xc073203c,0xc3f00000)
    clock, saved, sleeps = [0], [], []
    def states():
        t=clock[0]
        active=case=='always_recording' or case=='mode_transitions' and 12000<=t<18000 or case=='late_stop' and 12000<=t<46000
        still=case=='mode_transitions' and 3000<=t<9000
        profile_id=429 if active else 1 if still else 5
        row=next(r for r in profiles['rows'] if profile_id in r['profile_ids'])
        put(source,profile_id)
        u.mem_write(source+0x5c,struct.pack('<67I',*(row['words']+[6064,4042])))
        put(0xc343b58c,151 if active else 8)
        u.mem_write(0xc347e08f,bytes([int(active)]))
        put(0xc358e140,0x43000000 if active or case=='finalizing' else 0)
        put(0xc0732010,int(active))
    states()
    def guard(uc,access,address,size,value,data):
        assert pool<=address and address+size<=pool+0x20000 or stack<=address and address+size<=stack+0x4000 or address==0xc0bac2f8 and size==4,hex(address)
    u.hook_add(UC_HOOK_MEM_WRITE,guard)
    def cstring(address):
        return bytes(u.mem_read(address,64)).split(b'\0',1)[0].decode('ascii')
    def boundary(uc,address,size,data):
        if address==0xc0421770:
            delay=u.reg_read(UC_ARM_REG_R0)
            assert delay in (INTERVAL,250)
            clock[0]+=delay
            sleeps.append(delay)
            states()
        else:
            assert address==0xc03fa0e0
            assert get(0xc343b58c)==8 and get(0xc358e140)==0 and u.mem_read(0xc347e08f,1)==b'\0'
            assert u.reg_read(UC_ARM_REG_R0)==0x12345678 and u.reg_read(UC_ARM_REG_R1)==3
            argv=u.reg_read(UC_ARM_REG_R2)
            assert [cstring(get(argv+i*4)) for i in range(3)] == ['save','\\FP3KPV\\STATE.BIN',f'0x{pool:08X},,{TOTAL}']
            assert get(pool)==0x31565046 and get(pool+12)==COUNT and get(pool+0x20)==TOTAL
            assert clock[0]>=COUNT*INTERVAL+3000
            for i in range(COUNT):
                r=pool+64+i*STRIDE
                assert get(r)==i
                assert bytes(u.mem_read(r+0x440,0x360))==bytes((j*7)%256 for j in range(0x360))
                assert bytes(u.mem_read(r+0x800,256))==bytes(range(256))
                assert get(r+0x7d0)==(10 if STATE_BYTES>=56 else 0)
                assert get(r+0x7d4)==(2 if STATE_BYTES>=56 else 0)
                assert get(r+0x7d8)==(3 if STATE_BYTES>=64 else 0)
                assert get(r+0x7dc)==(0xc3f00000 if STATE_BYTES>=64 else 0)
                if case=='bad_source':assert get(r+0x18)&1==0
                else:assert get(r+0x18)&1==1
            if case=='mode_transitions':
                assert {get(pool+64+i*STRIDE+0x1a0) for i in range(COUNT)}=={1,5,429}
                assert {get(pool+64+i*STRIDE+0x7b0) for i in range(COUNT)}=={0,1}
            from read_preview_probe import analyze
            captured=bytes(u.mem_read(pool,TOTAL))
            parsed=analyze(captured)
            assert len(parsed['samples'])==COUNT
            try:
                analyze(captured[:-1])
            except AssertionError:
                pass
            else:
                raise AssertionError('Truncated capture accepted')
            saved.append(clock[0])
        u.reg_write(UC_ARM_REG_R0,1)
        u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
    for address in (0xc0421770,0xc03fa0e0):
        u.hook_add(UC_HOOK_CODE,boundary,begin=address,end=address)
    u.reg_write(UC_ARM_REG_R0,0x12345678)
    u.reg_write(UC_ARM_REG_SP,stack+0x3ff0)
    u.reg_write(UC_ARM_REG_LR,stop)
    u.emu_start(BASE,stop,count=1000000)
    assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack+0x3ff0
    assert get(0xc0bac2f8)==0xc03d99a0
    assert bytes(u.mem_read(BASE-16,16))==bytes(u.mem_read(BASE+len(code),16))==b'\xa5'*16
    assert bytes(u.mem_read(pool-16,16))==bytes(u.mem_read(pool+0x20000,16))==b'\xa5'*16
    assert bool(saved)==(case in ('mode_transitions','late_stop','idle','bad_source'))
    if case in ('bad_pool','small_pool','corrupt_body'):assert not sleeps
    assert clock[0]<=COUNT*INTERVAL+60000
    results.append(dict(case=case,passed=True,simulated_ms=clock[0],file_calls=len(saved)))

report=dict(probe_sha256=hashlib.sha256(code).hexdigest(),cases=results,
            limitations='Native sleep and filesystem mocked. Simulated RAM contents. No physical camera scheduling, resource lifecycle or display behavior tested.')
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
