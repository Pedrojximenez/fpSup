"""Offline replay of preserved Sensor Lab r10 picker/canvas, not a card install.

Runs the archived ARM instructions with the original firmware metadata tables.
No current assembler or calculator is used to recreate the old recipe. The
imager descriptor is a declared fixture; DMA, scheduler, USB and storage are
not emulated. This card is documented as recording successfully, but is not
proven to be the exact card for the user's A001_193 sequence.
"""
import hashlib
import json
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CARD = ROOT/'projects/res-lab/cards/20261001-240-r10-ramonly-no14bit/fast-debug'
DIGEST = '918c9b515ea45c0403e1b22e19497cdcfb948ecf72e019f56c5f11089af57f34'
ROM_DIGEST = '92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4'
PICKER, RECIPE, CANVAS = 0xc0730740, 0xc0730c20, 0xc0732400
STACK, KEY, CONFIG, HOLDER, DONE = (0x1000f000, 0x10001000, 0x10001100,
                                   0x10002000, 0x1000ff00)


def sections(blob):
    assert blob[:4] == b'VBIN'
    count = struct.unpack_from('<I', blob, 4)[0]
    at = 16 + 8*count
    result = {}
    for i in range(count):
        address, size = struct.unpack_from('<II', blob, 16+8*i)
        data = blob[at:at+size]
        assert len(data) == size and (address == 0 or address not in result)
        if address:  # multiple run-in-place launchers have destination zero
            result[address] = data
        at += (size+3)&~3
    assert at <= len(blob)
    return result


def replay(key, flag):
    blob = (CARD/'fpSup.BIN').read_bytes()
    assert hashlib.sha256(blob).hexdigest() == DIGEST
    rom = (ROOT/'out/MAIN_c0000000.bin').read_bytes()
    assert hashlib.sha256(rom).hexdigest() == ROM_DIGEST
    sec = sections(blob)
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    regions = ((0xc0700000, 0x100000), (0xc0b00000, 0x200000),
               (0xc2f00000, 0x100000), (0xc3400000, 0x100000),
               (0x10000000, 0x10000))
    for address, size in regions:
        mu.mem_map(address, size)
    mu.mem_write(0xc0b00000, rom[0xb00000:0xd00000])
    for address, data in sec.items():
        if any(lo <= address and address+len(data) <= lo+size
               for lo, size in regions):
            mu.mem_write(address, data)
    mu.mem_write(0xc2f1e654, struct.pack('<4I', 0xc0b59500, 70, 0xc0b59dc0, 70))
    mu.mem_write(0xc343b588, struct.pack('<I', 0xc2f1e654))
    mu.mem_write(0xc0731c48, struct.pack('<I', flag))
    mu.mem_write(KEY, key.encode().ljust(32, b'\0'))
    mu.mem_write(CONFIG+0x20, bytes(4))  # native eRawBitType 0 = 12 bit
    allowed = ((PICKER, PICKER+len(sec[PICKER])),
               (RECIPE, RECIPE+len(sec[RECIPE])),
               (CANVAS, CANVAS+len(sec[CANVAS])))
    def step(uc, address, size, data):
        assert any(lo <= address < hi for lo, hi in allowed), hex(address)
    mu.hook_add(UC_HOOK_CODE, step)
    for reg, value in ((UC_ARM_REG_R0, 0xaaaa0000), (UC_ARM_REG_R1, 0xc0be5b50),
                       (UC_ARM_REG_R2, KEY), (UC_ARM_REG_R6, CONFIG),
                       (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, DONE)):
        mu.reg_write(reg, value)
    mu.emu_start(PICKER, DONE, count=2000000)
    assert mu.reg_read(UC_ARM_REG_PC) == DONE and mu.reg_read(UC_ARM_REG_SP) == STACK
    entry = mu.reg_read(UC_ARM_REG_R0)
    assert entry == 0xc0732530
    w = lambda a: struct.unpack('<I', mu.mem_read(a, 4))[0]
    pid = w(entry+4)
    profiles = json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
    donor = next(row['words'] for row in profiles['rows'] if pid in row['profile_ids'])
    mu.mem_write(HOLDER+0x5c, struct.pack('<65I', *donor))
    for reg, value in ((UC_ARM_REG_R4, HOLDER), (UC_ARM_REG_R5, pid),
                       (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, DONE)):
        mu.reg_write(reg, value)
    mu.emu_start(CANVAS, DONE, count=20000)
    assert mu.reg_read(UC_ARM_REG_PC) == DONE and mu.reg_read(UC_ARM_REG_SP) == STACK
    row = list(struct.unpack('<65I', mu.mem_read(HOLDER+0x5c, 260)))
    recipe = list(struct.unpack('<27I', mu.mem_read(0xc07324c0, 108)))
    n = w(0xc0732560)
    assert 0 < n <= 32
    pairs = struct.unpack('<%dI' % (n*2), mu.mem_read(0xc0732564, n*8))
    tw0, tw1 = w(w(entry+0x10)+4), w(w(entry+0x10)+8)
    return {'key':key, 'rate240':flag, 'entry_profile':pid, 'entry_mode':w(entry+8),
            'axis':list(struct.unpack('<9I', mu.mem_read(0xc0732490, 36))),
            'recipe':recipe, 'canvas_pairs':{hex(pairs[i]):pairs[i+1] for i in range(0,2*n,2)},
            'canvas':{hex(i*4):v for i,v in enumerate(row)},
            'raw':row[:2], 'crop':[row[0x24//4],row[0x2c//4]],
            'engine_fps':struct.unpack('<f',struct.pack('<I',row[0x30//4]))[0],
            'sensor_timing':{'hmax':tw0&0xffff,'tail':tw0>>16,'vmax':tw1&0xffff,
                             'x':tw1>>16,'fps':72000000/((tw0&0xffff)*(tw1&0xffff))}}


def main():
    result = {'card':str(CARD), 'bin_sha256':DIGEST, 'rom_sha256':ROM_DIGEST,
              'exact_A001_193_card':False,
              'limitations':'Offline archived picker/canvas execution; no boot, DMA, scheduling, media, or exposure proof.',
              'cases':[replay('CUST120',1),replay('CUST120',0),replay('CUST30',0)]}
    a,b,c = result['cases']
    assert a['raw'] == b['raw'] == c['raw'] == [1008,672]
    assert a['crop'] == b['crop'] == c['crop'] == [992,662]
    assert a['entry_mode'] == 12 and a['sensor_timing']['vmax'] == 910
    assert b['entry_mode'] == c['entry_mode'] == 140
    assert b['sensor_timing']['vmax'] == 1349
    dest=HERE/'sensorlab-r10-exact-reference.json'
    assert not dest.exists()
    dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('key','rate240','entry_profile','raw','crop','engine_fps','sensor_timing')} for r in result['cases']],indent=2),flush=True)


if __name__ == '__main__':main()
