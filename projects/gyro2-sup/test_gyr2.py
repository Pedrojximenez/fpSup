#!/usr/bin/env python3
"""Gyro2 (stage P1) under unicorn: the real loader v3 (fpSup's sloader, as the
AutoRun spells it) loads 40GYR2.BIN from a card, then the tag observer is
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

SITE, SITE_STOCK = 0xC038C77C, 0xFAF5BD03         # the header DMA: not ours any more
TEMPLATE_PTR, TEMPLATE_LEN = 0xC358DBA8, 0xC358DBA4
ACCEL_SITE = 0xC050D4C8
VD_SITE, VD_STOCK = 0xC0125480, 0x341DF2CC          # Thumb: movt r4, #0xC31D
MODE_FN, F_TIMING, F_GEOM = 0xC032C720, 0xC0320FC8, 0xC0321028
F_SUBJECT, F_ATTACH, F_RATE, F_ADD_TAG = 0xC00577F0, 0xC00D2958, 0xC00C9BD0, 0xC00BA378
STOP = 0xC072EF00                  # a return address nothing else uses
LENS_FOCAL = 0xC307CDF0
MAGIC = b'FSG2'
GTAG_BYTES = 4096                  # the tag the observer adds (what it sizes for 23.976p and slower)
EV_RESERVE = 24 * 10 + 6 * 8

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


def with_gtag(hdr, n=GTAG_BYTES, shift=2):
    """The template as the firmware builds it with our observer: the
    MakerNote's last entry (0x0200) becomes our tag, its value appended past
    the header, `shift` bytes off a word boundary.  Returns (template,
    the block's offset)."""
    hdr = bytearray(hdr)
    mn_off, _ = F.maker_note(bytes(hdr))
    cnt = struct.unpack_from('<H', hdr, mn_off + 10)[0]
    e = mn_off + 12 + 12 * (cnt - 1)
    assert struct.unpack_from('<H', hdr, e)[0] == 0x200
    at = len(hdr) + shift
    struct.pack_into('<HHII', hdr, e, F.GTAG, 7, n, at)
    hdr += b'\0' * (shift + n)
    hdr += b'\0' * (-len(hdr) % 0x400)
    return bytes(hdr), (at + 3) & ~3


def capacity(n=GTAG_BYTES, shift=2):
    room = n - ((-(shift)) % 4 if shift % 4 else 0)
    return (room - 60 - EV_RESERVE) // 6


class Cam(V.Camera):
    """test_v3's camera plus the firmware routines Gyro2 calls."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for a_ in (MODE_FN, F_TIMING, F_GEOM, F_SUBJECT, F_ATTACH, F_RATE, F_ADD_TAG):
            self.mu.mem_write(a_, struct.pack('<I', 0xE12FFF1E))
        # The Subject: nine slots, the stock six observers in the first six.
        self.subject = self._alloc(0x28)
        self.mu.mem_write(self.subject, struct.pack('<10I', *([0xC3498D5C] * 6 + [0] * 4)))
        self.attached = []
        self.rate = (24000, 1001)
        self.added = []
        # The mode the accessors report: 106, hmax 380 clocks x 2000 lines at
        # 72 MHz = 10.555556 ms; 3000 wide, 2 x 2 binning = the whole sensor.
        self.mode = 106
        self.t_row = self._alloc(0x20)
        self.g_row = self._alloc(0x60)
        self.mu.mem_write(self.t_row, struct.pack('<IH', 0, 380))
        self.mu.mem_write(self.g_row, struct.pack('<III', 0, 3000, 2000))
        self.mu.mem_write(self.g_row + 0x44, struct.pack('<II', 2, 2))
        self.mu.mem_write(LENS_FOCAL, struct.pack('<I', 394))
        self.mode_calls = []

    def _hook(self, mu, addr, size, data):
        if addr == MODE_FN:
            self.mode_calls.append('mode')
            return self._ret(self.mode)
        if addr in (F_TIMING, F_GEOM):
            self.mode_calls.append((addr, self.r(V.UC_ARM_REG_R1)))
            return self._ret(self.t_row if addr == F_TIMING else self.g_row)
        if addr == F_SUBJECT:
            return self._ret(self.subject)
        if addr == F_ATTACH:
            subj, obs = self.r(UC_ARM_REG_R0), self.r(V.UC_ARM_REG_R1)
            self.attached.append((subj, obs))
            slots = list(struct.unpack('<9I', mu.mem_read(subj, 36)))
            assert 0 in slots, 'a full Subject asserts on the camera'
            self.put(subj + 4 * slots.index(0), obs)
            return self._ret(0)
        if addr == F_RATE:
            mu.mem_write(self.r(UC_ARM_REG_R0), struct.pack('<2I', *self.rate))
            return self._ret(0)
        if addr == F_ADD_TAG:
            sp = self.r(UC_ARM_REG_SP)
            count, src = struct.unpack('<2I', mu.mem_read(sp, 8))
            self.added.append((self.r(UC_ARM_REG_R0), self.r(V.UC_ARM_REG_R1), self.r(V.UC_ARM_REG_R2),
                               self.r(V.UC_ARM_REG_R3), count, bytes(mu.mem_read(src, count)), sp & 7))
            return self._ret(1)
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

    def test_loads_and_leaves_the_header_dma_alone(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        names = [e for e in cam.log() if e[0] in ('LOADED', 'RELEASED')]
        self.assertEqual(names[-1][0], 'LOADED', cam.log())
        self.assertEqual(cam.w(SITE), SITE_STOCK, 'frames are written from the tag observer')
        self.assertNotIn(SITE, [a for a, _, _ in cam.journal()])

    def test_another_layer_at_the_header_dma_is_no_concern(self):
        other = 0xEB000000 | (((0xC072EF00 - (SITE + 8)) >> 2) & 0xFFFFFF)   # BL somewhere
        first = V.test_sup('ZZZ1', [(SITE, SITE_STOCK, 2, other)])          # even EXCL
        cam = self.boot(('10OTHER.BIN', first), ('40GYR2.BIN', sup_bytes()))
        kinds = [e[0] for e in cam.log()]
        self.assertEqual(kinds.count('LOADED'), 2, cam.log())
        self.assertNotIn('RELEASED', kinds)
        self.assertEqual(cam.w(SITE), other)
        self.assertEqual(len(cam.attached), 1)

    def test_the_accel_site_stacks_on_an_earlier_layer(self):
        other = 0xEB000000 | (((0xC072EF00 - (ACCEL_SITE + 8)) >> 2) & 0xFFFFFF)
        first = V.test_sup('ZZZ3', [(ACCEL_SITE, 0xE3A02000, 1, other)])
        cam = self.boot(('10OTHER.BIN', first), ('40GYR2.BIN', sup_bytes()))
        kinds = [e[0] for e in cam.log()]
        self.assertEqual(kinds.count('LOADED'), 2, cam.log())
        self.assertNotEqual(cam.w(ACCEL_SITE), other)
        f = fire_accel(cam, (1, 2, 3))
        self.assertEqual(f['pc'], 0xC072EF00, 'the reading went on to the layer below')
        self.assertEqual(f['r2'], 0xDEAD, 'and that layer, not us, replays mov r2, #0')

    def test_alone_at_the_accel_site_it_replays_the_displaced_instruction(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        f = fire_accel(cam, (1, 2, 3))
        self.assertEqual(f['pc'], ACCEL_SITE + 4, 'back to the driver')
        self.assertEqual(f['r2'], 0, 'mov r2, #0, as the stock site did')
        self.assertTrue(f['regs_ok'])

    def test_the_vd_interrupt_is_hooked_through_an_arm_veneer(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        veneer = thumb_blx_target(VD_SITE, cam.w(VD_SITE))
        self.assertEqual(veneer % 4, 0)
        self.assertTrue(V.cave.CAVE_ARENA <= veneer < V.cave.CAVE_ARENA_END, f'{veneer:#x}')
        self.assertEqual(cam.w(veneer), 0xE51FF004)
        self.assertIn((VD_SITE, 4, struct.pack('<I', VD_STOCK)), cam.journal())
        self.assertEqual(cam.w(0xC01255C8), 0x351DF2CC, 'IRQ 0x7f is left alone')

    def test_the_vd_hook_replays_its_movt_and_keeps_every_register(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        f = fire_sync(cam, VD_SITE, UC_ARM_REG_R4, 0x89C0)
        self.assertEqual(f['pc'], VD_SITE + 4, 'back in the handler')
        self.assertTrue(f['thumb'], 'and in Thumb state')
        self.assertEqual(f['reg'], 0xC31D89C0)
        self.assertTrue(f['regs_ok'])

    def test_an_owner_of_the_vd_site_makes_it_back_off_and_write_nothing(self):
        owner = V.test_sup('ZZZ5', [(VD_SITE, VD_STOCK, 2, 0)])      # EXCL, claim only
        cam = self.boot(('10OWNER.BIN', owner), ('40GYR2.BIN', sup_bytes()))
        self.assertIn('RELEASED', [e[0] for e in cam.log()])
        self.assertEqual(cam.w(VD_SITE), VD_STOCK)
        self.assertEqual(cam.attached, [], 'frames without a time are no use: nothing attached')
        self.assertEqual(cam.w(ACCEL_SITE), 0xE3A02000)

    def test_loads_beside_the_v3_lossless_sup_without_sharing_a_site(self):
        loss = ROOT / 'projects/usb-shell-sup/cards/20261006-v3-step2-lossless/fpSup/10LOSS.BIN'
        if not loss.exists():
            self.skipTest('no v3 lossless card on this machine')
        cam = self.boot(('10LOSS.BIN', loss.read_bytes()), ('40GYR2.BIN', sup_bytes()))
        loaded = [e[3] for e in cam.log() if e[0] == 'LOADED']
        self.assertEqual(loaded, ['10LOSS.BIN', '40GYR2.BIN'])
        sites = [a for a, _, _ in cam.journal()]
        self.assertNotIn(SITE, sites)
        # lossless takes the frame at the save call after the header copy
        self.assertIn(0xC038BFF0, sites)
        self.assertEqual(len(cam.attached), 1)

    def test_an_exclusive_owner_of_the_accel_site_also_makes_it_back_off(self):
        owner = V.test_sup('ZZZ4', [(ACCEL_SITE, 0xE3A02000, 2, 0)])    # EXCL, claim only
        cam = self.boot(('10OWNER.BIN', owner), ('40GYR2.BIN', sup_bytes()))
        self.assertEqual(cam.w(ACCEL_SITE), 0xE3A02000)
        self.assertEqual(cam.attached, [])
        self.assertIn('RELEASED', [e[0] for e in cam.log()])

    def test_the_tag_observer_is_attached_to_the_subject(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        self.assertEqual(len(cam.attached), 1)
        subj, obs = cam.attached[0]
        self.assertEqual(subj, cam.subject)
        self.assertEqual(cam.w(cam.subject + 24), obs, 'in the first free slot')
        loaded = [e for e in cam.log() if e[0] == 'LOADED']
        blk = loaded[-1][1]
        self.assertTrue(blk <= obs < blk + 0x2000, 'the observer lives in our resident block')
        handler = cam.w(cam.w(obs) + 12)
        self.assertEqual(handler, blk + V.B.SL_HEADER_LEN + SYM['tag_observer'])

    def test_a_full_subject_makes_it_back_off_and_write_nothing(self):
        files, dirs = V.card(('40GYR2.BIN', sup_bytes()))
        cam = Cam(files, dirs)
        cam.mu.mem_write(cam.subject, struct.pack('<9I', *([0xC3498D5C] * 9)))
        cam.boot()
        self.assertEqual(cam.attached, [])
        self.assertIn('RELEASED', [e[0] for e in cam.log()])
        self.assertEqual(cam.w(ACCEL_SITE), 0xE3A02000)
        self.assertEqual(cam.w(VD_SITE), VD_STOCK)

    def test_a_cinemadng_take_start_adds_our_tag_sized_for_its_rate(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        for rate, n in (((24000, 1001), 105 * 24 + 351), ((30000, 1001), 84 * 24 + 351),
                        ((120000, 1001), 21 * 24 + 351), ((280000, 1001), 9 * 24 + 351),
                        ((18000, 1000), 139 * 24 + 351), ((10000, 1000), 4096), ((0, 0), 4096), ((0, 1001), 4096), ((24000, 0), 4096)):
            cam.rate = rate
            f = notify(cam, 0, 3)
            self.assertEqual((f['pc'], f['r0']), (STOP, 1), 'returns 1: 0 would detach it')
            self.assertTrue(f['regs_ok'])
            self.assertEqual(len(f['added']), 1, rate)
            b, ifd, tag, typ, count, data, sp7 = f['added'][0]
            self.assertEqual((b, ifd, tag, typ, count), (0xB0B0B0B0, 5, F.GTAG, 7, n), rate)
            self.assertEqual(data, b'\0' * n, 'it starts as zeros')
            self.assertEqual(sp7, 0, 'the stack is 8-aligned at the call')
            self.assertGreaterEqual((n - 3 - 60 - EV_RESERVE) // 6, min(4 * -(-2500 * rate[1] // rate[0]) if rate[0] else 0, 624))

    def test_other_notifies_add_nothing(self):
        cam = self.boot(('40GYR2.BIN', sup_bytes()))
        for mode, typ, builder in ((0, 4, 0xB0B0B0B0), (0, 5, 0xB0B0B0B0), (3, 3, 0xB0B0B0B0),
                                   (2, 3, 0xB0B0B0B0), (1, 3, 0xB0B0B0B0), (5, 3, 0xB0B0B0B0),
                                   (6, 3, 0xB0B0B0B0), (0, 3, 0)):
            f = notify(cam, mode, typ, builder)
            self.assertEqual((f['pc'], f['r0'], f['added']), (STOP, 1, []), (mode, typ, builder))
            self.assertTrue(f['regs_ok'])

    def test_a_stale_hook_from_a_missed_power_off_is_repaired_then_rehooked(self):
        stale = {ACCEL_SITE: 0xEB000001}
        cam = self.boot(('40GYR2.BIN', sup_bytes()), stale=stale)
        self.assertEqual(cam.w(ACCEL_SITE) >> 24, 0xEB)
        self.assertNotEqual(cam.w(ACCEL_SITE), 0xEB000001)
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


def notify(cam, mode, typ, builder=0xB0B0B0B0):
    """The Subject calling our handler as FUN_c0055fe0 does: (obs, DataPool)."""
    mu = cam.mu
    obs = cam.attached[0][1] if cam.attached else cam.w(cam.subject + 24)
    pools = cam.__dict__.setdefault('pools', {})
    if (mode, typ, builder) not in pools:           # one DataPool per event, made once
        ev = cam._alloc(12)
        mu.mem_write(ev, struct.pack('<3I', mode, typ, 0))
        code = cam._alloc(16)                       # two getters: ldr r0, [pc]; bx lr; .word v
        mu.mem_write(code, struct.pack('<4I', 0xE59F0000, 0xE12FFF1E, ev, 0))
        get_b = cam._alloc(12)
        mu.mem_write(get_b, struct.pack('<3I', 0xE59F0000, 0xE12FFF1E, builder))
        vt = cam._alloc(0x60)
        mu.mem_write(vt, b'\0' * 0x60)
        cam.put(vt + 0x40, code)
        cam.put(vt + 0x2C, get_b)
        dp = cam._alloc(8)
        cam.put(dp, vt)
        pools[(mode, typ, builder)] = dp
    dp = pools[(mode, typ, builder)]
    mu.reg_write(UC_ARM_REG_R0, obs)
    mu.reg_write(V.UC_ARM_REG_R1, dp)
    sent = {UC_ARM_REG_R4: 0x44, UC_ARM_REG_R5: 0x55, UC_ARM_REG_R6: 0x66, UC_ARM_REG_R7: 0x77,
            UC_ARM_REG_R8: 0x88, UC_ARM_REG_R9: 0x99, UC_ARM_REG_R10: 0xAA, UC_ARM_REG_R11: 0xBB}
    for r, v in sent.items():
        mu.reg_write(r, v)
    sp = V.STACK - 0x2800
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_LR, STOP)
    before = len(cam.added)
    stop = {}

    def until(mu_, addr, size, _):
        if addr == STOP:
            stop['pc'] = addr
            mu_.emu_stop()
    h = mu.hook_add(V.UC_HOOK_CODE, until)
    try:
        mu.emu_start(cam.w(cam.w(obs) + 12), 0, count=5_000_000)
    finally:
        mu.hook_del(h)
        if cam.error:
            raise cam.error
    ok = all(mu.reg_read(r) == v for r, v in sent.items()) and mu.reg_read(UC_ARM_REG_SP) == sp
    return {'r0': mu.reg_read(UC_ARM_REG_R0), 'pc': stop.get('pc'), 'regs_ok': ok, 'added': cam.added[before:]}



def run_frame(cam, template_or_buf, count, src=None, dst=None, n=None):
    """A frame as the firmware gives it to us now: the template where the MovRec
    singleton keeps it, then the frame's notify (mode 3).  count == 3 -- the old
    tag counter's first value -- is a take's first frame: the mode-2 notify of
    the serialized template comes first.  The DMA after is the firmware's, so
    'frame' is the template as it would copy it."""
    mu = cam.mu
    if src is None:
        n = len(template_or_buf)
        src = cam._alloc(n, 32)
        mu.mem_write(src, bytes(template_or_buf))
    cam.put(TEMPLATE_PTR, src)
    cam.put(TEMPLATE_LEN, n)
    ok = True
    if count == 3:
        f = notify(cam, 2, 3)
        ok = f['regs_ok'] and f['pc'] == STOP and f['r0'] == 1
    f = notify(cam, 3, 3)
    ok = ok and f['regs_ok'] and f['r0'] == 1
    t = bytes(mu.mem_read(src, n))
    return {'src': src, 'dst': None, 'n': n, 'pc_after': f['pc'], 'regs_ok': ok,
            'sp': 0 if ok else 1, 'sp0': 0, 'tmpl': t, 'frame': t}


@unittest.skipIf(V.Uc is None or not V.IMAGE.exists(), 'needs unicorn and the image')
class Frames(unittest.TestCase):
    """The two-buffer design (GYRO2_CAMERA_DESIGN.md 13): the level's hook
    drains the coprocessor ring into the gyro buffer at ~47 Hz; each frame
    slices exactly [last mark, this mark) from it, plus the ring's undrained
    tail."""

    US = 400                                   # per record, near enough

    def camera(self):
        files, dirs = V.card(('40GYR2.BIN', sup_bytes()))
        cam = Cam(files, dirs)
        cam.boot()
        cam.ring = Ring(cam)
        loaded = [e for e in cam.log() if e[0] == 'LOADED' and e[3] == '40GYR2.BIN']
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

    def sample_hdr(self, key='fhd', **k):
        p = find_sample(SAMPLES[key])
        if p is None:
            self.skipTest(f'sample {key} not on this machine')
        return with_gtag(header_of(p), **k)[0]

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
                at = with_gtag(header_of(find_sample(SAMPLES[key])))[1]
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
                    self.assertEqual(r['at'], at)
                    self.assertEqual(r['at'] % 4, 0)
                    self.assertEqual(r['writer'], G.VERSION)
                    self.assertEqual(s['pc_after'], STOP)
                    self.assertTrue(s['regs_ok'])
                    self.assertEqual(s['sp'], s['sp0'])
                    self.assertEqual(s['frame'], s['tmpl'])
                    self.assertEqual(r['flags'], F.F_FIRST if i == 0 else 0)
                    self.assertEqual((r['fmt'], r['mode_id'], r['hmax'], r['read_w'], r['lines'], r['bin_h'], r['bin_v']),
                                     (2, 106, 380, 3000, 2000, 2, 2))
                    self.assertEqual(r['calib_focal'], 394)
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
        c = capacity()
        self.assertFalse(r['flags'] & F.F_LOST)
        # more than the tag holds: the oldest now, the rest with the next frames
        self.assertEqual((r['base_idx'], r['n_samples'], r['frame_mark']), (333, c, 2500))
        self.assertEqual(r['samples'][0], sample(cam.ring.k - 2500), 'from the buffer, intact')
        self.assertEqual(r['frame_seq'], 2, 'not a new take')
        recs, n = [r], 3
        while recs[-1]['base_idx'] + recs[-1]['n_samples'] < 333 + 2500 + 83 * (n - 3):
            self.flow(cam, 83)
            recs.append(F.read_frame(self.frame(cam, 3 + n, prev=a[0])['frame']))
            n += 1
        self.assertEqual(len(recs), 5, 'caught up at capacity - 83 a frame')
        for x, y in zip(recs, recs[1:]):
            self.assertEqual(y['base_idx'], x['base_idx'] + x['n_samples'])
        self.assertTrue(all(not x['flags'] & F.F_LOST for x in recs))
        self.assertEqual(recs[-1]['frame_mark'], recs[-1]['n_samples'])
        self.assertEqual(recs[-1]['samples'][-1], sample(cam.ring.k - 1))

    def test_a_stall_longer_than_the_buffer_is_lost(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.flow(cam, 8192 + 2000)
        s = self.frame(cam, 4, prev=a[0])
        r = F.read_frame(s['frame'])
        self.assertTrue(r['flags'] & F.F_LOST)
        # from the oldest the buffer still holds safely: W less the margin
        self.assertEqual(r['base_idx'] + r['frame_mark'], 250 + 8192 + 2000)
        oldest = self.var(cam, 56) - (8192 - 1024)
        self.assertEqual(r['base_idx'], oldest - self.var(cam, 92))
        self.assertEqual(r['samples'][0], sample(cam.k0 + oldest))

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
        self.assertEqual((r['frame_seq'], r['base_idx'], r['n_samples'], r['flags']), (0, 0, 250, F.F_FIRST))
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
        for junk in (b'\0' * 0x400, b'MM\0\x2a' + b'\0' * 0x3FC):
            for count in (3, 4):                    # a take on it, two frames
                s = run_frame(cam, junk, count=count)
                self.assertTrue(s['regs_ok'])
                self.assertEqual(s['frame'], junk)
        self.assertEqual(self.var(cam, 36), 4, 'all four skipped')
        hdr = self.sample_hdr()
        a = run_frame(cam, hdr, count=4)            # a template take_start never saw
        self.assertEqual(a['frame'], hdr, 'is not written either')
        self.flow(cam, 83)
        s = run_frame(cam, hdr, count=3)            # its own take
        r = F.read_frame(s['frame'])
        self.assertEqual((r['frame_seq'], r['n_samples']), (0, 250))

    def test_the_take_start_finds_the_tag_and_frames_never_parse(self):
        hdr = self.sample_hdr()
        at = with_gtag(header_of(find_sample(SAMPLES['fhd'])))[1]
        cam = self.camera()
        self.flow(cam, 600)
        a = run_frame(cam, hdr, count=3)
        self.assertEqual(self.var(cam, 16), at, 'V_WOFF: found at the mode-2 notify')
        # break the header's IFD0 after the take started: frames do not look at it
        cam.mu.mem_write(a['src'] + 8, b'\xFF\xFF')
        self.flow(cam, 83)
        s = self.frame(cam, 4, prev=a)
        blk = s['frame'][at:at + 12]
        self.assertEqual(blk[:6], b'FSG2\x02\x02')
        payload = s['frame'][at + 12:at + 12 + struct.unpack_from('<I', blk, 8)[0]]
        self.assertEqual(F.decode_kind2(payload)['frame_seq'], 1)

    def test_a_template_the_take_did_not_start_on_is_not_written(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        self.flow(cam, 600)
        run_frame(cam, hdr, count=3)                # the take, on its template
        self.flow(cam, 83)
        other = run_frame(cam, hdr, count=4)        # the same bytes somewhere else
        self.assertEqual(other['frame'], hdr)
        self.assertTrue(other['regs_ok'])

    def test_only_cinemadng_frames_are_written(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        self.flow(cam, 600)
        a = run_frame(cam, hdr, count=3)
        before = bytes(cam.mu.mem_read(a['src'], a['n']))
        self.flow(cam, 83)
        for mode, typ in ((3, 4), (3, 5), (2, 4), (5, 3), (6, 3)):
            f = notify(cam, mode, typ)
            self.assertEqual((f['pc'], f['r0']), (STOP, 1))
            self.assertTrue(f['regs_ok'])
        self.assertEqual(bytes(cam.mu.mem_read(a['src'], a['n'])), before)
        self.assertEqual(self.var(cam, 32), 1, "one frame written: the take's first")

    def test_a_small_tag_carries_the_oldest_and_catches_up(self):
        # 120p: 21 records a frame, a tag of 4 frames' worth (84)
        n = 60 + EV_RESERVE + 6 * 84 + 2
        hdr = self.sample_hdr(n=n)
        self.assertEqual(capacity(n), 84)
        cam = self.camera()
        frames = self.take(cam, hdr, frames=6, per_frame=21)
        recs = [F.read_frame(s['frame']) for s in frames]
        self.assertEqual([r['n_samples'] for r in recs], [84, 84, 84, 61, 21, 21])
        self.assertEqual([r['base_idx'] for r in recs], [0, 84, 168, 252, 313, 334])
        self.assertEqual([r['base_idx'] + r['frame_mark'] for r in recs], [250 + 21 * k for k in range(6)])
        self.assertTrue(all(r['flags'] & F.F_LOST == 0 for r in recs))
        flat = [x for r in recs for x in r['samples']]
        self.assertEqual(flat, [sample(cam.ring.k - len(flat) + j) for j in range(len(flat))])
        self.assertTrue(all(len(s['frame']) == len(hdr) for s in frames))

    def test_without_our_tag_nothing_is_written_but_the_frame_is_copied(self):
        plain = header_of(find_sample(SAMPLES['fhd'])) if find_sample(SAMPLES['fhd']) else None
        if plain is None:
            self.skipTest('sample fhd not on this machine')
        cam = self.camera()
        a = self.take(cam, plain, frames=2)
        for s in a:
            self.assertEqual(s['frame'], plain)
            self.assertTrue(s['regs_ok'])
        self.assertEqual(self.var(cam, 36), 2, 'counted as skipped')
        # the stream goes on: a take with the tag starts afresh
        hdr = self.sample_hdr()
        self.flow(cam, 83)
        r = F.read_frame(self.frame(cam, 3, hdr=hdr)['frame'])
        self.assertEqual((r['frame_seq'], r['n_samples']), (0, 250))

    def test_a_block_left_half_written_has_no_magic(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        at = with_gtag(header_of(find_sample(SAMPLES['fhd'])))[1]
        cam.mu.mem_write(a[0]['src'] + at, b'FSG2')
        self.flow(cam, 83)
        seen = {}

        def on_write(mu_, access, addr, size, value, _):
            if addr == a[0]['src'] + at + 4 and 'magic' not in seen:   # the first header word
                seen['magic'] = bytes(mu_.mem_read(a[0]['src'] + at, 4))
        from unicorn import UC_HOOK_MEM_WRITE
        h = cam.mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        try:
            s = self.frame(cam, 4, prev=a[0])
        finally:
            cam.mu.hook_del(h)
        self.assertEqual(s['frame'][at:at + 4], b'FSG2', 'and set again at the end')
        self.assertEqual(seen.get('magic'), b'\0\0\0\0', 'the magic is cleared before the block is rewritten')

    def test_the_mode_is_read_once_a_take(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        self.take(cam, hdr, frames=3)
        self.assertEqual(cam.mode_calls, ['mode', (F_TIMING, 106), (F_GEOM, 106)])

    def test_each_frame_carries_the_calibrated_focal_length(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        a = self.take(cam, hdr, frames=1)
        self.assertEqual(F.read_frame(a[0]['frame'])['calib_focal'], 394)
        cam.mu.mem_write(LENS_FOCAL, struct.pack('<I', 700))          # zoomed
        self.flow(cam, 83)
        self.assertEqual(F.read_frame(self.frame(cam, 4, prev=a[0])['frame'])['calib_focal'], 700)
        cam.mu.mem_write(LENS_FOCAL, struct.pack('<I', 0x12345))      # not a focal length
        self.flow(cam, 83)
        self.assertEqual(F.read_frame(self.frame(cam, 5, prev=a[0])['frame'])['calib_focal'], 0)

    def test_an_unreadable_ring_writes_an_empty_lost_block(self):
        hdr = self.sample_hdr()
        cam = self.camera()
        cam.put(DESC_PTR, 0)
        s = run_frame(cam, hdr, count=3)
        r = F.read_frame(s['frame'])
        self.assertEqual((r['n_samples'], r['flags'] & F.F_LOST), (0, F.F_LOST))
        self.assertTrue(s['regs_ok'])

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
