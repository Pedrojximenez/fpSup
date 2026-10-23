#!/usr/bin/env python3
"""Offline native fp 5.02 tests of the HDMI RAW / res-custom interface boundary.

No product patch is built or installed. The RAM-entry classifier is a test
double demonstrating the required adapter contract, not a deployment hook.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn import UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import (UC_ARM_REG_CPSR, UC_ARM_REG_FPEXC, UC_ARM_REG_SP,
                              UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                              UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)


SEGMENTS = (
    (0xC0000000, 'out/seg0_c0000000.bin',
     'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'),
    (0xC2EF6E00, 'out/seg1_c2ef6e00.bin',
     '0dcaca8f5441fe4ddc6ed801cb888e325df4e76006e4f53a1c3219809b22ce7b'))
TABLE = 0xC0BE5450
STOP = 0xC0000000
BASE, STACK = 0x10000000, 0x10010000


def audit(repo):
    sources, blobs = [], []
    for base, name, expected in SEGMENTS:
        data = (repo / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert digest == expected, name
        sources.append({'path': name, 'sha256': digest})
        blobs.append((base, data))
    for name in ('out/decomp/full/blk_c04.c',
                 'projects/open-gate/build/res-custom/ogc.c',
                 'projects/open-gate/build/res-custom/virtual_rcd.h',
                 'projects/open-gate/build/res-custom/ogc_virtual.c'):
        data = (repo / name).read_bytes()
        sources.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest()})

    def rom(addr, size):
        for base, data in blobs:
            if base <= addr and addr + size <= base + len(data):
                return data[addr-base:addr-base+size]
        raise AssertionError(hex(addr))

    def romword(addr):
        return struct.unpack('<I', rom(addr, 4))[0]

    text = (repo / 'out/decomp/full/blk_c04.c').read_text()
    body = text.split('/* ==== FUN_c0439d18 @ c0439d18 ==== */', 1)[1].split('/* ====', 1)[0]
    columns = {0: 0xC0BE3ADC}
    for offset, address in re.findall(r'param_1\[([^\]]+)\] = \*\(undefined4 \*\)\(&DAT_([0-9a-f]+) \+ param_2 \* 4\)', body):
        columns[int(offset, 0)] = int(address, 16)
    assert set(columns) == set(range(65))
    # Mutation below models exactly these two current product assignments.
    ogc = (repo / 'projects/open-gate/build/res-custom/ogc.c').read_text()
    assert 'W(canvas + 0x80) = bd == BD12 ? 7u : 10u;' in ogc
    assert 'W(canvas + 0x84) = bd == BD8 ? 10u : bd == BD10 ? 9u : 7u;' in ogc

    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    end = (blobs[-1][0] + len(blobs[-1][1]) + 4095) & ~4095
    u.mem_map(0xC0000000, end - 0xC0000000)
    for base, data in blobs:
        u.mem_write(base, data)
    u.mem_protect(0xC0000000, end - 0xC0000000, UC_PROT_READ | UC_PROT_EXEC)
    u.mem_map(BASE, 0x10000)
    u.mem_map(STACK, 0x10000)

    def put(addr, *words):
        u.mem_write(addr, struct.pack('<' + 'I' * len(words), *words))

    def word(addr):
        return struct.unpack('<I', u.mem_read(addr, 4))[0]

    def ret(value):
        u.reg_write(UC_ARM_REG_R0, value)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    cfg, state, vtable, virtual, chosen_stub = [BASE + n for n in (0x100, 0x1000, 0x2000, 0x2100, 0x3000)]
    source, canvas, sigcfg, settings = [BASE + n for n in (0x4000, 0x4200, 0x4400, 0x4800)]
    disp, placeholder, lv_mode = BASE + 0x5000, BASE + 0x5100, BASE + 0x6000
    mode, selected_entry, classify_owned = '', 0, False
    executed, calls, native_classifier_calls = set(), [], 0

    def observe(uc, addr, size, data):
        nonlocal native_classifier_calls
        executed.add(addr)
        if addr == chosen_stub:
            calls.append('selected-entry provider')
            ret(selected_entry)
        elif addr in (0xC0019DC0, 0xC001A0D8):
            calls.append(f'logger 0x{addr:08X}')
            ret(0)
        elif addr == 0xC043D158:
            native_classifier_calls += 1
            if classify_owned and uc.reg_read(UC_ARM_REG_R1) == virtual and uc.reg_read(UC_ARM_REG_R2) == TABLE:
                calls.append('test adapter recognizes owned HDMI entry')
                ret(1)
        elif addr in (0xC00178D8, 0xC0017AC8, 0xC032C900):
            calls.append(f'settings/sensor lookup 0x{addr:08X}')
            ret(settings if addr == 0xC0017AC8 else 0)

    def guard(uc, access, addr, size, value, data):
        assert ((STACK <= addr and addr + size <= STACK + 0x10000) or
                (mode == 'sigcfg' and sigcfg <= addr and addr + size <= sigcfg + 0x1D0)), hex(addr)

    u.hook_add(UC_HOOK_CODE, observe)
    u.hook_add(UC_HOOK_MEM_WRITE, guard)

    def run(addr, *args, kind='query'):
        nonlocal mode
        mode = kind
        executed.clear()
        calls.clear()
        u.reg_write(UC_ARM_REG_CPSR, 0x13)
        u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        u.reg_write(UC_ARM_REG_SP, STACK + 0xFFF0)
        u.reg_write(UC_ARM_REG_LR, STOP)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            u.reg_write(reg, value)
        u.emu_start(addr, STOP, count=100000)
        assert u.reg_read(UC_ARM_REG_PC) == STOP, hex(u.reg_read(UC_ARM_REG_PC))
        return u.reg_read(UC_ARM_REG_R0)

    put(cfg + 8, vtable)
    put(vtable + 0x14, chosen_stub)
    put(disp + 0x24, placeholder)
    put(placeholder + 0x1C, 5)
    put(source + 4, canvas)
    put(settings + 0x1E0, 0)
    cases = []
    for entry in range(TABLE, TABLE + 0x1C0, 16):
        raw = rom(entry, 16)
        _, profile, sensor, nameptr = struct.unpack('<4I', raw)
        name = rom(nameptr, 32).split(b'\0', 1)[0].decode('ascii')
        row = romword(0xC0BD05D4 + 4 * profile)
        params = [romword(columns[i] + 4 * row) for i in range(65)] + [0x17B0, 0xFCA]
        expected = 0x560 if name.startswith('DCI4K') else 0x538
        u.mem_write(virtual, raw)
        found = run(0xC043CE18, cfg, TABLE, nameptr)
        assert found == entry and 0xC043CCF8 not in executed
        selected_entry, classify_owned = entry, False
        stock = run(0xC043C090, cfg, state) - cfg
        assert stock == expected, (name, hex(stock))
        stock_pcs = sorted(executed)
        selected_entry = virtual
        cloned = run(0xC043C090, cfg, state) - cfg
        assert cloned == 0x268, (name, hex(cloned))
        assert any(c.startswith('logger') for c in calls)
        classify_owned = True
        adapted = run(0xC043C090, cfg, state) - cfg
        assert adapted == expected, (name, hex(adapted))
        assert 'test adapter recognizes owned HDMI entry' in calls

        # Native HDMI-specific dispatch bypasses the base v5/v6 for RAW.
        dispatch = []
        for function, arg in ((0xC04380E0, 3), (0xC0438150, 2)):
            ptr = run(function, disp, arg)
            assert ptr == placeholder and word(ptr + 0x1C) == 5
            assert 0xC0437E98 not in executed
            dispatch.append({'function': f'0x{function:08X}', 'argument': arg,
                             'descriptor_type': word(ptr + 0x1C),
                             'base_v5_hook_visited': 0xC0437E98 in executed})

        # Execute native canvas -> Sig configuration on stock and the three
        # modelled CDNG overwrites. No res-custom ARM payload is run here.
        formats = []
        for depth in (None, 8, 10, 12):
            put(canvas, *params)
            if depth is not None:
                put(canvas + 0x80, 7 if depth == 12 else 10)
                put(canvas + 0x84, {8: 10, 10: 9, 12: 7}[depth])
            u.mem_write(sigcfg, bytes(0x1D0))
            run(0xC0434EF8, source, sigcfg, kind='sigcfg')
            result = [word(sigcfg + 8), word(sigcfg + 0x104)]
            assert result == [word(canvas + 0x80), word(canvas + 0x84)]
            assert result == ([7, 11] if depth is None else [7 if depth == 12 else 10, {8: 10, 10: 9, 12: 7}[depth]])
            formats.append({'modelled_cdng_bitdepth': depth, 'sigcfg_at_08_104': result,
                            'preserves_hdmi_format_11': result[1] == 11})
        classes = []
        for pid in (profile, 85):
            # The native constructor embeds the canvas at +5C. Thus its
            # +E0 test is precisely canvas+84, not a separate HDMI flag.
            put(lv_mode, pid)
            put(lv_mode + 0x5C, *params)
            put(lv_mode + 0x58, 0xC0BD05B8)
            flags = run(0xC043A1C8, lv_mode)
            assert flags == 0x100, (name, pid, hex(flags))
            put(lv_mode + 0x168, flags)
            raw_movie = run(0xC0436080, lv_mode)
            assert raw_movie == 0
            classes.append({'pid': pid, 'native_class_flags': f'0x{flags:X}',
                            'native_raw_movie_bit': raw_movie})
        cases.append({'name': name, 'profile': profile, 'sensor': sensor,
                      'entry_first_word': struct.unpack('<I', raw[:4])[0],
                      'native_hdmi_lookup_found_stock_entry': found == entry,
                      'cdng_picker_hook_visited_by_hdmi_lookup': False,
                      'stock_entry': f'0x{entry:08X}', 'display_offsets': {
                          'stock': f'0x{stock:X}', 'ram_clone_without_adapter': f'0x{cloned:X}',
                          'ram_clone_with_test_classifier': f'0x{adapted:X}'},
                      'raw_dispatch': dispatch, 'format_mutations': formats,
                      'native_profile_classes': classes,
                      'stock_selector_native_pcs': [f'0x{pc:08X}' for pc in stock_pcs]})
    assert native_classifier_calls == 84
    return {'scope': 'Offline interface research only; no camera I/O, product patch or pixel/HDMI transport simulation.',
            'sources': sources, 'counts': {'profiles': len(cases),
                'native_hdmi_lookup_runs': len(cases),
                'native_display_selection_runs': len(cases) * 3,
                'native_raw_dispatch_runs': len(cases) * 2,
                'native_canvas_to_sigcfg_runs': len(cases) * 4,
                'native_classification_and_raw_movie_query_runs': len(cases) * 4},
            'cases': cases,
            'test_doubles': ['Configurator v3 returns a selected stock entry or exact RAM clone',
                'Diagnostic logger', 'Settings/sensor lookup in C0434EF8',
                'Owned-entry classification experiment at C043D158 for the RAM clone and HDMI table only'],
            'modelled_not_executed': ['The two current ogc_canvas bit-depth assignments, source-text asserted'],
            'unverified': ['A production HDMI picker/display adapter and its relocation/chain ownership',
                'ASIC pixels, Bayer packing, actual frame geometry, metadata and receiver acceptance',
                'Other configurator families, live transitions, HPD/EDID fallback and external recording activity']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('hdmi-rescustom-interface-audit.json'))
    args = parser.parse_args()
    report = audit(args.repo)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'counts': report['counts'], 'output': str(args.output)}))
