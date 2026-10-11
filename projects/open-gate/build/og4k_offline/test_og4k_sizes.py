"""Project integration checks using original firmware arithmetic, host only."""

import importlib.util
import unittest

import og4k_sizes as sizes


class GeometryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = sizes.load_firmware()
        cls.model = sizes.load_model()
        cls.stock = sizes.profile_canvas(cls.image, cls.model, 429)

    def test_p429_offsets_resolve_to_reviewed_columns(self):
        sizes.check_p429_columns(self.image, self.model)
        candidate = sizes.apply_overrides(self.stock, sizes.RAW_OVERRIDES)
        self.assertEqual(sizes.canvas_mismatches(candidate), [])
        for offset, value in enumerate(self.stock):
            if offset * 4 not in sizes.RAW_OVERRIDES:
                self.assertEqual(candidate[offset], value)

    def test_base_only_or_override_only_is_detected(self):
        for omissions in ((0x00, 0x04), (0xDC, 0xE4)):
            overrides = {k: v for k, v in sizes.RAW_OVERRIDES.items() if k not in omissions}
            candidate = sizes.apply_overrides(self.stock, overrides)
            self.assertTrue(any("differ from getters" in x for x in sizes.canvas_mismatches(candidate)))

    def test_raw_plane_helper_does_not_prove_pixel_pool_allocation(self):
        candidate = sizes.apply_overrides(self.stock, sizes.RAW_OVERRIDES)
        self.assertEqual(sizes.get(candidate, 0x3C), 0)
        self.assertEqual(self.model.total(candidate, 1024, 682),
                         self.model.total(self.stock, 1024, 682))
        self.assertEqual(self.model.c04356b0(candidate, 1), 16_120_264)
        self.assertEqual(sizes.get(candidate, 0xF8), 3412)

    def test_conditional_file_and_reader_headroom(self):
        raw = sizes.raw12_bytes(4016, 2676)
        self.assertEqual(raw, {"packed_pixels": 16_120_224, "row_stride": 6024,
                               "final_row_bytes": 6032, "strip_byte_counts": 16_120_232,
                               "write_payload_512": 16_120_320})
        conditional_file = 78_848 + raw["write_payload_512"]
        self.assertEqual(conditional_file, 16_199_168)
        capacity = sizes.playback_file_capacity(conditional_file)
        self.assertEqual(capacity, 16_203_776)
        self.assertGreater(capacity, conditional_file)
        self.assertEqual(sizes.playback_file_capacity(4096), 8192)

    def test_bad_offsets_and_overflow_are_rejected(self):
        with self.assertRaises(sizes.SizingError):
            sizes.apply_overrides(self.stock, {sizes.CANVAS_BYTES: 1})
        with self.assertRaises(sizes.SizingError):
            sizes.raw12_bytes(-1, 2676)
        with self.assertRaises(sizes.SizingError):
            sizes.playback_file_capacity(0xFFFFFFFF)
        with self.assertRaises(sizes.SizingError):
            sizes.profile_canvas(self.image, self.model, 0)


@unittest.skipUnless(importlib.util.find_spec("unicorn"), "Unicorn is required for original firmware execution")
class NativeFirmwareChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = sizes.load_firmware()
        cls.model = sizes.load_model()
        cls.native = sizes.NativeSizing(cls.image)

    def test_original_column_gather_matches_all_valid_profiles(self):
        valid = 0
        for profile in range(sizes.PROFILE_COUNT):
            row = sizes.word(self.image, sizes.PROFILE_MAP + profile * 4)
            if row == 0xFFFFFFFF:
                continue
            expected = sizes.profile_canvas(self.image, self.model, profile)
            self.assertEqual(self.native.gather(row), expected, f"profile {profile}")
            valid += 1
        self.assertEqual(valid, 312)

    def test_original_size_callback_handles_stock_candidate_and_tail_boundaries(self):
        cases = ((3856, 2170), (3024, 2010), (4016, 2676), (6064, 4042),
                 (0, 10), (10, 0), (1, 1), (11, 2), (12, 2), (13, 2),
                 (4015, 2676), (4017, 2676))
        for raster in cases:
            self.assertEqual(self.native.raw12(*raster), sizes.raw12_bytes(*raster)["strip_byte_counts"], raster)

    def test_native_fieldangle_and_plane_helpers_match_model(self):
        cases = []
        for profile in (429, 71, 73, 51, 83, 221):
            canvas = sizes.profile_canvas(self.image, self.model, profile)
            cases.append((f"stock p{profile}", canvas))
        cases.append(("OG4K recording", sizes.apply_overrides(cases[0][1], sizes.RAW_OVERRIDES)))
        cases.append(("OG4K playback", sizes.apply_overrides(cases[1][1], sizes.PLAYBACK_OVERRIDES)))
        for label, canvas in cases:
            for which in (0, 1):
                self.assertEqual(self.native.plane(canvas, which), self.model.c04356b0(canvas, which), label)
            for dims in ((1024, 682), (1620, 911), (1620, 1080), (1920, 1080)):
                native = self.native.fieldangle(canvas, dims)
                self.assertEqual(native["total_bytes"], self.model.total(canvas, *dims), (label, dims))
                if sizes.get(canvas, 0x3C) == 0:
                    self.assertEqual(native["recording_count_in_total"], 0)
                    self.assertEqual(native["recording_plane_in_total"], 0)


if __name__ == "__main__":
    unittest.main()
