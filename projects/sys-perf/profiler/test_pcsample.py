#!/usr/bin/env python3
"""pcsample under unicorn: the real IRQ path of the real image, end to end.

An interrupt is taken from a task at X: the core is put in IRQ mode exactly as
the exception entry leaves it (lr_irq = X+4, SPSR_irq = the task's CPSR, sp_irq
= the reset value 0xC42F1FC0) and runs from the vector target C00014A0 —
C00014A0 -> C0000E64 -> hook C0000EC4 -> timer ISR C0016000 -> our handler ->
(A) the OS tick C0016978 -> ... -> ret_int C0000F88 -> back at X.  Stubbed: only
knl_timer_handler C000D9A8 (counted).  Interrupt controller and timer
registers are fake pages; the timer's pending word clears the bits written as
zero, as C0016000 expects.

Asserted, decoded independently of the handler:
  - we come back to X in the task's mode with r0-r12, sp, lr, CPSR, d0-d15
    as they were, and sp_irq back at its top;
  - the ring record holds X, the task's LR, (tid<<8)|SPSR&0xFF and the time;
  - A reaches the OS tick exactly once, B never does;
  - disabled / skip / limit / idle / Thumb / USR / garbage-SPSR behaviour.

    python3 -B test_pcsample.py            # all cases
    python3 -B test_pcsample.py --mutate   # every mutation must fail a case
"""
import pathlib, shutil, struct, sys, tempfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, \
    UC_HOOK_MEM_WRITE, UcError
from unicorn import arm_const as A

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble, symbols  # noqa: E402

SEG0 = ROOT / 'out' / 'seg0_c0000000.bin'   # code
SEG1 = ROOT / 'out' / 'seg1_c2ef6e00.bin'   # initialised data (MAIN's tail is not this)
CODE_AT = 0xC072E400          # any spare spot in the emulated image
RING = 0x45000000
INTC = 0x10000000
TMR = 0x10010000
TCB = 0xC30F0000
IRQ_TOP = 0xC42F1FC0
SVC_SP = 0xC5000F00
TICK = 0xC0016978
KNL_TIMER = 0xC000D9A8
TID = 44
NOW = 0x00123456


class Rig:
    def __init__(self, src, mode='A', ch=0):
        code = assemble(src)
        self.sym = symbols(src)
        self.entry = CODE_AT + self.sym['pcs_tick']
        self.ctl = CODE_AT + self.sym['ctl']
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
        mu.mem_map(0xC0000000, 0x03200000)
        mu.mem_write(0xC0000000, SEG0.read_bytes())
        mu.mem_write(0xC2EF6E00, SEG1.read_bytes())
        mu.mem_map(0xC42F0000, 0x2000)
        mu.mem_map(0xC4FF0000, 0x20000)
        mu.mem_map(RING, 0x10000)
        mu.mem_map(INTC, 0x1000)
        mu.mem_map(TMR, 0x1000)
        mu.mem_write(CODE_AT, code)

        w = self.w
        w(0xC30000AC + 4 * 4, 0xC0000E64)        # low-level table, IRQ 4
        w(0xC30004AC + 4 * 4, 0xC0016000)        # C handler, IRQ 4
        w(0xC3033460, INTC); w(INTC, 4)          # current IRQ number = 4
        w(0xC30337FC, TMR)                       # timer pending/ack page
        w(0xC30337F0, TMR + 0x100)               # channel registers
        w(0xC303380C, TICK)                      # channel 0 = OS tick
        w(0xC303326C, 0); w(0xC3000094, 0)       # taskindp, dispatch-disabled
        w(TCB + 8, TID)
        w(0xC3000098, TCB); w(0xC30000A0, TCB)   # ctxtsk == schedtsk
        w(0xC301EAE4, NOW)
        self.mode, self.ch = mode, ch
        if mode is None:                         # stock: nothing installed
            w(0xC3033808, 1)
            self.pend = 0
        elif mode == 'A':
            w(0xC303380C, self.entry)
            w(0xC3033808, 1)
            self.pend = 1
            self.c(0x14, TICK)
        else:
            w(0xC303380C + ch * 4, self.entry)
            w(0xC3033808, 1 << ch)
            self.pend = 1 << ch
            self.c(0x14, 0)
        if mode is not None:
            self.c(0x04, RING); self.c(0x08, 255); self.c(0x10, 0xFFFFFFFF)
            self.c(0x18, 1)

        self.ticks = 0
        self.trace = []
        mu.hook_add(UC_HOOK_CODE, self._code)
        mu.hook_add(UC_HOOK_MEM_READ, self._rd, begin=TMR + 4, end=TMR + 7)
        mu.hook_add(UC_HOOK_MEM_WRITE, self._wr, begin=TMR + 4, end=TMR + 7)

    def w(self, a, v):
        self.mu.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def r(self, a):
        return struct.unpack('<I', self.mu.mem_read(a, 4))[0]

    def c(self, off, v):
        self.w(self.ctl + off, v)

    def cr(self, off):
        return self.r(self.ctl + off)

    def _rd(self, mu, access, addr, size, value, _):
        mu.mem_write(TMR + 4, struct.pack('<I', self.pend))

    def _wr(self, mu, access, addr, size, value, _):
        self.pend &= value

    def _code(self, mu, addr, size, _):
        self.trace.append(addr)
        if len(self.trace) > 20000:
            mu.emu_stop()
        if addr == KNL_TIMER:                    # the OS clock: count and advance it
            self.ticks += 1
            self.w(0xC301EAE4, self.r(0xC301EAE4) + 1)
            mu.reg_write(A.UC_ARM_REG_PC, mu.reg_read(A.UC_ARM_REG_LR))

    def take_irq(self, x, task_cpsr=0x60000013, lr=0xC0ABCDE0, thumb=False):
        mu = self.mu
        mu.reg_write(A.UC_ARM_REG_C1_C0_2, 0xF00000)
        mu.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        mu.reg_write(A.UC_ARM_REG_CPSR, 0x1D3)
        mu.reg_write(A.UC_ARM_REG_SP, 0xC4FF8000)   # SVC stack; the task's own if it runs in SVC
        mode = task_cpsr & 0x1F
        bank = 0x1F if mode == 0x10 else mode
        mu.reg_write(A.UC_ARM_REG_CPSR, (task_cpsr & ~0x3F) | 0xC0 | bank)
        regs = {getattr(A, f'UC_ARM_REG_R{i}'): 0x11110000 + i for i in range(13)}
        for k, v in regs.items():
            mu.reg_write(k, v)
        mu.reg_write(A.UC_ARM_REG_SP, SVC_SP)
        mu.reg_write(A.UC_ARM_REG_LR, lr)
        for i in range(16):
            mu.reg_write(getattr(A, f'UC_ARM_REG_D{i}'), 0xD0D00000_00000000 + i)
        # exception entry
        mu.reg_write(A.UC_ARM_REG_CPSR, 0x000001D2)
        mu.reg_write(A.UC_ARM_REG_SP, IRQ_TOP)
        mu.reg_write(A.UC_ARM_REG_LR, x + 4)
        mu.reg_write(A.UC_ARM_REG_SPSR, task_cpsr | (0x20 if thumb else 0))
        self.trace.clear()
        try:
            mu.emu_start(0xC00014A0, x & ~1)
        except UcError as e:
            raise AssertionError(f'emulation fault {e} at {mu.reg_read(A.UC_ARM_REG_PC):#x}, '
                                 f'last {[hex(a) for a in self.trace[-8:]]}')
        pc = mu.reg_read(A.UC_ARM_REG_PC)
        assert pc == x & ~1, f'did not return to X: pc={pc:#x} last {[hex(a) for a in self.trace[-6:]]}'
        cpsr = mu.reg_read(A.UC_ARM_REG_CPSR)
        want = task_cpsr | (0x20 if thumb else 0)
        assert cpsr == want, f'cpsr {cpsr:#x} != {want:#x}'
        for k, v in regs.items():
            got = mu.reg_read(k)
            assert got == v, f'reg {k} {got:#x} != {v:#x}'
        assert mu.reg_read(A.UC_ARM_REG_SP) == SVC_SP, 'task sp moved'
        assert mu.reg_read(A.UC_ARM_REG_LR) == lr, 'task lr changed'
        for i in range(16):
            assert mu.reg_read(getattr(A, f'UC_ARM_REG_D{i}')) == 0xD0D00000_00000000 + i, f'd{i}'
        mu.reg_write(A.UC_ARM_REG_CPSR, 0x1D2)
        assert mu.reg_read(A.UC_ARM_REG_SP) == IRQ_TOP, 'irq sp not back at top'
        mu.reg_write(A.UC_ARM_REG_CPSR, cpsr)
        return self.trace[:]

    def rec(self, i):
        return struct.unpack('<4I', self.mu.mem_read(RING + 16 * i, 16))


# ------------------------------------------------------------------ cases
def case_basic_A(src):
    g = Rig(src, 'A')
    path = g.take_irq(0xC0123450)
    for a in (0xC00014A0, 0xC0000E64, 0xC0016000, g.entry, TICK, 0xC0000F88, 0xC0001034):
        assert a in path, f'real path skipped {a:#x}'
    assert g.ticks == 1, f'OS tick reached {g.ticks} times'
    assert g.cr(0x0C) == 1 and g.cr(0x24) == 1
    assert g.r(0xC301EAE4) == NOW + 1, 'OS clock did not advance'
    assert g.rec(0) == (0xC0123450, 0xC0ABCDE0, (TID << 8) | 0x13, NOW), \
        [hex(v) for v in g.rec(0)]
    assert g.r(0xC303326C) == 0, 'taskindp left raised'


def case_basic_B(src):
    g = Rig(src, 'B', ch=3)
    g.take_irq(0xC0123450)
    assert g.ticks == 0, 'B must not call the OS tick'
    assert g.rec(0) == (0xC0123450, 0xC0ABCDE0, (TID << 8) | 0x13, NOW)


def case_two_samples_and_time(src):
    g = Rig(src, 'A')
    g.take_irq(0xC0123450)
    g.pend = 1
    g.take_irq(0xC0200000, lr=0xC0300000)
    assert g.ticks == 2 and g.cr(0x0C) == 2
    assert g.rec(1) == (0xC0200000, 0xC0300000, (TID << 8) | 0x13, NOW + 1)


def case_thumb_usr(src):
    g = Rig(src, 'A')
    g.take_irq(0xC0123450, task_cpsr=0x60000010, lr=0xC0444445, thumb=True)
    pc, lr, w2, _ = g.rec(0)
    assert pc == 0xC0123450, hex(pc)     # Thumb: halfword address, bit 0 clear
    assert lr == 0xC0444445, 'USR lr must come from the SYS bank'
    assert w2 == (TID << 8) | 0x30, hex(w2)


def case_idle(src):
    g = Rig(src, 'A')
    g.w(0xC3000098, 0); g.w(0xC30000A0, 0)
    g.take_irq(0xC0000D64)
    assert g.rec(0)[2] >> 8 == 0, 'idle must record tid 0'


def case_disabled(src):
    g = Rig(src, 'A')
    g.c(0x18, 0)
    g.take_irq(0xC0123450)
    assert g.ticks == 1 and g.cr(0x24) == 1 and g.cr(0x0C) == 0
    assert g.rec(0) == (0, 0, 0, 0)


def case_skip_and_limit(src):
    g = Rig(src, 'A')
    g.c(0x28, 1); g.c(0x10, 1)
    for x in (0xC0100000, 0xC0100100, 0xC0100200):
        g.pend = 1
        g.take_irq(x)
    assert g.ticks == 3
    assert g.cr(0x0C) == 1, g.cr(0x0C)
    assert g.rec(0)[0] == 0xC0100100, 'first call skipped, second kept'
    assert g.cr(0x1C) == 1, 'third dropped at the limit'


def case_wrap(src):
    g = Rig(src, 'A')
    g.c(0x08, 1)                             # two records
    for x in (0xC0100000, 0xC0100100, 0xC0100200):
        g.pend = 1
        g.take_irq(x)
    assert g.cr(0x0C) == 3
    assert g.rec(0)[0] == 0xC0100200 and g.rec(1)[0] == 0xC0100100


def case_garbage_spsr(src):
    """A wrong C_FRAME reads a garbage SPSR: never switch into it."""
    g = Rig(src, 'A')
    scratch = 0xC42F0100
    g.w(scratch, 0xC0DEC0DE); g.w(scratch - 8, 0x1B)   # 'UND' mode
    g.c(0x20, scratch)
    g.mu.reg_write(A.UC_ARM_REG_CPSR, 0x1DB)             # seed lr_und with a marker
    g.mu.reg_write(A.UC_ARM_REG_LR, 0xBADBAD00)
    g.take_irq(0xC0123450)
    assert g.rec(0)[:2] == (0xC0DEC0DE, 0), [hex(v) for v in g.rec(0)]


CASES = [case_basic_A, case_basic_B, case_two_samples_and_time, case_thumb_usr,
         case_idle, case_disabled, case_skip_and_limit, case_wrap, case_garbage_spsr]


def run(src, quiet=False):
    bad = []
    for f in CASES:
        try:
            f(src)
            if not quiet:
                print(f'  ok   {f.__name__}')
        except AssertionError as e:
            bad.append(f.__name__)
            if not quiet:
                print(f'  FAIL {f.__name__}: {e}')
    return bad


MUTATIONS = [
    ('frame spsr offset', 'ldr     r5, [r0, #-8]', 'ldr     r5, [r0, #-4]'),
    ('tid offset', 'ldrne   r0, [r0, #8]', 'ldrne   r0, [r0, #4]'),
    ('no tail call', 'bx      r0                      /*', 'bx      lr                      /*'),
    ('cpsr not restored', '    msr     cpsr_c, r0\n', '    nop\n'),
    ('lr without bank switch', '    msr     cpsr_c, ip              /*', '    nop                             /*'),
    ('idx not advanced', '    add     r1, r1, #1\n    str     r1, [r3, #C_IDX]',
     '    nop\n    str     r1, [r3, #C_IDX]'),
    ('no pop', '    pop     {r4, r5}\n', '    nop\n'),
    ('limit ignored', '    bhs     full\n', '    nop\n'),
    ('skip ignored', '    bls     out                     /*', '    nop                             /*'),
    ('enable ignored', '    cmp     r1, #0\n    beq     out\n', '    cmp     r1, #0\n    nop\n'),
    ('mode whitelist dropped', '    cmpne   r2, #0x1F\n    bne     nolr\n', '    nop\n    nop\n'),
    ('USR not mapped to SYS', '    moveq   r2, #0x1F', '    nop'),
    ('mask ignored', '    and     r2, r1, r2\n', '    mov     r2, r1\n'),
    ('time not stored', '    str     r0, [r4, #12]\n', '    nop\n'),
    ('idle tid deref', '    ldrne   r0, [r0, #8]', '    ldr     r0, [r0, #8]'),
]


def mutate():
    src = (HERE / 'pcsample.S').read_text()
    survived = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, old, new in MUTATIONS:
            assert src.count(old) == 1, f'mutation {name!r}: anchor found {src.count(old)} times'
            p = pathlib.Path(tmp) / 'm.S'
            p.write_text(src.replace(old, new))
            bad = run(p, quiet=True)
            print(f'  {"caught " if bad else "SURVIVED"} {name:28s} {bad[:3]}')
            if not bad:
                survived.append(name)
    return survived


if __name__ == '__main__':
    if '--mutate' in sys.argv:
        s = mutate()
        print('mutations survived:', s or 'none')
        sys.exit(1 if s else 0)
    bad = run(HERE / 'pcsample.S')
    print('all passed' if not bad else f'{len(bad)} failed')
    sys.exit(1 if bad else 0)
