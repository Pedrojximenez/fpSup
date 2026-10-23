#!/usr/bin/env python3
"""wr (the native adapter) against a model of the stock file layer that calls
through the vol's own pointers, as C063F048/C063F380/C063F140/C063F310 do
(WRITER_LOCK_SCOPE §1-§6), and a fake driver + device.

What must hold, installed or not:
  every frame's cookie exactly once, in order, only after its bytes reached
  the device at the right sector; a failed device write reaches exactly the
  frames of that batch; after the stop the vol holds stock pointers and 484C=0.

    python3 -B -m unittest test_wr
"""
import ctypes as C, pathlib, random, subprocess, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
VOL = 0x10000000
MISC = 0x2000
U = C.c_uint32
SS, SPC, HEAP = 512, 256, 0x8000          # 128 KiB clusters
CLUSTER = SS * SPC
SD_ACQ, SSD_ACQ = 0xC065F021, 0xC06702B9
STOCK = dict(cb=0xC03A55D0, acq=SD_ACQ, add=0xC065F061, ckpt=0xC065EFE1, rb=0xC065F001, rel=0xC065F269)
OURS = dict(cb=0xAAA00001, acq=0xAAA00011, add=0xAAA00021, ckpt=0xAAA00031, rb=0xAAA00041, rel=0xAAA00051)
SLOTS = dict(cb=0x4834, acq=0x4838, add=0x483C, ckpt=0x4840, rb=0x4844, rel=0x4848)
ARENA = 0x43818EC8
PAD = 0x4FF00000
LR_STOP, LR_OTHER = 0xC063F34D, 0xC063F6F7
N = ['install', 'refuse', 'send', 'stock_send', 'chunk', 'acq_retry', 'dev_err', 'wait_free',
     'drain', 'drain_timeout', 'late', 'late_direct', 'late_full', 'mismatch', 'last_status', 'late_frame']
MGR = 0x4000                              # C03A5348's fp: +0xD = aggregation (byte)
NODE0, NODE_STRIDE = 0x4010, 0x10         # frame f's node; its state word is node+0x1104
HANDED, DONE_ST = 0xC, 0xD

ACQ = C.CFUNCTYPE(U); ADD = C.CFUNCTYPE(C.c_int, U, U); REL = C.CFUNCTYPE(None)
CB = C.CFUNCTYPE(None, U, U); DEV = C.CFUNCTYPE(C.c_int, U, U, U, U, U)
FSET = C.CFUNCTYPE(C.c_int, C.c_int, U); FWAIT = C.CFUNCTYPE(C.c_int, C.c_int, U, U, C.POINTER(U), C.c_int)
DLY = C.CFUNCTYPE(None, U)


def build(defines=()):
    out = pathlib.Path(tempfile.mkdtemp()) / 'libwr.dylib'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-shared', '-fPIC', '-DWR_HOST',
                    *[f'-D{d}' for d in defines], '-I', str(HERE),
                    *[str(HERE / f) for f in ('bq.c', 'wr.c', 'wr_fixture.c')], '-o', str(out)], check=True)
    lib = C.CDLL(str(out))
    lib.fx_new.restype = C.c_void_p
    lib.fx_new.argtypes = [ACQ, ADD, REL, CB, DEV, FSET, FWAIT, DLY, C.POINTER(U), U]
    for n, a in dict(fx_free=[], fx_installed=[U], fx_send=[U, U], fx_cookie=[U, U], fx_acquire=[],
                     fx_add=[U, U], fx_ckpt=[], fx_rb=[], fx_rel=[], fx_service=[], fx_idle=[],
                     fx_take_start=[], fx_late=[U, U],
                     fx_counter=[C.c_int]).items():
        getattr(lib, n).argtypes = [C.c_void_p] + a
    lib.fx_acquire.restype = U
    lib.fx_counter.restype = U
    lib.fx_rd.restype = U; lib.fx_rd.argtypes = [U]; lib.fx_wr.argtypes = [U, U]
    return lib


class Camera:
    """Stock file layer + driver + device, and wr wired in through the vol."""

    def __init__(self, lib, seed, block_bytes=8 << 20, acq_busy=0.0, fail_batch=None,
                 driver=SD_ACQ, maxdesc=0x10000, writer_bias=0.5, cap=0x80):
        self.lib, self.rnd = lib, random.Random(seed)
        self.acq_busy, self.fail_batch, self.wb, self.cap = acq_busy, fail_batch, writer_bias, cap
        self.drv_busy = False; self.drv_list = []
        self.dev_writes = 0
        self.pos = {}; self.pieces = {}; self.written = set(); self.returned = []; self.status = {}
        self.batch_of = {}                  # piece -> device write index
        self.errors = []                    # ctypes swallows exceptions in callbacks
        self.discarding = False
        self.cbs = [ACQ(self.drv_acquire), ADD(self.drv_add), REL(self.drv_release), CB(self.stock_cb),
                    DEV(self.dev_write), FSET(lambda i, p: 0), FWAIT(self.flg_wait), DLY(lambda ms: None)]
        ven = (U * 6)(*[OURS[k] for k in ('cb', 'acq', 'add', 'ckpt', 'rb', 'rel')])
        self.w = lib.fx_new(*self.cbs, ven, block_bytes)
        for a in range(VOL, VOL + 0x5000, 4): lib.fx_wr(a, 0)
        lib.fx_wr(MISC, maxdesc)
        lib.fx_wr(VOL + 0x1460, SS); lib.fx_wr(VOL + 0x146C, SPC); lib.fx_wr(VOL + 0x1458, HEAP)
        lib.fx_wr(VOL + 0x0, 0xE)
        stock = dict(STOCK, acq=driver)
        for k, off in SLOTS.items(): lib.fx_wr(VOL + off, stock[k])
        self.stock = stock
        self.next_cl = 0x40; self.addr = 0x50000000
        lib.fx_wr(MGR + 0xC, 0x0101)                  # mgr+0xC (records), +0xD (aggregation)
        self.late_completed = []

    # ---------------------------------------------------------------- vol
    def rd(self, off): return self.lib.fx_rd(VOL + off)
    def wr(self, off, v): self.lib.fx_wr(VOL + off, v & 0xFFFFFFFF)

    def call(self, slot, *a):
        """What stock does: call through the vol pointer."""
        p = self.rd(SLOTS[slot]); L, w = self.lib, self.w
        if p == OURS[slot]:
            return {'cb': L.fx_cookie, 'acq': L.fx_acquire, 'add': L.fx_add, 'ckpt': L.fx_ckpt,
                    'rb': L.fx_rb, 'rel': L.fx_rel}[slot](w, *a)
        assert p == self.stock[slot], f'{slot} points at {p:#x}'
        return {'cb': self.stock_cb, 'acq': self.drv_acquire, 'add': self.drv_add,
                'ckpt': self.drv_ckpt, 'rb': self.drv_rb, 'rel': self.drv_release}[slot](*a)

    # -------------------------------------------------------------- driver
    def drv_acquire(self):
        if self.drv_busy: return 0
        if self.lib.fx_counter(self.w, 0) and self.rnd.random() < self.acq_busy: return 0
        self.drv_busy = True; self.drv_list = []; self.drv_ck = 0
        return ARENA

    def drv_add(self, a, n):
        if not self.drv_busy: self.errors.append('add without the table')
        self.drv_list.append((a, n)); return 0

    def drv_ckpt(self): self.drv_ck = len(self.drv_list)
    def drv_rb(self): del self.drv_list[self.drv_ck:]
    def drv_release(self): self.drv_busy = False

    def dev_write(self, dev, lo, hi, n, buf):
        try:
            return self._dev_write(dev, lo, hi, n, buf)
        except AssertionError as e:
            self.errors.append(str(e)); return -99

    def _dev_write(self, dev, lo, hi, n, buf):
        assert dev == 0xE and buf == ARENA and self.drv_busy
        lba = lo | hi << 32
        assert sum(x for _, x in self.drv_list) == n * SS, 'sector count != table bytes'
        p = lba * SS
        k = self.dev_writes; self.dev_writes += 1
        fail = self.fail_batch is not None and k == self.fail_batch
        for a, x in self.drv_list:
            if a != PAD:
                assert self.pos[a] == p, f'piece {a:#x} at {p:#x}, expected {self.pos[a]:#x}'
                if not fail: self.written.add(a)
                self.batch_of[a] = k
            p += x
        self.drv_list = []
        return -7 if fail else 1

    def node(self, f): return NODE0 + NODE_STRIDE * f

    def stock_cb(self, frame, status):              # C03A55D0
        f = frame - 1
        self.lib.fx_wr(self.node(f) + 0x1104, DONE_ST)
        if status == 0 and not self.pieces[f] <= self.written and not self.discarding:
            self.errors.append(f'frame {f} handed back before its data was written')
        self.returned.append(frame); self.status[frame] = status

    def flg_wait(self, i, ptn, mode, out, tmo):     # the writer runs while we block
        self.lib.fx_service(self.w); return 0

    # ----------------------------------------------------------- stock FS
    def c063f220(self, thresh=0x04000000):
        self.lib.fx_take_start(self.w)                # hook220, before stock
        if self.rd(0x4828): return -3
        self.wr(0x4828, thresh); self.wr(0x482C, PAD); self.wr(0x4830, 0x40000); self.wr(0x4834, STOCK['cb'])
        self.wr(0x484C, self.call('acq'))
        for o in (0x4850, 0x4A54, 0x4A58): self.wr(o, 0)
        t = self.rd(0x4828); self.wr(0x4828, -(-t // CLUSTER) * CLUSTER)
        self.lib.fx_installed(self.w, VOL)            # our wrapper, after stock returned 1
        return 1

    def c063f140(self, lr):
        if self.lib.fx_send(self.w, VOL, lr) == 0: return
        if not self.rd(0x484C): return                # stock body
        st = 0
        if self.rd(0x4A54) and self.rd(0x4A58):
            lba = (self.rd(0x4A54) - 2) * SPC + HEAP
            st = 0 if self.dev_write(0xE, lba, 0, self.rd(0x4A58) // SS, ARENA) == 1 else -7
        for i in range(self.rd(0x4850)): self.call('cb', self.rd(0x4854 + 4 * i), st & 0xFFFFFFFF)
        self.call('rel'); self.wr(0x484C, self.call('acq'))
        for o in (0x4850, 0x4A54, 0x4A58): self.wr(o, 0)

    def c063f310(self, p):
        if not self.rd(0x4828): return -3
        if p: self.wr(0x4A54, 0); self.discarding = True
        self.c063f140(LR_STOP)
        assert self.lib.fx_idle(self.w), 'C063F310 returned with blocks in flight'
        if self.rd(0x484C): self.call('rel')
        self.wr(0x4828, 0); self.wr(0x484C, 0)
        return 1

    def extent(self, pieces):
        size = sum(n for _, n in pieces); ncl = -(-size // CLUSTER)
        cl = self.next_cl + (self.rnd.randint(1, 4) if self.rnd.random() < 0.05 else 0)
        self.next_cl = cl + ncl
        p = ((cl - 2) * SPC + HEAP) * SS
        for a, n in pieces: self.pos[a] = p; p += n
        if self.rd(0x4A58) and cl != self.rd(0x4A54) + self.rd(0x4A58) // CLUSTER:
            self.c063f140(LR_OTHER)                   # C063F682
        if not self.rd(0x484C):                       # no arena: direct, synchronous
            for a, _ in pieces: self.written.add(a)
            return
        self.call('ckpt'); ok = True
        for a, n in pieces:
            if self.call('add', a, n) < 0: ok = False; break
        pad = ncl * CLUSTER - size
        while ok and pad:
            t = min(pad, 0x40000)
            if self.call('add', PAD, t) < 0: ok = False
            pad -= t
        if not ok:                                    # C063F6A0
            self.call('rb'); self.c063f140(LR_OTHER)
            for a, _ in pieces: self.written.add(a)
            return
        if not self.rd(0x4A58): self.wr(0x4A54, cl)
        self.wr(0x4A58, self.rd(0x4A58) + ncl * CLUSTER)
        if self.rd(0x4A58) >= self.rd(0x4828): self.c063f140(LR_OTHER)   # C063F6F2

    def frame(self, f, stop_first=False):
        """C03A5348 for one frame: mark 0xC, C069ADE0 (its open, write and close each
        take the FS lock), then the aggregation test at C03A549C with our hook.
        stop_first: the stop task got the FS lock between the open and the write."""
        self.lib.fx_wr(self.node(f) + 0x1104, HANDED)               # C03A5460
        if stop_first:
            self.c063f310(0)
        self.write_frame(f)
        r3 = self.lib.fx_rd(MGR + 0xC) >> 8 & 0xFF                 # ldrb r3, [fp, #0xd]
        if self.lib.fx_late(self.w, MGR, self.node(f)): r3 = 0
        if r3 == 0:                                                 # C03A54A8: completes it itself
            self.late_completed.append(f + 1)
            self.stock_cb(f + 1, 0 if self.pieces[f] <= self.written else 0xFFFFFFFF)

    def write_frame(self, f):
        rnd = self.rnd
        size = rnd.choice([1_095_168, 3_244_544, 17_000, 8_447_488])
        pieces, left = [], size
        while left:
            n = min(left, rnd.choice([3, 70_000, 1 << 20, 4 << 20]))
            a = self.addr + rnd.choice([0, 0, 1, 3]); self.addr = a + n + 0x1000
            pieces.append((a, n)); left -= n
        self.pieces[f] = {a for a, _ in pieces}
        cut = rnd.randint(1, len(pieces)) if len(pieces) > 1 and rnd.random() < 0.2 else len(pieces)
        for part in (pieces[:cut], pieces[cut:]):
            if part: self.extent(part)
        if not self.rd(0x4828): return                                    # F816: no cookie at all
        if self.rd(0x4850) == self.cap: self.c063f140(LR_OTHER)          # C063F826
        if self.rd(0x4A58) == 0:
            self.call('cb', f + 1, 0)                                     # C063F830
        else:
            n = self.rd(0x4850); self.wr(0x4854 + 4 * n, f + 1); self.wr(0x4850, n + 1)

    def take(self, frames=200, stop_discard=False, thresh=0x04000000, late=0):
        """late: the last `late` frames are written after the stop (the race)."""
        assert self.c063f220(thresh) == 1
        for f in range(frames):
            self.frame(f, stop_first=late and f == frames - late)
            if self.rnd.random() < self.wb: self.lib.fx_service(self.w)
        if not late: self.c063f310(1 if stop_discard else 0)
        while not self.lib.fx_idle(self.w): self.lib.fx_service(self.w)
        return self

    def counters(self): return {k: self.lib.fx_counter(self.w, i) for i, k in enumerate(N)}

    def check_end(self, frames):
        assert not self.errors, self.errors[:3]
        assert self.returned == list(range(1, frames + 1)), 'cookies lost, repeated or reordered'
        for k, off in SLOTS.items(): assert self.rd(off) == self.stock[k], f'{k} not restored'
        assert self.rd(0x484C) == 0 and self.rd(0x4828) == 0
        assert not self.drv_busy, 'driver table left held'


class WrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = build()

    def test_sd_takes(self):
        for s in range(30):
            cam = Camera(self.lib, s).take()
            cam.check_end(200)
            c = cam.counters()
            self.assertEqual(c['install'], 1); self.assertGreater(c['send'], 5)
            self.assertEqual(c['drain'], 1); self.assertEqual(c['drain_timeout'], 0)
            self.assertEqual(c['stock_send'], 0)
            self.assertTrue(all(v == 0 for v in cam.status.values()))

    def test_threshold_is_ours_and_cluster_aligned(self):
        cam = Camera(self.lib, 1, block_bytes=(8 << 20) + 1)
        cam.c063f220()
        self.assertEqual(cam.rd(0x4828), (8 << 20) + CLUSTER)

    def test_ssd_and_host4_descriptors(self):
        for s in range(10):
            Camera(self.lib, 100 + s, driver=SSD_ACQ).take().check_end(200)
            Camera(self.lib, 200 + s, maxdesc=0x4000000).take().check_end(200)

    def test_driver_table_busy_is_retried(self):
        for s in range(10):
            cam = Camera(self.lib, 300 + s, acq_busy=0.3).take(); cam.check_end(200)
            self.assertGreater(cam.counters()['acq_retry'], 0)

    def test_device_error_reaches_exactly_its_frames(self):
        for s in range(120):
            cam = Camera(self.lib, 400 + s, fail_batch=3).take(); cam.check_end(200)
            bad = {f for f, st in cam.status.items() if st}
            hit = {f for f in range(1, 201) if any(cam.batch_of.get(a) == 3 for a in cam.pieces[f - 1])}
            self.assertTrue(hit)
            self.assertTrue(hit <= bad, 'a frame with bytes in the failed write was reported good')
            self.assertLessEqual(len(bad - hit), 1, 'more than the one possibly spanning frame')
            self.assertEqual(cam.counters()['dev_err'], 1)

    def test_stop_discard_writes_nothing_more(self):
        for s in range(10):
            cam = Camera(self.lib, 500 + s).take(stop_discard=True); cam.check_end(200)

    def test_unknown_driver_is_left_to_stock(self):
        for s in range(5):
            cam = Camera(self.lib, 600 + s, driver=0xC0123457).take(); cam.check_end(200)
            c = cam.counters()
            self.assertEqual((c['install'], c['refuse']), (0, 1))
            self.assertGreater(c['stock_send'], 0)

    def test_slow_writer_and_tiny_batches(self):
        for s in range(10):
            Camera(self.lib, 700 + s, block_bytes=1 << 20, writer_bias=0.02, cap=40).take().check_end(200)

    def test_frames_written_after_the_stop_complete_once(self):
        """10-15 OG3K freeze: the stop got the FS lock between the last frame's open
        and its write; F816 skipped its cookie and it never completed."""
        for s in range(30):
            late = 1 + s % 3
            cam = Camera(self.lib, 800 + s, writer_bias=0.1 if s % 2 else 0.6).take(late=late)
            cam.check_end(200)
            self.assertEqual(cam.late_completed, list(range(201 - late, 201)))
            self.assertEqual(cam.counters()['late_frame'], late)
            self.assertTrue(all(cam.status[f] == 0 for f in cam.late_completed))

    def test_guard_is_quiet_otherwise(self):
        for kw in (dict(), dict(stop_discard=True)):
            for s in range(10):
                cam = Camera(self.lib, 900 + s).take(**kw)
                self.assertEqual(cam.late_completed, []); self.assertEqual(cam.counters()['late_frame'], 0)
        cam = Camera(self.lib, 950).take(late=1)          # the next take, ours again
        cam.returned.clear(); cam.late_completed.clear()
        cam.take(); self.assertEqual(cam.late_completed, [])
        cam = Camera(self.lib, 951, driver=0xC0123457).take()   # stock's own take
        self.assertEqual(cam.late_completed, []); cam.check_end(200)


class MutationTests(unittest.TestCase):
    def test_no_late_frame_guard_is_caught(self):
        lib = build(['WR_MUTANT_NO_LATE'])
        with self.assertRaises(AssertionError):
            Camera(lib, 800).take(late=1).check_end(200)

    def test_no_failure_carry_is_caught(self):
        lib = build(['BQ_MUTANT_NO_CARRY'])
        caught = 0
        for s in range(120):                     # a frame spans the failed write ~1 take in 60
            cam = Camera(lib, 400 + s, fail_batch=3).take()
            hit = {f for f in range(1, 201) if any(cam.batch_of.get(a) == 3 for a in cam.pieces[f - 1])}
            if cam.errors or not hit <= {f for f, st in cam.status.items() if st}: caught += 1
        self.assertGreater(caught, 0)

    def test_no_drain_on_stop_is_caught(self):
        lib = build(['WR_MUTANT_NO_DRAIN'])
        caught = 0
        for s in range(10):
            try: Camera(lib, 900 + s, writer_bias=0.0).take().check_end(200)
            except AssertionError: caught += 1
        self.assertGreater(caught, 0)


if __name__ == '__main__':
    unittest.main()
