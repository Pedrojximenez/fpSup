#!/usr/bin/env python3
"""ULWR under unicorn: the real loader v3 loads build/20ULWR.BIN into the real
firmware image; then a take runs through the FIRMWARE's own code wherever it
can -- C063F220 (set-up, our hook220), C063F048 (extents, our arena veneers),
the SD driver's acquire/add/checkpoint/rollback/release (C065F020..C065F268),
C063F310 (stop, our hook140 with LR 0xC063F34D) -- with only the device write
C01EB790, C03A55D0, C0644B68 and the TK-OS calls in Python.  C063F380's own
control flow (threshold, cookie list, "4A58 == 0") is played by Python, as in
test_wr.py, calling through the vol's pointers.

The writer task is the real wr_service, run whenever stock blocks on our event
flag (a context switch: the emulation stops, the writer runs, the stopped code
resumes) and between frames.

Checked: every byte lands on the "disk" where its file says, every cookie once
and in order and only after its bytes are on the disk, the vol is stock again
after the stop, and the loader's journal/power-off still hold.

    python3 -B -m unittest test_card
    ULWR_V4=1 python3 -B -m unittest test_card     # the same, under the loader v4 core
                                                   # (fpSup/loader-v4/ports.py's ULWR.BIN)
"""
import ctypes, json, os, pathlib, random, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path[:0] = [str(HERE), str(V3), str(V3.parent)]
import test_v3 as V                                          # noqa: E402
V4 = None
if os.environ.get('ULWR_V4'):
    sys.path.insert(0, str(ROOT / 'fpSup' / 'loader-v4'))
    import test_v4 as V4                                     # noqa: E402
    import build_v4 as B4                                    # noqa: E402
import build as RB                                           # noqa: E402
from unicorn import UC_PROT_ALL                              # noqa: E402
from unicorn.arm_const import *                              # noqa: E402,F403

VOL = 0xC37D50D4                       # SD: 0xC37D066C + 1 * 0x4A68
DEV_ID = 1
SS, SPC, HEAP_LBA = 512, 256, 0x8000
CLUSTER = SS * SPC
PAD = 0x4FF00000                       # stock's zero buffer (uncached, below 0xC0000000)
DATA = 0x50000000                      # frame bytes (uncached alias, phys 0x10000000)
TBL, BOUNCE = 0x43818EC8, 0x4381AECC
DRV = 0xC3816E80                       # SD arena driver state
MAXDESC = 0xC2F2E750
STUBS = {'VOL_LOOKUP': 0xC0644B68, 'DEV_WRITE': 0xC01EB790, 'STOCK_CB': 0xC03A55D0,
         'FLG_CREATE': 0xC00169EC, 'FLG_SET': 0xC0016B9C, 'FLG_WAIT': 0xC0016C08,
         'REC_STATE': 0xC03A52D0, 'LOG_A': 0xC0019DC0, 'LOG_B': 0xC001A048}
THUMB_STUBS = {'VOL_LOOKUP', 'DEV_WRITE'}
SD = dict(acq=0xC065F021, add=0xC065F061, ckpt=0xC065EFE1, rb=0xC065F001, rel=0xC065F269)
SLOT = dict(cb=0x4834, acq=0x4838, add=0x483C, ckpt=0x4840, rb=0x4844, rel=0x4848)
DONE = V.DONE


class Cam(V4.Camera if V4 else V.Camera):
    """test_v3's camera, plus: the heap also at its cached alias (+0x80000000,
    as the MMU maps it), the frame/pad/ADMA memory, and the stubs above."""

    def __init__(self, files, dirs, seed=0, fail_write=None):
        super().__init__(files, dirs)
        mu = self.mu
        mu.mem_unmap(V.HEAP, V.HEAP_SIZE)
        if V4:                                               # v4's camera maps both already
            mu.mem_unmap(V.HEAP + 0x80000000, V.HEAP_SIZE)
        self._heap = ctypes.create_string_buffer(V.HEAP_SIZE)
        mu.mem_map_ptr(V.HEAP, V.HEAP_SIZE, UC_PROT_ALL, self._heap)
        mu.mem_map_ptr(V.HEAP + 0x80000000, V.HEAP_SIZE, UC_PROT_ALL, self._heap)
        mu.mem_map(0x43800000, 0x100000)
        mu.mem_map(PAD, 0x100000)
        mu.mem_map(DATA, 0x4000000)
        for k, a in STUBS.items():
            self.by_addr[a] = k
            mu.mem_write(a, b'\x70\x47' if k in THUMB_STUBS else struct.pack('<I', 0xE12FFF1E))
        self.rnd = random.Random(seed)
        self.fail_write = fail_write
        self.disk = {}                 # byte offset on the medium -> bytes
        self.writes = 0
        self.cookies = []              # (frame, status)
        self.flag_bits = 0
        self.switch = None
        self.on_cookie = None

    def _hook(self, mu, addr, size, _):
        name = self.by_addr.get(addr)
        if name not in STUBS:
            return super()._hook(mu, addr, size, _)
        r0, r1, r2, r3 = (self.r(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        self.calls.append(name)
        if name == 'VOL_LOOKUP':
            return self._ret(VOL if r0 == DEV_ID else 0)
        if name == 'FLG_CREATE':
            return self._ret(5)
        if name == 'FLG_SET':
            self.flag_bits |= r1
            return self._ret(0)
        if name == 'FLG_WAIT':
            tmo = struct.unpack('<i', struct.pack('<I', self.w(self.r(UC_ARM_REG_SP))))[0]
            if tmo == -1:
                raise AssertionError('the writer task body ran inside the emulation')
            # a submitter blocks: switch to the writer, then resume after the call
            self.switch = [self.r(r) for r in REGS]
            mu.emu_stop()
            return
        if name == 'STOCK_CB':
            self.cookies.append((r0, r1))
            if self.on_cookie: self.on_cookie(r0, r1)
            return self._ret(0)
        if name in ('REC_STATE', 'LOG_A', 'LOG_B'):
            return self._ret(0)
        if name == 'DEV_WRITE':
            return self._ret(self.dev_write(r0, r1, r2, r3, self.w(self.r(UC_ARM_REG_SP))))

    def dev_write(self, dev, lo, hi, n, buf):
        assert dev == 0xE, dev
        assert buf == self.w(DRV + 4) and self.w(DRV) == 1, 'not the held arena'
        cnt = self.w(DRV + 8)
        data = bytearray()
        for i in range(cnt):
            w0, phys = struct.unpack('<II', self.mu.mem_read(TBL + 8 * i, 8))
            assert w0 & 0x3F == 0x21, f'descriptor attrs {w0:#x}'
            ln = (w0 >> 16) | (((w0 >> 6) & 0x3FF) << 16) or self.w(MAXDESC)   # 0 = a full descriptor
            data += self.mu.mem_read(phys + 0x40000000, ln)
        assert len(data) == n * SS, f'{len(data)} bytes in the table, {n} sectors asked'
        k = self.writes; self.writes += 1
        if k == self.fail_write:
            return 0
        self.disk[(lo | hi << 32) * SS] = bytes(data)
        return 1

    def run(self, pc, r0=0, r1=0, thumb=True, lr=DONE):
        """call(), with the writer run each time stock blocks on our flag."""
        out = self.call(pc, r0=r0, r1=r1, thumb=thumb, lr=lr)
        while self.switch:
            regs, self.switch = self.switch, None
            self.service()
            for r, v in zip(REGS, regs): self.mu.reg_write(r, v)
            self.mu.reg_write(UC_ARM_REG_R0, 0)
            self.mu.reg_write(UC_ARM_REG_PC, regs[REGS.index(UC_ARM_REG_LR)])
            try:
                self.mu.emu_start(regs[REGS.index(UC_ARM_REG_LR)], DONE, count=20_000_000)
            finally:
                if self.error: raise self.error
            out = (self.r(UC_ARM_REG_R0), self.r(UC_ARM_REG_SP))
        return out[0]

    def service(self):
        self.flag_bits = 0
        self.call(self.entry['wr_service'], r0=self.state_addr, thumb=True, sp=V.STACK - 0x9004)


REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
        UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_CPSR]


def build_sup(defines=()):
    sup, info = RB.build(defines)
    if not V4:
        return sup, info
    shift = V4.B.SL4_HEADER_LEN - 32                 # from_v3 moves the body, nothing else
    info = dict(info, inner_at=info['inner_at'] + shift, state_at=info['state_at'] + shift)
    return B4.from_v3(sup, name='Unlocked Writer'), info


NAME = 'ULWR.BIN' if V4 else '20ULWR.BIN'


class Take:
    def __init__(self, seed=0, frames=120, fail_write=None, sizes=None, defines=()):
        self.sup, self.info = build_sup(defines)
        files, dirs = (V4.card if V4 else V.card)((NAME, self.sup))
        cam = self.cam = Cam(files, dirs, seed, fail_write)
        cam.boot()
        log = ([('LOADED' if c == V4.CODES['LOADED'] else c, a, b, t) for c, a, b, t in cam.loadlog()]
               if V4 else cam.log())
        loaded = [e for e in log if e[0] == 'LOADED' and e[3] == NAME]
        assert loaded, log
        block = loaded[0][1]
        cached = block + 0x80000000 if 0x40000000 <= block < 0x80000000 else block
        inner = cached + self.info['inner_at']
        cam.state_addr = cached + self.info['state_at']
        cam.entry = {k: inner + self.info['c_base'] + v for k, v in self.info['entries'].items()}
        self.inner, self.block = inner, block
        self.rnd = random.Random(seed)
        self.frames, self.sizes = frames, sizes or [1_095_168 // 8, 60_000, 300_001, 2_048, 700_000]
        self.pieces = {}; self.next_cl = 0x40; self.addr = DATA; self.expect = {}

    def rd(self, off): return self.cam.w(VOL + off)
    def wr(self, off, v): self.cam.put(VOL + off, v)

    def mount(self):
        c = self.cam
        for a in range(VOL, VOL + 0x4A68, 4): c.put(a, 0)
        c.put(VOL + 0x0, 0xE); c.put(VOL + 0x1460, SS); c.put(VOL + 0x146C, SPC); c.put(VOL + 0x1458, HEAP_LBA)
        for k, a in SD.items(): c.put(VOL + SLOT[k], a)
        for o in range(0, 0x30, 4): c.put(DRV + o, 0)
        c.put(DRV + 4, TBL); c.put(DRV + 0x10, BOUNCE)   # table, unaligned-head bounce slots
        c.put(MAXDESC, 0x10000)

    def start(self):
        p = V.HEAP + 0x700000
        for i, v in enumerate((0x04000000, PAD, 0x40000, 0xC03A55D0)): self.cam.put(p + 4 * i, v)
        return self.cam.run(0xC063F220, r0=DEV_ID, r1=p)

    def call_slot(self, slot, *args):
        """C063F380 calling through the vol (blx from Thumb)."""
        a = self.rd(SLOT[slot])
        return self.cam.run(a & ~1, *args, thumb=bool(a & 1), lr=DONE)

    def send(self, lr=DONE):
        self.cam.run(0xC063F140, r0=VOL, lr=lr)

    def extent(self, f, pieces):
        size = sum(n for _, n in pieces); ncl = -(-size // CLUSTER)
        cl = self.next_cl + (self.rnd.randint(1, 3) if self.rnd.random() < 0.05 else 0)
        self.next_cl = cl + ncl
        p = ((cl - 2) * SPC + HEAP_LBA) * SS
        for a, n in pieces: self.expect[a] = p; p += n
        if self.rd(0x4A58) and cl != self.rd(0x4A54) + self.rd(0x4A58) // CLUSTER:
            self.send()
        if not self.rd(0x484C):
            raise AssertionError('the take degraded to direct writes')
        lst = V.HEAP + 0x710000
        for i, (a, n) in enumerate(pieces): self.cam.put(lst + 8 * i, a); self.cam.put(lst + 8 * i + 4, n)
        st = V.HEAP + 0x720000                      # C063F048's frame, &local_50
        for i, v in enumerate((VOL, lst, 0, 0, PAD, 0x40000, CLUSTER, cl, 0, size, 0, 0)):
            self.cam.put(st + 4 * i, v)
        r = self.cam.run(0xC063F048, r0=st)
        assert r == 0, f'C063F048 -> {r:#x}'
        assert self.cam.w(st + 0x2C) == ncl * CLUSTER
        if not self.rd(0x4A58): self.wr(0x4A54, cl)
        self.wr(0x4A58, self.rd(0x4A58) + ncl * CLUSTER)
        if self.rd(0x4A58) >= self.rd(0x4828): self.send()

    def frame(self, f):
        rnd = self.rnd
        size = rnd.choice(self.sizes)
        pieces, left = [], size
        while left:
            n = min(left, rnd.choice([3, 4096, 70_001, 1 << 20]))
            a = self.addr + rnd.choice([0, 0, 1, 2])
            self.cam.mu.mem_write(a, rnd.randbytes(n))
            self.addr = (a + n + 0x40) & ~0x3
            pieces.append((a, n))
            left -= n
        self.pieces[f] = pieces
        cut = rnd.randint(1, len(pieces)) if len(pieces) > 1 and rnd.random() < 0.2 else len(pieces)
        for part in (pieces[:cut], pieces[cut:]):
            if part: self.extent(f, part)
        if self.rd(0x4850) == 0x80: self.send()
        if self.rd(0x4A58) == 0:
            self.call_slot('cb', f + 1, 0)
        else:
            n = self.rd(0x4850); self.wr(0x4854 + 4 * n, f + 1); self.wr(0x4850, n + 1)

    def on_disk(self, a, n):
        p = self.expect[a]
        for off, data in self.cam.disk.items():
            if off <= p and p + n <= off + len(data):
                return data[p - off:p - off + n] == bytes(self.cam.mu.mem_read(a, n))
        return False

    def run(self, writer_bias=0.5, stop_discard=0):
        c = self.cam
        self.mount()
        c.on_cookie = self.check_cookie
        assert self.start() == 1
        for f in range(self.frames):
            self.frame(f)
            if self.rnd.random() < writer_bias: c.service()
        assert c.run(0xC063F310, r0=DEV_ID, r1=stop_discard) == 1
        self.stopped = True
        return self

    MGR, NODE = V.HEAP + 0x730000, V.HEAP + 0x740000

    def after_write(self, written, aggregate=1, state=0xC):
        """Stock C03A5348 from C03A549C (our hook) to its return: fp = mgr, r4 = the
        frame's node, r6:r7 = what C069ADE0 wrote.  Returns the C03A55D0 calls."""
        c = self.cam
        c.put(self.MGR + 0xC, 0x0101 if aggregate else 0x0001)     # +0xC records, +0xD aggregation
        c.put(self.NODE + 0x1104, state); c.put(self.NODE + 0x10FC, 0x4E)
        sp = V.STACK - 0x14000
        for i in range(8): c.put(sp + 0xB4 + 4 * i, 0)
        c.put(sp + 0xB4 + 28, DONE)                               # pop {r4-r8, sb, fp, pc}
        for reg, v in ((UC_ARM_REG_R11, self.MGR), (UC_ARM_REG_R4, self.NODE), (UC_ARM_REG_R5, written),
                       (UC_ARM_REG_R6, written), (UC_ARM_REG_R7, 0)):
            c.mu.reg_write(reg, v)
        before = len(c.cookies)
        c.on_cookie = None
        c.call(0xC03A549C, sp=sp, thumb=False)
        return c.cookies[before:]

    def check_cookie(self, frame, status):
        if status == 0 and not getattr(self, 'stopped', False) and self.cam.fail_write is None:
            for a, n in self.pieces[frame - 1]:
                assert self.on_disk(a, n), f'frame {frame} handed back before its bytes were written'


class CardTests(unittest.TestCase):
    def test_loads_hooks_all_sites_and_restores_at_power_off(self):
        t = Take()
        c = t.cam
        for site in (0xC063F140, 0xC063F220):
            self.assertEqual(c.w(site), 0xF000F8DF)          # ldr.w pc, [pc, #0]
            self.assertTrue(0xC5000000 <= c.w(site + 4) < 0xC5800000, hex(c.w(site + 4)))
        self.assertEqual(c.w(0xC03A549C), 0xE51FF004)       # ldr pc, [pc, #-4]
        self.assertTrue(0xC5000000 <= c.w(0xC03A54A0) < 0xC5800000)
        for a, h in RB.SITES.items():
            self.assertIn((a, 8, bytes.fromhex(h)), c.journal())
        self.assertEqual(len(c.tasks), 1)
        c.power_off()
        for a, h in RB.SITES.items():
            self.assertEqual(bytes(c.mu.mem_read(a, 8)).hex(), h)

    def test_take_through_firmware_code(self):
        for seed in range(4):
            t = Take(seed).run()
            c = t.cam
            self.assertEqual([f for f, _ in c.cookies], list(range(1, t.frames + 1)))
            self.assertTrue(all(s == 0 for _, s in c.cookies))
            for f, pieces in t.pieces.items():
                for a, n in pieces:
                    self.assertTrue(t.on_disk(a, n), f'frame {f} piece {a:#x} not on disk')
            for k, a in SD.items():
                self.assertEqual(t.rd(SLOT[k]), a, f'{k} not stock after the stop')
            self.assertEqual(t.rd(0x484C), 0); self.assertEqual(t.rd(0x4828), 0)
            self.assertEqual(c.w(DRV), 0, 'driver table held after the take')
            self.assertGreater(c.writes, 3)

    def test_threshold_is_8_mib(self):
        t = Take(); t.mount(); t.start()
        self.assertEqual(t.rd(0x4828), 8 << 20)
        self.assertTrue(0xC5000000 <= t.rd(0x4838) < 0xC5800000)


    def test_device_failure_reaches_the_frames(self):
        t = Take(1, fail_write=2).run()
        bad = [f for f, s in t.cam.cookies if s]
        self.assertTrue(bad)
        self.assertEqual([f for f, _ in t.cam.cookies], list(range(1, t.frames + 1)))


    def test_frame_written_after_the_stop_is_completed_by_stock(self):
        """10-15 OG3K freeze, through stock's own C03A549C..C03A55CC."""
        t = Take(0, frames=30)
        n0 = t.after_write(0x123400)                        # not installed yet: nothing ended
        self.assertEqual(n0, [])
        t.run()
        self.assertEqual(t.after_write(0x8C7400), [(t.NODE, 0)])
        self.assertEqual(t.after_write(0), [(t.NODE, 0xFFFFFFFF)])      # its write failed
        self.assertEqual(t.after_write(0x8C7400, state=0xD), [])        # completed by the drain
        self.assertEqual(t.after_write(0x8C7400, aggregate=0), [(t.NODE, 0)])   # stock's own

    def test_guard_quiet_while_the_take_runs_and_after_a_new_start(self):
        t = Take(1, frames=20)
        t.mount(); t.cam.on_cookie = t.check_cookie
        self.assertEqual(t.start(), 1)
        for f in range(20): t.frame(f)
        self.assertEqual(t.after_write(0x8C7400), [])       # mid-take: the vol completes it
        t.cam.on_cookie = t.check_cookie
        self.assertEqual(t.cam.run(0xC063F310, r0=DEV_ID, r1=0), 1)
        self.assertEqual(t.after_write(0x8C7400), [(t.NODE, 0)])
        self.assertEqual(t.start(), 1)                      # the next take
        self.assertEqual(t.after_write(0x8C7400), [])


class MutationTests(unittest.TestCase):
    def test_no_late_frame_guard_is_caught(self):
        t = Take(0, frames=10, defines=['WR_MUTANT_NO_LATE']).run()
        self.assertEqual(t.after_write(0x8C7400), [], 'the mutant should leave the frame hanging')

    def test_stop_without_drain_is_caught(self):
        with self.assertRaises(AssertionError):
            t = Take(0, defines=['WR_MUTANT_NO_DRAIN']).run(writer_bias=0.0)
            self.assertEqual([f for f, _ in t.cam.cookies], list(range(1, t.frames + 1)))

    def test_late_cookie_called_directly_is_caught(self):
        with self.assertRaises(AssertionError):
            for seed in range(4):
                Take(seed, defines=['BQ_MUTANT_LATE_DIRECT']).run(writer_bias=0.1)


if __name__ == '__main__':
    unittest.main()
