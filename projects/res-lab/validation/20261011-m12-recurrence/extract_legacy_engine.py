"""Run only the frozen 2026-09-26 HSW canvas hook offline.

The ctrl240 card is a preserved legacy reference, not proven to be the exact
card used for A001_160. No historical loader or fixed address runs on hardware.
"""
import hashlib
import json
import pathlib
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CARD = ROOT / 'projects/open-gate/cards/hsw-win-20260926/ctrl240/fpSup.BIN'
EXPECTED = '387aa6cb70d5ec5aefa29656ff08c1759ec7f3dcc77a2196c044b2a7b5422a20'


def main():
    blob = CARD.read_bytes()
    assert hashlib.sha256(blob).hexdigest() == EXPECTED
    n = struct.unpack_from('<I', blob, 4)[0]
    at, sections = 16 + 8*n, {}
    for i in range(n):
        address, size = struct.unpack_from('<II', blob, 16+8*i)
        sections[address] = blob[at:at+size]
        at += (size+3)&~3
    profiles = json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
    donor = next(row['words'] for row in profiles['rows'] if 13 in row['profile_ids'])
    table = sections[0xc0731000]
    entries = [struct.unpack_from('<12I', table, i) for i in range(0, len(table), 48)
               if table[i+20:i+36].split(b'\0')[0] == b'HSW120']
    assert len(entries) == 1
    entry = entries[0]
    assert entry[1:3] == (13, 12)
    hmax, tail, vmax, x = entry[9]&0xffff, entry[9]>>16, entry[10]&0xffff, entry[10]>>16
    assert (hmax, tail, vmax, x) == (330, 330, 910, 6)
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0xc0730000, 0x10000)
    uc.mem_map(0x10000000, 0x10000)
    for address, data in sections.items():
        if 0xc0730000 <= address < 0xc0740000:
            assert address+len(data) <= 0xc0740000
            uc.mem_write(address, data)
    holder, canvas, stop = 0x10004000, 0x1000405c, 0x1000f000
    uc.mem_write(canvas, struct.pack('<65I', *donor))
    uc.mem_write(0xc0731c08, struct.pack('<I', 1))
    uc.mem_write(0xc0731c14, struct.pack('<I', 3))  # historical clean take: 10-bit
    def step(uc, address, size, data):
        assert 0xc0732400 <= address < 0xc0732400+len(sections[0xc0732400]), hex(address)
    uc.hook_add(UC_HOOK_CODE, step)
    for reg, value in ((UC_ARM_REG_R4, holder), (UC_ARM_REG_R5, 13),
                       (UC_ARM_REG_SP, 0x1000fff8), (UC_ARM_REG_LR, stop)):
        uc.reg_write(reg, value)
    uc.emu_start(0xc0732400, stop, count=20000)
    assert uc.reg_read(UC_ARM_REG_PC) == stop
    words = struct.unpack('<65I', uc.mem_read(canvas, 260))
    engine = struct.unpack('<f', struct.pack('<I', words[0x30//4]))[0]
    assert engine == 60.0
    result = {'card': str(CARD), 'sha256': EXPECTED, 'exact_A001_160_card': False,
              'sensor_timing': {'hmax': hmax, 'tail': tail, 'vmax': vmax, 'x': x,
                                'fps': 72000000/(hmax*vmax)},
              'profile': 13, 'engine_fps': engine,
              'raw': list(words[:2]), 'crop': [words[0x24//4], words[0x2c//4]],
              'canvas': {hex(i*4): v for i, v in enumerate(words)}}
    dest = HERE/'legacy-ctrl240.json'
    assert not dest.exists()
    dest.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'canvas'}, indent=2))


if __name__ == '__main__':
    main()
