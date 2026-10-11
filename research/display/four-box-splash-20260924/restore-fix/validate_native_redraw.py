#!/usr/bin/env python3
"""Offline native-code regression for splash restoration; no device access.

Execute the firmware's scheduling, context extraction and UicDrawHandler mode
selection in Unicorn. Only OS events, logging, locks and the downstream GUI
renderer are stubbed. This validates the missing full-redraw signal, not LCD
timing, triple-buffer presentation or hardware cache behavior.
"""
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as reg

ROOT = Path(__file__).resolve().parents[3]
FIRMWARE = ROOT / 'out' / 'MAIN_c0000000.bin'
BASE = 0xC0000000
MANAGER, THREAD, CONTROLLER = 0xC3000000, 0xC3001000, 0xC3002000
HANDLER, CONTEXT, REQUEST = 0xC3003000, 0xC3004000, 0xC3005000
STACK, STOP = 0x10000000, 0x10100000
NATIVE_RANGES = (
    (0xC0527DD8, 0xC0527E08),  # clear group + pending
    (0xC0527E40, 0xC0527F10),  # conditional wake and full request
    (0xC05284A0, 0xC05285C0),  # clear mode / event bits / pending query
    (0xC05291A8, 0xC05291D0),  # wake DrawThread
    (0xC0529538, 0xC05295A8),  # event flags -> draw context
    (0xC0529610, 0xC0529698),  # request -> event flags
    (0xC06D1948, 0xC06D19F0),  # UicDrawHandler mode selection
)


def scenario(blob, full_redraw):
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(BASE, 0x04000000)
    uc.mem_write(BASE, blob)
    uc.mem_map(STACK, 0x10000)
    uc.mem_map(STOP, 0x1000)
    events = {}
    draw_modes = []
    event_updates = []

    def put32(address, value):
        uc.mem_write(address, struct.pack('<I', value))

    def event_set(args):
        events[args[0]] = events.get(args[0], 0) | args[1]
        event_updates.append([hex(args[0]), 'set', hex(args[1])])
        return 0

    def event_mask(args):
        events[args[0]] = events.get(args[0], 0) & args[1]
        event_updates.append([hex(args[0]), 'mask', hex(args[1])])
        return 0

    def event_query(args):
        uc.mem_write(args[1], struct.pack('<III', 0, 0, events.get(args[0], 0)))
        return 1

    def gui_draw(args):
        draw_modes.append(args[2])
        return 1

    callbacks = {
        0xC0019DC0: lambda args: 0xC3006000,  # native logger object
        0xC001A048: lambda args: 0,           # logger sink
        0xC0010298: lambda args: 0,           # lock guard
        0xC00102D0: lambda args: 0,           # unlock guard
        0xC036D758: event_set,
        0xC036D7E0: event_mask,
        0xC036D888: event_query,
        0xC055F0F0: lambda args: 0xC3007000,  # existing UI manager
        0xC055F7D0: lambda args: 0,           # ordinary UI maintenance
        0xC05278F8: lambda args: MANAGER,
        0xC0527D50: lambda args: 0,           # draw thread is not suspended
        0xC0561198: gui_draw,
    }

    def code_hook(cpu, address, size, data):
        if address == STOP:
            cpu.emu_stop()
            return
        callback = callbacks.get(address)
        if callback is not None:
            args = [cpu.reg_read(getattr(reg, f'UC_ARM_REG_R{n}')) for n in range(4)]
            lr = cpu.reg_read(reg.UC_ARM_REG_LR)
            value = callback(args)
            for number in (0, 1, 2, 3, 12):
                cpu.reg_write(getattr(reg, f'UC_ARM_REG_R{number}'), 0xBAD00000 + number)
            cpu.reg_write(reg.UC_ARM_REG_R0, value)
            cpu.reg_write(reg.UC_ARM_REG_PC, lr)
            return
        assert any(lo <= address < hi for lo, hi in NATIVE_RANGES), hex(address)

    uc.hook_add(UC_HOOK_CODE, code_hook)

    def call(address, *args):
        initial_sp = STACK + 0xFFF0
        uc.reg_write(reg.UC_ARM_REG_SP, initial_sp)
        uc.reg_write(reg.UC_ARM_REG_LR, STOP)
        for number, value in enumerate(args):
            uc.reg_write(getattr(reg, f'UC_ARM_REG_R{number}'), value)
        uc.emu_start(address, STOP + 4, count=10000)
        assert uc.reg_read(reg.UC_ARM_REG_PC) == STOP
        assert uc.reg_read(reg.UC_ARM_REG_SP) == initial_sp

    put32(MANAGER, THREAD)
    put32(MANAGER + 4, CONTROLLER)
    uc.mem_write(REQUEST, struct.pack('<III', 0x101, 0xFFFFFFFF, 0))
    # Widgets are already clean: clearing their backing buffer alone must not
    # be mistaken for a request to reconstruct unchanged UI elements.
    uc.mem_write(HANDLER, bytes(12))
    call(0xC0527DD8, MANAGER, 0, 1)
    call(0xC0527DD8, MANAGER, 1, 1)
    if full_redraw:
        call(0xC0527E68, MANAGER, REQUEST)
    else:
        call(0xC0527E40, MANAGER)
    call(0xC0529538, THREAD, CONTEXT)
    call(0xC06D1948, HANDLER, 0xC3008000, CONTEXT)
    result = {
        'draw_thread_event_bits': hex(events.get(THREAD + 0x14, 0)),
        'controller_pending_bits': hex(events.get(CONTROLLER + 0x34, 0)),
        'draw_context_force_byte': uc.mem_read(CONTEXT + 1, 1)[0],
        'gui_draw_modes': draw_modes,
        'event_updates': event_updates,
    }
    assert result['draw_context_force_byte'] == int(full_redraw)
    assert draw_modes == ([2] if full_redraw else [0])
    assert bool(events.get(THREAD + 0x14, 0) & 0x10) == full_redraw
    return result


def main():
    blob = FIRMWARE.read_bytes()
    assert blob[0x528700:0x528704] == struct.pack('<I', 0xE92D4BF0)
    evidence = {
        'firmware': str(FIRMWARE),
        'firmware_sha256': hashlib.sha256(blob).hexdigest(),
        'old_clear_and_wake': scenario(blob, False),
        'fixed_full_redraw_request': scenario(blob, True),
        'scope': 'Offline native ARM control flow; no LCD/presentation/timing claim.',
    }
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
