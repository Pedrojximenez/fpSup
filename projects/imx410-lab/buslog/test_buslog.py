#!/usr/bin/env python3
"""IMXB under unicorn: the real loader v4 loads IMXB.BIN into the real image;
then FUN_c0322c70 runs for real (through FUN_c0322cb0 / FUN_c0128898) into a
mapped sensor-bus controller, with the logger off and on.

    python3 -B -m unittest test_buslog
"""
import pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[2] / 'fpSup' / 'fp_usb_shell'
sys.path[:0] = [str(HERE), str(SHELL.parent / 'loader-v4'), str(SHELL / 'v3'), str(SHELL)]
import test_v4 as V4                                         # noqa: E402
import test_v3 as V3                                         # noqa: E402
import build as BB                                           # noqa: E402

SITE = 0xC0322C70
BUS = 0x21C00000
_B = {}


def sup(defines=()):
    k = tuple(defines)
    if k not in _B:
        _B[k] = BB.build(defines)
    return _B[k]


class Bus:
    def __init__(self, defines=()):
        self.blob, self.info = sup(defines)
        cam = self.cam = V4.Camera(*V4.card(('IMXB.BIN', self.blob)))
        cam.mu.mem_map(BUS, 0x1000)
        cam.mu.mem_map(0x30000000, 0x3000)
        cam.boot()
        self.block = V4.blocks(cam).get('IMXB.BIN')
        assert self.block, cam.loadlog()
        self.st = self.block + self.info['state_off']

    def w(self, off): return self.cam.w(self.st + off)

    def write(self, reg, val):
        self.cam.call(SITE, r0=reg, r1=val)
        return self.cam.w(BUS + 0x114), self.cam.w(BUS + 0x118)

    def entries(self):
        n, cap = self.w(8), self.w(12)
        out = []
        for i in range(max(0, n - cap), n):
            e = self.st + 64 + 16 * (i & (cap - 1))
            out.append(struct.unpack('<4I', self.cam.mu.mem_read(e, 16)))
        return out


class BusLogTests(unittest.TestCase):
    def test_loads_cached_hooks_and_restores(self):
        b = Bus()
        c = b.cam
        self.assertTrue(b.block >= 0xC0000000, hex(b.block))           # SL_F_CACHED_OK
        self.assertEqual(c.w(SITE), 0xE51FF004)
        self.assertEqual(c.w(SITE + 4), b.w(16))
        self.assertTrue(b.block <= c.w(SITE + 4) < b.block + b.info['file_len'])
        self.assertEqual((b.w(0), b.w(12)), (0x42584D49, BB.CAP))
        self.assertIn((SITE, 8, struct.pack('<2I', *BB.STOCK)), c.journal())
        c.power_off()
        self.assertEqual(struct.unpack('<2I', c.mu.mem_read(SITE, 8)), BB.STOCK)

    def test_off_passes_through_unlogged(self):
        b = Bus()
        self.assertEqual(b.write(0x003D, 0x55), (0x3D << 16 | 0x81, 0x55))
        self.assertEqual(b.write(0x05E1, 0x01), (0xE1 << 16 | 0x81 | 0x05 << 8, 0x01))
        self.assertEqual(b.w(8), 0)

    def test_on_logs_every_write_and_still_writes_the_bus(self):
        b = Bus()
        b.cam.put(b.st + 4, 1)
        seq = [(0x0005, 0x10), (0x0006, 0x02), (0x003D, 0xFE), (0x0716, 0x07)]
        for reg, val in seq:
            self.assertEqual(b.write(reg, val), ((reg & 0xFF) << 16 | 0x81 | (reg >> 8) << 8, val))
        got = b.entries()
        self.assertEqual([(r, v) for _, r, v, _ in got], seq)
        self.assertTrue(all(lr == V3.DONE for *_, lr in got))
        ticks = [t for t, *_ in got]
        self.assertEqual(ticks, sorted(ticks))
        self.assertEqual(len(set(ticks)), len(ticks))

    def test_ring_wraps(self):
        b = Bus()
        b.cam.put(b.st + 4, 1)
        b.cam.put(b.st + 8, BB.CAP - 2)                  # as if the ring were nearly full
        for i in range(4):
            b.write(0x0100 + i, i)
        self.assertEqual(b.w(8), BB.CAP + 2)
        e = lambda i: struct.unpack('<4I', b.cam.mu.mem_read(b.st + 64 + 16 * i, 16))
        self.assertEqual((e(0)[1], e(1)[1]), (0x102, 0x103))
        self.assertEqual((e(BB.CAP - 2)[1], e(BB.CAP - 1)[1]), (0x100, 0x101))

    def test_substitution_changes_only_listed_registers(self):
        b = Bus()
        b.cam.put(b.st + 4, 1)
        b.cam.put(b.st + 32, 0x003F << 16 | 0x55)
        b.cam.put(b.st + 36, 0x0007 << 16 | 0x10)
        b.cam.put(b.st + 20, 2)
        self.assertEqual(b.write(0x003D, 0xEC)[1], 0xEC)            # not listed: unchanged
        self.assertEqual(b.write(0x003F, 0xEC)[1], 0x55)            # listed: the bus gets 0x55
        self.assertEqual(b.write(0x0007, 0x00)[1], 0x10)
        self.assertEqual(b.write(0x0040, 0x09)[1], 0x09)            # 0x40 is not 0x3F
        self.assertEqual(b.w(24), 2)                                 # hits
        self.assertEqual([(r, v) for _, r, v, _ in b.entries()],
                         [(0x3D, 0xEC), (0x3F, 0x55), (0x07, 0x10), (0x40, 0x09)])

    def test_substitution_off_and_bounded(self):
        b = Bus()
        b.cam.put(b.st + 32, 0x003F << 16 | 0x55)
        self.assertEqual(b.write(0x003F, 0xEC)[1], 0xEC)            # nsub 0: nothing
        for i in range(8):
            b.cam.put(b.st + 32 + 4 * i, 0x0100 << 16 | i)
        b.cam.put(b.st + 64, 0x0101 << 16 | 0x77)                   # a ninth entry (the log ring)
        b.cam.put(b.st + 20, 200)                                    # clamped to 8
        self.assertEqual(b.write(0x0101, 0x01)[1], 0x01)
        self.assertEqual(b.write(0x0100, 0xAA)[1], 7)                # last match wins

    def test_alternation_flips_per_frame_block(self):
        b = Bus()
        b.cam.put(b.st + 32, 0x003F << 16 | 0x22 << 8 | 0x11)        # odd 0x22, even 0x11
        b.cam.put(b.st + 20, 1)
        b.cam.put(b.st + 28, 1)                                      # alt on, phase even
        seen = []
        for frame in range(4):
            b.write(0x041F, 0x00)                                     # the block's first write
            seen.append(b.write(0x003F, 0xEC)[1])
            self.assertEqual(b.write(0x003D, 0xEC)[1], 0xEC)         # unlisted: untouched
        self.assertEqual(seen, [0x22, 0x11, 0x22, 0x11])
        b.cam.put(b.st + 28, 0)                                      # alt off: the even value only
        self.assertEqual(b.write(0x041F, 0)[1], 0)
        self.assertEqual(b.write(0x003F, 0xEC)[1], 0x11)

    def capt(self, b):
        return b.st + BB.CAPT

    def test_frame_cb_steps_through_buffers_then_parks(self):
        b = Bus()
        c = b.cam
        c.mu.mem_map(0x30180000, 0x4000)
        cp = self.capt(b)
        cb = c.w(cp + 0x4C)
        self.assertTrue(b.block <= cb < b.block + b.info['file_len'], hex(cb))
        for off, v in ((0, 2), (4, 0), (8, 0x123), (0xC, 0xAAA), (0x10, 0xBBB)):
            c.put(cp + off, v)
        got = []
        for k in range(3):
            c.call(cb, r0=0, r1=0x45000000 + k * 0x1000)
            got.append(c.w(0x30182180))
        self.assertEqual(got, [0xAAA, 0xBBB, 0x123])
        self.assertEqual(c.w(cp + 4), 3)
        log = [struct.unpack('<2I', c.mu.mem_read(cp + 0x50 + 8 * k, 8)) for k in range(3)]
        self.assertEqual([d for _, d in log], [0x45000000, 0x45001000, 0x45002000])
        self.assertEqual([t for t, _ in log], sorted(t for t, _ in log))

    def test_frame_cb_log_is_bounded(self):
        b = Bus()
        c = b.cam
        c.mu.mem_map(0x30180000, 0x4000)
        cp = self.capt(b)
        c.put(cp, 1); c.put(cp + 4, BB.CAPT_LOG); c.put(cp + 8, 0x77)
        guard = c.w(cp + 0x50 + 8 * BB.CAPT_LOG)
        c.call(c.w(cp + 0x4C), r0=0, r1=0x45000000)
        self.assertEqual(c.w(0x30182180), 0x77)
        self.assertEqual(c.w(cp + 0x50 + 8 * BB.CAPT_LOG), guard)    # nothing past the log

    def test_refuses_a_changed_site(self):
        cam = V4.Camera(*V4.card(('IMXB.BIN', sup()[0])))
        cam.mu.mem_write(SITE, struct.pack('<I', 0xE1A00000))
        cam.boot()
        self.assertNotIn('IMXB.BIN', V4.blocks(cam))
        self.assertEqual(cam.w(SITE), 0xE1A00000)


class MutationTests(unittest.TestCase):
    def test_no_replay_is_caught(self):
        r = unittest.TextTestRunner(stream=open('/dev/null', 'w'))
        global sup
        keep = sup
        try:
            sup = lambda defines=(): keep(tuple(defines) + ('MUTANT_NO_REPLAY',))
            res = r.run(BusLogTests('test_on_logs_every_write_and_still_writes_the_bus'))
        finally:
            sup = keep
        self.assertFalse(res.wasSuccessful())

    def test_no_alternation_is_caught(self):
        global sup
        keep = sup
        try:
            sup = lambda defines=(): keep(tuple(defines) + ('MUTANT_NO_ALT',))
            with open('/dev/null', 'w') as null:
                res = unittest.TextTestRunner(stream=null).run(
                    BusLogTests('test_alternation_flips_per_frame_block'))
        finally:
            sup = keep
        self.assertFalse(res.wasSuccessful())

    def test_no_substitution_is_caught(self):
        global sup
        keep = sup
        try:
            sup = lambda defines=(): keep(tuple(defines) + ('MUTANT_NO_SUB',))
            with open('/dev/null', 'w') as null:
                res = unittest.TextTestRunner(stream=null).run(
                    BusLogTests('test_substitution_changes_only_listed_registers'))
        finally:
            sup = keep
        self.assertFalse(res.wasSuccessful())


if __name__ == '__main__':
    unittest.main()
