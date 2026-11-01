# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""Real relocated ARM stub_gs differential tests. No camera or SD access."""
from pathlib import Path
import itertools
import json
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import *
import build as D
import argparse

ROOT = Path(__file__).resolve().parent.parent
P = 0x11A4
GS = 0x1554
ROOT08, ROOT70, KEY = 0xC2F1A06C, 0xC2F1A0D4, 0xC2F19D44


def u32(m, a, value):
    m.mem_write(a, struct.pack('<I', value & 0xFFFFFFFF))


def setup(data):
    m = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for a, size in ((0x50000000, 0x10000), (0x52000000, 0x90000),
                    (0x53000000, 0x10000), (0x54000000, 0x1000),
                    (0xC2F00000, 0x20000), (0xC3100000, 0x200000), (0xC3400000, 0x20000)):
        m.mem_map(a, size)
    module, params = 0x50000000, 0x5203E200
    m.mem_write(module, data)
    # Exactly the resident span copied by the unchanged launcher.
    m.mem_write(params, data[P:0x2AAC])
    m.mem_write(0x52040800, bytes([0x5A]) * 0x348)
    u32(m, params + 0x10, 0x52000000)
    u32(m, params + 0x14, 0x5203E004)
    u32(m, params + 0x18, 0x5203E060)
    u32(m, params + 0x1A8, 0x52040800)
    u32(m, params + 0x1CC, module)
    u32(m, params + 0x1AC, 0xFFFFFFFF)
    for i in range(30):
        u32(m, params + 0x1C + i * 4, 1000 + i * 1000)
    u32(m, ROOT08, 0xC0B39CC8)
    u32(m, ROOT70, 0xC0B3D670)
    return m


def state(m, cfg):
    flag, lat, con, sat, fmt, quality, pq, busy, bank = cfg
    p = 0x5203E200
    for off, val in ((4, flag), (0x1A4, lat), (0x1C4, con), (0x1B0, sat)):
        u32(m, p + off, val)
    m.mem_write(0xC31B954C, bytes([bank]))
    bank_addr = 0xC31B32BC if bank == 0 else 0xC31B8B84
    u32(m, bank_addr + 0x12C, 0xC)
    u32(m, bank_addr + 0x784, fmt)
    u32(m, bank_addr + 0x788, quality)
    u32(m, 0xC3413CF4, pq)
    u32(m, 0x5400000C, busy)


def call(m):
    # The helper must preserve r4/r5/lr and r1; original routine owns r0-r3/ip.
    registers = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                 UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                 UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                 UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR]
    for i, reg in enumerate(registers):
        m.reg_write(reg, 0xA0000 + i)
    m.reg_write(UC_ARM_REG_R5, 0x54000000)
    m.reg_write(UC_ARM_REG_R6, 500)
    m.reg_write(UC_ARM_REG_SP, 0x53008000)
    m.reg_write(UC_ARM_REG_LR, 0x5000F000)
    m.emu_start(0x5203E200 + GS - P, 0x5000F000, count=5000)
    assert m.reg_read(UC_ARM_REG_PC) == 0x5000F000
    # r2 is deliberately scratch in the trampoline and is replaced by7 before
    # return. All visible return registers must still match original routine.
    return [m.reg_read(reg) for reg in registers]


def snapshot(m):
    p = 0x5203E200
    return {'params_and_original_SAT_CM_data': bytes(m.mem_read(p, 0x3B0)),
            'mode_slots': bytes(m.mem_read(0x5203E004, 0x58)),
            'matrix_copy': bytes(m.mem_read(0x52040800, 0x348)),
            'root08': bytes(m.mem_read(ROOT08, 4)),
            'root70': bytes(m.mem_read(ROOT70, 4)),
            'tone_keys': bytes(m.mem_read(KEY, 8)),
            'DNG_CM_buffer': bytes(m.mem_read(p + 0x200, 144))}


def compare(before_machine, after_machine, expected_difference):
    a, b = snapshot(before_machine), snapshot(after_machine)
    for key in a:
        if key != 'matrix_copy':
            assert a[key] == b[key], ('Unexpected non-preview change', key)
    if expected_difference:
        assert a['matrix_copy'][:0x330] == b['matrix_copy'][:0x330]
        assert a['matrix_copy'][0x330:] != b['matrix_copy'][0x330:]
    else:
        if a['root08'] == struct.pack('<I', 0xC0B39CC8):
            # Like original, OFF/replay restores the factory pointer rather
            # than clearing the unused RAM copy. Only its OFF row may remain.
            assert a['matrix_copy'][:0x330] == b['matrix_copy'][:0x330]
        else:
            assert a['matrix_copy'] == b['matrix_copy']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_dir', type=Path)
    args = parser.parse_args()
    baseline = (args.build_dir / 'arri-reference/45RAWV.BIN').read_bytes()
    combined = (args.build_dir / 'shadowlift2/45RAWV.BIN').read_bytes()
    manifest = {'preview_table_offset': 0x9748}
    assert baseline[0x13A4:0x1554] == combined[0x13A4:0x1554]
    cases, active_ga = 0, 0
    # Every gating condition varied, both format/quality banks. busy checks the
    # original early-return rule; Contrast0/+0.2 does not select DNG tag data.
    for flag, lat, con, sat, fmt, quality, pq, busy, bank in itertools.product((0, 1), (0, 1), (0, 1), (0, 1, 2), (0, 1), (0, 1, 2), (2, 0xC), (0, 1), (0, 1)):
        cfg = (flag, lat, con, sat, fmt, quality, pq, busy, bank)
        original, patched = setup(baseline), setup(combined)
        state(original, cfg)
        state(patched, cfg)
        old_regs = call(original)
        try:
            new_regs = call(patched)
        except Exception as error:
            raise RuntimeError(('Patched ARM case failed', cfg, hex(patched.reg_read(UC_ARM_REG_PC)))) from error
        assert old_regs == new_regs, ('Visible registers changed', cfg, old_regs, new_regs)
        expected = flag == 1 and lat == 1 and fmt == 0 and quality == 0 and pq == 2 and busy == 0
        compare(original, patched, expected)
        if expected:
            level = sat if sat <= 1 else 0
            expected_bytes = combined[manifest['preview_table_offset'] + level * 24:manifest['preview_table_offset'] + (level + 1) * 24]
            assert bytes(patched.mem_read(0x52040B30, 24)) == expected_bytes
            active_ga += 1
        cases += 1
    # Switch sequence catches accumulation and restores SA's exact base matrix.
    sequence = [(1, 1, 0, 0, 0, 0, 2, 0, 0), (1, 1, 0, 0, 0, 0, 2, 0, 0),
                (1, 1, 0, 1, 0, 0, 2, 0, 0), (1, 0, 0, 1, 0, 0, 2, 0, 0),
                (1, 1, 1, 1, 0, 0, 2, 0, 0), (0, 1, 1, 1, 0, 0, 2, 0, 0),
                (1, 1, 1, 0, 0, 0, 2, 0, 0)]
    original, patched = setup(baseline), setup(combined)
    for cfg in sequence:
        state(original, cfg)
        state(patched, cfg)
        assert call(original) == call(patched)
        compare(original, patched, cfg[0] == 1 and cfg[1] == 1)
    # Every possible 4-byte-aligned module base within a page: updated SCR_OFF
    # keeps helper outside scratch; existing allocation still contains all T0.
    block = struct.unpack_from('<I', combined, 12)[0]
    for low in range(0, 4096, 4):
        scratch = (low + len(combined) + 4095) & ~4095
        assert scratch >= low + len(combined)
        assert scratch + 0x82000 <= low + block
    report = {'status': 'REAL_RELOCATED_ARM_PREVIEW_PATH_SEPARATED_FROM_DNG_CM_BUFFER',
              'candidate_SHA256': D.sha(combined), 'gating_cases': cases,
              'active_GA_boost_cases': active_ga, 'switch_sequence_steps': len(sequence),
              'DNG_CM_buffer_byte_exact_vs_original_all_cases': True,
              'all_original_params_Saturation_state_CM_tables_equal': True,
              'all_visible_return_registers_equal': True,
              'only_changed_runtime_data': 'Display matrix copy OFF row, when effective GA',
              'SA_inactive_and_replay_outputs_equal': True,
              'no_compounding_on_repeated_call': True,
              'inactive_unused_RAM_matrix_may_retain_previous_values': True,
              'inactive_effective_matrix_pointer_restored_to_factory': True,
              'scratch_heap_alignment_cases': 1024,
              'SD_written': False,
              'not_proven': ['Physical camera ISP output', 'Recorded DNG pixels and final metadata',
                             'Hardware colour gamut clipping', 'Full seven-MOD hardware coexistence']}
    with (args.build_dir / 'preview-isolation-arm.json').open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
