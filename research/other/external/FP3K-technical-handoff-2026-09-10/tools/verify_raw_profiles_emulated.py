"""Run stock ARM table loader/getters locally. No camera access or MMIO model."""
import hashlib
import json
import struct
from pathlib import Path
import unicorn
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware'
firmware = (OUT / 'MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(firmware).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
profiles = json.loads((OUT / 'raw-profiles.json').read_text())
uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
uc.mem_map(0xc0000000, (len(firmware)+4095)&~4095)
uc.mem_write(0xc0000000, firmware)
uc.mem_protect(0xc0000000, (len(firmware)+4095)&~4095, UC_PROT_READ | UC_PROT_EXEC)
DATA, STACK, STOP = 0x10000000, 0x10010000, 0xc0000000
uc.mem_map(DATA, 0x1000)
uc.mem_map(STACK, 0x4000)
allowed = []

def check_write(engine, access, address, size, value, user):
    assert any(lo <= address and address+size <= hi for lo, hi in allowed), hex(address)

uc.hook_add(UC_HOOK_MEM_WRITE, check_write)

def run(address, *args, writes=()):
    allowed[:] = [(STACK, STACK+0x4000), *writes]
    uc.reg_write(UC_ARM_REG_SP, STACK+0x3ff0)
    uc.reg_write(UC_ARM_REG_LR, STOP)
    for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
        uc.reg_write(reg, value)
    uc.emu_start(address, STOP, count=10000)
    assert uc.reg_read(UC_ARM_REG_PC) == STOP, 'Instruction budget exhausted'
    return uc.reg_read(UC_ARM_REG_R0)

PARAM, SOURCE = DATA+0x100, DATA+0x400
uc.mem_write(SOURCE, struct.pack('<2I', 0, PARAM))
for row in profiles['rows']:
    uc.mem_write(PARAM-16, bytes([0xa5])*0x12c)
    assert run(0xc0439d18, PARAM, row['index'], 0, writes=[(PARAM, PARAM+0x10c)]) == PARAM
    expected = row['words'] + [6064, 4042]
    actual = struct.unpack('<67I', uc.mem_read(PARAM, 0x10c))
    assert list(actual) == expected, row['index']
    assert bytes(uc.mem_read(PARAM-16,16)) == bytes([0xa5])*16
    assert bytes(uc.mem_read(PARAM+0x10c,16)) == bytes([0xa5])*16
    width = run(0xc0435918, SOURCE)
    height = run(0xc0435948, SOURCE)
    assert [width,height] == row['raw_dimensions'], row['index']

# Explicit override test: values differ from base fields, unlike most stock rows.
uc.mem_write(PARAM, struct.pack('<2I',6064,4042))
uc.mem_write(PARAM+0xdc, struct.pack('<I',3032))
uc.mem_write(PARAM+0xe4, struct.pack('<I',2020))
assert run(0xc0435918,SOURCE) == 3032
assert run(0xc0435948,SOURCE) == 2020
uc.mem_write(PARAM+0xdc, bytes(4))
uc.mem_write(PARAM+0xe4, bytes(4))
assert run(0xc0435918,SOURCE) == 6064
assert run(0xc0435948,SOURCE) == 4042

formats = {str(value):run(0xc0436360,value) for value in (7,8,9,10,11,65543,65545,65546)}
result = {'emulator': 'Unicorn '+unicorn.__version__, 'stock_loader_rows': len(profiles['rows']),
          'words_per_row':67, 'stock_dimension_getter_pairs':len(profiles['rows']),
          'nonzero_and_zero_overrides_passed':True, 'format_enum_conversion':formats,
          'writes_checked':'Only destination parameter structure and local stack; firmware mapped read/execute.',
          'limitations':'Validates local ARM routines, not sensor operation, scaling filters, buffer DMA, recording, or image quality.'}
(OUT/'raw-profile-emulation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
from verify_raw_snapshot import verify
snapshot_result = verify(profiles)
(OUT/'raw-snapshot-emulation.json').write_text(json.dumps(snapshot_result,indent=2)+'\n')
print(json.dumps(snapshot_result,indent=2))
from verify_raw_capture import verify as verify_capture
capture_result = verify_capture(profiles)
(OUT/'raw-capture-emulation.json').write_text(json.dumps(capture_result,indent=2)+'\n')
print(json.dumps(capture_result,indent=2))
