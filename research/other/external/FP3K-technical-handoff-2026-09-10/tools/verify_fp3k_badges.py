"""Decode new badge frames with Sigma's actual ARM decoder, no API mocks."""
from pathlib import Path
import json, struct, hashlib
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from inspect_xci import decode

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'prototype/development/native-ui'
main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
cases=[]
for asset in json.loads((OUT/'badges.json').read_text())['assets']:
    file=OUT/(asset['name']+'.xci')
    data=file.read_bytes();raw=file.with_suffix('.raw').read_bytes()
    w,h,decoded=decode(data)
    assert decoded==raw and len(raw)==w*h*2
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    size=(len(main)+4095)&~4095
    u.mem_map(0xc0000000,size)
    u.mem_write(0xc0000000,main)
    u.mem_protect(0xc0000000,size,UC_PROT_READ|UC_PROT_EXEC)
    u.mem_map(0x10000000,0x40000)
    source=0x10001000;destination=0x10010000;sp=0x1003fff0
    u.mem_write(source,data[32:])
    u.mem_write(destination,bytes([0xa5])*(len(raw)+32))
    u.mem_write(sp,struct.pack('<I',len(raw)))
    def guard(uc,access,address,length,value,opaque):
        assert destination<=address and address+length<=destination+len(raw) or 0x10030000<=address and address+length<=sp,hex(address)
    u.hook_add(UC_HOOK_MEM_WRITE,guard)
    for reg,value in [(UC_ARM_REG_R0,0x10000100),(UC_ARM_REG_R1,source),
                      (UC_ARM_REG_R2,len(data)-32),(UC_ARM_REG_R3,destination),
                      (UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,0xc0000000)]:
        u.reg_write(reg,value)
    u.emu_start(0xc05a7e50,0xc0000000,count=500000)
    assert u.reg_read(UC_ARM_REG_PC)==0xc0000000
    assert u.reg_read(UC_ARM_REG_SP)==sp
    assert u.reg_read(UC_ARM_REG_R0)==len(raw)
    assert bytes(u.mem_read(destination,len(raw)))==raw
    assert bytes(u.mem_read(destination+len(raw),32))==bytes([0xa5])*32
    cases.append(dict(asset=file.name,decoded_bytes=len(raw),sha256=hashlib.sha256(data).hexdigest(),passed=True))
report=dict(cases=cases,native_decoder='0xc05a7e50',mocked=[],
            limitations='Verifies image decompression and output bounds. Resource registration and screen rendering remain separate checks.')
(OUT/'badge-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS',len(cases),'native badge decodes')
