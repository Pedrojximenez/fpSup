#!/usr/bin/env python3
"""Emulate boot_tstamp.S: does it sample, and does the tail behave?

Three things are worth checking before a card carrying this goes in a camera,
and none of them can be read off the source with confidence:

  * a sample lands in the next slot and the index moves;
  * with a tail, the handler's arguments survive into it -- the abort is a
    command handler and is entitled to (ctx, argc, argv);
  * with a tail whose target is still zero -- the first boot of a fast card,
    where stage2 never ran -- it returns instead of branching into nothing.

    ./test_boot_tstamp.py
"""
import pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / 'fpSup/fp_usb_shell'))
import armasm

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_ALL
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, \
    UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

STUB = HERE / 'boot_tstamp.S'
CLOCK = 0xC002B920
CODE_AT = 0xC072F200
SLOTS = 0xC072F280
ABORT_AT = 0xC072F080
STACK = 0x40000000
RET_TO = 0x10000000
TICKS = 0x00123456
BX_LR = 0xE12FFF1E


def run(tail, *, arm_the_tail=True, args=(0xC0FFEE00, 3, 0xC0DE0000)):
    blob = armasm.assemble(STUB, (f'SLOTS=0x{SLOTS:08X}', f'TAIL=0x{tail:08X}'))
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0xC072F000, 0x1000), (0xC002B000, 0x1000),
                       (STACK, 0x10000), (RET_TO, 0x1000)):
        uc.mem_map(base, size, UC_PROT_ALL)
    uc.mem_write(CODE_AT, blob)
    # The clock: r0 = TICKS, then return.
    uc.mem_write(CLOCK, struct.pack('<III',
                 0xE3000000 | ((TICKS & 0xF000) << 4) | (TICKS & 0xFFF),
                 0xE3400000 | (((TICKS >> 16) & 0xF000) << 4)
                 | ((TICKS >> 16) & 0xFFF), BX_LR))
    if tail and arm_the_tail:
        # Something that looks like the abort: records that it ran, then returns.
        uc.mem_write(tail, struct.pack('<I', BX_LR))
    uc.reg_write(UC_ARM_REG_SP, STACK + 0x8000)
    uc.reg_write(UC_ARM_REG_LR, RET_TO)
    for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
        uc.reg_write(r, v)
    seen = []
    if tail:
        uc.hook_add(4, lambda _u, a, _s, _x: a == tail and seen.append(a),
                    begin=tail, end=tail)      # UC_HOOK_CODE
    uc.emu_start(CODE_AT, RET_TO, count=200)
    return uc, seen, len(blob)


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(('  ok   ' if cond else '  FAIL ') + what)
        ok = ok and bool(cond)

    def word(uc, a):
        return struct.unpack('<I', uc.mem_read(a, 4))[0]

    print('no tail:')
    uc, _seen, n = run(0)
    check(word(uc, SLOTS) == 1, 'the index moved to 1')
    check(word(uc, SLOTS + 4) == TICKS, f'slot 0 holds the clock (0x{TICKS:X})')
    check(uc.reg_read(UC_ARM_REG_R0) == 0, 'returns 0, like echo')
    print(f'  ({n} bytes of code)')

    print('called twice:')
    blob = armasm.assemble(STUB, (f'SLOTS=0x{SLOTS:08X}', 'TAIL=0x0'))
    uc, _s, _n = run(0)
    uc.reg_write(UC_ARM_REG_SP, STACK + 0x8000)
    uc.reg_write(UC_ARM_REG_LR, RET_TO)
    uc.emu_start(CODE_AT, RET_TO, count=200)
    check(word(uc, SLOTS) == 2, 'the index moved to 2')
    check(word(uc, SLOTS + 8) == TICKS, 'the second sample went to slot 1')

    print('tail, armed:')
    args = (0xC0FFEE00, 3, 0xC0DE0000)
    uc, seen, _n = run(ABORT_AT, args=args)
    check(word(uc, SLOTS) == 1, 'the sample was taken first')
    check(seen == [ABORT_AT], f'the tail at 0x{ABORT_AT:08X} ran')
    # The arguments are checked in the run below, which stops AT the tail and
    # reads them there -- a check that cannot fail is not a check.
    blob = armasm.assemble(STUB, (f'SLOTS=0x{SLOTS:08X}', f'TAIL=0x{ABORT_AT:08X}'))
    uc2 = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0xC072F000, 0x1000), (0xC002B000, 0x1000),
                       (STACK, 0x10000), (RET_TO, 0x1000)):
        uc2.mem_map(base, size, UC_PROT_ALL)
    uc2.mem_write(CODE_AT, blob)
    uc2.mem_write(CLOCK, struct.pack('<III',
                  0xE3000000 | ((TICKS & 0xF000) << 4) | (TICKS & 0xFFF),
                  0xE3400000 | (((TICKS >> 16) & 0xF000) << 4)
                  | ((TICKS >> 16) & 0xFFF), BX_LR))
    uc2.mem_write(ABORT_AT, struct.pack('<I', BX_LR))
    uc2.reg_write(UC_ARM_REG_SP, STACK + 0x8000)
    uc2.reg_write(UC_ARM_REG_LR, RET_TO)
    for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
        uc2.reg_write(r, v)
    uc2.emu_start(CODE_AT, ABORT_AT, count=200)      # stops AT the tail
    at_tail = tuple(uc2.reg_read(r) for r in
                    (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
    check(at_tail == args, f'(ctx, argc, argv) arrive intact: '
                           f'{[hex(x) for x in at_tail]}')
    check(uc2.reg_read(UC_ARM_REG_LR) == RET_TO,
          'lr still points at the interpreter, so the tail can return')
    check(uc2.reg_read(UC_ARM_REG_SP) == STACK + 0x8000,
          'the stack is balanced before the tail is entered')

    print('tail, not armed (a fast card\'s first boot):')
    uc, seen, _n = run(ABORT_AT, arm_the_tail=False)
    check(word(uc, SLOTS) == 1, 'the sample is still taken')
    check(seen == [], 'nothing is branched into')
    check(uc.reg_read(UC_ARM_REG_R0) == 0, 'returns 0, and the script goes on')

    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
