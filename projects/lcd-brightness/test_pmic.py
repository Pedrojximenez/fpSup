"""Offline PMIC current, callback and exact-table regressions."""
import copy
import unittest

from firmware import Firmware
from pmic import (PmicModel, NativeAssertion, INIT_TABLES, INIT_SIZE,
                  init_entries, make_current_plan, guarded_init_table, current_ratio)


class PmicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.firmware = Firmware()

    def test_both_original_init_paths_write_dim18(self):
        for selector, base in ((0, INIT_TABLES[1]), (1, INIT_TABLES[0])):
            with self.subTest(selector=selector):
                cam = PmicModel(self.firmware, selector=selector)
                events = cam.run("init")
                self.assertEqual(events, [{"op": "write", "register": r, "value": v, "result": 0}
                                          for r, v in init_entries(self.firmware, base)])
                self.assertEqual(cam.registers[4], 0xB2)
                self.assertEqual(cam.registers[4] & 31, 18)

    def test_all_32_native_current_levels_preserve_vout8(self):
        cam = PmicModel(self.firmware)
        for dim in range(32):
            with self.subTest(dim=dim):
                self.assertEqual(cam.run("set_dim", dim), [{"op": "write", "register": 4,
                                    "value": 0xA0 | dim, "result": 0}])
                self.assertEqual(cam.registers[4] & 0xE0, 0xA0)
                self.assertEqual(cam.registers[4] & 31, dim)

    def test_native_assert_stops_invalid_dim_before_i2c(self):
        for dim in (-1, 32, 33, 0x80000000, 0x7FFFFFFF):
            with self.subTest(dim=dim):
                cam = PmicModel(self.firmware)
                with self.assertRaises(NativeAssertion):
                    cam.run("set_dim", dim)
                self.assertFalse(cam.events)
                self.assertEqual(cam.registers[4], 0xB2)

    def test_lcd_callback_only_toggles_en7_and_preserves_current(self):
        for initial in (0, 0xA9, 0xFF):
            cam = PmicModel(self.firmware)
            cam.registers[0xE] = initial
            enabled = cam.run("lcd_enable", 1)
            self.assertEqual(enabled, [{"op": "read", "register": 0xE, "value": initial, "result": 0},
                                       {"op": "write", "register": 0xE,
                                        "value": initial | 4, "result": 0}])
            disabled = cam.run("lcd_enable", 0)
            self.assertEqual(disabled[-1], {"op": "write", "register": 0xE,
                                            "value": initial & ~4, "result": 0})
            self.assertEqual(cam.registers[4], 0xB2)

    def test_native_power_test_path_is_a_separate_dim31_writer(self):
        cam = PmicModel(self.firmware)
        events = cam.run("power_test_init")
        writes = [e["value"] for e in events if e["register"] == 4]
        self.assertEqual(writes, [0xB2, 0xBF])
        self.assertEqual(events[-1], {"op": "write", "register": 0xE, "value": 0xFD, "result": 0})
        self.assertEqual(cam.registers[4] & 31, 31)

    def test_all_13_higher_init_candidates_both_paths(self):
        for dim in range(19, 32):
            plan = make_current_plan(self.firmware, dim)
            for selector, base in ((0, INIT_TABLES[1]), (1, INIT_TABLES[0])):
                with self.subTest(dim=dim, selector=selector):
                    cam = PmicModel(self.firmware, selector=selector, plan=plan)
                    events = cam.run("init")
                    expected = init_entries(self.firmware, base)
                    expected[3] = (4, 0xA0 | dim)
                    self.assertEqual(events, [{"op": "write", "register": r, "value": v, "result": 0}
                                              for r, v in expected])
                    self.assertEqual(cam.registers[4], 0xA0 | dim)

    def test_current_ratios_are_not_nits(self):
        self.assertEqual(current_ratio(18), 19 / 32)
        self.assertEqual(current_ratio(31), 1)
        self.assertAlmostEqual(make_current_plan(self.firmware, 31)["current_ratio_to_stock_init"], 32 / 19)
        for value in (-1, 32, 1.5, True):
            with self.assertRaises(ValueError):
                current_ratio(value)

    def test_exact_restore_and_foreign_guard_rejection(self):
        plan = make_current_plan(self.firmware, 20)
        for base in INIT_TABLES:
            before = self.firmware.read(base, INIT_SIZE)
            after = guarded_init_table(before, self.firmware, plan, base)
            self.assertEqual(guarded_init_table(after, self.firmware, plan, base, restore=True), before)
            self.assertEqual([i for i, (a, b) in enumerate(zip(before, after)) if a != b], [28])
            for wrong in (b"\0" * INIT_SIZE, after):
                with self.assertRaises(ValueError):
                    guarded_init_table(wrong, self.firmware, plan, base)
        corrupt = copy.deepcopy(plan)
        corrupt["guards"][0]["after_hex"] = "00" * INIT_SIZE
        with self.assertRaises(ValueError):
            guarded_init_table(self.firmware.read(INIT_TABLES[0], INIT_SIZE),
                               self.firmware, corrupt, INIT_TABLES[0])

    def test_failed_i2c_write_is_not_treated_as_applied(self):
        cam = PmicModel(self.firmware)
        cam.write_error = -5
        event = cam.run("set_dim", 31)[0]
        self.assertEqual(event["result"], -5)
        self.assertEqual(cam.registers[4], 0xB2)

    def test_failed_enable_read_does_not_write(self):
        cam = PmicModel(self.firmware)
        cam.read_error = -5
        self.assertEqual(len(cam.run("lcd_enable", 1)), 1)
        self.assertEqual(cam.events[0]["op"], "read")
        self.assertEqual(cam.registers[0xE], 0xA9)

    def test_strict_execution_and_mutation_detection(self):
        cam = PmicModel(self.firmware)
        cam.allowed = ()
        with self.assertRaisesRegex(AssertionError, "unapproved PMIC execution"):
            cam.run("init")
        cam = PmicModel(self.firmware)
        # In emulator RAM only: a changed init current is detected independently.
        cam.uc.mem_write(INIT_TABLES[1] + 28, bytes([0xB3]))
        cam.run("init")
        with self.assertRaises(AssertionError):
            self.assertEqual(cam.registers[4], 0xB2)
        # In emulator RAM only: changing ORR's fixed VOUT8 bits is caught.
        cam = PmicModel(self.firmware)
        self.assertEqual(cam.u32(0xC0042A14), 0xE3A050A0)
        cam.put32(0xC0042A14, 0xE3A05080)
        cam.run("set_dim", 20)
        with self.assertRaises(AssertionError):
            self.assertEqual(cam.registers[4] & 0xE0, 0xA0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
