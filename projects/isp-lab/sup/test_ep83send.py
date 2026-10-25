#!/usr/bin/env python3
"""ep83send.S under unicorn: the TRB it arms, the calls it makes, what it reports.
    python3 -B -m unittest test_ep83send"""
import pathlib, struct, sys, unittest
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1].parent / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble                                    # noqa: E402
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE  # noqa: E402
from unicorn.arm_const import *                                # noqa: E402,F403

CODE, P, TRB = 0xC072E000, 0xC072E400, 0xC31E3300
STARTX, WAIT, ENDX, PRINT, RET = 0xC01E6B80, 0xC01E4E80, 0xC01E6D48, 0xC0100000, 0xC0200000
CTXOBJ, STACK = 0xC3700000, 0xC3800000


class Run:
    def __init__(self, start_rc=0, complete=True, defines=()):
        self.code = assemble(HERE / 'ep83send.S', [f'P=0x{P:08X}', *defines])
        mu = self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for base, size in ((0xC0000000, 0x400000), (0xC0700000, 0x100000), (0xC3000000, 0x900000)):
            mu.mem_map(base, size)
        mu.mem_write(CODE, self.code)
        for a in (STARTX, WAIT, ENDX, PRINT):
            mu.mem_write(a, b'\x70\x47')                        # bx lr (Thumb)
        mu.mem_write(RET, struct.pack('<I', 0xE12FFF1E))
        mu.mem_write(0xC31E3264 + 4 * 3, struct.pack('<I', TRB))
        mu.mem_write(TRB, struct.pack('<4I', 0xAAAAAAAA, 0xBBBBBBBB, 0, 0))
        mu.mem_write(CTXOBJ, struct.pack('<I', PRINT | 1))
        mu.mem_write(P, struct.pack('<5I', 0x4A000000, 16384, 3, 7, 1000) + b'\xEE' * 0x18)
        self.calls, self.start_rc, self.complete = [], start_rc, complete
        mu.hook_add(UC_HOOK_CODE, self.hook)
        mu.reg_write(UC_ARM_REG_R0, CTXOBJ)
        mu.reg_write(UC_ARM_REG_SP, STACK - 0x100)
        mu.reg_write(UC_ARM_REG_LR, RET)
        mu.emu_start(CODE, RET, count=10000)

    def r(self, reg):
        return self.mu.reg_read(reg)

    def hook(self, mu, addr, size, _):
        name = {STARTX: 'start', WAIT: 'wait', ENDX: 'end', PRINT: 'print'}.get(addr)
        if not name:
            return
        r0, r1 = self.r(UC_ARM_REG_R0), self.r(UC_ARM_REG_R1)
        trb = struct.unpack('<4I', mu.mem_read(TRB, 16))
        self.calls.append((name, r0, r1, trb))
        ret = 0
        if name == 'start':
            ret = self.start_rc & 0xFFFFFFFF
        if name == 'wait' and self.complete:
            mu.mem_write(TRB + 8, struct.pack('<I', 0))
            mu.mem_write(TRB + 12, struct.pack('<I', 0x812))   # HWO cleared
        mu.reg_write(UC_ARM_REG_R0, ret)

    def out(self):
        return struct.unpack('<6I', self.mu.mem_read(P + 0x14, 24))


class Ep83Send(unittest.TestCase):
    def test_arms_one_trb_then_starts_phys_7(self):
        r = Run()
        start = r.calls[0]
        self.assertEqual(start[0], 'start')
        self.assertEqual(start[1], 7)
        self.assertEqual(start[3], (0x4A000000, 0, 16384, 0x813))
        self.assertEqual([c[0] for c in r.calls], ['start', 'wait', 'print'])
        self.assertEqual(r.calls[1][1:3], (3, 1000))
        self.assertEqual(r.out(), (0, 0, 0x812, 0, 0, 0xD09E0083))
        self.assertLess(len(r.code), 320)

    def test_refused_start_waits_for_nothing(self):
        r = Run(start_rc=-1)
        self.assertEqual([c[0] for c in r.calls], ['start', 'print'])
        self.assertEqual(r.out()[0], 0xFFFFFFFF)
        self.assertEqual(r.out()[5], 0xD09E0083)

    def test_unfinished_transfer_is_ended(self):
        r = Run(complete=False)
        self.assertEqual([c[0] for c in r.calls], ['start', 'wait', 'end', 'print'])
        self.assertEqual(r.calls[2][1], 3)
        self.assertEqual(r.out()[2] & 1, 1)
        self.assertEqual(r.out()[4], 1)


if __name__ == '__main__':
    unittest.main()
