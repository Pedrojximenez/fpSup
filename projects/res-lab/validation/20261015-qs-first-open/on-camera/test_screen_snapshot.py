"""Synthetic-memory ABI and bounds checks for the observation-only leaf."""
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
from armasm import assemble
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import *

CODE, P, DONE, STACK = 0x45000000, 0x45001000, 0x45002000, 0x45004000
blob = assemble(HERE / 'screen_snapshot.S', [f'P={P}'])
assert len(blob) <= 320
results = []
for label, app, screen, name, valid in (
    ('valid_c_region', 0xC3E00000, 0xC3E01000, 0xC3E02003, True),
    ('valid_heap', 0x45005000, 0x45006000, 0x45007003, True),
    ('valid_native_gui_heap', 0xC6800018, 0xC6801000, 0xC6802003, True),
    ('null_app', 0, 0, 0, False),
    ('unaligned_app', 0xC3E00001, 0, 0, False),
    ('unknown_app_region', 0x60000000, 0, 0, False),
    ('null_screen', 0xC3E00000, 0, 0, False),
    ('unknown_name_region', 0xC3E00000, 0xC3E01000, 0x30000000, False),
):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0xC37B7000, 0x1000)
    mu.mem_map(0xC3E00000, 0x10000)
    mu.mem_map(0xC6800000, 0x10000)
    mu.mem_map(0x45000000, 0x10000)
    mu.mem_write(CODE, blob)
    mu.mem_write(0xC37B7048, struct.pack('<I', app))
    if app in (0xC3E00000, 0x45005000, 0xC6800018):
        mu.mem_write(app + 0x84c, struct.pack('<I', screen))
    if screen in (0xC3E01000, 0x45006000, 0xC6801000):
        mu.mem_write(screen + 8, struct.pack('<I', name))
    if valid:
        mu.mem_write(name, b'QS_CINE\0' + bytes([0xAB]) * 24)
    regs = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
            UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
    for i, reg in enumerate(regs):
        mu.reg_write(reg, 0x12340000 + i)
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(CODE, DONE, count=1000)
    assert mu.reg_read(UC_ARM_REG_PC) == DONE
    assert mu.reg_read(UC_ARM_REG_SP) == STACK
    assert [mu.reg_read(r) for r in regs] == [0x12340000 + i for i in range(8)]
    assert mu.reg_read(UC_ARM_REG_R0) == 0
    result = bytes(mu.mem_read(P + 0x40, 48))
    assert struct.unpack_from('<I', result, 12)[0] == int(valid)
    if valid:
        assert struct.unpack_from('<3I', result) == (app, screen, name)
        assert result[16:] == b'QS_CINE\0' + bytes([0xAB]) * 24
    results.append({'case': label, 'passed': True})
(HERE / 'screen-snapshot-verification.json').write_text(
    json.dumps({'bytes': len(blob), 'cases': results, 'LCD_scanout_verified': False}, indent=2) + '\n')
print(json.dumps({'bytes': len(blob), 'passed': len(results)}))
