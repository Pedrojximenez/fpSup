"""Firmware-level regressions. All memory and command transport are emulated."""
import copy
import unittest

from firmware import (Firmware, TABLE, TABLE_SIZE, PATCH_ADDRESS, STOCK_TABLE,
                      guarded_table, make_plan)
from emulate import (CameraModel, STATE, CACHED_FINE, CACHED_COARSE,
                     CACHED_GROUP)


class BrightnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.firmware = Firmware()
        cls.plan = make_plan(cls.firmware)

    def assert_command(self, result, expected):
        self.assertEqual(result["return_u32"], 0)
        self.assertEqual(result["dispatches"], [
            {"bytes": expected, "words": [x | 0x100 for x in expected]}])

    def test_all_stock_manual_indices_and_invalid_boundary(self):
        cam = CameraModel(self.firmware)
        for index in range(7):
            with self.subTest(index=index):
                self.assert_command(cam.run("coarse", index), self.firmware.coarse(index))
        for index in (7, 8, 255):
            with self.subTest(invalid=index):
                result = cam.run("coarse", index)
                self.assertEqual(result["return_u32"], 0xFFFFFFFF)
                self.assertFalse(result["dispatches"])
                self.assertFalse(result["writes"])

    def test_all_native_fine_values_and_signed_boundaries(self):
        cam = CameraModel(self.firmware)
        for value in range(1, 100):
            with self.subTest(value=value):
                self.assert_command(cam.run("fine", value), self.firmware.fine(value))
        for value in (-1, 0, 100, 101, 0x7FFFFFFF, 0x80000000):
            with self.subTest(invalid=value):
                result = cam.run("fine", value)
                self.assertEqual(result["return_u32"], 0xFFFFFFFF)
                self.assertFalse(result["dispatches"])
                self.assertFalse(result["writes"])

    def test_patched_maximum_matches_unused_lut100_other_indices_identical(self):
        cam = CameraModel(self.firmware, self.plan)
        for index in range(7):
            with self.subTest(index=index):
                expected = (self.firmware.fine(100, include_rejected_100=True)
                            if index == 6 else self.firmware.coarse(index))
                self.assert_command(cam.run("coarse", index), expected)
        actual = bytes(cam.uc.mem_read(TABLE, TABLE_SIZE))
        self.assertEqual([i for i, (a, b) in enumerate(zip(STOCK_TABLE, actual)) if a != b],
                         [PATCH_ADDRESS - TABLE])

    def test_stock_maximum_matches_fine99_exactly(self):
        self.assertEqual(self.firmware.coarse(6), self.firmware.fine(99))
        stock = CameraModel(self.firmware).run("coarse", 6)
        fine = CameraModel(self.firmware).run("fine", 99)
        self.assertEqual(stock["dispatches"], fine["dispatches"])

    def test_hal_success_does_not_prove_a_command_was_submitted(self):
        for value in (0, 100):
            result = CameraModel(self.firmware).run("hal_fine", value)
            self.assertEqual(result["return_u32"], 0)
            self.assertFalse(result["dispatches"])
        for value in (-1, 101):
            result = CameraModel(self.firmware).run("hal_fine", value)
            self.assertEqual(result["return_u32"], 0xFFFFFFFF)
            self.assertFalse(result["dispatches"])
        self.assert_command(CameraModel(self.firmware).run("hal_fine", 99),
                            self.firmware.fine(99))

    def test_warm_cache_skips_second_coarse_and_fine_submission(self):
        cam = CameraModel(self.firmware)
        self.assert_command(cam.run("coarse", 6), self.firmware.coarse(6))
        cam.uc.mem_write(TABLE, guarded_table(cam.uc.mem_read(TABLE, TABLE_SIZE), self.plan))
        self.assertFalse(cam.run("coarse", 6)["dispatches"],
                         "editing the table does not invalidate a cached maximum")
        self.assert_command(cam.run("coarse", 5), self.firmware.coarse(5))
        self.assert_command(cam.run("coarse", 6),
                            self.firmware.fine(100, include_rejected_100=True))
        self.assert_command(cam.run("fine", 99), self.firmware.fine(99))
        self.assertFalse(cam.run("fine", 99)["dispatches"])
        self.assert_command(cam.run("fine", 99, force=1), self.firmware.fine(99))

    def test_runtime_state_controls_submission_and_caches(self):
        for kind, value in (("coarse", 6), ("fine", 99)):
            with self.subTest(kind=kind):
                cam = CameraModel(self.firmware)
                cam.put32(STATE, 0)
                result = cam.run(kind, value)
                self.assertEqual(result["return_u32"], 0xFFFFFFFF)
                self.assertFalse(result["dispatches"])
                self.assertEqual(cam.u32(CACHED_COARSE if kind == "coarse" else CACHED_FINE), value)
        cam = CameraModel(self.firmware)
        cam.put32(STATE, 1)
        result = cam.run("fine", 99)
        self.assertEqual(result["return_u32"], 0)
        self.assertFalse(result["dispatches"])
        self.assertEqual(cam.u32(CACHED_FINE), 0xFFFFFF9D)

    def test_fine_and_coarse_invalidate_each_others_cached_mode(self):
        cam = CameraModel(self.firmware)
        cam.run("coarse", 6)
        self.assertEqual(cam.u32(CACHED_FINE), 0xFFFFFF9D)
        cam.run("fine", 99)
        self.assertEqual(cam.u32(CACHED_COARSE), 0xFFFFFF9D)
        self.assertEqual(cam.u32(CACHED_GROUP), 0xFFFFFF9D)

    def test_guard_restore_and_foreign_before_image(self):
        stock = self.firmware.read(TABLE, TABLE_SIZE)
        after = guarded_table(stock, self.plan)
        self.assertEqual(guarded_table(after, self.plan, restore=True), stock)
        for current, restore in ((after, False), (stock, True), (b"\x00" * 42, False)):
            with self.assertRaises(ValueError):
                guarded_table(current, self.plan, restore=restore)
        malformed = copy.deepcopy(self.plan)
        malformed["edits"][0]["address"] = hex(TABLE)
        with self.assertRaises(ValueError):
            guarded_table(stock, malformed)
        malformed = copy.deepcopy(self.plan)
        image = bytearray.fromhex(malformed["guard"]["before_hex"])
        image[0] ^= 1
        malformed["guard"]["before_hex"] = image.hex()
        with self.assertRaises(ValueError):
            guarded_table(bytes(image), malformed)

    def test_strict_execution_rejects_unapproved_native_code(self):
        cam = CameraModel(self.firmware)
        cam.allowed = ()
        with self.assertRaisesRegex(AssertionError, "unapproved native execution"):
            cam.run("fine", 99)

    def test_mutations_are_detected_without_modifying_source_images(self):
        cam = CameraModel(self.firmware, self.plan)
        cam.uc.mem_write(PATCH_ADDRESS, bytes([121]))
        with self.assertRaises(AssertionError):
            self.assert_command(cam.run("coarse", 6),
                                self.firmware.fine(100, include_rejected_100=True))
        # In a new model only: replace fine-value upper-bound conditional branch
        # with an unconditional branch that accepts 100. Rejection must fail.
        cam = CameraModel(self.firmware)
        self.assertEqual(bytes(cam.uc.mem_read(0xC00FA9D0, 2)), bytes.fromhex("02db"))
        cam.uc.mem_write(0xC00FA9D0, bytes.fromhex("02e0"))
        result = cam.run("fine", 100)
        with self.assertRaises(AssertionError):
            self.assertEqual(result["return_u32"], 0xFFFFFFFF)
        self.assertTrue(result["dispatches"])
        self.assert_command(result, self.firmware.fine(100, include_rejected_100=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
