#!/usr/bin/env python3
"""Offline: capture stock component property tables from original Thumb code.

Uses synthetic zeroed RAM; stops constructors BEFORE property registration.
Four constructors need renderer/context setup: instead verify their original
argument-setup instruction windows, without executing those constructors.
No camera, allocator, UI renderer or component constructor side effects on a
real system. Constructor discovery failures are reported, never guessed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import (Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_PROT_READ,
                     UC_PROT_WRITE, UC_PROT_EXEC, UC_HOOK_CODE)
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_REG_R1, ARM_REG_R2

BASE = 0xC0000000
PIN = 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
SIZE = 49245696
RAM, RAM_SIZE = 0x10000000, 0x10000
STOP, PROP_REGISTER = 0x20000000, 0xC05D5E30
KINDS = {'objectBase', 'focusEvent', 'controlAnimation', 'controlAppVariable',
         'controlAppState', 'keyEvent', 'controlFocus', 'changePropertyByControl',
         'controlTimer', 'controlValue', 'appVariableEvent', 'appVariableChangeEvent',
         'timerEvent', 'controlValueEvent', 'screenEvent', 'drawRect', 'drawImage',
         'drawText'}

# (constructor, call-window start, end, table, constructor-declared count).
# All are verified against actual argument-setting instructions below.
STATIC = {
    'controlAnimation': (0xC05F1201, 0xC05F1212, 0xC05F1226, 0xC2E0108C, 9),
    'drawImage': (0xC05FD299, 0xC05FD2E8, 0xC05FD300, 0xC2E031E0, 7),
    'drawRect': (0xC05FD779, 0xC05FD7C4, 0xC05FD7DC, 0xC2E033E0, 9),
    'drawText': (0xC05FE1A9, 0xC05FE1F2, 0xC05FE202, 0xC2E035AC, 30),
}
DRAW_COMMON = (0xC2DFFC00, 0xC2DFFBF4)


def check(ok, why):
    if not ok:
        raise ValueError(why)


def static_capture(data, name, constructor):
    expected_ctor, start, end, expected_table, expected_count = STATIC[name]
    check(constructor == expected_ctor, 'static constructor mismatch')
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    cs.detail = True
    regs, trace, cursor = {}, [], start
    for insn in cs.disasm(data[start - BASE:end - BASE], start):
        check(insn.address == cursor, 'disassembly gap')
        cursor += insn.size
        trace.append({'address': hex(insn.address), 'instruction': insn.mnemonic + ' ' + insn.op_str})
        if insn.mnemonic == 'bl':
            check(cursor == end and (insn.operands[0].imm & 0xFFFFFFFF) == PROP_REGISTER,
                  'unexpected call in argument window')
            break
        # Invalidate any other write to an argument register. Only immediate
        # MOV/MOVW/MOVT is eligible evidence for table/count, not guessed values.
        _, writes = insn.regs_access()
        for reg in (ARM_REG_R1, ARM_REG_R2):
            if reg not in writes:
                continue
            operands = insn.operands
            is_immediate = (len(operands) == 2 and operands[0].type == ARM_OP_REG
                            and operands[0].reg == reg and operands[1].type == ARM_OP_IMM)
            if is_immediate and insn.mnemonic in ('mov', 'movs', 'movw'):
                regs[reg] = operands[1].imm
            elif is_immediate and insn.mnemonic == 'movt' and reg in regs:
                regs[reg] = (regs[reg] & 0xFFFF) | (operands[1].imm << 16)
            else:
                regs.pop(reg, None)
    check(cursor == end and trace[-1]['instruction'].startswith('bl '), 'incomplete argument window')
    check(regs.get(ARM_REG_R2) == expected_table and regs.get(ARM_REG_R1) == expected_count,
          'native table/count arguments differ')
    return expected_count, expected_table, trace


class Capture:
    def __init__(self, data):
        check(len(data) == SIZE and hashlib.sha256(data).hexdigest() == PIN, 'wrong pinned seg0')
        self.data = data
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        length = (len(data) + 4095) & ~4095
        self.uc.mem_map(BASE, length)
        self.uc.mem_write(BASE, data)
        self.uc.mem_protect(BASE, length, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.mem_map(RAM, RAM_SIZE, UC_PROT_READ | UC_PROT_WRITE)
        self.uc.mem_map(STOP, 4096, UC_PROT_READ | UC_PROT_EXEC)
        self.uc.hook_add(UC_HOOK_CODE, self.instruction)
        self.capture = None
        self.executed = []
        self.capture_mode = False

    def instruction(self, uc, address, size, _):
        self.executed.append(address)
        if address == PROP_REGISTER and self.capture_mode:
            self.capture = (uc.reg_read(UC_ARM_REG_R1), uc.reg_read(UC_ARM_REG_R2))
            uc.emu_stop()
        elif not (BASE <= address < BASE + len(self.data)):
            raise ValueError('unexpected execution outside pinned firmware')

    def run(self, entry, capture=False):
        check(entry & 1 and BASE <= entry < BASE + 0x1000000, 'not a bounded Thumb entry')
        self.uc.mem_write(RAM, bytes(RAM_SIZE))
        self.uc.reg_write(UC_ARM_REG_SP, RAM + RAM_SIZE - 0x100)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.uc.reg_write(UC_ARM_REG_R0, RAM + 0x1000 if capture else 0)
        self.uc.reg_write(UC_ARM_REG_R1, 0)
        self.uc.reg_write(UC_ARM_REG_R2, 0)
        self.capture, self.executed, self.capture_mode = None, [], capture
        self.uc.emu_start(entry, STOP, timeout=100000, count=1000)
        check(self.capture is not None or self.uc.reg_read(UC_ARM_REG_PC) == STOP,
              'instruction/time limit without a completed return/capture')
        return self.uc.reg_read(UC_ARM_REG_R0)

    def string(self, address):
        check(BASE <= address < BASE + len(self.data), 'string outside firmware')
        at = address - BASE
        end = self.data.find(b'\0', at, min(at + 128, len(self.data)))
        check(end >= at, 'unbounded native name')
        return self.data[at:end].decode('ascii')

    def property(self, address, index):
        check(BASE <= address <= BASE + len(self.data) - 12, 'property outside firmware')
        typ, ptr, default = struct.unpack_from('<3I', self.data, address - BASE)
        check(typ <= 14, 'unclassified property type')
        return {'index': index, 'type': typ, 'name': self.string(ptr),
                'default_raw': default, 'descriptor_address': hex(address)}

    def scan(self):
        result, failures, seen = {}, [], set()
        for at in range(0x2D00000, len(self.data) - 44, 4):
            v = struct.unpack_from('<11I', self.data, at)
            if not all(0xC05D0000 <= (v[i] & ~1) < 0xC0630000 and v[i] & 1
                       for i in (0, 2, 3)):
                continue
            try:
                name = self.string(self.run(v[3]))
            except (ValueError, UnicodeDecodeError, UcError):
                continue
            if name not in KINDS or name in seen:
                continue
            seen.add(name)
            try:
                if name in STATIC:
                    count, table, trace = static_capture(self.data, name, v[0])
                    provenance = {'method': 'verified_static_argument_window', 'instructions': trace}
                else:
                    self.run(v[0], capture=True)
                    check(self.capture is not None, 'constructor returned without property declaration')
                    count, table = self.capture
                    provenance = {'method': 'native_constructor_prefix_capture',
                                  'instructions_before_capture': len(self.executed)}
                check(0 < count <= 128 and BASE <= table <= BASE + len(self.data) - count * 12,
                      'invalid property descriptor table')
                props = [self.property(table + i * 12, i) for i in range(count)]
                if name in ('drawImage', 'drawRect', 'drawText'):
                    props += [self.property(p, count + i) for i, p in enumerate(DRAW_COMMON)]
                    check([(p['type'], p['name']) for p in props[-2:]] == [(5, 'rect'), (10, 'layout')],
                          'drawable common descriptors mismatch')
                    provenance['common_tail'] = {
                        'method': 'pinned_native_lookup_static_trace',
                        'lookup': '0xc05d5670', 'register': '0xc05d5e30',
                        'component_type': 4, 'order': ['count-2:rect', 'count-1:layout']}
                result[name] = {'plugin_table': hex(BASE + at), 'constructor': hex(v[0]),
                                'property_table': hex(table), 'declared_count': count,
                                'count': len(props), 'properties': props, 'provenance': provenance}
            except (ValueError, UnicodeDecodeError, UcError) as exc:
                failures.append({'component': name, 'plugin_table': hex(BASE + at),
                                 'constructor': hex(v[0]), 'reason': str(exc),
                                 'last_instructions': [hex(p) for p in self.executed[-12:]]})
        return {'input_sha256': PIN, 'scope': 'native getters/14 constructor prefixes plus 4 static argument windows',
                'not_executed': ['property registration', 'allocator', 'renderer', 'UI events', 'camera',
                                 'controlAnimation/drawImage/drawRect/drawText constructors'],
                'custom_record_decoders': ['animationClip: separate 0x1000a serialized structure'],
                'components': result, 'failures': failures, 'missing': sorted(KINDS - set(result))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seg0', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = args.seg0.read_bytes()
    report = Capture(data).scan()
    out = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        with args.output.open('x') as target:
            target.write(out)
    print(out)
    return 0 if not report['missing'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
