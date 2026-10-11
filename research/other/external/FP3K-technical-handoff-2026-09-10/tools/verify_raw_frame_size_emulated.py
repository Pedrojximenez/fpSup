"""Run fp 5.02's stock RAW size callback offline; no camera or firmware writes."""
import hashlib
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware'
firmware = (OUT / 'MAIN_c0000000.bin').read_bytes()
digest = hashlib.sha256(firmware).hexdigest()
assert digest == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
size = (len(firmware) + 4095) & ~4095
u.mem_map(0xc0000000, size)
u.mem_write(0xc0000000, firmware)
u.mem_protect(0xc0000000, size, UC_PROT_READ | UC_PROT_EXEC)
DESC, STACK, STOP = 0x10000000, 0x10010000, 0xc0000000
u.mem_map(DESC, 4096)
u.mem_map(STACK, 0x4000)

def guard(uc, access, address, length, value, data):
    assert STACK <= address and address + length <= STACK + 0x4000, hex(address)

u.hook_add(UC_HOOK_MEM_WRITE, guard)

def run(width, height):
    descriptor = bytearray(0x48)
    struct.pack_into('<II', descriptor, 0, width, height)
    struct.pack_into('<I', descriptor, 0x20, 0)  # Stock profile429: 12-bit format enum0.
    u.mem_write(DESC, bytes(descriptor))
    u.reg_write(UC_ARM_REG_R0, DESC)
    u.reg_write(UC_ARM_REG_SP, STACK + 0x3ff0)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(0xc03d9630, STOP, count=10000)
    assert u.reg_read(UC_ARM_REG_PC) == STOP
    return u.reg_read(UC_ARM_REG_R0)

def expected(width, height):
    if not width or not height:
        return 0
    row = ((width * 3 // 2) + 3) & ~3
    final_width = ((width + 11) // 12) * 12
    final_row = ((final_width * 3 // 2) + 3) & ~3
    return (height - 1) * row + final_row

cases = []
for width, height in [(3856, 2170), (3032, 2020), (3000, 2000), (6064, 4042),
                      (0, 2020), (3032, 0), (1, 1), (11, 2), (12, 2),
                      (13, 2), (3031, 2020), (3033, 2020)]:
    result = run(width, height)
    assert result == expected(width, height), (width, height, result)
    cases.append({'width': width, 'height': height, 'firmware_bytes': result,
                  'packed_pixel_bytes_floor': width * height * 3 // 2,
                  'difference_from_packed_pixels': result - width * height * 3 // 2})

metadata = json.loads((ROOT / 'analysis/v003-uhd24-retry-frame-metadata.json').read_text())
matched = []
for frame in metadata:
    tags = frame['ifds'][0]['tags']
    assert tags['BitsPerSample'] == [12] and tags['Compression'] == [1]
    predicted = run(tags['ImageWidth'][0], tags['ImageLength'][0])
    assert tags['StripByteCounts'] == [predicted]
    # C03A5418..C03A5424 rounds RAW bytes to a 512-byte boundary.
    assert tags['StripOffsets'][0] + ((predicted + 511) & ~511) == frame['size']
    matched.append(frame['file'])
assert len(matched) == 10

report = {
    'firmware_sha256': digest,
    'entry': '0xc03d9630',
    'executed_chain': ['0xc03d9630', '0xc03d9668', '0xc01aaa30 Thumb',
                       '0xc0135d40 Thumb', '0xc0135db8 Thumb'],
    'format': 0,
    'cases': cases,
    'matching_stock_dng_frames': matched,
    'candidate_3032x2020': {
        'raw_bytes': run(3032, 2020),
        'raw_bytes_rounded_to_512': (run(3032, 2020) + 511) & ~511,
        'file_bytes_if_stock_78848_byte_header_is_retained': 78848 + ((run(3032, 2020) + 511) & ~511),
        'header_size_is_assumed_for_candidate': True,
    },
    'validation': 'Unmodified firmware executed without stubs; only stack writes permitted; bounded execution.',
    'limitations': 'Validates byte-count calculation only. Does not prove live DMA allocation, recording route, DNG metadata propagation, sensor timing, or all-pixel reduction.',
}
(OUT / 'raw-frame-size-emulation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'cases': cases, 'matching_stock_frames': len(matched)}, indent=2))
