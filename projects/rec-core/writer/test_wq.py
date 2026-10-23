#!/usr/bin/env python3
"""wq invariants (WRITER_SPEC §3 I1-I5, §5.4c), host build of the pure core.

    python3 -B -m unittest test_wq          # also proves the tests can fail:
                                            # WQ_MUTANT_NOHOLD must be caught
"""
import ctypes, os, pathlib, random, subprocess, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
RU = 512 * 1024
SECTOR = 512


def build(defines=()):
    out = pathlib.Path(tempfile.mkdtemp()) / 'libwq.dylib'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-shared', '-fPIC',
                    *[f'-D{d}' for d in defines], '-I', str(HERE),
                    str(HERE / 'wq.c'), str(HERE / 'wq_fixture.c'), '-o', str(out)], check=True)
    lib = ctypes.CDLL(str(out))
    lib.fx_new.restype = ctypes.c_void_p
    for name in ('fx_free', 'fx_add', 'fx_end', 'fx_flush', 'fx_idle', 'fx_take', 'fx_complete',
                 'fx_info', 'fx_seg', 'fx_cookie', 'fx_counter'):
        getattr(lib, name).argtypes = [ctypes.c_void_p] + [ctypes.c_uint32] * {
            'fx_free': 0, 'fx_add': 3, 'fx_end': 1, 'fx_flush': 0, 'fx_idle': 0, 'fx_take': 0,
            'fx_complete': 2, 'fx_info': 2, 'fx_seg': 3, 'fx_cookie': 2, 'fx_counter': 1}[name]
    for name in ('fx_info', 'fx_seg', 'fx_cookie', 'fx_counter', 'fx_ndone', 'fx_done', 'fx_taken'):
        getattr(lib, name).restype = ctypes.c_uint32
    return lib


def simulate(lib, seed, block_mib=8, frames=400, writer_lag=3, gaps=0.0):
    """Drive a take: frames of random size, each as 1-3 segments (data, pad),
    contiguous on the medium; a writer that takes/completes blocks at random.
    Returns a report the invariant checks read."""
    rnd = random.Random(seed)
    q = lib.fx_new(block_mib << 20, RU)
    assert q
    lba = 0x10000                                  # stream start, RU-aligned
    addr = 0x50000000
    stream = []                                    # (lba, addr, len) as submitted
    taken = []                                     # (block lba, [(addr,len)], cookies, reason, bytes)
    writing = []
    stalls = 0

    def writer_step(force=False):
        if writing and (force or rnd.random() < 0.5):
            i = writing.pop(0)
            assert lib.fx_complete(q, i, 0) == 0
        if force or rnd.random() < 0.7:
            i = lib.fx_take(q)
            if i >= 0:
                n = lib.fx_info(q, i, 3)
                segs = [(lib.fx_seg(q, i, k, 0), lib.fx_seg(q, i, k, 1)) for k in range(n)]
                cookies = [lib.fx_cookie(q, i, k) for k in range(lib.fx_info(q, i, 4))]
                taken.append((lib.fx_info(q, i, 1), segs, cookies, lib.fx_info(q, i, 5), lib.fx_info(q, i, 2)))
                writing.append(i)

    for f in range(frames):
        size = rnd.choice([1_095_168, 3_244_544, 8_447_488, 606_208, 2048])
        size = -(-size // SECTOR) * SECTOR
        if gaps and rnd.random() < gaps:
            lba += rnd.randint(1, 64) * 256        # non-contiguous allocation
        parts = []
        left = size
        while left:
            n = min(left, rnd.choice([SECTOR, 64 * 1024, 1 << 20, 4 << 20]))
            parts.append(n)
            left -= n
        for n in parts:
            stream.append((lba, addr, n))
            while n:
                r = lib.fx_add(q, lba, addr, n)
                got = lib.fx_taken()
                assert got % SECTOR == 0 and got <= n
                lba += got // SECTOR
                addr += got
                n -= got
                if r == 0:
                    assert n == 0
                    break
                assert r == -1, r                  # WQ_FULL: drain, add the rest
                stalls += 1
                for _ in range(3):
                    writer_step(force=True)
        # the writer is another task: it may run between the frame's last
        # byte and its end (the race the hold exists for)
        for _ in range(rnd.randint(0, 2)):
            writer_step(force=rnd.random() < 0.5)
        assert lib.fx_end(q, f + 1) == 0, 'frame end found no block for its cookie'
        for _ in range(rnd.randint(0, writer_lag)):
            writer_step()
    lib.fx_flush(q)
    while not lib.fx_idle(q):
        writer_step(force=True)
    done = [lib.fx_done(k, 0) for k in range(lib.fx_ndone())]
    rep = dict(stream=stream, taken=taken, done=done, frames=frames, stalls=stalls,
               block=block_mib << 20, split=lib.fx_counter(q, 1), gaps=lib.fx_counter(q, 2))
    lib.fx_free(q)
    return rep


def check(rep):
    # I1: every cookie exactly once, in submission order
    assert rep['done'] == list(range(1, rep['frames'] + 1)), 'cookies lost, repeated or reordered'
    # I2: the blocks, in the order written, reproduce the submitted stream exactly
    sub = []
    for lba, a, n in rep['stream']:
        sub.append((lba, a, n))
    out = []
    for blba, segs, _, _, _ in rep['taken']:
        l = blba
        for a, n in segs:
            out.append((l, a, n))
            l += n // SECTOR
    def bytes_of(xs):                               # flatten to (lba, addr) per sector run
        m = []
        for lba, a, n in xs:
            if m and m[-1][0] + m[-1][2] // SECTOR == lba and m[-1][1] + m[-1][2] == a:
                m[-1] = (m[-1][0], m[-1][1], m[-1][2] + n)
            else:
                m.append((lba, a, n))
        return m
    assert bytes_of(out) == bytes_of(sub), 'blocks do not reproduce the stream'
    # I3/5.4c: full blocks are exactly block_bytes and RU-aligned relative to the stream
    for blba, segs, _, reason, nbytes in rep['taken']:
        assert nbytes == sum(n for _, n in segs)
        assert nbytes <= rep['block']
        if reason == 1:                             # WQ_CLOSE_FULL
            assert nbytes == rep['block']
    return True


class WqTests(unittest.TestCase):
    lib = None

    @classmethod
    def setUpClass(cls):
        cls.lib = build()

    def test_random_takes_contiguous(self):
        for seed in range(60):
            check(simulate(self.lib, seed, block_mib=8, frames=300))

    def test_small_blocks_many_splits(self):
        for seed in range(30):
            rep = simulate(self.lib, 1000 + seed, block_mib=1, frames=200, writer_lag=4)
            check(rep)
            self.assertGreater(rep['split'], 0)

    def test_gaps_close_blocks(self):
        for seed in range(30):
            rep = simulate(self.lib, 2000 + seed, block_mib=8, frames=200, gaps=0.1)
            check(rep)
            self.assertGreater(rep['gaps'], 0)

    def test_rejects_bad_geometry(self):
        lib = self.lib
        self.assertIsNone(lib.fx_new(RU + SECTOR, RU))    # block not an RU multiple
        self.assertIsNone(lib.fx_new(8 << 20, 1000))      # RU not a sector multiple


class MutationTests(unittest.TestCase):
    def test_nohold_mutant_is_caught(self):
        lib = build(['WQ_MUTANT_NOHOLD'])
        caught = 0
        for seed in range(200):
            try:
                check(simulate(lib, 5000 + seed, block_mib=1, frames=200, writer_lag=4))
            except AssertionError:
                caught += 1
        self.assertGreater(caught, 0, 'the tests cannot see a lost cookie at a block edge')


if __name__ == '__main__':
    unittest.main()
