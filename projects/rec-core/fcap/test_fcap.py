#!/usr/bin/env python3
"""FCAP under unicorn: the real loader v3 (fpSup's sloader, read-only) and the
firmware's own compare at C063F826.

    python3 -B -m unittest test_fcap
"""
import pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))

import test_v3 as V                          # noqa: E402
import build as F                            # noqa: E402
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_CPSR, UC_ARM_REG_PC  # noqa: E402
from unicorn import UC_HOOK_CODE              # noqa: E402

SITE = F.SITE
CHECK = 0xC063F81C            # ldr r2,[sp,#0x14] ; movw r8,#0x4850 ; ldr.w r2,[r8,r2] ; cmp ; bne
FLUSH = 0xC063F82C            # bl C063F140 -- the batch is sent
SKIP = 0xC063F830             # bne target -- no flush
VOL = 0xC37D50D4              # SD volume object (0xC37D066C + 1 * 0x4A68)


def boot(*sups):
    files, dirs = V.card(*sups)
    cam = V.Camera(files, dirs)
    cam.boot()
    return cam


def flushes_at(cam, count):
    """Run the firmware's own compare with vol+0x4850 = count; True if it flushes."""
    mu = cam.mu
    sp = V.STACK - 0x400
    mu.mem_write(sp + 0x14, struct.pack('<I', VOL))
    mu.mem_write(VOL + 0x4850, struct.pack('<I', count))
    hit = {}

    def stop(uc, addr, size, _):
        if addr in (FLUSH, SKIP):
            hit['at'] = addr
            uc.emu_stop()
    h = mu.hook_add(UC_HOOK_CODE, stop, begin=CHECK, end=SKIP + 2)
    mu.reg_write(UC_ARM_REG_SP, sp)
    try:
        mu.emu_start(CHECK | 1, SKIP + 4, count=16)
    finally:
        mu.hook_del(h)
    if 'at' not in hit:
        raise AssertionError('the compare sequence did not reach either exit')
    return hit['at'] == FLUSH


class Build(unittest.TestCase):
    def test_only_the_compare_immediate_changes(self):
        new = F.patched_word()
        self.assertEqual(new[:2], F.STOCK[:2], 'the ldr.w tail must stay')
        self.assertEqual(struct.unpack('<H', new[2:])[0], 0x2A00 | F.CAP, 'T1 cmp r2, #imm8')
        self.assertEqual(sum(a != b for a, b in zip(new, F.STOCK)), 1)

    def test_cap_bounds(self):
        with self.assertRaises(F.BuildError):
            F.patched_word(0x80)                  # stock value: no guardrail
        with self.assertRaises(F.BuildError):
            F.patched_word(0)

    def test_derivation(self):
        reserve, usable = 14, 94
        self.assertEqual(F.CAP, (usable - reserve) // 2)


class Load(unittest.TestCase):
    def test_loads_patches_journals_and_restores(self):
        cam = boot(('30FCAP.BIN', F.build()))
        kinds = [e[0] for e in cam.log()]
        self.assertIn('LOADED', kinds, cam.log())
        self.assertNotIn('RELEASED', kinds)
        self.assertEqual(cam.w(SITE), struct.unpack('<I', F.patched_word())[0])
        self.assertIn((SITE, 4, F.STOCK), cam.journal())
        cam.power_off()
        self.assertEqual(cam.w(SITE), struct.unpack('<I', F.STOCK)[0], 'power-off must restore stock')

    def test_exclusive_owner_refuses_a_second_claim(self):
        other = V.test_sup('ZZZ9', [(SITE, struct.unpack('<I', F.STOCK)[0], 2, 0x2A102002)])
        cam = boot(('10OTHER.BIN', other), ('30FCAP.BIN', F.build()))
        log = cam.log()
        self.assertIn('RELEASED', [e[0] for e in log], log)
        self.assertEqual(cam.w(SITE), 0x2A102002, 'FCAP must not overwrite the first owner')


class Behaviour(unittest.TestCase):
    """The firmware's compare, executed: flush exactly when the 40th frame ends."""

    @classmethod
    def setUpClass(cls):
        cls.cam = boot(('30FCAP.BIN', F.build()))

    def test_flushes_at_the_cap_only(self):
        self.assertTrue(flushes_at(self.cam, F.CAP))
        for n in (0, 1, F.CAP - 1, F.CAP + 1, 0x7F):
            self.assertFalse(flushes_at(self.cam, n), n)

    def test_stock_never_flushes_at_the_cap(self):
        """Mutation: without FCAP the same count does not flush (the test can fail)."""
        stock = boot()
        self.assertFalse(flushes_at(stock, F.CAP))
        self.assertTrue(flushes_at(stock, 0x80))


if __name__ == '__main__':
    unittest.main()
