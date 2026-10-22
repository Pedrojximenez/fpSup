#!/usr/bin/env python3
"""Synthetic-environment tests; never proves original Lua/heap runtime readiness."""
import argparse
import json
from pathlib import Path
import sys
import unittest

import unicorn
from registry_probe import (RegistryProbe, ProbeError, load_firmware, validate_image,
                            BASE, SEG0_SHA256, REGISTER, LOOKUP_APP, MAP_APPEND,
                            NATIVE, LUA_WRAPPER, STRCMP)

IMAGE = None
OBSERVATIONS = {}
COVERAGE = set()
SERVICE_ADDRESSES = set()


class NativeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.p = RegistryProbe(IMAGE)

    def tearDown(self):
        COVERAGE.update(self.p.visited)
        SERVICE_ADDRESSES.update(call["address"] for call in self.p.calls)
        self.p.close()

    def full_map(self):
        self.p.close()
        self.p = RegistryProbe(IMAGE, map_capacity=2)
        for slot, name in enumerate(("existing_A", "existing_B")):
            _, name_address = self.p.definition(name, slot=slot)
            self.assertEqual(self.p.run(MAP_APPEND, self.p.MAP, name_address, self.p.RAM + 0x3800 + 0x20 * slot), 0)
        self.p.allocation_calls = 0

    def test_01_register_default_off_descriptor(self):
        self.assertEqual(self.p.register(), 0)
        status, descriptor = self.p.lookup()
        self.assertEqual(status, 0)
        self.assertNotEqual(descriptor, 0)
        self.assertEqual(self.p.words(descriptor, 8), (0, self.p.NAME, 0, 0, 0, 0, 0, 0))
        self.assertEqual(self.p.snapshot()["vector_count"], 1)
        self.assertEqual(self.p.snapshot()["map_count"], 1)
        OBSERVATIONS["success"] = self.p.snapshot()

    def test_02_integer_initial_value_one_and_both_lookup_routes(self):
        self.assertEqual(self.p.register(value=1), 0)
        self.assertEqual(self.p.lookup(), self.p.lookup(app_wrapper=False))
        self.assertEqual(self.p.words(self.p.lookup()[1] + 8)[0], 1)

    def test_03_borrowed_name_not_copied(self):
        self.assertEqual(self.p.register(), 0)
        descriptor = self.p.lookup()[1]
        self.assertEqual(self.p.words(descriptor + 4)[0], self.p.NAME)
        entry = self.p.words(self.p.MAP + 0xC)[0]
        self.assertEqual(self.p.words(entry + 4)[0], self.p.NAME)
        self.assertNotIn(self.p.NAME, self.p.blocks)

    def test_04_missing_lookup_success_with_null_out(self):
        self.assertEqual(self.p.lookup("not_registered"), (0, 0))
        self.assertEqual(self.p.register(), 0)
        self.assertEqual(self.p.lookup("not_registered", app_wrapper=False), (0, 0))

    def test_05_map_append_native_return_zero(self):
        _, name = self.p.definition()
        self.assertEqual(self.p.run(MAP_APPEND, self.p.MAP, name, self.p.RAM + 0x3800), 0)
        self.assertEqual(self.p.snapshot()["map_count"], 1)
        self.assertEqual(self.p.snapshot()["map_sorted"], 0)
        self.assertEqual(self.p.lookup()[1], self.p.RAM + 0x3800)

    def test_06_distinct_names_native_growth_and_hash_sort(self):
        self.assertEqual(self.p.register("MV_fpLossless", slot=0), 0)
        self.assertEqual(self.p.register("AA_private", value=1, slot=1), 0)
        for slot in range(2, 6):
            self.assertEqual(self.p.register("private_%d" % slot, value=slot, slot=slot), 0)
        first, second = self.p.lookup("MV_fpLossless")[1], self.p.lookup("AA_private")[1]
        self.assertNotEqual(first, second)
        self.assertEqual(self.p.words(first + 0xC)[0], 0)
        self.assertEqual(self.p.words(second + 0xC)[0], 1)
        self.assertIn("map_sort", self.p.visited)
        self.assertGreater(self.p.snapshot()["vector_capacity"], 4)
        self.assertGreater(self.p.snapshot()["map_capacity"], 4)
        for slot in range(2, 6):
            descriptor = self.p.lookup("private_%d" % slot)[1]
            self.assertNotEqual(descriptor, 0)
            self.assertEqual(self.p.words(descriptor + 8)[0], slot)

    def test_07_invalid_arguments_and_uninitialized_wrapper(self):
        definition, name = self.p.definition()
        self.assertEqual(self.p.run(REGISTER, 0, 1, definition), 6)
        self.assertEqual(self.p.run(REGISTER, self.p.APP, 0, definition), 3)
        self.assertEqual(self.p.run(REGISTER, self.p.APP, 1, 0), 4)
        self.assertEqual(self.p.run(LOOKUP_APP, self.p.APP, 0, self.p.OUT), 4)
        self.p.write_words(self.p.REGISTRY + 0x48, 0)
        self.assertEqual(self.p.run(LOOKUP_APP, self.p.APP, name, self.p.OUT), 2)

    def test_08_descriptor_allocation_failure_no_publish(self):
        before = self.p.snapshot()
        self.p.fail_allocation = {1}
        self.assertEqual(self.p.register(), 1)
        self.assertEqual(self.p.snapshot(), before)
        self.assertEqual(self.p.lua_names, [])

    def test_09_lua_failure_leaks_unpublished_descriptor(self):
        before = self.p.snapshot()
        self.p.lua_result = 3
        self.assertEqual(self.p.register(), 3)
        after = self.p.snapshot()
        self.assertEqual(after["live_allocations"], before["live_allocations"] + 1)
        self.assertEqual(after["vector_count"], 0)
        self.assertEqual(after["map_count"], 0)
        self.assertFalse(any(call["address"] == "0x%08X" % self.p.FREE for call in self.p.calls))
        OBSERVATIONS["lua_failure_descriptor_leak"] = after

    def test_10_vector_growth_failure_frees_descriptor_but_not_lua(self):
        self.p.write_words(self.p.REGISTRY + 8, 0)
        before = self.p.snapshot()
        self.p.fail_allocation = {2}
        self.assertEqual(self.p.register(), 1)
        after = self.p.snapshot()
        self.assertEqual(after["live_allocations"], before["live_allocations"])
        self.assertEqual(after["vector_count"], 0)
        self.assertEqual(after["map_count"], 0)
        self.assertEqual(after["lua_stub_names"], ["MV_fpLossless"])
        OBSERVATIONS["vector_failure_lua_not_rolled_back"] = after

    def test_11_map_first_growth_failure_leaves_vector_published(self):
        self.full_map()
        self.p.fail_allocation = {2}
        self.assertEqual(self.p.register(slot=2), 1)
        after = self.p.snapshot()
        self.assertEqual(after["vector_count"], 1)
        self.assertEqual(after["map_count"], 2)
        self.assertEqual(self.p.lookup(), (0, 0))
        OBSERVATIONS["map_first_growth_failure"] = after

    def test_12_map_second_growth_failure_changes_entries_before_capacity(self):
        self.full_map()
        before = self.p.snapshot()
        self.p.fail_allocation = {3}
        self.assertEqual(self.p.register(slot=2), 1)
        after = self.p.snapshot()
        self.assertEqual(after["vector_count"], 1)
        self.assertEqual(after["map_count"], 2)
        self.assertEqual(after["map_capacity"], before["map_capacity"])
        self.assertNotEqual(after["map_entries"], before["map_entries"])
        self.assertEqual(after["map_indices"], before["map_indices"])
        self.assertEqual(self.p.lookup(), (0, 0))
        OBSERVATIONS["map_second_growth_failure"] = after

    def test_13_initial_map_reserve_failure_before_descriptor(self):
        self.p.close()
        self.p = RegistryProbe(IMAGE, map_capacity=0)
        before = self.p.snapshot()
        self.p.fail_allocation = {1}
        self.assertEqual(self.p.register(), 1)
        self.assertEqual(self.p.snapshot(), before)
        self.assertEqual(self.p.lua_names, [])

    def test_14_bounds_and_unknown_execution_fail_closed(self):
        with self.assertRaisesRegex(ProbeError, "unknown external"):
            self.p.run(0xC05DB430, self.p.APP, 0, 0)
        with self.assertRaisesRegex(ProbeError, "bound exhausted"):
            self.p.run(LOOKUP_APP, self.p.APP, self.p.NAME, self.p.OUT, instruction_limit=1)
        self.p.definition()
        with self.assertRaisesRegex(ProbeError, "native write outside|write-protected"):
            self.p.run(LOOKUP_APP, self.p.APP, self.p.NAME, BASE)

    def test_15_reject_unpinned_firmware(self):
        with self.assertRaises(ProbeError):
            validate_image(b"not firmware")


def main():
    global IMAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seg0", required=True, type=Path)
    args = parser.parse_args()
    IMAGE = load_firmware(args.seg0)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeRegistryTests))
    passed = result.wasSuccessful() and not result.skipped
    print(json.dumps({
        "passed": passed, "tests_run": result.testsRun, "tests_skipped": len(result.skipped),
        "unicorn_version": unicorn.__version__, "seg0_sha256": SEG0_SHA256,
        "firmware_rx": True, "only_synthetic_ram_writable": True,
        "instruction_limit_per_call": RegistryProbe.MAX_INSTRUCTIONS,
        "timeout_us_per_call": RegistryProbe.TIMEOUT_US,
        "executed_native_functions": {name: ["0x%08X" % x for x in NATIVE[name]] for name in sorted(COVERAGE)},
        "stubbed_services": {"lua_wrapper": "0x%08X" % LUA_WRAPPER, "strcmp": "0x%08X" % STRCMP,
                             "allocator_alloc": "0x%08X" % RegistryProbe.ALLOC,
                             "allocator_free": "0x%08X" % RegistryProbe.FREE,
                             "allocator_realloc": "0x%08X" % RegistryProbe.REALLOC},
        "observed_service_addresses": sorted(SERVICE_ADDRESSES),
        "original_lua_executed": False, "original_allocator_executed": False,
        "registry_initialization": "synthetic layout, not original resource parser/VarData initialization",
        "camera_accessed": False, "hook_installed": False, "runtime_ready": False,
        "observations": OBSERVATIONS,
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
