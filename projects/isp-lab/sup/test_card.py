#!/usr/bin/env python3
"""ISPL under unicorn (fork of projects/imx410-lab/sup/test_card.py, sha256
2a7b7dfa...): IMXL's tests unchanged in substance, plus the keep policy, the
block log and the control task (KeepTests, LogTests, ControlTests).

IMXL under unicorn: the real loader v4 loads build.py's IMXL.BIN into the real
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
import ispl_records as R                                     # noqa: E402
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
         'REC_STATE': 0xC03A52D0, 'LOG_A': 0xC0019DC0, 'LOG_B': 0xC001A048,
         'SHELL_EXEC': 0xC03D9C20, 'PUSH': 0x438F0000}     # PUSH: the engine stand-in (another sup's)
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
        mu.mem_map(0x30180000, 0x10000)                       # display DMA channel registers
        mu.mem_write(CAP, bytes([GUARD]) * CAP_SIZE)
        for k, a in STUBS.items():
            self.by_addr[a] = k
            mu.mem_write(a, b'\x70\x47' if k in THUMB_STUBS else struct.pack('<I', 0xE12FFF1E))
        self.rnd = random.Random(seed)
        self.fail_write = fail_write
        self.disk, self.writes, self.cookies, self.shell = {}, 0, [], []
        self.switch = self.on_cookie = self.on_shell = None
        self.pushes, self.push_ret = [], 0

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
        if name == 'SHELL_EXEC':
            assert r0 == 0xC3756904, 'not the console context'
            line = self.cstr(r1)
            self.shell.append((line, self.now))
            if self.on_shell: self.on_shell(line)
            return self._ret(0)
        if name == 'PUSH':
            f = struct.unpack('<19I', self.mu.mem_read(r0, 76))
            self.pushes.append(dict(zip(('mode', 'source', 'frame_no', 'w', 'h', 'fmt', 'stride', 'flags',
                                         'aux0', 'aux1', 'nseg'), f[:11]), segs=list(zip(f[11::2], f[12::2]))))
            return self._ret(self.push_ret)
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


def build_sup(defines=(), ctl_only=False):
    key = (tuple(defines), ctl_only)
    if key not in _BUILDS:
        _BUILDS[key] = IB.build(defines, ctl_only=ctl_only)
    return _BUILDS[key]


class Take:
    def __init__(self, seed=0, frames=120, fail_write=None, sizes=None, defines=(), cached_frames=False,
                 ctl_only=False):
        self.sup, self.info = build_sup(defines, ctl_only) if ctl_only else build_sup(defines)
        fname = 'ISPC.BIN' if ctl_only else 'ISPL.BIN'
        cam = self.cam = Cam(*V4.card((fname, self.sup)), seed, fail_write)
        cam.boot()
        blocks = V4.blocks(cam)
        assert fname in blocks, cam.loadlog()
        block = blocks[fname]
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

    def arm(self, mode, chunks=(), keep_first=1 << 30, every_us=0, log=(0, 0)):
        c = self.cam
        for o in range(R.O_HOST, R.CAP_BYTES, 4): c.put(self.cap_at + o, 0)
        c.put(self.cap_at + R.OFF['keep_first'], keep_first)
        c.put(self.cap_at + R.OFF['every_us'], every_us)
        c.put(self.cap_at + R.OFF['log_addr'], log[0]); c.put(self.cap_at + R.OFF['log_max'], log[1])
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
        self.assertEqual((cap['magic'], cap['version'], cap['mode']), (R.CAP_MAGIC, R.CAP_VERSION, 0))
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
        # big enough for every record: refused for its address, not its size
        # (IMXL's 1 MiB chunk was refused only because nothing fit in it)
        bad = [(0xC5000000, 0x10000000)]          # the heap's cached alias: code lives up there
        t = Take(0, frames=20); t.arm('capture', bad); t.run()
        self.assert_completed(t)
        cap = t.cap()
        self.assertEqual((cap['n_rec'], cap['used']), (0, 0))
        self.assertGreater(cap['n_full'], 0)


LOG_AT = CAP + 0x1F00000                # inside CAP, past every CHUNKS entry


class KeepTests(unittest.TestCase):
    def kept(self, t, chunks=CHUNKS):
        cap = t.cap()
        return cap, list(R.records(t.stream(chunks), cap['used']))

    def test_first_k_then_nothing(self):
        t = Take(4, frames=80, sizes=SMALL); t.arm('capture', CHUNKS, keep_first=2, every_us=0); t.run()
        SinkTests.assert_completed(self, t)
        cap, recs = self.kept(t)
        self.assertEqual(len(recs), 2)
        self.assertGreater(cap['n_skip'], 0)
        self.assertEqual(t.cam.writes, 0, 'a skipped block reached the card')
        # the kept ones are the first two the writer took
        self.assertEqual([r['seq'] for r in recs], sorted(r['seq'] for r in recs)[:2])

    def test_every_interval(self):
        t = Take(5, frames=80, sizes=SMALL); t.arm('capture', CHUNKS, keep_first=1, every_us=5_000); t.run()
        # (the stub clock moves 1 ms per tick call, a few calls per block)
        SinkTests.assert_completed(self, t)
        cap, recs = self.kept(t)
        self.assertGreater(cap['n_skip'], 0)
        self.assertGreater(len(recs), 1)
        gaps = [b['t_us'] - a['t_us'] for a, b in zip(recs, recs[1:])]
        self.assertTrue(all(g >= 5_000 for g in gaps), gaps)

    def test_full_sink_still_skips(self):
        # a full sink must not degrade to "keep everything": the copy never runs again
        small = [(CAP, 0x9FFFF1)]
        t = Take(1, frames=120, sizes=SMALL); t.arm('capture', small, keep_first=3, every_us=0); t.run()
        cap = t.cap()
        self.assertLessEqual(cap['n_rec'] + cap['n_full'], 3)
        self.assertGreater(cap['n_skip'], 0)


class LogTests(unittest.TestCase):
    def test_a_line_per_block(self):
        t = Take(6, frames=60, sizes=SMALL); t.arm('capture', CHUNKS, keep_first=2, log=(LOG_AT, 4096)); t.run()
        cap = t.cap()
        lines = R.log_lines(bytes(t.cam.mu.mem_read(LOG_AT, 16 * cap['log_n'])), cap['log_n'])
        self.assertEqual(cap['log_n'], cap['n_rec'] + cap['n_skip'] + cap['n_full'])
        self.assertEqual([l['seq'] for l in lines], sorted(l['seq'] for l in lines))
        self.assertTrue(all(l['bytes'] > 0 and l['ncookie'] >= 0 for l in lines))
        self.assertEqual([l['t_us'] for l in lines], sorted(l['t_us'] for l in lines))

    def test_log_is_bounded(self):
        t = Take(6, frames=60); t.arm('discard', CHUNKS, log=(LOG_AT, 1)); t.run()
        self.assertEqual(t.cap()['log_n'], 1)
        self.assertEqual(set(bytes(t.cam.mu.mem_read(LOG_AT + 16, 4096))), {GUARD}, 'log ran past log_max')

    def test_log_refuses_the_cached_alias(self):
        t = Take(6, frames=20); t.arm('discard', CHUNKS, log=(0xC5000000, 64)); t.run()
        self.assertEqual(t.cap()['log_n'], 0)


RECSTATE = 0xC3757F30
START = ['recstate ena', 'recstate init', 'key MOVON', 'recstate movrecstwai']
STOP = ['key MOVON', 'recstate movsavewai']


class ControlTests(unittest.TestCase):
    def setup(self, start_ms=100, rec_ms=1000, starts=True, saves_on=2, ctl_only=False):
        """starts: the first MOVON sets recstate +6.  saves_on: the n-th MOVON
        sets +7 (None: never)."""
        t = Take(0, frames=1, ctl_only=ctl_only)
        t.arm('discard')
        c = t.cam
        c.mu.mem_write(RECSTATE, bytes(8))
        presses = [0]

        def on_shell(line):
            if line == 'recstate init':
                c.mu.mem_write(RECSTATE + 5, bytes(3))
            if line == 'key MOVON':
                presses[0] += 1
                if presses[0] == 1 and starts:
                    c.mu.mem_write(RECSTATE + 6, b'\1')
                if presses[0] == saves_on:
                    c.mu.mem_write(RECSTATE + 7, b'\1')
        c.on_shell = on_shell
        c.put(t.cap_at + R.OFF['start_ms'], start_ms); c.put(t.cap_at + R.OFF['rec_ms'], rec_ms)
        c.put(t.cap_at + R.OFF['ctl'], R.CTL['armed'])          # last, as the host does
        return t

    def step(self, t, now):
        t.cam.now = now
        t.cam.call(t.cam.entry['ix_ctl_step'], r0=t.cam.state_addr, thumb=True, sp=V3.STACK - 0x9004)
        return t.cap()

    def lines(self, t):
        return [l for l, _ in t.cam.shell]

    def test_the_firmware_script_on_time(self):
        t = self.setup(start_ms=100, rec_ms=1000)
        base = 5_000_000
        self.assertEqual(self.step(t, base)['ctl'], R.CTL['armed'])        # t_arm stamped
        self.assertEqual(self.step(t, base + 50_000)['ctl'], R.CTL['armed'])
        self.assertEqual(t.cam.shell, [])
        cap = self.step(t, base + 120_000)
        self.assertEqual(cap['ctl'], R.CTL['rec'])
        self.assertEqual(self.lines(t), START)
        self.assertNotIn('key MOVOFF', self.lines(t))                 # the firmware's script never sends it
        self.assertEqual(self.step(t, base + 700_000)['ctl'], R.CTL['rec'])
        cap = self.step(t, base + 1_200_000)
        self.assertEqual(cap['ctl'], R.CTL['done'])
        self.assertEqual(self.lines(t), START + STOP + ['recstate disa'])
        self.assertEqual((cap['n_press'], cap['rs_started'], cap['rs_saved']), (2, 1, 1))
        self.assertGreaterEqual(cap['t_stop'] - cap['t_rec'], 1_000_000)
        self.step(t, base + 9_000_000)
        self.assertEqual(len(t.cam.shell), 7, 'ran again after done')

    def test_no_start_no_second_press(self):
        t = self.setup(starts=False, saves_on=None)
        self.step(t, 1_000_000); cap = self.step(t, 2_000_000)
        self.assertEqual(cap['ctl'], R.CTL['fail_start'])
        self.assertEqual(self.lines(t), START + ['recstate disa'])
        for now in (5_000_000, 60_000_000):
            self.step(t, now)
        self.assertEqual(self.lines(t).count('key MOVON'), 1, 'pressed REC on a camera that never started')

    def test_stop_is_retried(self):
        t = self.setup(saves_on=3)
        self.step(t, 1_000_000); self.step(t, 2_000_000); cap = self.step(t, 9_000_000)
        self.assertEqual(cap['ctl'], R.CTL['done'])
        self.assertEqual(self.lines(t), START + STOP * 2 + ['recstate disa'])

    def test_stop_gives_up_after_three(self):
        t = self.setup(saves_on=None)
        self.step(t, 1_000_000); self.step(t, 2_000_000); cap = self.step(t, 9_000_000)
        self.assertEqual(cap['ctl'], R.CTL['fail_stop'])
        self.assertEqual(self.lines(t), START + STOP * 3 + ['recstate disa'])
        self.assertEqual(cap['ctl_line'], 6)

    def test_cancel_before_start(self):
        t = self.setup(start_ms=100)
        self.step(t, 1_000_000)
        t.cam.put(t.cap_at + R.OFF['ctl'], R.CTL['idle'])
        self.step(t, 9_000_000)
        self.assertEqual(t.cam.shell, [])

    def test_idle_presses_nothing(self):
        t = Take(0, frames=1)
        for now in (1_000_000, 50_000_000):
            self.step(t, now)
        self.assertEqual(t.cam.shell, [])

    def test_tick_wraps(self):
        t = self.setup(start_ms=100, rec_ms=1000)
        base = 0xFFFFFFFF - 50_000
        self.step(t, base)
        self.step(t, (base + 150_000) & 0xFFFFFFFF)
        self.assertEqual(t.cap()['ctl'], R.CTL['rec'])


LV_DESC, LV_CHSEL = 0xC30255B4, 0xC31DF8D8
LV_REG = {0: 0x301832E8, 3: 0x301835E8}                # [LV_CHSEL] -> channel 2 / 5's slot register
LV_W, LV_H, LV_N = 1620, 911, 4
LV_SLOT = [0x4B000000 + i * 0x300000 for i in range(LV_N)]


class LvTests(unittest.TestCase):
    """The LV sampler (PUSH_CALLERS §1): the last slot the display DMA finished
    (register byte1), every lv_every_us, handed to the engine in mode 0; nothing waits."""
    def setup(self, every_us=250_000, lag=0, chsel=0, reg=0x20102, n=LV_N, w=LV_W, push=True, lv_max=0):
        t = Take(0, frames=1)
        t.arm('discard')
        c = t.cam
        desc = [0] * 32
        desc[3], desc[4], desc[8] = w, LV_H, n
        for i, a in enumerate(LV_SLOT):
            desc[9 + i] = (a - 0x40000000) // 4
        c.mu.mem_write(LV_DESC, struct.pack('<32I', *desc))
        c.put(LV_CHSEL, chsel)
        c.put(LV_REG.get(chsel, 0x301837E8), reg)
        for k, v in (('lv_every_us', every_us), ('lv_lag', lag), ('lv_max', lv_max),
                     ('lv_push', STUBS['PUSH'] if push else 0)):
            c.put(t.cap_at + R.OFF[k], v)
        return t

    step = ControlTests.step

    def test_pushes_the_slot_before_the_current_one(self):
        t = self.setup(reg=0x20102)              # writing 2, finished 1, on screen 2 (measured 10-24)
        cap = self.step(t, 1_000_000)
        self.assertEqual(len(t.cam.pushes), 1)
        p = t.cam.pushes[0]
        self.assertEqual((p['mode'], p['source'], p['fmt'], p['w'], p['h'], p['stride'], p['nseg']),
                         (0, 1, 1, LV_W, LV_H, 2 * LV_W, 1))
        self.assertEqual(p['segs'][0], (LV_SLOT[1], 2 * LV_W * LV_H))
        self.assertEqual((p['frame_no'], p['aux0'], p['aux1'], p['flags']), (1, 0x20102, 2, 0))
        self.assertEqual((cap['lv_n_sent'], cap['lv_last_addr']), (1, LV_SLOT[1]))

    def test_slot_zero_wraps_to_the_last(self):
        t = self.setup(reg=0x10000, lag=2)        # finished 0, one older = 3
        self.step(t, 1_000_000)
        self.assertEqual(t.cam.pushes[0]['segs'][0][0], LV_SLOT[3])

    def test_hdmi_channel_and_its_wider_mask(self):
        t = self.setup(chsel=3, reg=0x20101)               # channel 5's register: finished 1
        self.step(t, 1_000_000)
        p = t.cam.pushes[0]
        self.assertEqual((p['aux1'], p['segs'][0][0]), (5, LV_SLOT[1]))

    def test_lag(self):
        t = self.setup(reg=0x30203, lag=2)        # finished 2, one older = 1
        self.step(t, 1_000_000)
        self.assertEqual(t.cam.pushes[0]['segs'][0][0], LV_SLOT[1])

    def test_interval_and_the_cap(self):
        t = self.setup(every_us=250_000, lv_max=3)
        for now in range(1_000_000, 3_000_000, 20_000):     # the task's 20 ms steps for 2 s
            self.step(t, now)
        self.assertEqual(len(t.cam.pushes), 3)
        t = self.setup(every_us=250_000)
        for now in range(1_000_000, 3_000_000, 20_000):
            self.step(t, now)
        self.assertEqual(len(t.cam.pushes), 8)

    def test_busy_engine_is_counted_not_waited(self):
        t = self.setup(every_us=20_000)
        t.cam.push_ret = 1
        for now in (1_000_000, 1_020_000):
            cap = self.step(t, now)
        self.assertEqual((cap['lv_n_sent'], cap['lv_n_skip'], cap['lv_n_err']), (0, 2, 0))
        t.cam.push_ret = 7
        cap = self.step(t, 1_040_000)
        self.assertEqual(cap['lv_n_err'], 1)

    def test_off_without_an_engine(self):
        t = self.setup(push=False)
        for now in (1_000_000, 5_000_000):
            self.step(t, now)
        self.assertEqual(t.cam.pushes, [])

    def test_bad_descriptor_pushes_nothing(self):
        for kw in (dict(n=0), dict(n=9), dict(w=0), dict(w=8000), dict(lag=5), dict(reg=0x50400)):
            t = self.setup(**kw)
            cap = self.step(t, 1_000_000)
            self.assertEqual(t.cam.pushes, [], kw)
            self.assertEqual(cap['lv_n_bad'], 1, kw)

    def test_recording_flag(self):
        t = self.setup()
        t.cam.put(t.cap_at + R.OFF['rec_ms'], 3_000_000)   # 50 min; x1000 still fits u32
        t.cam.put(t.cap_at + R.OFF['t_rec'], 1)
        t.cam.put(t.cap_at + R.OFF['ctl'], R.CTL['rec'])
        self.step(t, 1_000_000)
        self.assertEqual(t.cam.pushes[0]['flags'] & 1, 1)
        self.assertEqual(t.cam.shell, [], 'the sampler pressed something')


class CtlOnlyTests(unittest.TestCase):
    """ISPC.BIN: the control task alone (RESEARCH_PLAN §7 step 1)."""
    def test_loads_without_touching_the_writer(self):
        t = Take(0, frames=1, ctl_only=True)
        c = t.cam
        for a, h in IB.SITES.items():
            self.assertEqual(bytes(c.mu.mem_read(a, 8)).hex(), h, f'0x{a:08X} hooked by the control-only build')
        self.assertEqual(t.cap()['magic'], R.CAP_MAGIC)
        c.power_off()

    def test_runs_the_firmware_script(self):
        t = ControlTests.setup(self, ctl_only=True)
        ControlTests.step(self, t, 1_000_000); ControlTests.step(self, t, 2_000_000)
        cap = ControlTests.step(self, t, 9_000_000)
        self.assertEqual(cap['ctl'], R.CTL['done'])
        self.assertEqual([l for l, _ in t.cam.shell], START + STOP + ['recstate disa'])


class MutationTests(unittest.TestCase):
    """Each mutant must make a SinkTests check fail."""
    def failing(self, define, test, cls=None):
        global _BUILDS
        saved = build_sup
        try:
            globals()['build_sup'] = lambda defines=(): saved(tuple(defines) + (define,))
            with open('/dev/null', 'w') as null:
                r = unittest.TextTestRunner(stream=null).run((cls or SinkTests)(test))
            return not r.wasSuccessful()
        finally:
            globals()['build_sup'] = saved

    def test_always_sd_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_ALWAYS_SD', 'test_capture_rebuilds_the_disk_and_writes_nothing'))

    def test_no_uncache_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_NO_UNCACHE', 'test_frames_at_the_cached_alias_are_read_uncached'))

    def test_no_room_check_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_NO_ROOM', 'test_full_sink_keeps_whole_records_and_the_take_going'))

    def test_address_wrap_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_WRAP', 'test_lent_memory_must_be_the_uncached_alias'))

    def test_keep_all_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_KEEP_ALL', 'test_first_k_then_nothing', KeepTests))

    def test_no_stop_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_NO_STOP', 'test_the_firmware_script_on_time', ControlTests))

    def test_no_start_check_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_NO_START_CHECK', 'test_no_start_no_second_press', ControlTests))

    def test_lv_current_slot_is_caught(self):
        self.assertTrue(self.failing('IX_MUTANT_LV_CURRENT', 'test_pushes_the_slot_before_the_current_one', LvTests))


if __name__ == '__main__':
    unittest.main()
