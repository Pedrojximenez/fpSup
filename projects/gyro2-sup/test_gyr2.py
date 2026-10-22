#!/usr/bin/env python3
"""Gyro2 (stage P1) under unicorn: the real loader v3 (fpSup's sloader, as the
AutoRun spells it) loads 20GYR2.BIN from a card, then the hooked DMA call is
run against real fp CinemaDNG headers placed in a template buffer.

    python3 -B -m unittest test_gyr2

Emulated only.  What this cannot tell: whether the camera's DMA sees the
cleaned lines, the real tag-manager/request layouts at run time, timing in
the MovRec task, and anything the stubbed DMA does differently.
"""
import pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))

import test_v3 as V                        # noqa: E402  (fpSup, read-only)
import build as G                          # noqa: E402
import fsg2 as F                           # noqa: E402

try:
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                                   UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
                                   UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR)
except ImportError:                        # pragma: no cover
    pass

SITE, DMA, AFTER = 0xC038C77C, 0xC00FBB90, 0xC038C780
ACCEL_SITE = 0xC050D4C8
VD_SITE, VD_STOCK = 0xC0125480, 0x341DF2CC          # Thumb: movt r4, #0xC31D
MODE_FN, F_TIMING, F_GEOM = 0xC032C720, 0xC0320FC8, 0xC0321028
LENS_FOCAL, LENS_AXIS, LENS_NODES = 0xC307CDF0, 0xC307CE2C, 0xC307D270
MAGIC = b'FSG2'
GAP = 64

CAPTURES = ROOT / 'projects'
SAMPLES = {
    # name: path relative to projects/; the zero tail sizes are what find_tail must see
    'fhd': 'gyro-sup/captures/fpGFTest_pre_stage4_20260817_2207/CINEMA/A001_001/A001_001_20260817_000244.DNG',
    'og2k_small_tail': 'sensor-lab/build/og2k_3x3_20260924/A001_009/A001_009_20260924_000016.DNG',
    'og3k120_moved_makernote': 'open-gate/captures/og3k120-defect-A001_182/A001_182_20260927_000001.DNG',
}


def find_sample(rel):
    p = CAPTURES / rel
    if p.exists():
        return p
    hits = list(ROOT.glob('**/' + pathlib.Path(rel).name))
    hits = [h for h in hits if 'worktrees' not in h.parts]
    return hits[0] if hits else None


def header_of(path):
    """The bytes the firmware's template holds: everything before the RAW."""
    data = path.read_bytes()[:0x20000]
    ifd = struct.unpack_from('<I', data, 4)[0]
    n = struct.unpack_from('<H', data, ifd)[0]
    for k in range(n):
        tag, typ, cnt, val = struct.unpack_from('<HHII', data, ifd + 2 + 12 * k)
        if tag == 0x111:
            return data[:val]
    raise ValueError('no StripOffsets')


def expected_tail(hdr):
    """Independent decode: (aligned offset of the 0x200 area's trailing zeros, their length)."""
    def entries(off):
        n = struct.unpack_from('<H', hdr, off)[0]
        return {t: (ty, c, v) for t, ty, c, v in
                (struct.unpack_from('<HHII', hdr, off + 2 + 12 * k) for k in range(n))}
    root = entries(struct.unpack_from('<I', hdr, 4)[0])
    exif = entries(root[0x8769][2])
    _, mn_len, mn_off = exif[0x927C]
    assert hdr[mn_off:mn_off + 8] == b'SIGMA\0\0\0'
    mn = entries(mn_off + 10)
    _, a_len, a_off = mn[0x200]
    end = a_off + a_len
    assert end <= mn_off + mn_len
    i = end
    while i > a_off and hdr[i - 1] == 0:
        i -= 1
    start = (i + 3) & ~3
    return start, end - start


class Cam(V.Camera):
    """test_v3's camera plus the DMA the hook forwards to."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mu.mem_write(DMA, b'\x70\x47')            # bx lr (Thumb), as test_v3 does for its stubs
        for a_ in (MODE_FN, F_TIMING, F_GEOM):
            self.mu.mem_write(a_, struct.pack('<I', 0xE12FFF1E))
        self.dmas = []
        # The mode the accessors report: 106, hmax 380 clocks x 2000 lines at
        # 72 MHz = 10.555556 ms; 3000 wide, 2 x 2 binning = the whole sensor.
        self.mode = 106
        self.t_row = self._alloc(0x20)
        self.g_row = self._alloc(0x60)
        self.mu.mem_write(self.t_row, struct.pack('<IH', 0, 380))
        self.mu.mem_write(self.g_row, struct.pack('<III', 0, 3000, 2000))
        self.mu.mem_write(self.g_row + 0x44, struct.pack('<II', 2, 2))
        self.mode_calls = []

    def _hook(self, mu, addr, size, data):
        if addr == MODE_FN:
            self.mode_calls.append('mode')
            return self._ret(self.mode)
        if addr in (F_TIMING, F_GEOM):
            self.mode_calls.append((addr, self.r(V.UC_ARM_REG_R1)))
            return self._ret(self.t_row if addr == F_TIMING else self.g_row)
        if addr == DMA:
            r0 = self.r(UC_ARM_REG_R0)
            src, dst, n, flags = struct.unpack('<4I', mu.mem_read(r0, 16))
            self.dmas.append((r0, src, dst, n, flags, self.r(UC_ARM_REG_LR)))
            mu.mem_write(dst, bytes(mu.mem_read(src, n)))
            return self._ret(0)
        return super()._hook(mu, addr, size, data)


def _symbols():
    import os
    from armasm import symbols
    return symbols(os.environ.get('GYR2_SRC') or G.SRC)


SYM = _symbols()


def sup_bytes(src=None):
    import os
    src = src or os.environ.get('GYR2_SRC')      # mutate.py points this at a mutated copy
    sup, _ = G.build(src) if src else G.build()
    return sup


@unittest.skipIf(V.Uc is None or not V.IMAGE.exists(), 'needs unicorn and the image')
class Load(unittest.TestCase):
    def boot(self, *sups, stale=None):
        files, dirs = V.card(*sups)
        cam = Cam(files, dirs, stale=stale)
        cam.boot()
        return cam

    def test_loads_and_hooks_the_dma_call_through_a_veneer(self):
        cam = self.boot(('20GYR2.BIN', sup_bytes()))
        names = [e for e in cam.log() if e[0] in ('LOADED', 'RELEASED')]
        self.assertEqual(names[-1][0], 'LOADED', cam.log())
        site = cam.w(SITE)
        self.assertEqual(site >> 24, 0xEB, f'{site:#x} is not BL')
        off = (site & 0xFFFFFF) << 2
        veneer = (SITE + 8 + (off - (1 << 26) if off & (1 << 25) else off)) & 0xFFFFFFFF
        self.assertTrue(V.cave.CAVE_ARENA <= veneer < V.cave.CAVE_ARENA_END)
        self.assertEqual(cam.w(veneer), 0xE51FF004)
        hook = cam.w(veneer + 4)
        self.assertTrue(V.HEAP <= hook < V.HEAP + V.HEAP_SIZE, f'{hook:#x}')
        # the layer below is the firmware's own DMA, as a Thumb target
        self.assertIn((SITE, 4, struct.pack('<I', 0xFAF5BD03)), cam.journal())

    def test_stacks_on_an_earlier_chain_layer(self):
        other = 0xEB000000 | (((0xC072EF00 - (SITE + 8)) >> 2) & 0xFFFFFF)   # BL somewhere
        first = V.test_sup('ZZZ1', [(SITE, 0xFAF5BD03, 1, other)])
        cam = self.boot(('10OTHER.BIN', first), ('20GYR2.BIN', sup_bytes()))
        kinds = [e[0] for e in cam.log()]
        self.assertEqual(kinds.count('LOADED'), 2, cam.log())
        self.assertNotIn('RELEASED', kinds)
        self.assertNotEqual(cam.w(SITE), other, 'Gyro2 should be the outer layer')
        # run the hook with a bad template: it must forward to the layer below
        state = run_frame(cam, b'\0' * 0x400, count=1)
        self.assertEqual(state['pc_after'], 0xC072EF00)

    def test_the_accel_site_stacks_on_an_earlier_layer(self):
        other = 0xEB000000 | (((0xC072EF00 - (ACCEL_SITE + 8)) >> 2) & 0xFFFFFF)
        first = V.test_sup('ZZZ3', [(ACCEL_SITE, 0xE3A02000, 1, other)])
        cam = self.boot(('10OTHER.BIN', first), ('20GYR2.BIN', sup_bytes()))
        kinds = [e[0] for e in cam.log()]
        self.assertEqual(kinds.count('LOADED'), 2, cam.log())
        self.assertNotEqual(cam.w(ACCEL_SITE), other)
        f = fire_accel(cam, (1, 2, 3))
        self.assertEqual(f['pc'], 0xC072EF00, 'the reading went on to the layer below')
        self.assertEqual(f['r2'], 0xDEAD, 'and that layer, not us, replays mov r2, #0')

    def test_alone_at_the_accel_site_it_replays_the_displaced_instruction(self):
        cam = self.boot(('20GYR2.BIN', sup_bytes()))
        f = fire_accel(cam, (1, 2, 3))
        self.assertEqual(f['pc'], ACCEL_SITE + 4, 'back to the driver')
        self.assertEqual(f['r2'], 0, 'mov r2, #0, as the stock site did')
        self.assertTrue(f['regs_ok'])

    def test_the_vd_interrupt_is_hooked_through_an_arm_veneer(self):
        cam = self.boot(('20GYR2.BIN', sup_bytes()))
        veneer = thumb_blx_target(VD_SITE, cam.w(VD_SITE))
        self.assertEqual(veneer % 4, 0)
        self.assertTrue(V.cave.CAVE_ARENA <= veneer < V.cave.CAVE_ARENA_END, f'{veneer:#x}')
        self.assertEqual(cam.w(veneer), 0xE51FF004)
        self.assertIn((VD_SITE, 4, struct.pack('<I', VD_STOCK)), cam.journal())
        self.assertEqual(cam.w(0xC01255C8), 0x351DF2CC, 'IRQ 0x7f is left alone')

    def test_the_vd_hook_replays_its_movt_and_keeps_every_register(self):
        cam = self.boot(('20GYR2.BIN', sup_bytes()))
        f = fire_sync(cam, VD_SITE, UC_ARM_REG_R4, 0x89C0)
        self.assertEqual(f['pc'], VD_SITE + 4, 'back in the handler')
        self.assertTrue(f['thumb'], 'and in Thumb state')
        self.assertEqual(f['reg'], 0xC31D89C0)
        self.assertTrue(f['regs_ok'])

    def test_an_owner_of_the_vd_site_makes_it_back_off_and_write_nothing(self):
        owner = V.test_sup('ZZZ5', [(VD_SITE, VD_STOCK, 2, 0)])      # EXCL, claim only
        cam = self.boot(('10OWNER.BIN', owner), ('20GYR2.BIN', sup_bytes()))
        self.assertIn('RELEASED', [e[0] for e in cam.log()])
        self.assertEqual(cam.w(VD_SITE), VD_STOCK)
        self.assertEqual(cam.w(SITE), 0xFAF5BD03, 'frames without a time are no use: nothing hooked')
        self.assertEqual(cam.w(ACCEL_SITE), 0xE3A02000)

    def test_an_exclusive_owner_makes_it_back_off_and_write_nothing(self):
        owner = V.test_sup('ZZZ2', [(SITE, 0xFAF5BD03, 2, 0)])          # EXCL, claim only
        cam = self.boot(('10OWNER.BIN', owner), ('20GYR2.BIN', sup_bytes()))
        self.assertEqual(cam.w(SITE), 0xFAF5BD03)
        self.assertIn('RELEASED', [e[0] for e in cam.log()])

    def test_loads_beside_the_v3_lossless_sup_without_sharing_a_site(self):
        loss = ROOT / 'projects/usb-shell-sup/cards/20261006-v3-step2-lossless/fpSup/10LOSS.BIN'
        if not loss.exists():
            self.skipTest('no v3 lossless card on this machine')
        cam = self.boot(('10LOSS.BIN', loss.read_bytes()), ('20GYR2.BIN', sup_bytes()))
        loaded = [e[3] for e in cam.log() if e[0] == 'LOADED']
        self.assertEqual(loaded, ['10LOSS.BIN', '20GYR2.BIN'])
        sites = [a for a, _, _ in cam.journal()]
        self.assertEqual(sites.count(SITE), 1, 'only Gyro2 claims the header DMA')
        # lossless takes the frame at the save call after the header copy
        self.assertIn(0xC038BFF0, sites)
        self.assertEqual(cam.w(SITE) >> 24, 0xEB)

    def test_an_exclusive_owner_of_the_accel_site_also_makes_it_back_off(self):
        owner = V.test_sup('ZZZ4', [(ACCEL_SITE, 0xE3A02000, 2, 0)])    # EXCL, claim only
        cam = self.boot(('10OWNER.BIN', owner), ('20GYR2.BIN', sup_bytes()))
        self.assertEqual(cam.w(ACCEL_SITE), 0xE3A02000)
        self.assertEqual(cam.w(SITE), 0xFAF5BD03, 'the header site was claimed first, but not written')
        self.assertIn('RELEASED', [e[0] for e in cam.log()])

    def test_a_stale_hook_from_a_missed_power_off_is_repaired_then_rehooked(self):
        stale = {SITE: 0xEB000001}
        cam = self.boot(('20GYR2.BIN', sup_bytes()), stale=stale)
        self.assertEqual(cam.w(SITE) >> 24, 0xEB)
        self.assertNotEqual(cam.w(SITE), 0xEB000001)
        self.assertIn('REPAIRED', [e[0] for e in cam.log()])



# The coprocessor's gyro ring, as the camera lays it out (fpSup gyro_drain.S).
DESC_PTR = 0xC31E3FCC
RAM2E, P_OBJ, RING = 0x2E000000, 0x2E006004, 0x2E00644C
SPAN = 0x12C0                      # 600 records of 8 bytes
PERIOD_PS = 400085400


def sample(k):
    """The value the fake coprocessor writes as its k-th record ever: x, y, z."""
    return ((k * 7) % 30000 - 15000, (-k * 3) % 20000 - 10000, k % 32768)


class Ring:
    def __init__(self, cam):
        self.cam, self.k = cam, 0                       # k: records ever written
        mu = cam.mu
        mu.mem_map(RAM2E, 0x10000)
        cam.put(DESC_PTR, P_OBJ)
        cam.put(P_OBJ + 0x60, RING)
        cam.put(RING, RING)                              # head offset 0

    def advance(self, n):
        for _ in range(n):
            off = (self.k % 600) * 8
            x, y, z = sample(self.k)
            self.cam.mu.mem_write(RING + 4 + off, struct.pack('<hhhh', x, y, 0x5A5A, z))
            self.k += 1
        self.cam.put(RING, RING + (self.k % 600) * 8)


def fire_accel(cam, xyz):
    """The driver publishing one reading: run ACCEL_SITE with r4 at the values."""
    mu = cam.mu
    cache = getattr(cam, '_cache', None) or cam._alloc(8)
    cam._cache = cache
    mu.mem_write(cache, struct.pack('<3h', *xyz))
    sent = {UC_ARM_REG_R0: 0x10, UC_ARM_REG_R5: 0x55, UC_ARM_REG_R6: 0x66, UC_ARM_REG_R7: 0x77,
            UC_ARM_REG_R8: 0x88, UC_ARM_REG_R9: 0x99, UC_ARM_REG_R10: 0xAA, UC_ARM_REG_R11: 0xBB}
    for reg, v in sent.items():
        mu.reg_write(reg, v)
    mu.reg_write(V.UC_ARM_REG_R2, 0xDEAD)
    mu.reg_write(V.UC_ARM_REG_R3, 0x33)
    mu.reg_write(UC_ARM_REG_R4, cache)
    sp = V.STACK - 0x2400
    mu.reg_write(UC_ARM_REG_SP, sp)
    stop = {}

    def until(mu_, addr, size, _):
        if addr in (ACCEL_SITE + 4, 0xC072EF00):
            stop['pc'] = addr
            mu_.emu_stop()
    h = mu.hook_add(V.UC_HOOK_CODE, until)
    try:
        mu.emu_start(ACCEL_SITE, 0, count=200_000)
    finally:
        mu.hook_del(h)
        if cam.error:
            raise cam.error
    ok = all(mu.reg_read(r) == v for r, v in sent.items()) and mu.reg_read(V.UC_ARM_REG_R3) == 0x33 \
        and mu.reg_read(UC_ARM_REG_R4) == cache and mu.reg_read(UC_ARM_REG_SP) == sp
    return {'pc': stop.get('pc'), 'r2': mu.reg_read(V.UC_ARM_REG_R2), 'regs_ok': ok}


def thumb_blx_target(site, word):
    """Decode a Thumb-2 BLX (T2) independently of the sup's encoder."""
    hw1, hw2 = word & 0xFFFF, word >> 16
    assert hw1 >> 11 == 0b11110 and hw2 & 0xD001 == 0xC000, f'{word:#x} is not BLX'
    s = (hw1 >> 10) & 1
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    i1, i2 = 1 - (j1 ^ s), 1 - (j2 ^ s)
    imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((hw1 & 0x3FF) << 12) | (((hw2 >> 1) & 0x3FF) << 2)
    if s:
        imm -= 1 << 25
    return (((site + 4) & ~3) + imm) & 0xFFFFFFFF


def fire_sync(cam, site, reg, low):
    """The interrupt reaching the movt at `site`: run it in Thumb, stop after it."""
    mu = cam.mu
    sent = {UC_ARM_REG_R0: 0x10, V.UC_ARM_REG_R1: 0x11, V.UC_ARM_REG_R2: 0x12, V.UC_ARM_REG_R3: 0x13,
            UC_ARM_REG_R4: 0x44, UC_ARM_REG_R5: 0x55, UC_ARM_REG_R6: 0x66, UC_ARM_REG_R7: 0x77,
            UC_ARM_REG_R8: 0x88, UC_ARM_REG_R9: 0x99, UC_ARM_REG_R10: 0xAA, UC_ARM_REG_R11: 0xBB}
    sent[reg] = low                                      # what the movw before it left
    for r, v in sent.items():
        mu.reg_write(r, v)
    sp = V.STACK - 0x2800
    mu.reg_write(UC_ARM_REG_SP, sp)
    stop = {}

    def until(mu_, addr, size, _):
        if addr == site + 4:
            stop['pc'] = addr
            mu_.emu_stop()
    h = mu.hook_add(V.UC_HOOK_CODE, until)
    try:
        mu.emu_start(site | 1, 0, count=200_000)
    finally:
        mu.hook_del(h)
        if cam.error:
            raise cam.error
    got = {r: mu.reg_read(r) for r in sent}
    want = dict(sent); want[reg] = 0xC31D0000 | low
    return {'pc': stop.get('pc'), 'regs_ok': got == want and mu.reg_read(UC_ARM_REG_SP) == sp,
            'reg': got[reg], 'thumb': bool(mu.reg_read(V.UC_ARM_REG_CPSR) & 0x20)}


def run_frame(cam, template_or_buf, count, src=None, dst=None, n=None):
    """Execute the site with the registers the firmware has there."""
    mu = cam.mu
    if src is None:
        n = len(template_or_buf)
        src = cam._alloc(n, 32)
        mu.mem_write(src, bytes(template_or_buf))
        dst = cam._alloc(n, 32)
    req = getattr(cam, '_req', None) or cam._alloc(0x1200)
    tag = getattr(cam, '_tag', None) or cam._alloc(0x200)
    cam._req, cam._tag = req, tag
    cam.put(tag + 0x174, count)
    desc = V.STACK - 0x3000
    mu.mem_write(desc, struct.pack('<4I', src, dst, n, 0x01000000))
    sentinels = {UC_ARM_REG_R4: 0x44440004, UC_ARM_REG_R7: 0x77770007, UC_ARM_REG_R8: 0x88880008,
                 UC_ARM_REG_R9: 0x99990009, UC_ARM_REG_R10: 0xAAAA000A, UC_ARM_REG_R11: 0xBBBB000B}
    for reg, v in sentinels.items():
        mu.reg_write(reg, v)
    mu.reg_write(UC_ARM_REG_R5, req)
    mu.reg_write(UC_ARM_REG_R6, tag)
    mu.reg_write(UC_ARM_REG_R0, desc)
    sp = V.STACK - 0x2000
    mu.reg_write(UC_ARM_REG_SP, sp)
    before = len(cam.dmas)
    stop = {}

    def until(mu_, addr, size, _):
        if addr in (AFTER, 0xC072EF00):
            stop['pc'] = addr
            mu_.emu_stop()
    h = mu.hook_add(V.UC_HOOK_CODE, until)
    try:
        mu.emu_start(SITE, 0, count=5_000_000)
    finally:
        mu.hook_del(h)
        if cam.error:
            raise cam.error
    regs_ok = all(mu.reg_read(r) == v for r, v in sentinels.items()) and \
        mu.reg_read(UC_ARM_REG_R5) == req and mu.reg_read(UC_ARM_REG_R6) == tag
    return {'src': src, 'dst': dst, 'n': n, 'desc': desc, 'dmas': cam.dmas[before:],
            'pc_after': stop.get('pc'), 'sp': mu.reg_read(UC_ARM_REG_SP), 'sp0': sp,
            'regs_ok': regs_ok, 'tmpl': bytes(mu.mem_read(src, n)),
            'frame': bytes(mu.mem_read(dst, n))}


@unittest.skipIf(V.Uc is None or not V.IMAGE.exists(), 'needs unicorn and the image')
class Frames(unittest.TestCase):
    """The two-buffer design (GYRO2_CAMERA_DESIGN.md 13): the level's hook
    drains the coprocessor ring into the gyro buffer at ~47 Hz; each frame
    slices exactly [last mark, this mark) from it, plus the ring's undrained
    tail."""

    US = 400                                   # per record, near enough

    def camera(self):
        files, dirs = V.card(('20GYR2.BIN', sup_bytes()))
        cam = Cam(files, dirs)
        cam.boot()
        cam.ring = Ring(cam)
        loaded = [e for e in cam.log() if e[0] == 'LOADED' and e[3] == '20GYR2.BIN']
        cam.block = loaded[0][1]
        cam.vars = cam.block + V.B.SL_HEADER_LEN + SYM['vars']
        cam.k0 = None
        return cam

    def var(self, cam, off):
        return cam.w(cam.vars + off)

    def flow(self, cam, n, accel=True, every=53, xyz=(10, -1000, -200)):
        """n records at 2.5 kHz in real time; the level fires every `every`."""
        left = n
        while left:
            k = min(every, left)
            cam.ring.advance(k)
            cam.now += k * self.US
            left -= k
            if accel and k == every:
                fire_accel(cam, xyz)
                if cam.k0 is None:                       # the first drain arms the stream:
                    cam.k0 = cam.ring.k                  # global index 0 is the next record

    def frame(self, cam, count, hdr=None, prev=None):
        if prev is None:
            return run_frame(cam, hdr, count=count)
        return run_frame(cam, None, count=count, src=prev['src'], dst=prev['dst'], n=prev['n'])

    def sample_hdr(self, key='fhd'):
        p = find_sample(SAMPLES[key])
        if p is None:
            self.skipTest(f'sample {key} not on this machine')
        return header_of(p)

    def take(self, cam, hdr, frames, per_frame=83, history=600, accel=True):
        self.flow(cam, history, accel=accel)
        out, s = [], None
        for i in range(frames):
            if i:
                self.flow(cam, per_frame, accel=accel)
            s = self.frame(cam, 3 + i, hdr=hdr, prev=s)
            out.append(s)
        return out

    def records(self, cam, r):
        """What the block should hold, from the fake coprocessor's history."""
        origin = cam.ring.k - 0                          # unused; kept for symmetry
        return r['samples']

    def check_exact(self, cam, recs, last_k):
        """Blocks tile the stream: each starts where the last ended, and the
        newest block ends at the newest record written."""
        for a, b in zip(recs, recs[1:]):
            self.assertEqual(b['base_idx'], a['base_idx'] + a['n_samples'])
            self.assertEqual(a['frame_mark'], a['n_samples'])
        self.assertEqual(recs[-1]['samples'][-1], sample(last_k))

    def test_blocks_are_exactly_the_frames_intervals(self):
        for key in SAMPLES:
            with self.subTest(key):
                hdr = self.sample_hdr(key)
                toff, _ = expected_tail(hdr)
                cam = self.camera()
                frames = self.take(cam, hdr, frames=5)
                recs = [F.read_frame(s['frame']) for s in frames]
                self.assertEqual([r['n_samples'] for r in recs], [250, 83, 83, 83, 83])
                self.assertEqual([r['base_idx'] for r in recs], [0, 250, 333, 416, 499])
                self.check_exact(cam, recs, cam.ring.k - 1)
                # every sample is the record it should be
                flat = [x for r in recs for x in r['samples']]
                first_k = cam.ring.k - len(flat)
                self.assertEqual(flat, [sample(first_k + j) for j in range(len(flat))])
                for i, (s, r) in enumerate(zip(frames, recs)):
                    self.assertEqual(r['at'], toff + GAP)
                    self.assertEqual(s['pc_after'], AFTER)
                    self.assertEqual(len(s['dmas']), 1)
                    self.assertTrue(s['regs_ok'])
                    self.assertEqual(s['sp'], s['sp0'])
                    self.assertEqual(s['frame'], s['tmpl'])
                    self.assertEqual(r['flags'], F.F_FIRST | F.F_LENS if i == 0 else 0)
                    self.assertEqual((r['readout_ns'], r['mode_id'], r['crop_w'], r['crop_h']), (10555556, 106, 6000, 4000))
                    self.assertEqual(r['frame_seq'], i)

    def test_each_block_ends_on_the_newest_record_even_between_drains(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.flow(cam, 30)                              # no drain since: all in the ring
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertEqual((r['n_samples'], r['base_idx']), (30, 250))
        self.assertEqual(r['samples'], [sample(cam.ring.k - 30 + j) for j in range(30)])
        self.flow(cam, 60)                              # one drain in the middle
        s = self.frame(cam, 5, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertEqual((r['n_samples'], r['base_idx']), (60, 280))
        self.assertEqual(r['samples'], [sample(cam.ring.k - 60 + j) for j in range(60)])

    def test_a_one_second_stall_loses_nothing_while_the_level_drains(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=2)
        self.flow(cam, 2500)                            # MovRec held up a second
        s = self.frame(cam, 5, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertFalse(r['flags'] & F.F_LOST)
        self.assertTrue(r['flags'] & F.F_TRUNC)         # more than the tail holds: the newest
        self.assertEqual(r['base_idx'] + r['n_samples'], 333 + 2500)
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))
        self.assertEqual(r['frame_seq'], 2, 'not a new take')
        self.assertEqual(r['samples'][0], sample(cam.ring.k - r['n_samples']), 'from the buffer, intact')

    def test_a_stall_longer_than_the_buffer_is_lost(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.flow(cam, 8192 + 2000)
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertTrue(r['flags'] & F.F_LOST)
        self.assertEqual(r['base_idx'] + r['n_samples'], 250 + 8192 + 2000)
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))

    def test_with_the_level_silent_frames_read_the_ring_until_it_runs_out(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        w = self.var(cam, 56)
        recs = [F.read_frame(a[0]['frame'])]
        for i in range(6):                              # 30 + 6 x 83 = 528 < 584: still in the ring
            self.flow(cam, 83, accel=False)
            recs.append(F.read_frame(self.frame(cam, 4 + i, prev=a[0])['frame']))
        self.assertEqual(self.var(cam, 56), w, 'the frame hook never writes the buffer')
        self.assertEqual([r['flags'] & F.F_LOST for r in recs], [0] * 7)
        self.check_exact(cam, recs, cam.ring.k - 1)
        self.flow(cam, 83, accel=False)                 # 611 undrained: past what the ring keeps
        r = F.read_frame(self.frame(cam, 10, prev=a[0])['frame'])
        self.assertTrue(r['flags'] & F.F_LOST)
        self.assertEqual(r['base_idx'] + r['n_samples'], recs[-1]['base_idx'] + recs[-1]['n_samples'] + 83)
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))

    def test_level_silent_and_a_long_stall_is_lost_but_the_timeline_holds(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.flow(cam, 700, accel=False)                # nobody drained for 280 ms
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertTrue(r['flags'] & F.F_LOST)
        self.assertEqual(r['base_idx'] + r['n_samples'], 250 + 700)
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))
        n = r['n_samples']
        self.assertLessEqual(n, 584, 'only what the ring still holds')
        self.assertEqual(r['samples'], [sample(cam.ring.k - n + j) for j in range(n)])

    def test_the_level_back_after_a_long_quiet_counts_the_laps(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.flow(cam, 1500, accel=False)               # 600 ms of quiet: two and a half laps
        fire_accel(cam, (5, 5, 5))
        w = cam.ring.k - cam.k0
        self.assertEqual(self.var(cam, 56), w, 'the index counts every record, lost or not')
        self.assertEqual(self.var(cam, 72), w - 584, 'the oldest the ring still held is the lowest usable')
        self.flow(cam, 20, accel=False)
        r = F.read_frame(self.frame(cam, 4, prev=a[0])['frame'])
        self.assertTrue(r['flags'] & F.F_LOST)
        self.assertEqual(r['base_idx'] + r['n_samples'], 250 + 1500 + 20)
        n = r['n_samples']
        self.assertEqual(r['samples'], [sample(cam.ring.k - n + j) for j in range(n)])

    def test_each_drain_keeps_the_set_before_it(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        self.take(cam, hdr, frames=1)
        before = [self.var(cam, o) for o in (56, 60, 72)]
        seq = self.var(cam, 124)
        self.flow(cam, 53)
        self.assertEqual([self.var(cam, o) for o in (128, 132, 136)], before)
        self.assertEqual(self.var(cam, 124), seq + 2, 'odd while writing, even after')
        self.assertNotEqual(self.var(cam, 56), before[0])

    def test_vendor_bytes_in_our_place_are_not_written_over(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        woff = self.var(cam, 16)
        junk = b'VEND' + bytes(range(1, 61))
        cam.mu.mem_write(a[0]['src'] + woff, junk)      # the template changed under us
        self.flow(cam, 83)
        s = self.frame(cam, 4, prev=a[0])
        self.assertEqual(s['frame'][woff:woff + 64], junk)
        r = F.read_frame(s['frame'])
        self.assertGreater(r['at'], woff, 'placed after the new bytes')

    def test_vd_lands_in_its_frame_with_its_time(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        cam.ring.advance(10); cam.now += 10 * self.US
        fire_sync(cam, VD_SITE, UC_ARM_REG_R4, 0x89C0)       # 10 records into the frame
        t_vd = cam.now
        cam.ring.advance(73); cam.now += 73 * self.US
        fire_sync(cam, VD_SITE, UC_ARM_REG_R4, 0x89C0)       # exactly at the mark: the next block's
        r = F.read_frame(self.frame(cam, 4, prev=a[0])['frame'])
        sync = [(pos, kind, struct.unpack('<I', v)[0]) for pos, kind, v in r['events'] if kind == 3]
        self.assertEqual(sync, [(10, 3, t_vd & 0xFFFFFFFF)])
        self.assertEqual(r['n_events'], len(r['events']))
        self.assertEqual(r['rest'], 0, 'the payload length covers the events')
        cam.ring.advance(83); cam.now += 83 * self.US
        r = F.read_frame(self.frame(cam, 5, prev=a[0])['frame'])
        self.assertEqual([(pos, kind) for pos, kind, _ in r['events'] if kind == 3], [(0, 3)])

    def test_a_vd_before_any_drain_is_not_recorded(self):
        cam = self.camera()
        f = fire_sync(cam, VD_SITE, UC_ARM_REG_R4, 0x89C0)   # the level has not run: no stream yet
        self.assertTrue(f['regs_ok'])
        self.assertEqual(self.var(cam, 140), 0)
        self.flow(cam, 60)
        fire_sync(cam, VD_SITE, UC_ARM_REG_R4, 0x89C0)
        self.assertEqual(self.var(cam, 140), 1)

    def test_level_readings_land_in_their_frame_at_their_place(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        cam.ring.advance(20); cam.now += 20 * self.US
        fire_accel(cam, (100, -200, 1024))              # 20 records into the frame
        cam.ring.advance(40); cam.now += 40 * self.US
        fire_accel(cam, (101, -201, 1023))              # 60 in
        cam.ring.advance(23); cam.now += 23 * self.US
        fire_accel(cam, (7, 7, 7))                      # exactly at the mark: the next block's
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        ev = [(pos, kind, struct.unpack('<3h', v)) for pos, kind, v in r['events']]
        self.assertEqual(ev, [(20, 1, (100, -200, 1024)), (60, 1, (101, -201, 1023))])
        self.assertEqual((r['n_samples'], r['n_events'], r['rest']), (83, 2, 0))
        cam.ring.advance(83); cam.now += 83 * self.US
        s = self.frame(cam, 5, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertEqual([(pos, struct.unpack('<3h', v)) for pos, _, v in r['events']], [(0, (7, 7, 7))])

    def test_readings_from_before_the_take_are_not_carried(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        self.flow(cam, 2000)                            # many readings before recording
        s = self.frame(cam, 3, hdr=hdr)
        r = F.read_frame(s['frame'])
        # the 250 backfilled records span ~4.7 readings; older ones are skipped
        self.assertLessEqual(len(r['events']), 5)
        self.assertTrue(all(0 <= pos < 250 for pos, _, _ in r['events']))

    def test_a_new_take_starts_over(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=3)
        self.flow(cam, 1000)
        s = self.frame(cam, 3, prev=a[0])               # the counter restarts
        r = F.read_frame(s['frame'])
        self.assertEqual((r['frame_seq'], r['base_idx'], r['n_samples'], r['flags']), (0, 0, 250, F.F_FIRST | F.F_LENS))
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))
        self.assertNotEqual(r['clip_id'], F.read_frame(a[0]['frame'])['clip_id'])

    def test_a_reader_that_preempts_a_drain_uses_the_kept_set(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.flow(cam, 53)                              # drained: W moved on
        w, dh = self.var(cam, 56), self.var(cam, 60)
        # freeze a drain half-way: odd sequence, W already advanced by 100
        # past what dhead says -- only the kept set is consistent
        cam.put(cam.vars + 128, w)                      # V_PW
        cam.put(cam.vars + 132, dh)                     # V_PDH
        cam.put(cam.vars + 136, self.var(cam, 72))      # V_PLU
        cam.put(cam.vars + 56, w + 100)
        cam.put(cam.vars + 124, self.var(cam, 124) | 1)
        cam.ring.advance(30); cam.now += 30 * self.US
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertEqual((r['base_idx'], r['n_samples']), (250, 53 + 30))
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))

    def test_garbage_templates_are_skipped_but_still_copied(self):
        cam = self.camera()
        self.flow(cam, 600)
        for i, junk in enumerate((b'\0' * 0x400, b'MM\0\x2a' + b'\0' * 0x3FC)):
            s = run_frame(cam, junk, count=3 + i)
            self.assertEqual(len(s['dmas']), 1)
            self.assertEqual(s['frame'], junk)
            self.assertTrue(s['regs_ok'])
        hdr = self.sample_hdr()
        self.flow(cam, 83)
        s = run_frame(cam, hdr, count=5)
        r = F.read_frame(s['frame'])
        self.assertEqual((r['base_idx'], r['n_samples']), (250, 83), 'the stream went on under the skipped frame')

    def test_a_short_tail_keeps_the_newest_records(self):
        hdr = bytearray(self.sample_hdr())
        toff, tlen = expected_tail(bytes(hdr))
        keep = GAP + 64 + 192 + 6 * (100 + 84) + 3       # 184 samples; 100 beside the lens table (192: EV_RESERVE)
        hdr[toff:toff + tlen - keep] = b'\x33' * (tlen - keep)
        end = toff + tlen
        hdr[end:end + 1024] = b'\0' * 1024
        cam = self.camera()
        frames = self.take(cam, bytes(hdr), frames=2, per_frame=130)
        r0, r1 = (F.read_frame(s['frame']) for s in frames)
        self.assertEqual((r0['n_samples'], r0['base_idx'], r0['flags'] & F.F_TRUNC), (100, 150, F.F_TRUNC))
        self.assertEqual((r1['n_samples'], r1['base_idx'], r1['flags']), (130, 250, 0))
        self.assertEqual(r1['samples'][-1], sample(cam.ring.k - 1))

    def test_the_mode_is_read_once_a_take(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        self.take(cam, hdr, frames=3)
        self.assertEqual(cam.mode_calls, ['mode', (F_TIMING, 106), (F_GEOM, 106)])

    def test_the_lens_table_is_the_cameras_bytes(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        cam.mu.mem_write(LENS_FOCAL, struct.pack('<I', 394))
        cam.mu.mem_write(LENS_AXIS, struct.pack('<5I', 0, 18641, 37283, 49637, 55924))
        nodes = [1.0 + k * 1e-3 for k in range(60)]
        cam.mu.mem_write(LENS_NODES, struct.pack('<60d', *nodes))
        r = F.read_frame(self.take(cam, hdr, frames=1)[0]['frame'])
        self.assertEqual(r['lens'], (394, (0, 18641, 37283, 49637, 55924), tuple(nodes)))

    def test_an_unreadable_ring_writes_an_empty_lost_block(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        cam.put(DESC_PTR, 0)
        s = run_frame(cam, hdr, count=3)
        r = F.read_frame(s['frame'])
        self.assertEqual((r['n_samples'], r['flags'] & F.F_LOST), (0, F.F_LOST))
        self.assertEqual(len(s['dmas']), 1)

    def test_the_drain_takes_a_head_parked_at_the_ring_end(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1, history=600 - 83 + 53 * 0)
        left = 600 - cam.ring.k % 600
        self.flow(cam, left, accel=False)               # head now at offset 0 ...
        cam.put(RING, RING + SPAN)                      # ... but parked at the end
        fire_accel(cam, (1, 1, 1))
        self.assertEqual(self.var(cam, 60), 0, 'the level drained it: the head is at offset 0')
        self.assertEqual(self.var(cam, 56), cam.ring.k - cam.k0)
        cam.ring.advance(10); cam.now += 4000
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertFalse(r['flags'] & F.F_LOST)
        self.assertEqual(r['samples'][-1], sample(cam.ring.k - 1))
        self.assertEqual(r['n_samples'], left + 10)


if __name__ == '__main__':
    unittest.main()
