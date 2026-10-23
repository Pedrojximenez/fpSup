"""Execute stock FUN_c06a5290's RAW/tile branches offline, against pinned ROM.

The TIFF tag setter is intercepted to record arguments; its graph allocation
and serialization are NOT emulated. Native descriptor/tile-state accessors
execute their actual instructions. No hook is installed, no USB imported.
"""
from pathlib import Path
import hashlib
import json
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC
from unicorn.arm_const import *

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
IMAGE = ROOT / 'out/seg0_c0000000.bin'
EXPECTED = 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
FUNC, END = 0xC06A5290, 0xC06A5630
RAM, FORMAT, TABLE, CONTAINER = 0x45000000, 0x45001000, 0x45002000, 0x45003000
STACK, STOP = 0x46010000, 0x47000000
SIZE, BITS, SET, SET_SUB = 0xC02DA770, 0xC02DA870, 0xC00BA378, 0xC00BA310
ACCESSORS = {0xC06A5C88, 0xC06A5C8C, 0xC06A5C90, 0xC06A5C94,
             0xC06A5CB8, 0xC06A5CBC, 0xC06A5CC0, 0xC06A5CC4}
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


def trace(compressed):
    rom = IMAGE.read_bytes()
    assert hashlib.sha256(rom).hexdigest() == EXPECTED
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0xC0000000, (len(rom) + 4095) & ~4095, UC_PROT_READ | UC_PROT_WRITE)
    mu.mem_write(0xC0000000, rom)
    mu.mem_protect(0xC0000000, (len(rom) + 4095) & ~4095, UC_PROT_READ | UC_PROT_EXEC)
    mu.mem_map(RAM, 0x10000, UC_PROT_READ | UC_PROT_WRITE)
    mu.mem_map(STACK - 0x10000, 0x10000, UC_PROT_READ | UC_PROT_WRITE)
    mu.mem_map(STOP, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
    def put(at, value):
        mu.mem_write(at, struct.pack('<I', value))
    put(FORMAT + 0x14, TABLE)
    put(TABLE + 0x48, 0xC06A5C88)
    put(TABLE + 0x58, 0xC06A5CB8)
    put(FORMAT + 0x88, 1)  # main RAW image, not thumbnail-root branch
    put(FORMAT + 0x18, 1936)
    put(FORMAT + 0x1C, 1090)
    put(FORMAT + 0x18 + 9 * 4, 0)  # 12-bit descriptor enum
    put(FORMAT + 0x6C, int(compressed))
    put(FORMAT + 0x80, 40)  # ceil(1936/256) * ceil(1090/256)
    records, stats = [], {'instructions': 0, 'call_stack_mod8': []}
    def read32(at):
        return struct.unpack('<I', mu.mem_read(at, 4))[0]
    def instruction(_mu, pc, size, _data):
        stats['instructions'] += 1
        if FUNC <= pc < END or pc in ACCESSORS:
            return
        if pc == STOP:
            mu.emu_stop()
            return
        assert pc in (SIZE, BITS, SET, SET_SUB), f'unknown ROM call {pc:#x}'
        stats['call_stack_mod8'].append(mu.reg_read(UC_ARM_REG_SP) & 7)
        if pc in (SET, SET_SUB):
            args = [mu.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1,
                                            UC_ARM_REG_R2, UC_ARM_REG_R3)]
            sp = mu.reg_read(UC_ARM_REG_SP)
            args += [read32(sp), read32(sp + 4)]
            if pc == SET_SUB:
                args.append(read32(sp + 8))
                obj, group, sub, tag, kind, count, value = args
            else:
                obj, group, tag, kind, count, value = args
                sub = 0
            assert obj == CONTAINER
            nbytes = {3: 2, 4: 4}[kind] * count
            # A NULL value means reserve a setter slot, not populated data.
            raw = bytes(mu.mem_read(value, nbytes)).hex() if value else None
            records.append(dict(group=group, sub=sub, tag=tag, type=kind,
                                count=count, raw=raw))
            result = 1
        else:
            assert mu.reg_read(UC_ARM_REG_R0) == (0 if pc == BITS else FORMAT + 0x18)
            result = 12 if pc == BITS else 3165372
        mu.reg_write(UC_ARM_REG_R0, result)
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))
    mu.hook_add(UC_HOOK_CODE, instruction)
    seeds = [0xABCD0000 + n for n in range(len(SAVED))]
    for r, value in zip(SAVED, seeds):
        mu.reg_write(r, value)
    sp = STACK - 0x104  # preserve native incoming ABI; no custom shim here
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_R0, FORMAT)
    mu.reg_write(UC_ARM_REG_R1, CONTAINER)
    mu.reg_write(UC_ARM_REG_LR, STOP)
    mu.emu_start(FUNC, STOP, count=10000)
    assert mu.reg_read(UC_ARM_REG_PC) == STOP
    assert mu.reg_read(UC_ARM_REG_SP) == sp
    assert [mu.reg_read(r) for r in SAVED] == seeds
    return dict(compressed=bool(compressed), tags=records, **stats)


def verify(result):
    tags = {r['tag']: r for r in result['tags']}
    scalar = lambda tag: int.from_bytes(bytes.fromhex(tags[tag]['raw']), 'little')
    assert scalar(256) == 1936 and scalar(257) == 1090 and scalar(258) == 12
    assert scalar(259) == (7 if result['compressed'] else 1)
    if result['compressed']:
        assert not ({273, 278, 279} & tags.keys())
        assert {322, 323, 324, 325} <= tags.keys()
        assert scalar(322) == 256 and scalar(323) == 256
        assert tags[324]['count'] == tags[325]['count'] == 40
        assert tags[324]['raw'] is None and tags[325]['raw'] is None
    else:
        assert {273, 278, 279} <= tags.keys()
        assert not ({322, 323, 324, 325} & tags.keys())
        assert scalar(278) == 1090 and scalar(279) == 3165372
    return True


if __name__ == '__main__':
    runs = [trace(False), trace(True)]
    for result in runs:
        verify(result)
    output = dict(image_sha256=EXPECTED, function=hex(FUNC), runs=runs,
                  limitation='setter argument trace only; no TIFF serializer, adapter hook or camera timing')
    (HERE / 'native-builder-results.json').write_text(json.dumps(output, indent=2) + '\n')
    print('Verified actual native RAW and compressed tile tag branches; no live camera calls.')
