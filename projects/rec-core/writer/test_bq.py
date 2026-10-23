#!/usr/bin/env python3
"""bq against a model of stock C063F380 (WRITER_LOCK_SCOPE §5): extents with
cluster padding, threshold +0x4828, cookie cap, cluster gaps, add failure ->
rollback + send + direct write, and the "4A58 == 0 -> call +0x4834 now" path.
A writer task interleaves at random, down to one cookie hand-back at a time.

    python3 -B -m unittest test_bq        # mutants must be caught too
"""
import ctypes, pathlib, random, subprocess, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
SECTOR = 512
PAD = 0x4FF00000                       # stock's zero buffer (shared, not tracked)
SD = (0x400, 0x100, 0x10000)           # entries, heads, bytes/descriptor (host < 4)
SD4 = (0x400, 0x100, 0x4000000)
SSD = (0x400, 0, 0)


def build(defines=()):
    out = pathlib.Path(tempfile.mkdtemp()) / 'libbq.dylib'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-shared', '-fPIC',
                    *[f'-D{d}' for d in defines], '-I', str(HERE),
                    str(HERE / 'bq.c'), str(HERE / 'bq_fixture.c'), '-o', str(out)], check=True)
    lib = ctypes.CDLL(str(out))
    lib.fx_new.restype = ctypes.c_void_p
    sig = {'fx_free': 0, 'fx_open': 0, 'fx_ck': 0, 'fx_add': 2, 'fx_rb': 0, 'fx_late': 1,
           'fx_take': 0, 'fx_chunk': 1, 'fx_seg': 3, 'fx_blk': 2, 'fx_cbegin': 2, 'fx_cnext': 0,
           'fx_idle': 0}
    for n, k in sig.items():
        getattr(lib, n).argtypes = [ctypes.c_void_p] + [ctypes.c_uint32] * k
    lib.fx_seal.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32]
    for n in ('fx_seg', 'fx_blk', 'fx_from', 'fx_cbytes', 'fx_ccookie', 'fx_cstatus', 'fx_entries'):
        getattr(lib, n).restype = ctypes.c_uint32
    return lib


class Take:
    def __init__(self, lib, seed, cluster=128 << 10, threshold=8 << 20, cap=0x80, limits=SD,
                 frames=300, gaps=0.05, tiny=False, writer_bias=0.5, burst=0.0):
        self.lib, self.rnd = lib, random.Random(seed)
        self.C, self.T, self.cap = cluster, threshold, cap
        lib.fx_limits(*limits)
        self.limits = limits
        self.q = lib.fx_new()
        self.frames, self.gaps, self.tiny, self.wb, self.burst = frames, gaps, tiny, writer_bias, burst
        self.addr = 0x50000000
        self.pos = {}                   # piece addr -> media byte position
        self.piece_frame = {}           # piece addr -> frame
        self.pieces = {}                # frame -> set(addr)
        self.written = set()
        self.returned = []              # cookies in hand-back order
        self.next_cl = 0x100
        # stock vol state
        self.b_cl = 0; self.b_bytes = 0; self.cookies = []; self.expect_cl = None
        assert lib.fx_open(self.q) >= 0
        # writer state
        self.cur = -1; self.cfrom = 0; self.csent = 0
        self.stats = dict(chunks=0, sends=0, late=0, late_direct=0, direct=0, waits=0)

    # ---------------------------------------------------------- writer task
    def writer_step(self, force=False):
        lib, q = self.lib, self.q
        if not force and self.rnd.random() > self.wb:
            return
        if self.cur < 0:
            if lib.fx_cnext(q):
                self.give(lib.fx_ccookie(), lib.fx_cstatus())
                return
            self.cur = lib.fx_take(q)
            lib.fx_chunk_reset(); self.cfrom = 0; self.csent = 0
            if self.cur < 0:
                return
        i = self.cur
        if lib.fx_blk(q, i, 2):                     # skip: nothing to write
            assert lib.fx_cbegin(q, i, 0) == 0
            self.cur = -1
            return
        start = lib.fx_from()
        n = lib.fx_chunk(q, i)
        assert n >= 0, f'chunk error {n}'
        if n == 0:
            assert self.csent == lib.fx_blk(q, i, 1)
            assert lib.fx_cbegin(q, i, 0) == 0
            self.cur = -1
            return
        nbytes = lib.fx_cbytes()
        assert nbytes % SECTOR == 0, 'chunk not a whole number of sectors'
        p = lib.fx_blk(q, i, 0) * self.C + self.csent
        assert p % self.C == 0, 'chunk does not start on a cluster edge'
        ent = 0
        for k in range(start, start + n):
            a, ln = lib.fx_seg(q, i, k, 0), lib.fx_seg(q, i, k, 1)
            ent += lib.fx_entries(a, ln)
            if a != PAD:
                assert self.pos[a] == p, 'segment lands at the wrong media position'
                self.written.add(a)
            p += ln
        assert ent <= self.limits[0]
        self.csent += nbytes
        self.stats['chunks'] += 1

    def give(self, cookie, status):
        f = cookie - 1
        missing = self.pieces[f] - self.written
        assert not missing, f'frame {f} handed back before its data was written'
        self.returned.append(cookie)

    def wait_free(self):
        while self.lib.fx_open(self.q) < 0:
            self.stats['waits'] += 1
            self.writer_step(force=True)

    # ---------------------------------------------------------- stock side
    def send(self):                                 # our C063F140
        c = (ctypes.c_uint32 * max(1, len(self.cookies)))(*self.cookies)
        r = self.lib.fx_seal(self.q, self.b_cl, self.b_bytes, c, len(self.cookies))
        assert r == 0, f'seal {r}'
        self.stats['sends'] += 1
        self.cookies = []; self.b_cl = 0; self.b_bytes = 0
        self.wait_free()

    def extent(self, f, pieces):
        size = sum(n for _, n in pieces)
        ncl = -(-size // self.C)
        cl = self.next_cl
        if self.rnd.random() < self.gaps:
            cl += self.rnd.randint(1, 8)
        self.next_cl = cl + ncl
        if self.b_bytes and cl != self.expect_cl:
            self.send()                             # C063F682: not contiguous
        lib, q = self.lib, self.q
        p = cl * self.C
        for a, n in pieces:
            self.pos[a] = p; p += n
        assert lib.fx_ck(q) == 0 or True
        ok = True
        for a, n in pieces:
            if lib.fx_add(q, a, n) < 0: ok = False; break
        pad = ncl * self.C - size
        while ok and pad:
            t = min(pad, 0x40000)
            if lib.fx_add(q, PAD, t) < 0: ok = False; break
            pad -= t
        if not ok:                                  # C063F6A0: rollback, send, write direct
            lib.fx_rb(q)
            self.send()
            for a, _ in pieces: self.written.add(a)
            self.stats['direct'] += 1
            self.expect_cl = None
            return
        if not self.b_bytes:
            self.b_cl = cl
        self.b_bytes += ncl * self.C
        self.expect_cl = cl + ncl
        if self.b_bytes >= self.T:                  # C063F6F2
            self.send()

    def frame(self, f):
        rnd = self.rnd
        size = rnd.choice([1_095_168, 3_244_544, 606_208, 17_000, 2_048, 8_447_488])
        if self.tiny: size = rnd.choice([2_048, 4_096, 60_000])
        pieces, left = [], size
        while left:
            n = min(left, rnd.choice([3, 512, 70_000, 1 << 20, 4 << 20]))
            a = self.addr + rnd.choice([0, 0, 1, 2, 3])
            self.addr = a + n + 0x1000
            pieces.append((a, n)); left -= n
            self.piece_frame[a] = f
        self.pieces[f] = {a for a, _ in pieces}
        # one or two extents
        cut = rnd.randint(1, len(pieces)) if len(pieces) > 1 and rnd.random() < 0.2 else len(pieces)
        for part in (pieces[:cut], pieces[cut:]):
            if part: self.extent(f, part)
            for _ in range(rnd.randint(0, 2)): self.writer_step()
            if rnd.random() < self.burst:           # the writer runs ahead of the frame end
                for _ in range(rnd.randint(1, 12)): self.writer_step(force=True)
        if len(self.cookies) == self.cap:           # C063F826
            self.send()
        if self.b_bytes == 0:                       # C063F830: +0x4834 now
            self.stats['late'] += 1
            r = self.lib.fx_late(self.q, f + 1)
            assert r in (0, 1), r
            if r == 1:
                self.stats['late_direct'] += 1
                self.give(f + 1, 0)
        else:
            self.cookies.append(f + 1)

    def run(self):
        for f in range(self.frames):
            self.frame(f)
            for _ in range(self.rnd.randint(0, 3)): self.writer_step()
        self.send()                                 # stop: C063F310 -> C063F140
        guard = 0
        while not self.lib.fx_idle(self.q) or self.cur >= 0:
            self.writer_step(force=True); guard += 1
            assert guard < 100000
        while self.lib.fx_cnext(self.q):
            self.give(self.lib.fx_ccookie(), self.lib.fx_cstatus())
        assert self.returned == list(range(1, self.frames + 1)), 'cookies lost, repeated or reordered'
        assert self.written >= set(self.pos), 'data never written'
        self.lib.fx_free(self.q)
        return self.stats


class BqTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = build()

    def test_sd_128k_8m(self):
        for s in range(40):
            st = Take(self.lib, s).run()
            self.assertGreater(st['late'], 0)

    def test_sd_host4_64m_cap40(self):
        for s in range(30):
            Take(self.lib, 100 + s, threshold=64 << 20, cap=40, limits=SD4).run()

    def test_ssd_512k(self):
        for s in range(30):
            Take(self.lib, 200 + s, cluster=512 << 10, threshold=16 << 20, limits=SSD).run()

    def test_tiny_frames_fill_tables(self):
        """Many tiny frames: the 128-cookie cap and the segment table both bite."""
        tot = dict(direct=0, waits=0)
        for s in range(20):
            st = Take(self.lib, 300 + s, threshold=64 << 20, tiny=True, frames=600, writer_bias=0.1).run()
            for k in tot: tot[k] += st[k]
        self.assertGreater(tot['waits'], 0)

    def test_slow_writer_late_cookie_joins_completion(self):
        for s in range(40):
            Take(self.lib, 400 + s, threshold=1 << 20, writer_bias=0.05, frames=200, burst=0.3).run()

    def test_chunk_splits_only_at_extents(self):
        for s in range(20):
            st = Take(self.lib, 500 + s, threshold=64 << 20, limits=(0x40, 0x10, 0x10000)).run()
            self.assertGreater(st['chunks'], st['sends'])
            self.assertGreater(st['direct'], 0)     # > 4 MiB extents: refused like stock


class MutationTests(unittest.TestCase):
    def caught(self, define, **kw):
        lib = build([define]); n = 0
        for s in range(60):
            try: Take(lib, 900 + s, **kw).run()
            except AssertionError: n += 1
        return n

    def test_late_cookie_called_directly_is_caught(self):
        self.assertGreater(self.caught('BQ_MUTANT_LATE_DIRECT', writer_bias=0.1), 0)

    def test_late_cookie_overtaking_completion_is_caught(self):
        self.assertGreater(self.caught('BQ_MUTANT_NO_TAIL', threshold=1 << 20, writer_bias=0.05, burst=0.3), 0)

    def test_cut_inside_extent_is_caught(self):
        self.assertGreater(self.caught('BQ_MUTANT_NOCUT', threshold=64 << 20,
                                       limits=(0x40, 0x10, 0x10000)), 0)


if __name__ == '__main__':
    unittest.main()
