#!/usr/bin/env python3
"""OG6K over HDMI RAW 建置器的離線測試。全部純讀韌體映像。"""

from __future__ import annotations

import struct
import unittest

import build as Bd


class TestEncoding(unittest.TestCase):
    def test_encoder_round_trips_the_stock_instructions(self):
        """編碼器必須能重現原廠那兩道指令 —— 否則它就是錯的。"""
        self.assertEqual(Bd.movw(1, Bd.HDMIRAW_TABLE & 0xFFFF), Bd.STOCK_MOVW)
        self.assertEqual(Bd.movt(1, Bd.HDMIRAW_TABLE >> 16), Bd.STOCK_MOVT)

    def test_patch_reassembles_to_the_private_table(self):
        w = Bd.movw(1, Bd.PRIV_TABLE & 0xFFFF)
        t = Bd.movt(1, Bd.PRIV_TABLE >> 16)
        got = (((t & 0xF0000) >> 4 | (t & 0xFFF)) << 16) | ((w & 0xF0000) >> 4 | (w & 0xFFF))
        self.assertEqual(got, Bd.PRIV_TABLE)


class TestFirmwareShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = Bd.Plan()

    def test_sites_are_stock(self):
        self.p.check_sites()

    def test_table_span_matches_the_searcher(self):
        """搜尋器的 span 是寫死的,表必須正好那麼長。"""
        self.assertEqual(Bd.HDMIRAW_SPAN, 0x1C0)
        self.assertEqual(Bd.ENTRIES, 28)

    def test_tables_are_contiguous(self):
        """五張表首尾相接,沒有可以偷用的空隙。"""
        self.assertEqual(Bd.HDMIRAW_TABLE + Bd.HDMIRAW_SPAN, 0xC0BE5610)

    def test_table_is_full(self):
        """28 筆全滿 —— 所以非用私有表不可。"""
        for i in range(Bd.ENTRIES):
            self.assertNotEqual(self.p.word(Bd.HDMIRAW_TABLE + i * 16), 0,
                                f"entry {i} 是空的?")

    def test_every_stock_entry_is_const_3(self):
        for i in range(Bd.ENTRIES):
            self.assertEqual(self.p.word(Bd.HDMIRAW_TABLE + i * 16), Bd.CONST)

    def test_donors_differ_only_in_nominal_fps(self):
        self.p.check_donors()

    def test_donor_keys_are_the_uhd_crop_four(self):
        slots = self.p.check_table()
        keys = {self.p.key_of(i) for i in slots.values()}
        self.assertEqual(keys, {"UHD30CROP", "UHD25CROP",
                                "UHD24CROP", "UHD23_98CROP"})

    def test_layout_clears_every_resident(self):
        self.p.check_layout()


class TestPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = Bd.Plan().build()
        cls.fw = Bd.Plan()

    def test_only_two_code_writes(self):
        code = [w for w in self.plan["writes"]
                if w[0] in (Bd.SITE_MOVW, Bd.SITE_MOVT)]
        self.assertEqual(len(code), 2)
        self.assertEqual(self.plan["code_writes"], 2)

    def test_no_write_lands_on_stock_table(self):
        """私有表的重點就是不碰原廠那張。"""
        for a, _v, _w in self.plan["writes"]:
            self.assertFalse(
                Bd.HDMIRAW_TABLE <= a < Bd.HDMIRAW_TABLE + Bd.HDMIRAW_SPAN,
                f"{a:#010x} 落在原廠 HdmiRaw 表裡")

    def test_private_table_is_exactly_the_span(self):
        tw = [w for w in self.plan["writes"]
              if Bd.PRIV_TABLE <= w[0] < Bd.PRIV_TABLE + Bd.HDMIRAW_SPAN]
        self.assertEqual(len(tw), Bd.HDMIRAW_SPAN // 4)

    def test_untouched_entries_are_byte_identical_to_stock(self):
        """只換四筆,其餘 24 筆必須逐字相同。"""
        vals = {a: v for a, v, _ in self.plan["writes"]}
        replaced = {i for i, _n, _k in self.plan["replaced"]}
        for i in range(Bd.ENTRIES):
            if i in replaced:
                continue
            for j in range(4):
                a = Bd.PRIV_TABLE + i * 16 + j * 4
                self.assertEqual(vals[a],
                                 self.fw.word(Bd.HDMIRAW_TABLE + i * 16 + j * 4),
                                 f"entry {i} word {j} 被動到了")

    def test_replaced_entries_carry_const3_and_mode3(self):
        vals = {a: v for a, v, _ in self.plan["writes"]}
        for i, _name, _key in self.plan["replaced"]:
            self.assertEqual(vals[Bd.PRIV_TABLE + i * 16 + 0], 3, "const 必須是 3")
            self.assertEqual(vals[Bd.PRIV_TABLE + i * 16 + 8], 3, "mode 必須是 M3")

    def test_key_pointers_land_in_our_string_area(self):
        vals = {a: v for a, v, _ in self.plan["writes"]}
        for i, _n, _k in self.plan["replaced"]:
            ptr = vals[Bd.PRIV_TABLE + i * 16 + 12]
            self.assertTrue(Bd.PRIV_STR <= ptr < Bd.PRIV_END,
                            f"鍵指標 {ptr:#010x} 不在字串區")

    def test_strings_are_nul_terminated(self):
        vals = {a: v for a, v, _ in self.plan["writes"]}
        for key, _p, _n in Bd.RATES:
            ptr = None
            for i, _name, k in self.plan["replaced"]:
                if k == key:
                    ptr = vals[Bd.PRIV_TABLE + i * 16 + 12]
            self.assertIsNotNone(ptr)
            blob = b"".join(struct.pack("<I", vals[ptr + j])
                            for j in range(0, ((len(key) + 4) & ~3), 4))
            self.assertTrue(blob.startswith(key.encode()))
            self.assertIn(b"\x00", blob[len(key):])

    def test_raw_plane_rwzm_is_not_written(self):
        """+0x64 / +0xD4 原本就是 unity,寫它只會增加風險。"""
        for _k, prof, _n in Bd.RATES:
            for off in (0x064, 0x0D4):
                a = self.fw.field_addr(prof, off)
                self.assertNotIn(a, [w[0] for w in self.plan["writes"]])

    def test_nominal_fps_is_not_written(self):
        """四個捐贈者的 +0x030 本來就對應各自的格率。"""
        for _k, prof, _n in Bd.RATES:
            a = self.fw.field_addr(prof, 0x030)
            self.assertNotIn(a, [w[0] for w in self.plan["writes"]])

    def test_geometry_edits_are_6064x4042(self):
        vals = {a: v for a, v, _ in self.plan["writes"]}
        for _k, prof, _n in Bd.RATES:
            for off, want in ((0x000, 6064), (0x004, 4042),
                              (0x024, 6064), (0x02C, 4042),
                              (0x0F4, 6064), (0x0F8, 4042)):
                self.assertEqual(vals[self.fw.field_addr(prof, off)], want)


class TestRefusals(unittest.TestCase):
    def test_refuses_when_the_site_is_not_stock(self):
        p = Bd.Plan()
        saved = Bd.STOCK_MOVW
        try:
            Bd.STOCK_MOVW = saved ^ 0xFF
            with self.assertRaises(Bd.BuildError) as cm:
                p.check_sites()
            self.assertIn("不產生計畫", str(cm.exception))
        finally:
            Bd.STOCK_MOVW = saved

    def test_refuses_on_a_layout_collision(self):
        p = Bd.Plan()
        saved = list(Bd.RESIDENTS)
        try:
            Bd.RESIDENTS.append((Bd.PRIV_TABLE, Bd.PRIV_TABLE + 4, "假常駐者"))
            with self.assertRaises(Bd.BuildError):
                p.check_layout()
        finally:
            Bd.RESIDENTS[:] = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)
