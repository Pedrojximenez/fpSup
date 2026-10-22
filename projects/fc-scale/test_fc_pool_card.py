#!/usr/bin/env python3
"""Run the pool card's entry under emulation and check what it leaves behind.

The container's shape can be checked by reading it.  What cannot is the entry:
it allocates, copies the payload, patches trampolines, arms three firmware sites
and publishes caches, and the ORDER of those is the difference between a card
that works and a freeze on the next frame -- the display submit fires every
frame, so a site armed before its target is copied and published branches into
whatever the pool held before.

So this emulates it: the file in a buffer, the cave and the three sites as
memory, the allocator and the two cache routines as stubs, every write recorded
in order.  Then it asserts what the camera would see, on both paths -- the
allocator answering, and the allocator refusing, which must arm nothing.

    ./test_fc_pool_card.py --lab-repo DIR

Emulation is not the camera.  This checks the entry's logic, not the firmware's
behaviour: that H_GET hands out executable memory, that 0xC000E91C publishes it,
and that the payload draws anything, are all still open.
"""
import argparse, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fc_scale_pool_card as B

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_WRITE, \
    UC_HOOK_CODE, UC_PROT_ALL
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, \
    UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

FILE_AT = 0x51000000            # where the loader's staging buffer would be
POOL_AT = 0xC3800000            # what the allocator hands back
STACK_AT = 0x40000000
RET_TO = 0x10000000             # an address the entry returns to
BX_LR = 0xE12FFF1E
STUBS = {0xC001D740: 'H_GET', 0xC001D7F0: 'H_ADDR',
         0xC000E91C: 'F_DCACHE', 0xC000EABC: 'F_ICACHE'}


def mov32(reg, value):
    """movw/movt, so a stub can answer an address."""
    return struct.pack('<II',
                       0xE3000000 | (reg << 12) | ((value & 0xF000) << 4)
                       | (value & 0xFFF),
                       0xE3400000 | (reg << 12) | (((value >> 16) & 0xF000) << 4)
                       | ((value >> 16) & 0xFFF))


class Run:
    """One run of the entry.  `answer` is what H_ADDR returns."""

    def __init__(self, blob, entry_off, answer=POOL_AT):
        self.events, self.calls = [], []
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc = uc
        for base, size in ((FILE_AT, 0x10000), (0xC072E000, 0x2000),
                           (0xC0372000, 0x1000), (0xC02E8000, 0x1000),
                           (0xC001D000, 0x1000), (0xC000E000, 0x1000),
                           (POOL_AT, 0x4000), (STACK_AT, 0x10000),
                           (RET_TO, 0x1000)):
            uc.mem_map(base, size, UC_PROT_ALL)
        uc.mem_write(FILE_AT, blob)

        # The stubs.  The entry is told where the descriptor is and writes the
        # trampolines by address, so the sections stage2 places before it are
        # not needed here -- what it writes does not depend on them.
        uc.mem_write(0xC001D740, struct.pack('<I', BX_LR))
        uc.mem_write(0xC001D7F0, mov32(0, answer) + struct.pack('<I', BX_LR))
        for a in (0xC000E91C, 0xC000EABC):
            uc.mem_write(a, struct.pack('<I', BX_LR))

        def on_code(_uc, address, _size, _user):
            if address in STUBS:
                regs = tuple(uc.reg_read(r) for r in
                             (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                              UC_ARM_REG_R3))
                self.events.append(('call', STUBS[address]))
                self.calls.append((STUBS[address],) + regs)

        def on_write(_uc, _type, address, _size, value, _user):
            self.events.append(('write', address, value))

        uc.hook_add(UC_HOOK_CODE, on_code)
        uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
        uc.reg_write(UC_ARM_REG_SP, STACK_AT + 0x8000)
        uc.reg_write(UC_ARM_REG_LR, RET_TO)
        uc.reg_write(UC_ARM_REG_R0, FILE_AT)
        uc.emu_start(FILE_AT + entry_off, RET_TO, count=100000)
        self.ret = uc.reg_read(UC_ARM_REG_R0)

    def word(self, addr):
        return struct.unpack('<I', self.uc.mem_read(addr, 4))[0]

    def writes_to(self, lo, hi=None):
        hi = lo + 4 if hi is None else hi
        return [i for i, e in enumerate(self.events)
                if e[0] == 'write' and lo <= e[1] < hi]

    def call_after(self, name, after):
        return next((i for i, e in enumerate(self.events)
                     if e[0] == 'call' and e[1] == name and i > after), None)


def hop(blob, hooks, site, tramp_target):
    """Follow the site through its trampoline, the way the camera would: two
    instructions, and the second one is `ldr pc`."""
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0xC072E000, 0x2000), (0xC0372000, 0x1000),
                       (0xC02E8000, 0x1000), (POOL_AT, 0x4000)):
        uc.mem_map(base, size, UC_PROT_ALL)
    count = struct.unpack_from('<I', blob, 4)[0]          # stage2 pass 1
    off = 16 + 8 * count
    for i in range(count):
        dest, ln = struct.unpack_from('<II', blob, 16 + 8 * i)
        if dest:
            uc.mem_write(dest, blob[off:off + ln])
        off += ln + (-ln % 4)
    for n in range(3):                                    # what the entry does
        uc.mem_write(B.TRAMP_AT + 8 * n + 4,
                     struct.pack('<I', tramp_target[n]))
    for n, (_why, s, _o) in enumerate(hooks):
        uc.mem_write(s, struct.pack('<I', B.branch(s, B.TRAMP_AT + 8 * n)))
    uc.mem_write(POOL_AT, b'\x1e\xff\x2f\xe1' * 0x400)     # bx lr everywhere
    uc.emu_start(site, POOL_AT, count=2)
    return uc.reg_read(UC_ARM_REG_PC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lab-repo', type=pathlib.Path, required=True)
    a = ap.parse_args()
    blob, info = B.build(a.lab_repo)
    code, hooks, entry = info['code'], info['hooks'], info['entry']
    ok = True

    def check(cond, what):
        nonlocal ok
        print(('  ok   ' if cond else '  FAIL ') + what)
        ok = ok and bool(cond)

    print('the allocator answers:')
    r = Run(blob, entry)
    check(r.ret == 0, 'the entry returns 0, as stage2 requires')
    check(bytes(r.uc.mem_read(POOL_AT, len(code))) == code,
          f'the payload is in the pool, {len(code)} B identical')
    check(r.word(B.POOLPTR_AT) == POOL_AT,
          f'the pool address is published at 0x{B.POOLPTR_AT:08X}')
    got = [c for c in r.calls if c[0] == 'H_GET']
    check(len(got) == 1 and got[0][1:] == (B.DESC_AT, 0, info['size'], 0),
          f'H_GET(0x{B.DESC_AT:08X}, class 0, 0x{info["size"]:X}, 0) once')
    for n, (why, site, off) in enumerate(hooks):
        t = B.TRAMP_AT + 8 * n
        check(r.word(t + 4) == POOL_AT + off,
              f'{why}: the trampoline at 0x{t:08X} points at pool+0x{off:X}')
        check(r.word(site) == B.branch(site, t),
              f'{why}: the site 0x{site:08X} branches to 0x{t:08X}')

    dep = max(r.writes_to(POOL_AT, POOL_AT + len(code))
              + r.writes_to(B.TRAMP_AT, B.TRAMP_AT + 24))
    first_site = min(min(r.writes_to(site)) for _w, site, _o in hooks)
    pub = r.call_after('F_DCACHE', dep)
    ipub = r.call_after('F_ICACHE', pub if pub is not None else dep)
    check(dep < first_site,
          'the pool and the trampolines are written before any site is armed')
    check(pub is not None and ipub is not None and ipub < first_site,
          'a D-cache clean and an I-cache invalidate happen in between')
    check(r.call_after('F_ICACHE', first_site) is not None,
          'and the sites themselves are published afterwards')

    print('the camera follows a site:')
    targets = [POOL_AT + off for _w, _s, off in hooks]
    for n, (why, site, off) in enumerate(hooks):
        check(hop(blob, hooks, site, targets) == POOL_AT + off,
              f'{why}: 0x{site:08X} two hops to pool+0x{off:X}')

    print('the allocator refuses:')
    r = Run(blob, entry, answer=0)
    check(r.ret == 0, 'the entry still returns 0')
    for why, site, _off in hooks:
        check(not r.writes_to(site),
              f'{why}: the site 0x{site:08X} is left alone')
    check(not r.writes_to(B.TRAMP_AT, B.TRAMP_AT + 24),
          'no trampoline is pointed anywhere')
    check(not r.writes_to(POOL_AT, POOL_AT + 0x1000),
          'nothing is copied anywhere')

    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
