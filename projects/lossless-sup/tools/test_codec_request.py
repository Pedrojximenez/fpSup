#!/usr/bin/env python3
"""The transcribed encoder ABI, held against the one live number we have.

The arithmetic here was read out of the disassembly, and static reading has
already misled this project twice. One thing anchors it: the camera reported
0x305000 as its declared output length on 2026-09-28, read from the engine's own
parameter block, and this module computes exactly that from the geometry. That
test is the reason to believe the rest.
"""
import pathlib
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import codec_request as cr

FHD = dict(width=1936, height=1090, tile_w=512, tile_h=368, depth_code=0)
UHD12 = dict(width=3840, height=2160, tile_w=512, tile_h=368, depth_code=0)
UHD10 = dict(UHD12, depth_code=3)


class AnchorTests(unittest.TestCase):

    def test_fhd_band_capacity_is_the_length_the_camera_reported(self):
        """0x305000, read live from 0xC302CDE0 on 2026-09-28 and printed by the
        probe as both a constant and a readback. If this line fails, the depth
        table or the rounding is wrong and nothing else here can be trusted."""
        plan = cr.plan(**FHD)
        self.assertEqual(plan["bands"], 1)
        self.assertEqual(plan["band"][0]["capacity"], 0x305000)
        self.assertEqual(plan["band"][0]["capacity"], 3_166_208)

    def test_fhd_tile_grid_matches_every_measurement_so_far(self):
        plan = cr.plan(**FHD)
        self.assertEqual((plan["tile_cols"], plan["tile_rows"]), (4, 3))
        self.assertEqual(plan["tiles"], 12)


class DepthTests(unittest.TestCase):

    def test_the_table_is_the_one_C062FE40_implements(self):
        self.assertEqual(cr.DEPTH_BITS, {0: 12, 1: 14, 2: 16, 3: 10})

    def test_a_code_outside_the_table_is_refused(self):
        for code in (4, 5, -1, 255):
            with self.assertRaises(cr.Refused):
                cr.depth_bits(code)

    def test_ten_bit_uhd_is_one_field_not_a_template(self):
        twelve = cr.plan(**UHD12)["band"][0]["capacity"]
        ten = cr.plan(**UHD10)["band"][0]["capacity"]
        self.assertEqual(twelve, 12_441_600)
        self.assertEqual(ten, 10_368_000)
        self.assertLess(ten, twelve)


class BandTests(unittest.TestCase):

    def test_every_geometry_this_camera_records_is_a_single_band(self):
        """Which is what makes the asynchronous plan simple: one submit, one
        completion, no band state machine."""
        for geometry in (FHD, UHD12, UHD10):
            self.assertEqual(cr.bands(**geometry), 1, geometry)

    def test_the_bands_cover_the_frame_exactly(self):
        # A frame tall enough to force several bands: the 64 MiB budget caps
        # rows_per_pass once one tile row is large enough.
        wide = dict(width=0x4000, height=368 * 40, tile_w=512, tile_h=368,
                    depth_code=2)
        plan = cr.plan(**wide)
        self.assertGreater(plan["bands"], 1)
        self.assertEqual(sum(b["band_height"] for b in plan["band"]),
                         wide["height"])
        self.assertEqual(sum(b["tiles"] for b in plan["band"]), plan["tiles"])
        self.assertEqual(sum(b["tile_rows"] for b in plan["band"]),
                         plan["tile_rows"])

    def test_a_tile_row_over_the_budget_is_refused(self):
        with self.assertRaises(cr.Refused):
            cr.rows_per_pass(width=0x100000, height=368, tile_w=512,
                             tile_h=368, depth_code=2)

    def test_the_source_step_must_be_1024_aligned(self):
        """The driver tests (step << 22) and returns 1, so a multi-band geometry
        whose step is not a multiple of 1024 cannot be encoded at all."""
        with self.assertRaises(cr.Refused):
            cr.source_advance(width=1001, tile_h=3, depth_code=0, per=1)
        # 12 * 1024 * 368 / 8 = 565,248 = 552 * 1024
        self.assertEqual(
            cr.source_advance(width=1024, tile_h=368, depth_code=0, per=1),
            565_248)

    def test_fhds_step_would_be_refused_and_is_never_computed(self):
        """A consequence worth keeping: 12 * 1936 * 368 / 8 * 3 = 3,206,016 is
        NOT a multiple of 1024. FHD gets away with it only because it is a single
        band and the driver computes the step only while i < bands-1. Any
        geometry that did need bands would have to clear this too."""
        with self.assertRaises(cr.Refused):
            cr.source_advance(width=1936, tile_h=368, depth_code=0, per=3)
        self.assertNotIn("source_step", cr.plan(**FHD))
        self.assertNotIn("source_step", cr.plan(**UHD12))


class MeasuredTests(unittest.TestCase):
    """What PHASE 11 stage one actually read off the camera on 2026-09-29."""

    MEASURED = {"+0x00": 0x85177000, "+0x04": 0x0019E000, "+0x08": 0x85317000,
                "+0x0C": 0x0019E000, "+0x10": 0x45568000, "+0x14": 0x18}
    SRC, DST, TABLE = 0x45177000, 0x45317000, 0x45568000
    GEOMETRY = dict(width=1536, height=736, tile_w=512, tile_h=368, depth_code=0)

    def test_the_two_data_pointers_come_back_uncached_and_the_table_does_not(self):
        self.assertEqual(self.MEASURED["+0x00"], self.SRC + 0x40000000)
        self.assertEqual(self.MEASURED["+0x08"], self.DST + 0x40000000)
        self.assertEqual(self.MEASURED["+0x10"], self.TABLE)

    def test_the_source_length_is_what_the_geometry_implies(self):
        bits = cr.depth_bits(0)
        self.assertEqual(self.MEASURED["+0x04"],
                         bits * 1536 * 736 // 8)
        self.assertEqual(self.MEASURED["+0x04"], 1_695_744)

    def test_the_declared_length_is_the_capacity_this_module_computes(self):
        plan = cr.plan(**self.GEOMETRY)
        self.assertEqual(plan["bands"], 1)
        self.assertEqual(plan["band"][0]["capacity"], self.MEASURED["+0x0C"])

    def test_the_table_length_is_four_bytes_a_tile(self):
        plan = cr.plan(**self.GEOMETRY)
        self.assertEqual(plan["tiles"], 6)
        self.assertEqual(self.MEASURED["+0x14"], plan["tiles"] * 4)

    def test_the_flag_is_created_lazily_by_an_idempotent_call(self):
        """C062F440 returns the id and creates it only if it is negative, so the
        asynchronous path needs one call to it and not a whole F_ENC."""
        self.assertEqual(cr.FLAG_CREATE, 0xC062F441, "Thumb: low bit set")
        self.assertEqual(cr.FLAG_CREATE & 1, 1)
        self.assertEqual(cr.FLAG_CREATE_TEMPLATE, 0xC2E32CAC)
        self.assertEqual(cr.ACRE_FLG_VENEER, 0xC00169EC)

    def test_the_flag_carries_more_than_one_operations_completion(self):
        self.assertEqual(cr.OTHER_WAIT_PATTERN, 2)
        self.assertNotEqual(cr.OTHER_WAIT_PATTERN, cr.WAIT_PATTERN)

    def test_the_flag_does_not_exist_after_F_INIT_alone(self):
        """-42 is E_NOEXS. Anything that waits on this id before the driver's own
        path has created it waits on nothing."""
        self.assertEqual(cr.FLAG_ID_UNINITIALISED, 0xFFFFFFD6)
        self.assertEqual(cr.FLAG_ID_UNINITIALISED - (1 << 32), -42)


class AbiConstantTests(unittest.TestCase):
    """The addresses and codes, so a later edit cannot drift from the listing."""

    def test_the_addresses_read_out_of_the_firmware(self):
        self.assertEqual(cr.ENGINE, 0xC302CDD4)
        self.assertEqual(cr.ENGINE + cr.ENG_DEST_LEN, 0xC302CDE0,
                         "the declared length this project read live")
        self.assertEqual(cr.SUBMIT, 0xC062FFF8)
        self.assertEqual(cr.CALLBACK, 0xC062FCB1, "Thumb, low bit set")
        self.assertEqual(cr.TWAI_FLG, 0xC0016C08)
        self.assertEqual(cr.CLR_FLG, 0xC00169C8)
        self.assertEqual(cr.E_TMOUT, -50)
        self.assertEqual((cr.WAIT_PATTERN, cr.WAIT_MODE), (5, 1))
        self.assertEqual((cr.DONE_BIT, cr.ERROR_BIT), (1, 4))
        self.assertEqual(cr.WAIT_PATTERN, cr.DONE_BIT | cr.ERROR_BIT,
                         "the wait pattern is exactly the two bits the callback "
                         "sets")

    def test_the_request_layout_is_contiguous_and_fits(self):
        offsets = [cr.R_WIDTH, cr.R_BAND_HEIGHT, cr.R_DEPTH, cr.R_TILE_W,
                   cr.R_TILE_H, cr.R_SOURCE, cr.R_BAND_CAPACITY, cr.R_DEST,
                   cr.R_DEST_REMAINING, cr.R_SIZE_SCRATCH,
                   cr.R_SIZE_SCRATCH_LEN, cr.R_CALLBACK]
        self.assertEqual(offsets, list(range(0, cr.REQ_BYTES, 4)))
        self.assertEqual(cr.REQ_BYTES, 0x30)


if __name__ == "__main__":
    unittest.main()
