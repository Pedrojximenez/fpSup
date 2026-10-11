"""Offline relocation checks for Sensor Lab's compact USER core."""
import struct
import unittest

import imx410_plan as P
import res_lab_user_pack as U


def _bw(site, target):
    delta = target - (site + 4)
    if delta & 1 or not -(1 << 24) <= delta < (1 << 24):
        raise ValueError("test Thumb branch out of range")
    s, i1, i2 = (delta >> 24) & 1, (delta >> 23) & 1, (delta >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    return ((0xF000 | s << 10 | (delta >> 12 & 0x3FF))
            | ((0x9000 | j1 << 13 | j2 << 11 | (delta >> 1 & 0x7FF)) << 16))


def fixture(*, bad_pointer=False, bad_branch=False, unpaired=False):
    a, b, data = 0xC0730000, 0xC0730100, 0xC0730200
    arm_site, thumb_site, ptr_site = 0xC0100200, 0xC0100300, 0xC0100100
    target = 0xC0730050 if bad_pointer else data
    movw = U._set_mov_imm(0xE3000000, target & 0xFFFF)
    movt = U._set_mov_imm(0xE3400000, target >> 16)
    if unpaired:
        movw = 0xE1A00000
    branch_target = 0xC0731234 if bad_branch else b
    code_a = struct.pack("<4I", movw, movt,
                         U._encode_arm_branch(0xEA000000, a + 8, branch_target),
                         0xE1A00000)
    code_b = struct.pack("<2I", 0xE1A00000, a)
    rows = [(a + i * 4, v, "code a") for i, v in enumerate(struct.unpack("<4I", code_a))]
    rows += [(b + i * 4, v, "code b") for i, v in enumerate(struct.unpack("<2I", code_b))]
    rows += [(data, b + 4, "data pointer")]
    rows += [(ptr_site, movw, "external pointer low"),
             (ptr_site + 4, movt, "external pointer high"),
             (arm_site, U._encode_arm_branch(0xEA000000, arm_site, a), "ARM hook"),
             (thumb_site, _bw(thumb_site, b), "Thumb hook")]
    rom = bytearray(0x740000)
    for site, stock in ((ptr_site, 0xE3010000), (ptr_site + 4, 0xE34C1000),
                        (arm_site, 0xE92D4010), (thumb_site, 0x48F0E92D)):
        struct.pack_into("<I", rom, site - U.ROM_BASE, stock)
    regions = [(a, a + len(code_a), "a"), (b, b + len(code_b), "b"),
               (data, data + 4, "data")]
    payloads = [("a", a, code_a), ("b", b, code_b)]
    return rows, regions, payloads, bytes(rom), (arm_site, thumb_site), ptr_site


class PackUnit(unittest.TestCase):
    def test_sparse_roundtrip_and_external_descriptors(self):
        rows, regions, payloads, rom, hook_sites, ptr_site = fixture()
        pack = U.build_pack(rows, regions, payloads, rom,
                            hook_sites=hook_sites, late_ui_hook_sites=(hook_sites[1],),
                            named_addresses={"b": regions[1][0]})
        self.assertEqual(pack.total_bytes, 32)
        self.assertEqual(pack.core_magic, 28)
        self.assertEqual(pack.address_map(regions[1][0]), 16)
        self.assertEqual(pack.named_offsets["b"], 16)
        self.assertEqual(len(pack.mov_fixups), 1)
        self.assertEqual(len(pack.abs_fixups), 2)
        self.assertEqual(len(pack.branch_fixups), 1)
        self.assertEqual(len(pack.runtime_table()), 24)
        self.assertEqual(len(pack.external_fixups), 1)
        self.assertEqual(pack.external_fixups[0][:2], (ptr_site, ptr_site + 4))
        self.assertEqual([h.kind for h in pack.external_hooks], ["arm_b", "thumb_bw"])
        self.assertEqual([h.late_ui for h in pack.external_hooks], [False, True])
        self.assertEqual(len(pack.dynamic_journal_words), 4)
        for hook in pack.external_hooks:
            veneer = 0xC072E100
            redirected = hook.veneer_word(veneer)
            target = (U._thumb_bw_target(hook.site, redirected) if hook.kind == "thumb_bw"
                      else U._arm_branch_target(hook.site, redirected))
            self.assertEqual(target, veneer)
        self.assertEqual(pack.static_words, ())
        base = 0x45000000
        moved = pack.materialize(base)
        lo, hi = struct.unpack_from("<II", moved)
        self.assertEqual(U._pair_target(lo, hi), base + pack.address_map(0xC0730200))
        self.assertEqual(U._arm_branch_target(base + 8, struct.unpack_from("<I", moved, 8)[0]),
                         base + pack.address_map(0xC0730100))
        self.assertEqual(struct.unpack_from("<I", moved, 20)[0], base)
        self.assertEqual(struct.unpack_from("<I", moved, 24)[0], base + 20)
        self.assertEqual(struct.unpack_from("<I", moved, 28)[0], U.CORE_MAGIC)
        self.assertEqual(pack.to_blob()[:4], b"SLPK")

    def test_unowned_pointer_rejected(self):
        rows, regions, payloads, rom, hooks, _ = fixture(bad_pointer=True)
        with self.assertRaisesRegex(ValueError, "unowned"):
            U.build_pack(rows, regions, payloads, rom, hook_sites=hooks)

    def test_unowned_branch_rejected(self):
        rows, regions, payloads, rom, hooks, _ = fixture(bad_branch=True)
        with self.assertRaisesRegex(ValueError, "unowned"):
            U.build_pack(rows, regions, payloads, rom, hook_sites=hooks)

    def test_unpaired_cave_movt_rejected(self):
        rows, regions, payloads, rom, hooks, _ = fixture(unpaired=True)
        with self.assertRaisesRegex(ValueError, "unpaired"):
            U.build_pack(rows, regions, payloads, rom, hook_sites=hooks)

    def test_duplicate_write_rejected(self):
        rows, regions, payloads, rom, hooks, _ = fixture()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            U.build_pack(rows + [rows[0]], regions, payloads, rom, hook_sites=hooks)

    def test_nonzero_unwritten_factory_state_rejected(self):
        rows, regions, payloads, rom, hooks, _ = fixture()
        start, end, name = regions[-1]
        regions[-1] = (start, end + 4, name)
        changed = bytearray(rom)
        struct.pack_into("<I", changed, end - U.ROM_BASE, 0x12345678)
        with self.assertRaisesRegex(ValueError, "unwritten region"):
            U.build_pack(rows, regions, payloads, bytes(changed), hook_sites=hooks)


class RealPlan(unittest.TestCase):
    def test_default_and_private_page_relocations(self):
        old_flags = (P.WITH_SL_EXCL, P.WITH_RATE_ROW, P.WITH_BIT_ROW)
        try:
            for menu in (False, True):
                with self.subTest(private_page=menu):
                    P.WITH_SL_EXCL = menu
                    P.WITH_RATE_ROW = P.WITH_BIT_ROW = not menu
                    plan = P.plan()
                    pack = U.res_lab_pack(plan)
                    bit14 = menu and P.SLX.WITH_BIT14   # imx410_bit14: getter hook + pair pointer
                    self.assertEqual(len(pack.core_hooks), 19 + 3 * bit14 + P.WITH_SEL_LOG + 2 * (menu and P.WITH_BINFILT))   # getter + 2 BlackLevel bl; selector log
                    self.assertEqual(len(pack.late_ui_hooks), 10 if menu else 0)
                    self.assertEqual(len(pack.external_fixups), 3 + bit14)
                    self.assertLess(pack.total_bytes, 10000 + 0x500 * P.WITH_SEL_LOG + 0x200 * P.WITH_BINFILT)   # + selector log ring
                    self.assertEqual(pack.total_bytes & 3, 0)
                    self.assertEqual(struct.unpack_from("<I", pack.image, pack.core_magic)[0],
                                     U.CORE_MAGIC)
                    moved = pack.materialize(0x45000000)
                    for relocation in pack.relocations:
                        if relocation.kind == U.ABS32:
                            self.assertEqual(struct.unpack_from("<I", moved, relocation.source_offset)[0],
                                             0x45000000 + relocation.target_offset)
                        else:
                            low, high = struct.unpack_from("<II", moved, relocation.source_offset)
                            self.assertEqual(U._pair_target(low, high),
                                             0x45000000 + relocation.target_offset)
                    self.assertEqual(pack.external_hooks[-1].site if menu else pack.core_hooks[-1].site,
                                     0xC05E82F0 if menu else P.PIK_HOOK)
        finally:
            P.WITH_SL_EXCL, P.WITH_RATE_ROW, P.WITH_BIT_ROW = old_flags


if __name__ == "__main__":
    unittest.main()
