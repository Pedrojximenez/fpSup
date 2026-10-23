#!/usr/bin/env python3
"""Offline fp 5.02 HDMI RAW profile/CRCT audit; MMIO is RAM, not a pixel model."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3


def audit(repo):
    segments = [(0xC0000000, repo / 'out/seg0_c0000000.bin'),
                (0xC2EF6E00, repo / 'out/seg1_c2ef6e00.bin')]
    blobs = [(base, path.read_bytes()) for base, path in segments]
    sources = [{'path': str(path.relative_to(repo)), 'sha256': hashlib.sha256(data).hexdigest()}
               for (_, path), (_, data) in zip(segments, blobs)]
    assert sources[0]['sha256'] == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'

    def read(addr, size):
        for base, data in blobs:
            if base <= addr and addr + size <= base + len(data):
                return data[addr-base:addr-base+size]
        raise ValueError(hex(addr))

    def romword(addr):
        return struct.unpack('<I', read(addr, 4))[0]

    # Column addresses are re-extracted from the maintained native constructor,
    # not copied from the historical raw-profiles.json.
    decomp = repo / 'out/decomp/full/blk_c04.c'
    import re
    text = decomp.read_text()
    body = text.split('/* ==== FUN_c0439d18 @ c0439d18 ==== */', 1)[1].split('/* ====', 1)[0]
    columns = {0: 0xC0BE3ADC}
    for offset, address in re.findall(r'param_1\[([^\]]+)\] = \*\(undefined4 \*\)\(&DAT_([0-9a-f]+) \+ param_2 \* 4\)', body):
        columns[int(offset, 0)] = int(address, 16)
    assert len(columns) == 65 and set(columns) == set(range(65))
    sources.append({'path': str(decomp.relative_to(repo)), 'sha256': hashlib.sha256(decomp.read_bytes()).hexdigest()})

    # Native W71c1 HDMI-RAW branch C043B988 selects C0BE5450..C0BE5610.
    table = 0xC0BE5450
    cases = []
    for rowaddr in range(table, table + 0x1C0, 16):
        _, profile, sensor, nameptr = struct.unpack('<4I', read(rowaddr, 16))
        name = read(nameptr, 32).split(b'\0', 1)[0].decode('ascii')
        profile_row = romword(0xC0BD05D4 + profile * 4)
        assert profile_row < 306
        params = [romword(columns[i] + profile_row * 4) for i in range(65)] + [0x17B0, 0xFCA]
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        end = (blobs[-1][0] + len(blobs[-1][1]) + 4095) & ~4095
        u.mem_map(0xC0000000, end - 0xC0000000)
        for base, blob in blobs:
            u.mem_write(base, blob)
        u.mem_protect(0xC0000000, end - 0xC0000000, UC_PROT_READ | UC_PROT_EXEC)
        base, stack, stop = 0x10000000, 0x10010000, 0xC0000000
        param, source, desc, ctx, obj, result = [base + n for n in (0x100, 0x300, 0x600, 0x800, 0x900, 0xB00)]
        u.mem_map(base, 0x4000)
        u.mem_map(stack, 0x4000)
        mmio = [(0x300F0000, 0x300F3000), (0x30100000, 0x30101000), (0x30001000, 0x30002000)]
        for lo, hi in mmio:
            u.mem_map(lo, hi-lo)

        def put(addr, words):
            u.mem_write(addr, struct.pack('<' + 'I' * len(words), *words))

        def words(addr, count):
            return list(struct.unpack('<' + 'I' * count, u.mem_read(addr, count * 4)))

        allowed, writes, executed = [], [], set()

        def guard(uc, access, addr, size, value, data):
            assert any(lo <= addr and addr + size <= hi for lo, hi in allowed), hex(addr)
            if any(lo <= addr and addr + size <= hi for lo, hi in mmio):
                writes.append({'address': f'0x{addr:08X}', 'value': f'0x{value:08X}'})

        def observe(uc, addr, size, data):
            executed.add(addr)

        u.hook_add(UC_HOOK_MEM_WRITE, guard)
        u.hook_add(UC_HOOK_CODE, observe)

        def run(addr, *args, until=stop, extra=()):
            allowed[:] = [(stack, stack + 0x4000), *extra]
            u.reg_write(UC_ARM_REG_CPSR, 0x13)
            u.reg_write(UC_ARM_REG_SP, stack + 0x3FF0)
            u.reg_write(UC_ARM_REG_LR, stop)
            for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
                u.reg_write(reg, value)
            u.emu_start(addr, until, count=100000)
            assert u.reg_read(UC_ARM_REG_PC) == until, hex(u.reg_read(UC_ARM_REG_PC))

        put(param, params)
        put(source, [profile, param])
        put(source + 0x58, [0xC0BD04B0])
        put(ctx, [0, 0])
        run(0xC0438018, desc, source, ctx, extra=[(desc, desc+0xC0)])
        descriptor = words(desc, 48)
        assert descriptor[18:22] == [params[0x64//4], params[0xD4//4], params[0x5C//4], params[0xC8//4]]
        put(obj, [0xC2F1E654])
        put(obj + 0xD0, [0xC0B5FCC0])

        def mock(uc, addr, size, data):
            if addr == 0xC0436590:
                value = base + 0x2000
            elif addr == 0xC04370E8:
                put(uc.reg_read(UC_ARM_REG_R1), [desc])
                value = 0
            elif addr == 0xC0322E48:
                value = obj
            else:
                raise AssertionError(hex(addr))
            uc.reg_write(UC_ARM_REG_R0, value)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        for addr in (0xC0436590, 0xC04370E8, 0xC0322E48):
            u.hook_add(UC_HOOK_CODE, mock, begin=addr, end=addr)
        run(0xC031D988, result, until=0xC031DCA0,
            extra=[(result, result+0x20), (stack, stack+0x4000), *mmio])
        route = list(u.mem_read(result, 3))
        regs = {f'0x{addr:08X}': f'0x{words(addr, 1)[0]:08X}'
                for addr in sorted({int(w['address'], 16) for w in writes})}
        crop = name.endswith('CROP')
        if not crop:
            expected_route = [0, 1, 0] if name.startswith('FHD') else [0, 0, 1]
            assert route == expected_route, (name, route)
            if name.startswith('FHD'):
                assert words(result, 3)[2] == 4  # CrctHbin2ToBufA
            assert regs['0x300F0900'] == '0x00000001'
            ratio = 1500 if name == 'DCI4K24' else 1600
            assert int(regs['0x300F0908'], 16) & 0xFFFF == ratio
            assert int(regs['0x300F090C'], 16) & 0xFFFF == ratio
        else:
            assert route == [1, 0, 0], (name, route)
            assert words(result, 3)[1] == 1  # CrctCrmfToBufA
            # Crop records use the CRMF tap while main RAW zoom serves preview.
            # Its enable/ratio must not be attributed to the record sink.
            assert descriptor[18:20] == [1023, 1023], (name, descriptor[18:20])
        cases.append({'name': name, 'table_address': f'0x{rowaddr:08X}', 'profile': profile,
                      'profile_row': profile_row, 'sensor_mode': sensor,
                      'record_size': descriptor[:2], 'record_zoom': descriptor[18:20],
                      'preview_zoom': descriptor[40:42], 'preview_bin_enums': descriptor[42:44],
                      'format_at_80_84': params[32:34], 'raw_source_mask_at_3c': params[15],
                      'route_enabled_a0_a7_a1': route, 'registers': regs,
                      'native_instruction_addresses': [f'0x{a:08X}' for a in sorted(executed)]})
    return {'scope': 'Offline native configuration execution only; no camera I/O and no ASIC pixel arithmetic.',
            'sources': sources, 'table': '0xC0BE5450', 'cases': cases,
            'counts': dict(Counter({(1,0,0): 'crop_crmf', (0,0,1): 'full_width_rwzm',
                                    (0,1,0): 'full_width_hbin2'}[tuple(c['route_enabled_a0_a7_a1'])] for c in cases)),
            'unverified': ['Active camera state and other configurator families',
                           'Black-level, defective-pixel, shading, WB and NR pixel effects in HDMI RAW',
                           'Exact Bayer-to-HDMI packing and interpolation kernel'],
            'mocked': ['Descriptor/manager lookup', 'Sensor singleton lookup', 'MMIO is zero-seeded RAM'],
            'executed': ['Native descriptor construction C0438018',
                         'C031D988 through C031DCA0, native selector C0325228 and CRCT register drivers']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument('--output', type=Path, default=Path(__file__).with_name('hdmi-raw-isp-audit.json'))
    args = ap.parse_args()
    report = audit(args.repo)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'cases': len(report['cases']), 'counts': report['counts'], 'output': str(args.output)}))
