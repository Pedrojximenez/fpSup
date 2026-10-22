"""raw-view as a Loader v3 sup, loaded by the real 加載器.

    cd projects/rawview/build && python3 -B -m unittest test_v3_rawview

The real loader.S (as the AutoRun spells it), the real LOADER.BIN and the
built 45RAWV.BIN run in Unicorn against the reference image (MAIN plus the
.data segment); the firmware's file, directory, allocator and power-off
routines are Python (fpSup/fp_usb_shell/v3/test_v3.Camera). uia_apply is
answered by the test: the image's RAM has no GUI objects (the same limit as
test_v3_lossless). Covers what V3=1 changes: claims before anything, release
with nothing written, the three CHAIN sites, power-off, and the settings
record in the sup's own file. The stubs themselves are the AutoRun card's
(test_rawview_image.py) except stub_sv, which is tested here.

Emulated, not on the camera.
"""
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = ROOT / 'fpSup' / 'fp_usb_shell' / 'v3'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(V3))
sys.path.insert(0, str(V3.parent))

import test_v3 as T                                       # noqa: E402
import build_v3 as B                                      # noqa: E402
import build_v3_rawview as V                              # noqa: E402
import build_rawview as R                                 # noqa: E402

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4  # noqa: E402

PATH = '\\fpSup\\' + V.NAME
SITE_A = 0xC0313244
SV, PQ, AI = 0xC0088C60, 0xC02B8E64, 0xC05E2200
SV_ORIG, PQ_ORIG, AI_ORIG = 0xC0088660, 0xC02B97A8, 0xC05D6BB9
F_ITEM, F_SETCOLOR = 0xC0057AE8, 0xC005C958
F_SEEK = 0xC03661E0
BANK_COLOR = 0xC31B33E8
P_FLAG, P_PEND, P_VAR, P_SAT, P_SATF, P_CON, P_CONF = 0x04, 0x94, 0x1A4, 0x1B0, 0x1B4, 0x1C4, 0x1C8
P_PATH, P_BLOCK = 0x1C0, 0x1CC
SV_GROUP, SV_COLOR = 0x58CC, 0x13C
LOWER = 0xC0100000                                        # a layer below: within bl reach
SEG1 = ROOT / 'out' / 'seg1_c2ef6e00.bin'


def bl(site, target):
    return 0xEB000000 | (((target - site - 8) >> 2) & 0xFFFFFF)


def bl_target(site, word):
    d = word & 0xFFFFFF
    d -= 0x1000000 if d & 0x800000 else 0
    return site + 8 + 4 * d


class RawCamera(T.Camera):
    """test_v3's camera with the .data segment, the routines raw-view calls,
    and uia_apply answered by the test."""
    uia_result = 0

    def __init__(self, files, dirs, stale=None, bank_color=0, block_size=0, ui_off=0):
        super().__init__(files, dirs, stale=None)
        seg1 = SEG1.read_bytes()
        self.mu.mem_write(R.SEG1_BASE, seg1[:0xC3000000 - R.SEG1_BASE])
        for a, v in (stale or {}).items():
            self.put(a, v)
        for a, n in ((F_ITEM, 'F_ITEM'), (F_SETCOLOR, 'F_SETCOLOR'), (SV_ORIG, 'SV_ORIG'),
                     (F_SEEK, 'F_SEEK')):
            self.mu.mem_write(a, struct.pack('<I', 0xE12FFF1E))
            self.by_addr[a] = n
        self.put(BANK_COLOR, bank_color)
        self.block_size, self.ui_off = block_size, ui_off
        self.uia_at = None
        self.block = None
        self.setcolor = []
        self.seek_ok, self.write_ok = 1, 'ok'   # 'ok', 'lost' (says 1, wrote nothing),
                                                # 'failed' (wrote it, says 0)

    def _hook(self, mu, addr, size, data):
        if self.uia_at is not None and addr == self.uia_at:
            self.calls.append('UIA_APPLY')
            return self._ret(self.uia_result)
        name = self.by_addr.get(addr)
        r1 = self.r(UC_ARM_REG_R1)
        if name == 'F_SETCOLOR':
            self.setcolor.append(r1)
        if name == 'SV_ORIG':
            self.calls.append('SV_ORIG')
            return self._ret(0x55)
        r0, r2 = self.r(UC_ARM_REG_R0), self.r(T.UC_ARM_REG_R2)
        if name == 'F_OPEN' and r2 == 7:                    # mode 7 keeps what is there
            path = self.cstr(r1)
            self.written.setdefault(path, self.files.get(path, b''))
        if name == 'F_SEEK':
            self.calls.append(name)
            if self.seek_ok:
                self.fobj[r0][1] = r1
            return self._ret(self.seek_ok)
        if name == 'F_WRITE' and self.write_ok == 'lost':
            self.calls.append(name)
            return self._ret(1)
        if name == 'F_WRITE' and self.write_ok == 'failed':
            super()._hook(mu, addr, size, data)
            return self._ret(0)
        if name == 'F_READ' and self.fobj[r0][0] in self.written:
            self.calls.append(name)
            path, pos = self.fobj[r0]
            d = self.written[path][pos:pos + r2]
            mu.mem_write(r1, d)
            self.fobj[r0][1] += len(d)
            self.put(self.r(T.UC_ARM_REG_R3), len(d))
            return self._ret(len(d))
        super()._hook(mu, addr, size, data)
        if name == 'MEM_GET' and r1 == self.block_size:
            self.block = self.r(UC_ARM_REG_R0)
            self.uia_at = (self.block + self.ui_off) & ~1


@unittest.skipIf(T.Uc is None or not T.IMAGE.exists() or not SEG1.exists(),
                 'needs unicorn and the images')
class RawViewV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sup, cls.facts, cls.rows = V.build()
        d = dict(x.split('=') for x in cls.facts['defines'])
        cls.ui_off = cls.facts['blob_off'] + int(d['UI_APPLY'], 0)
        cls.img = T.IMAGE.read_bytes()
        cls.seg1 = SEG1.read_bytes()
        cls.sites = {a: s for a, s, _ in cls.rows}

    def boot(self, *inner, sup=None, stale=None, bank=0, uia=0):
        files, dirs = T.card(*inner, (V.NAME, sup or self.sup))
        cam = RawCamera(files, dirs, stale=stale, bank_color=bank,
                        block_size=self.facts['block'], ui_off=self.ui_off)
        cam.uia_result = uia
        r0, sp = cam.boot()
        self.assertEqual(sp, T.STACK - 0x1004)
        self.assertEqual(cam.misaligned, [])
        return cam

    def outcome(self, cam, name=V.NAME):
        return {t: c for c, _, _, t in cam.log() if c in ('LOADED', 'RELEASED')}.get(name)

    def resident(self, cam):
        """Site A -> veneer -> stub_gs; the resident starts stub_gs before it."""
        ven = bl_target(SITE_A, cam.w(SITE_A))
        return cam.w(ven + 4) - self.facts['res_syms']['stub_gs']

    def other(self, sid, *rows):
        return T.test_sup(sid, [(a, struct.unpack('<I', self.sites[a])[0], k, new)
                                for a, k, new in rows])

    def with_cfg(self, *words):
        cfg = struct.pack('<8I', *(list(words) + [0] * (8 - len(words))))
        s = bytearray(self.sup)
        s[32:64] = cfg
        return bytes(s)

    # ---- loaded -----------------------------------------------------------
    def test_loads_claims_every_site_and_hooks(self):
        cam = self.boot()
        self.assertEqual(self.outcome(cam), 'LOADED')
        self.assertIn('UIA_APPLY', cam.calls)
        self.assertEqual(sorted(a for a, *_ in cam.journal()), sorted(self.sites))
        for a, n, data in cam.journal():
            self.assertEqual(data, self.sites[a], hex(a))
        st = cam.state()
        claims = [struct.unpack('<IIBBBB', cam.mu.mem_read(st + T.O_CLAIMS + 12 * i, 12))
                  for i in range(cam.w(st + T.O_NCLAIMS))]
        self.assertEqual({a: k for a, n, k, _, res, _ in claims},
                         {a: k for a, _, k in self.rows})
        res = self.resident(cam)
        self.assertEqual(cam.w(res), 0x31575652)                # "RVW1"
        self.assertTrue(cam.block < res < cam.block + self.facts['block'])
        self.assertEqual(cam.w(res + P_BLOCK), cam.block)
        self.assertEqual(cam.cstr(cam.w(res + P_PATH)), PATH)
        rs = self.facts['res_syms']
        self.assertEqual(cam.w(res + rs['sv_next']), SV_ORIG)
        self.assertEqual(cam.w(res + rs['pq_next']), PQ_ORIG)
        self.assertEqual(cam.w(res + rs['ai_next']), AI_ORIG)
        self.assertEqual(bl_target(SV, cam.w(SV)) & 0xFFFFF000, T.cave.CAVE_ARENA & 0xFFFFF000)
        self.assertEqual(cam.w(bl_target(SV, cam.w(SV)) + 4), res + rs['stub_sv'])
        self.assertEqual(cam.setcolor, [])                      # nothing to restore

    def test_every_firmware_word_it_changed_is_claimed(self):
        cam = self.boot()
        claimed = set()
        for a, s, _ in self.rows:
            claimed |= set(range(a, a + len(s), 4))
        lo, hi = T.CAVE_LOW, 0xC0730000           # the loader's cave: arena, LOAD_DONE, store_boot
        ref = bytearray(self.img[:0x03000000].ljust(0x03000000, b'\0'))   # mapped, zero past the image
        part = self.seg1[:0xC3000000 - R.SEG1_BASE]
        o = R.SEG1_BASE - 0xC0000000
        ref[o:o + len(part)] = part
        now = bytes(cam.mu.mem_read(0xC0000000, 0x03000000))
        step = 0x10000
        changed = []
        for off in range(0, len(ref), step):
            if now[off:off + step] == ref[off:off + step]:
                continue
            for o in range(off, off + step, 4):
                if now[o:o + 4] != ref[o:o + 4]:
                    changed.append(0xC0000000 + o)
        harness = set(cam.by_addr)                             # the camera's `bx lr` stubs
        stray = [hex(a) for a in changed
                 if a not in claimed and a not in harness and not lo <= a < hi]
        self.assertEqual(stray, [])

    def test_power_off_puts_every_site_back(self):
        cam = self.boot()
        cam.power_off()
        for a, s in self.sites.items():
            self.assertEqual(bytes(cam.mu.mem_read(a, len(s))), s, hex(a))

    def test_residue_is_repaired_then_armed(self):
        stale = {SITE_A: 0xEB0DEAD0, SV: 0xEB0DEAD0, 0xC06C07D8: 0xE3A02011}
        cam = self.boot(stale=stale)
        self.assertEqual(self.outcome(cam), 'LOADED')
        repaired = {a for c, a, _, t in cam.log() if c == 'REPAIRED'}
        self.assertTrue(set(stale) <= repaired, repaired)
        res = self.resident(cam)
        self.assertEqual(cam.w(res + self.facts['res_syms']['sv_next']), SV_ORIG)

    # ---- CHAIN ------------------------------------------------------------
    def test_a_layer_below_on_the_save_site_is_chained(self):
        o = self.other('OTHR', (SV, 1, bl(SV, LOWER)))
        cam = self.boot(('05OTHER.BIN', o))
        self.assertEqual(self.outcome(cam, '05OTHER.BIN'), 'LOADED')
        self.assertEqual(self.outcome(cam), 'LOADED')
        res = self.resident(cam)
        self.assertEqual(cam.w(res + self.facts['res_syms']['sv_next']), LOWER)
        self.assertEqual(cam.w(bl_target(SV, cam.w(SV)) + 4),
                         res + self.facts['res_syms']['stub_sv'])

    # ---- released: nothing written ------------------------------------------
    def assert_released_clean(self, cam, held=()):
        self.assertEqual(self.outcome(cam), 'RELEASED')
        self.assertEqual(cam.setcolor, [])
        for a, s in self.sites.items():
            if a not in held:
                self.assertEqual(bytes(cam.mu.mem_read(a, len(s))), s, f'{a:#x} written')
        self.assertEqual(sorted(j[0] for j in cam.journal()), sorted(held))

    def test_an_exclusive_site_held_by_another_releases(self):
        o = self.other('OTHR', (SITE_A, 1, 0))                 # even a CHAIN hold
        cam = self.boot(('05OTHER.BIN', o))
        self.assert_released_clean(cam, held=(SITE_A,))
        self.assertEqual(cam.w(T.cave.CAVE_BUMP), T.cave.CAVE_ARENA, 'cave taken')

    def test_a_chain_site_held_exclusively_releases(self):
        o = self.other('OTHR', (PQ, 2, 0))
        cam = self.boot(('05OTHER.BIN', o))
        self.assert_released_clean(cam, held=(PQ,))

    def test_the_ui_site_held_exclusively_releases(self):
        o = self.other('OTHR', (V.H1_SITE, 2, 0))
        cam = self.boot(('05OTHER.BIN', o))
        self.assert_released_clean(cam, held=(V.H1_SITE,))

    def test_ui_refused_releases_before_any_firmware_write(self):
        cam = self.boot(uia=2)                                  # UIA_NO_UI
        self.assert_released_clean(cam)

    # ---- the settings record in its own file --------------------------------
    def save(self, cam, flag, lat, con, sat, color=0xC, group=0):
        res = self.resident(cam)
        for off, v in ((P_FLAG, flag), (P_VAR, lat), (P_CON, con), (P_SAT, sat)):
            cam.put(res + off, v)
        obj = 0xC3F00000
        cam.put(obj + SV_GROUP, group)
        cam.put(obj + SV_COLOR, color)
        cam.mu.reg_write(UC_ARM_REG_R4, obj)
        cam.calls.clear()
        cam.opened.clear()
        # FUN_c0088bb0 calls with sp 8-aligned (push 4 + sub 16)
        r0, sp = cam.call(res + self.facts['res_syms']['stub_sv'], r0=0x11, r1=0x22,
                          sp=T.STACK - 0x1000)
        self.assertEqual(r0, 0x55)                              # the original's return
        self.assertEqual(sp, T.STACK - 0x1000)
        self.assertEqual(cam.misaligned, [])
        self.assertEqual(cam.w(obj + SV_COLOR), color, 'firmware settings touched')
        self.assertEqual(cam.calls[0], 'SV_ORIG')               # firmware saves first
        return cam.written.get(PATH)

    def test_save_writes_the_record_into_its_own_file(self):
        cam = self.boot()
        got = self.save(cam, 1, 1, 1, 1)
        self.assertEqual(got[:32], self.sup[:32])               # the header unchanged
        self.assertEqual(got[64:], self.sup[64:])               # and the rest
        self.assertEqual(struct.unpack('<8I', got[32:64]),
                         (V.CFG_MAGIC, 1, 1, 1, 1, 0, 0, 0))
        self.assertIn('F_READ', cam.calls)                      # read back
        self.assertEqual(cam.opened, [PATH])
        self.save(cam, 1, 1, 1, 1)                              # unchanged: no card write
        self.assertEqual(cam.opened, [])

    def test_a_failed_seek_writes_nothing_and_retries_next_time(self):
        cam = self.boot()
        cam.seek_ok = 0
        got = self.save(cam, 1, 1, 1, 1)
        self.assertNotIn('F_WRITE', cam.calls)
        self.assertEqual(got, self.sup)
        cam.seek_ok = 1
        got = self.save(cam, 1, 1, 1, 1)                        # same values: written now
        self.assertEqual(struct.unpack('<5I', got[32:52]), (V.CFG_MAGIC, 1, 1, 1, 1))

    def test_a_write_that_did_not_take_is_retried_next_time(self):
        """Read back catches a write that says done but is not on the card."""
        cam = self.boot()
        cam.write_ok = 'lost'
        got = self.save(cam, 1, 1, 1, 1)
        self.assertEqual(got, self.sup)
        cam.write_ok = 'ok'
        got = self.save(cam, 1, 1, 1, 1)
        self.assertIn('F_WRITE', cam.calls)
        self.assertEqual(struct.unpack('<5I', got[32:52]), (V.CFG_MAGIC, 1, 1, 1, 1))

    def test_a_write_that_reports_failure_is_retried_next_time(self):
        """The write's own result counts even when the bytes look right."""
        cam = self.boot()
        cam.write_ok = 'failed'
        self.save(cam, 1, 1, 1, 1)
        cam.write_ok = 'ok'
        self.save(cam, 1, 1, 1, 1)
        self.assertIn('F_WRITE', cam.calls)                     # not "unchanged"

    def test_save_records_off_when_colour_is_not_off_and_skips_custom_groups(self):
        cam = self.boot()
        self.assertIsNone(self.save(cam, 1, 0, 0, 0, group=2))
        self.assertEqual(cam.opened, [])
        got = self.save(cam, 1, 1, 0, 1, color=3)
        self.assertEqual(struct.unpack('<5I', got[32:52]), (V.CFG_MAGIC, 0, 1, 0, 1))

    def test_saved_record_restores_at_next_boot(self):
        cam = self.boot()
        sup = self.save(cam, 1, 1, 0, 1)                        # lat ≠ con: a swap shows
        cam = self.boot(sup=sup, bank=0xC)
        self.assertEqual(self.outcome(cam), 'LOADED')
        self.assertEqual(cam.setcolor, [0xC])
        res = self.resident(cam)
        vals = {o: cam.w(res + o) for o in (P_FLAG, P_PEND, P_VAR, P_CON, P_CONF, P_SAT, P_SATF)}
        self.assertEqual(vals, {P_FLAG: 1, P_PEND: 17, P_VAR: 1, P_CON: 0, P_CONF: 0,
                                P_SAT: 1, P_SATF: 1})

    def test_record_not_restored_when_the_colour_changed_without_the_card(self):
        cam = self.boot(sup=self.with_cfg(V.CFG_MAGIC, 1, 1, 1, 4), bank=3)
        self.assertEqual(self.outcome(cam), 'LOADED')
        self.assertEqual(cam.setcolor, [])
        self.assertEqual(cam.w(self.resident(cam) + P_FLAG), 0)

    def test_saturation_out_of_range_is_zero(self):
        cam = self.boot(sup=self.with_cfg(V.CFG_MAGIC, 1, 0, 0, V.rv_color.SAT_MAX + 1), bank=0xC)
        self.assertEqual(cam.w(self.resident(cam) + P_SAT), 0)

    def test_old_cards_colour_0x1x_is_read_once_and_put_back(self):
        cam = self.boot(bank=0x13)                              # lat 1, con 1, sat 0
        self.assertEqual(cam.setcolor, [0xC])
        res = self.resident(cam)
        self.assertEqual((cam.w(res + P_FLAG), cam.w(res + P_VAR), cam.w(res + P_CON),
                          cam.w(res + P_SAT)), (1, 1, 1, 0))


if __name__ == '__main__':
    unittest.main()
