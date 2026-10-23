#!/usr/bin/env python3
"""IMXL under unicorn: the real loader v4 loads build.py's IMXL.BIN into the real
firmware image, then takes run through the firmware's own code as in
rec-core/writer/test_card.py (C063F220 set-up, C063F048 extents, the SD
driver's arena routines, C063F310 stop), with only C01EB790, C03A55D0,
C0644B68 and the TK-OS calls in Python.  The writer task is the real
wr_service, run whenever stock blocks on our flag and between frames.

What is new against ULWR is the sink:
  - sd       : unchanged ULWR behaviour (every byte on the disk where it belongs)
  - capture  : nothing reaches the device; the lent chunks hold records that
               rebuild exactly the disk ULWR would have written; every cookie
               once, in order, status 0
  - full     : a sink that runs out stores only whole records, writes nothing
               past its chunks, and still completes every frame
  - discard  : nothing stored, nothing written, every frame completed
  - frames given at the cached alias are read through the uncached one
  - lent memory outside the uncached alias is refused

    python3 -B -m unittest test_card
"""
import ctypes, pathlib, random, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / 'fpSup' / 'fp_usb_shell'
sys.path[:0] = [str(HERE), str(SHELL.parent / 'loader-v4'), str(SHELL / 'v3'), str(SHELL)]
import test_v4 as V4                                         # noqa: E402
import test_v3 as V3                                         # noqa: E402
import build as IB                                           # noqa: E402
import imxl_records as R                                     # noqa: E402
from unicorn import UC_PROT_ALL                              # noqa: E402
from unicorn.arm_const import *                              # noqa: E402,F403

VOL = 0xC37D50D4                       # SD: 0xC37D066C + 1 * 0x4A68
DEV_ID = 1
SS, SPC, HEAP_LBA = 512, 256, 0x8000
CLUSTER = SS * SPC
PAD = 0x4FF00000                       # stock's zero buffer (uncached)
DATA = 0x50000000                      # frame bytes (uncached alias)
DATA_SIZE = 0x4000000
CACHED = 0x80000000                    # DATA + this: the cached alias, holding STALE bytes
CAP = 0x48000000                       # memory lent to the sink (uncached alias)
CAP_SIZE = 0x2000000
GUARD = 0xA5
TBL, BOUNCE = 0x43818EC8, 0x4381AECC
DRV = 0xC3816E80
MAXDESC = 0xC2F2E750
STUBS = {'VOL_LOOKUP': 0xC0644B68, 'DEV_WRITE': 0xC01EB790, 'STOCK_CB': 0xC03A55D0,
         'FLG_CREATE': 0xC00169EC, 'FLG_SET': 0xC0016B9C, 'FLG_WAIT': 0xC0016C08,
         'REC_STATE': 0xC03A52D0, 'LOG_A': 0xC0019DC0, 'LOG_B': 0xC001A048}
THUMB_STUBS = {'VOL_LOOKUP', 'DEV_WRITE'}
SD = dict(acq=0xC065F021, add=0xC065F061, ckpt=0xC065EFE1, rb=0xC065F001, rel=0xC065F269)
SLOT = dict(cb=0x4834, acq=0x4838, add=0x483C, ckpt=0x4840, rb=0x4844, rel=0x4848)
DONE = V3.DONE
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
        UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_R12, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_CPSR]
_BUILDS = {}


class Cam(V4.Camera):
    """v4's camera (heap at both aliases) plus the frame/pad/ADMA/lent memory and
    the stubs above.  DATA's cached alias is a separate buffer full of 0xEE: a
    read through it instead of the uncached alias sees stale bytes."""

    def __init__(self, files, dirs, seed=0, fail_write=None):
        super().__init__(files, dirs)
        mu = self.mu
        mu.mem_map(0x43800000, 0x100000)
        mu.mem_map(PAD, 0x100000)
        mu.mem_map(DATA, DATA_SIZE)
        self._stale = ctypes.create_string_buffer(b'\xEE' * DATA_SIZE, DATA_SIZE)
        mu.mem_map_ptr(DATA + CACHED, DATA_SIZE, UC_PROT_ALL, self._stale)
        mu.mem_map(CAP, CAP_SIZE)
        mu.mem_write(CAP, bytes([GUARD]) * CAP_SIZE)
        for k, a in STUBS.items():
            self.by_addr[a] = k
            mu.mem_write(a, b'\x70\x47' if k in THUMB_STUBS else struct.pack('<I', 0xE12FFF1E))
        self.rnd = random.Random(seed)
        self.fail_write = fail_write
        self.disk, self.writes, self.cookies = {}, 0, []
        self.switch = self.on_cookie = None

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
            return self._ret(0)
        if name == 'FLG_WAIT':
            tmo = struct.unpack('<i', struct.pack('<I', self.w(self.r(UC_ARM_REG_SP))))[0]
            if tmo == -1:
                raise AssertionError('the writer task body ran inside the emulation')
            self.switch = [self.r(r) for r in REGS]          # stock blocks: run the writer
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
        data = bytearray()
        for i in range(self.w(DRV + 8)):
            w0, phys = struct.unpack('<II', self.mu.mem_read(TBL + 8 * i, 8))
            ln = (w0 >> 16) | (((w0 >> 6) & 0x3FF) << 16) or self.w(MAXDESC)
            data += self.mu.mem_read(phys + 0x40000000, ln)
        assert len(data) == n * SS
        k = self.writes; self.writes += 1
        if k == self.fail_write:
            return 0
        self.disk[(lo | hi << 32) * SS] = bytes(data)
        return 1

    def run(self, pc, r0=0, r1=0, thumb=True, lr=DONE):
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
        self.call(self.entry['wr_service'], r0=self.state_addr, thumb=True, sp=V3.STACK - 0x9004)


def build_sup(defines=()):
    key = tuple(defines)
    if key not in _BUILDS:
        _BUILDS[key] = IB.build(defines)
    return _BUILDS[key]


class Take:
    def __init__(self, seed=0, frames=120, fail_write=None, sizes=None, defines=(), cached_frames=False):
        self.sup, self.info = build_sup(defines)
        cam = self.cam = Cam(*V4.card(('IMXL.BIN', self.sup)), seed, fail_write)
        cam.boot()
        blocks = V4.blocks(cam)
        assert 'IMXL.BIN' in blocks, cam.loadlog()
        block = blocks['IMXL.BIN']
        cached = block + 0x80000000 if 0x40000000 <= block < 0x80000000 else block
        inner = cached + self.info['inner_at']
        cam.state_addr = cached + self.info['state_at']
        cam.entry = {k: inner + self.info['c_base'] + v for k, v in self.info['entries'].items()}
        self.block, self.cap_at = block, cam.state_addr + self.info['cap_off']
        self.rnd = random.Random(seed)
        self.frames, self.sizes = frames, sizes or [1_095_168 // 8, 60_000, 300_001, 2_048, 700_000]
        self.cached_frames = cached_frames
        self.pieces = {}; self.next_cl = 0x40; self.addr = DATA; self.expect = {}

    # ---- the sink, as the host tool sets it
    def cap(self):
        return R.parse_cap(bytes(self.cam.mu.mem_read(self.cap_at, R.CAP_BYTES)))

    def arm(self, mode, chunks=()):
        c = self.cam
        for o in range(R.O_TAIL, R.CAP_BYTES, 4): c.put(self.cap_at + o, 0)
        for i in range(R.MAX_CHUNK):
            a, n = chunks[i] if i < len(chunks) else (0, 0)
            c.put(self.cap_at + R.O_CHUNK + 8 * i, a); c.put(self.cap_at + R.O_CHUNK + 8 * i + 4, n)
        c.put(self.cap_at + 12, len(chunks))
        c.put(self.cap_at + 8, R.MODES[mode])

    def stream(self, chunks):
        return b''.join(bytes(self.cam.mu.mem_read(a, n)) for a, n in chunks)

    # ---- the take (rec-core/writer/test_card.py)
    def rd(self, off): return self.cam.w(VOL + off)
    def wr(self, off, v): self.cam.put(VOL + off, v)

    def mount(self):
        c = self.cam
        for a in range(VOL, VOL + 0x4A68, 4): c.put(a, 0)
        c.put(VOL + 0x0, 0xE); c.put(VOL + 0x1460, SS); c.put(VOL + 0x146C, SPC); c.put(VOL + 0x1458, HEAP_LBA)
        for k, a in SD.items(): c.put(VOL + SLOT[k], a)
        for o in range(0, 0x30, 4): c.put(DRV + o, 0)
        c.put(DRV + 4, TBL); c.put(DRV + 0x10, BOUNCE)
        c.put(MAXDESC, 0x10000)

    def start(self):
        p = V3.HEAP + 0x700000
        for i, v in enumerate((0x04000000, PAD, 0x40000, 0xC03A55D0)): self.cam.put(p + 4 * i, v)
        return self.cam.run(0xC063F220, r0=DEV_ID, r1=p)

    def call_slot(self, slot, *args):
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
        lst = V3.HEAP + 0x710000
        alias = CACHED if self.cached_frames else 0
        for i, (a, n) in enumerate(pieces): self.cam.put(lst + 8 * i, a + alias); self.cam.put(lst + 8 * i + 4, n)
        st = V3.HEAP + 0x720000
        for i, v in enumerate((VOL, lst, 0, 0, PAD, 0x40000, CLUSTER, cl, 0, size, 0, 0)):
            self.cam.put(st + 4 * i, v)
        r = self.cam.run(0xC063F048, r0=st)
        assert r == 0, f'C063F048 -> {r:#x}'
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

    def in_image(self, image, a, n):
        p = self.expect[a]
        for off, data in image.items():
            if off <= p and p + n <= off + len(data):
                return data[p - off:p - off + n] == bytes(self.cam.mu.mem_read(a, n))
        return False

    def run(self, writer_bias=0.5):
        c = self.cam
        self.mount()
        assert self.start() == 1
        for f in range(self.frames):
            self.frame(f)
            if self.rnd.random() < writer_bias: c.service()
        assert c.run(0xC063F310, r0=DEV_ID, r1=0) == 1
        return self


CHUNKS = [(CAP, 0x7FFFF3), (CAP + 0x900000, 0x500001), (CAP + 0x1000000, 0xFFFFFC)]   # odd sizes: records span
SMALL = [2_048, 60_000, 130_001]      # capture takes: unicorn copies every word through a code hook


class SinkTests(unittest.TestCase):
    def assert_completed(self, t):
        c = t.cam
        self.assertEqual([f for f, _ in c.cookies], list(range(1, t.frames + 1)))
        self.assertTrue(all(s == 0 for _, s in c.cookies))
        for k, a in SD.items():
            self.assertEqual(t.rd(SLOT[k]), a, f'{k} not stock after the stop')
        self.assertEqual(c.w(DRV), 0, 'driver table held after the take')

    def guards_intact(self, t, chunks):
        mem = bytes(t.cam.mu.mem_read(CAP, CAP_SIZE))
        inside = bytearray(CAP_SIZE)
        for a, n in chunks: inside[a - CAP:a - CAP + n] = b'\1' * n
        bad = [i for i in range(0, CAP_SIZE, 997) if not inside[i] and mem[i] != GUARD]
        self.assertEqual(bad[:4], [], 'the sink wrote outside the lent chunks')

    def test_loads_as_v4_and_restores_at_power_off(self):
        t = Take()
        c = t.cam
        for site in (0xC063F140, 0xC063F220):
            self.assertEqual(c.w(site), 0xF000F8DF)
            self.assertTrue(0xC5000000 <= c.w(site + 4) < 0xC5800000, hex(c.w(site + 4)))
        self.assertEqual(c.w(0xC03A549C), 0xE51FF004)
        cap = t.cap()
        self.assertEqual((cap['magic'], cap['version'], cap['mode']), (R.CAP_MAGIC, 1, 0))
        self.assertEqual(t.info['cap_bytes'], R.CAP_BYTES)
        c.power_off()
        for a, h in IB.SITES.items():
            self.assertEqual(bytes(c.mu.mem_read(a, 8)).hex(), h)

    def test_sd_mode_is_ulwr(self):
        for seed in range(2):
            t = Take(seed).run()
            self.assert_completed(t)
            for f, pieces in t.pieces.items():
                for a, n in pieces:
                    self.assertTrue(t.in_image(t.cam.disk, a, n), f'frame {f} not on disk')
            self.assertGreater(t.cam.writes, 3)
            self.assertEqual(t.cap()['n_rec'], 0)

    def test_capture_rebuilds_the_disk_and_writes_nothing(self):
        for seed in range(3):
            t = Take(seed, frames=80, sizes=SMALL); t.arm('capture', CHUNKS); t.run()
            self.assert_completed(t)
            self.assertEqual(t.cam.writes, 0, 'capture reached the card')
            cap = t.cap()
            recs = list(R.records(t.stream(CHUNKS), cap['used']))
            self.assertEqual(len(recs), cap['n_rec']); self.assertEqual(cap['n_full'], 0)
            self.assertEqual([r['seq'] for r in recs], sorted(r['seq'] for r in recs))
            self.assertEqual(sum(r['ncookie'] for r in recs) <= t.frames, True)
            img = R.disk_image(recs, HEAP_LBA, SPC)
            for f, pieces in t.pieces.items():
                for a, n in pieces:
                    self.assertTrue(t.in_image(img, a, n), f'seed {seed} frame {f} piece {a:#x} not captured')
            self.guards_intact(t, CHUNKS)

    def test_frames_at_the_cached_alias_are_read_uncached(self):
        t = Take(2, frames=30, sizes=SMALL, cached_frames=True); t.arm('capture', CHUNKS); t.run()
        recs = list(R.records(t.stream(CHUNKS), t.cap()['used']))
        img = R.disk_image(recs, HEAP_LBA, SPC)
        for f, pieces in t.pieces.items():
            for a, n in pieces:
                self.assertTrue(t.in_image(img, a, n), f'frame {f}: stale (cached) bytes captured')

    def test_full_sink_keeps_whole_records_and_the_take_going(self):
        small = [(CAP, 0x9FFFF1), (CAP + 0xC00000, 0x3FFFF)]
        t = Take(1, frames=120, sizes=SMALL); t.arm('capture', small); t.run()
        self.assert_completed(t)
        self.assertEqual(t.cam.writes, 0)
        cap = t.cap()
        self.assertGreater(cap['n_full'], 0)
        recs = list(R.records(t.stream(small), cap['used']))
        self.assertEqual(len(recs), cap['n_rec'])
        self.assertGreater(len(recs), 0)
        self.guards_intact(t, small)

    def test_discard_stores_and_writes_nothing(self):
        t = Take(3, frames=60); t.arm('discard', CHUNKS); t.run()
        self.assert_completed(t)
        cap = t.cap()
        self.assertEqual((t.cam.writes, cap['n_rec'], cap['used']), (0, 0, 0))
        self.assertGreater(cap['n_discard'], 0)
        self.guards_intact(t, [])

    def test_lent_memory_must_be_the_uncached_alias(self):
        bad = [(0xC5000000, 0x100000)]            # the heap's cached alias: code lives up there
        t = Take(0, frames=20); t.arm('capture', bad); t.run()
        self.assert_completed(t)
        cap = t.cap()
        self.assertEqual((cap['n_rec'], cap['used']), (0, 0))
        self.assertGreater(cap['n_full'], 0)


class MutationTests(unittest.TestCase):
    """Each mutant must make a SinkTests check fail."""
    def failing(self, define, test):
        global _BUILDS
        saved = build_sup
        try:
            globals()['build_sup'] = lambda defines=(): saved(tuple(defines) + (define,))
            with open('/dev/null', 'w') as null:
                r = unittest.TextTestRunner(stream=null).run(SinkTests(test))
            return not r.wasSuccessful()
        finally:
            globals()['build_sup'] = saved

    def test_always_sd_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_ALWAYS_SD', 'test_capture_rebuilds_the_disk_and_writes_nothing'))

    def test_no_uncache_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_NO_UNCACHE', 'test_frames_at_the_cached_alias_are_read_uncached'))

    def test_no_room_check_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_NO_ROOM', 'test_full_sink_keeps_whole_records_and_the_take_going'))


if __name__ == '__main__':
    unittest.main()
