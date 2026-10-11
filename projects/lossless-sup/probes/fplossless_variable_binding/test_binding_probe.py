#!/usr/bin/env python3
"""Bounded integer-only synthetic-environment native tests, no device access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest
import unicorn
from binding_probe import (BindingProbe, registry, EXTRA_NATIVE, SUBSCRIBE,
                           UNSUBSCRIBE, NOTIFY, SET_NOTIFY, SET_INDEX)

IMAGE = None
COVERAGE = set()
OBSERVATIONS = {}


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.p = BindingProbe(IMAGE)
        self.descriptor = self.p.register_private()

    def tearDown(self):
        COVERAGE.update(self.p.visited)
        self.p.close()

    def test_01_subscription_pair_copied_context_borrowed(self):
        self.assertEqual(self.p.subscribe(), 0)
        pair = self.p.words(self.descriptor + 0x18)[0]
        self.assertNotEqual(pair, self.p.PAIR)
        self.assertEqual(self.p.blocks[pair], 8)
        self.assertEqual(self.p.words(pair, 2), (self.p.PRIVATE_CALLBACK | 1, self.p.CONTEXT))
        self.p.write_words(self.p.PAIR, 0xDEAD0001, 0xDEAD0002)
        self.assertEqual(self.p.run(NOTIFY, self.p.APP, self.descriptor), 0)
        event = self.p.callback_events()[0]
        self.assertEqual((event["descriptor"], event["context"]), (self.descriptor, self.p.CONTEXT))

    def test_02_single_slot_and_duplicate_preserves_owner(self):
        self.assertEqual(self.p.subscribe(), 0)
        original = self.p.words(self.descriptor + 0x18)[0]
        before = self.p.allocation_calls
        self.assertEqual(self.p.subscribe(), 2)
        self.assertEqual(self.p.words(self.descriptor + 0x18)[0], original)
        self.assertEqual(self.p.allocation_calls, before)

    def test_03_missing_and_invalid_arguments(self):
        self.p.write(self.p.NAME, b"not_registered\0")
        self.assertEqual(self.p.subscribe(), 3)
        self.assertEqual(self.p.unsubscribe(), 3)
        self.assertEqual(self.p.run(SUBSCRIBE, 0, 0, self.p.PAIR), 6)
        self.assertEqual(self.p.run(SUBSCRIBE, self.p.APP, 0, 0), 4)
        self.assertEqual(self.p.run(UNSUBSCRIBE, 0, 0), 6)
        self.p.write_words(self.p.REGISTRY + 0x48, 0)
        self.assertEqual(self.p.subscribe(), 2)
        self.assertEqual(self.p.unsubscribe(), 2)

    def test_04_allocation_failure_no_subscription_published(self):
        self.p.fail_allocation = {self.p.allocation_calls + 1}
        self.assertEqual(self.p.subscribe(), 1)
        self.assertEqual(self.p.words(self.descriptor + 0x18)[0], 0)
        self.assertEqual(self.p.lock_depth, 0)

    def test_05_unsubscribe_frees_pair_and_is_not_idempotent_success(self):
        self.assertEqual(self.p.subscribe(), 0)
        pair = self.p.words(self.descriptor + 0x18)[0]
        self.assertEqual(self.p.unsubscribe(), 0)
        self.assertNotIn(pair, self.p.blocks)
        self.assertEqual(self.p.words(self.descriptor + 0x18)[0], 0)
        self.assertEqual(self.p.unsubscribe(), 2)
        self.p.events.clear()
        self.assertEqual(self.p.run(NOTIFY, self.p.APP, self.descriptor), 0)
        self.assertEqual(self.p.callback_events(), [])

    def test_06_global_slot_and_callback_return_precedence(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.assertEqual(self.p.subscribe(global_slot=True), 0)
        global_pair = self.p.words(self.p.REGISTRY + 0x5C)[0]
        self.assertEqual(self.p.words(global_pair, 2), (self.p.GLOBAL_CALLBACK | 1, self.p.CONTEXT + 16))
        self.p.callback_results = {self.p.PRIVATE_CALLBACK: 7, self.p.GLOBAL_CALLBACK: 9}
        self.assertEqual(self.p.run(NOTIFY, self.p.APP, self.descriptor), 7)
        self.assertEqual([x["kind"] for x in self.p.callback_events()], ["private", "global"])
        self.p.callback_results[self.p.PRIVATE_CALLBACK] = 0
        self.assertEqual(self.p.run(NOTIFY, self.p.APP, self.descriptor), 9)
        self.assertEqual(self.p.unsubscribe(global_slot=True), 0)
        self.assertEqual(self.p.words(self.p.REGISTRY + 0x5C)[0], 0)

    def test_07_named_integer_set_notify_and_lookup_read(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.p.events.clear()
        self.assertEqual(self.p.set_integer(1), 0)
        status, pointer = self.p.lookup()
        self.assertEqual((status, pointer), (0, self.descriptor))
        self.assertEqual(self.p.words(pointer, 4), (0, self.p.NAME, 1, 0))
        self.assertEqual(self.p.callback_events()[0]["value"], 1)
        self.assertEqual(self.p.callback_events()[0]["lock_depth"], 0)
        self.assertEqual(self.p.words(self.p.REGISTRY + 0x44)[0], 0)
        OBSERVATIONS["set_event_order"] = self.p.events[:]

    def test_08_unchanged_integer_no_callback_and_no_component_dispatch(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.p.events.clear()
        self.p.visited.clear()
        self.assertEqual(self.p.set_integer(0), 0)
        self.assertEqual(self.p.callback_events(), [])
        self.assertNotIn("dispatch_bound_components", self.p.visited)

    def test_09_no_callback_wrapper_still_dispatches_components(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.p.events.clear()
        self.p.visited.clear()
        self.assertEqual(self.p.set_integer(1, notify=False), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 1)
        self.assertEqual(self.p.callback_events(), [])
        self.assertIn("dispatch_bound_components", self.p.visited)

    def test_10_index_assignment_and_negative_index_name_lookup(self):
        self.assertEqual(self.p.set_integer(1, index=0), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 1)
        self.assertEqual(self.p.set_integer(0, index=-1), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 0)

    def test_11_unknown_name_and_wrapper_argument_checks(self):
        self.assertEqual(self.p.set_integer(1, name="missing"), 3)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 0)
        self.assertEqual(self.p.run(SET_NOTIFY, 0, 0, 1, self.p.ASSIGNMENT), 6)
        self.assertEqual(self.p.run(SET_NOTIFY, self.p.APP, 0, 0, self.p.ASSIGNMENT), 3)
        self.assertEqual(self.p.run(SET_NOTIFY, self.p.APP, 0, 1, 0), 4)
        self.assertEqual(self.p.run(SET_INDEX, self.p.APP, 0, self.p.ASSIGNMENT), 3)
        self.assertEqual(self.p.run(SET_INDEX, self.p.APP, 1, 0), 4)

    def test_12_native_integer_not_boolean_clamped(self):
        self.assertEqual(self.p.set_integer(7), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 7)
        self.assertEqual(self.p.set_integer(-1), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 0xFFFFFFFF)

    def test_13_callback_errors_not_propagated_by_setter(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.p.callback_results[self.p.PRIVATE_CALLBACK] = 7
        self.assertEqual(self.p.run(NOTIFY, self.p.APP, self.descriptor), 7)
        self.assertEqual(self.p.set_integer(1), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 1)

    def test_14_unsubscribe_after_callback_loaded_does_not_cancel_inflight(self):
        self.assertEqual(self.p.subscribe(), 0)
        saved = self.p.begin_paused_notify(self.descriptor, 0xC05D9FA4)
        self.assertEqual(self.p.unsubscribe_while_paused(), 0)
        self.p.events.clear()
        self.assertEqual(self.p.resume_saved(saved), 0)
        self.assertEqual(len(self.p.callback_events()), 1)
        OBSERVATIONS["post_unsubscribe_inflight_callback"] = self.p.callback_events()

    def test_15_unsubscribe_between_pair_load_and_dereference_exposes_freed_read(self):
        self.assertEqual(self.p.subscribe(), 0)
        saved = self.p.begin_paused_notify(self.descriptor, 0xC05D9F9C)
        self.assertEqual(self.p.unsubscribe_while_paused(), 0)
        with self.assertRaisesRegex(registry.ProbeError, "native read of freed"):
            self.p.resume_saved(saved)
        OBSERVATIONS["forced_interleaving_freed_read"] = True

    def test_16_allocation_failure_before_write_and_recursion_depth_gate(self):
        self.p.fail_allocation = {self.p.allocation_calls + 1}
        self.assertEqual(self.p.set_integer(1), 1)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 0)
        self.p.fail_allocation.clear()
        self.p.write_words(self.p.REGISTRY + 0x44, 10)
        self.assertEqual(self.p.set_integer(1), 2)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 0)

    def test_17_callback_can_unsubscribe_self_before_global_callback(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.assertEqual(self.p.subscribe(global_slot=True), 0)
        self.p.events.clear()
        self.p.private_callback_action = "unsubscribe_self"
        self.assertEqual(self.p.set_integer(1), 0)
        self.assertEqual(self.p.words(self.descriptor + 0x18)[0], 0)
        self.assertEqual([event["kind"] for event in self.p.callback_events()], ["private", "global"])
        self.assertEqual(self.p.lock_depth, 0)
        OBSERVATIONS["self_unsubscribe_during_callback"] = self.p.events[:]

    def test_18_callback_can_reenter_silent_setter_and_revert_before_outer_return(self):
        self.assertEqual(self.p.subscribe(), 0)
        self.p.events.clear()
        self.p.private_callback_action = "revert_without_app_callback"
        self.assertEqual(self.p.set_integer(1), 0)
        self.assertEqual(self.p.words(self.descriptor + 8)[0], 0)
        self.assertEqual(len(self.p.callback_events()), 1)
        self.assertEqual(self.p.words(self.p.REGISTRY + 0x44)[0], 0)
        OBSERVATIONS["synchronous_reentrant_revert"] = self.p.events[:]


def main():
    global IMAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seg0", required=True, type=Path)
    args = parser.parse_args()
    IMAGE = registry.load_firmware(args.seg0)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BindingTests))
    passed = result.wasSuccessful() and not result.skipped
    all_native = dict(registry.NATIVE, **EXTRA_NATIVE)
    print(json.dumps({"passed": passed, "tests_run": result.testsRun, "tests_skipped": len(result.skipped),
                      "probe_files_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                             for path in (Path(__file__), Path(__file__).with_name("binding_probe.py"),
                                                          Path(registry.__file__))},
                      "unicorn_version": unicorn.__version__, "seg0_sha256": registry.SEG0_SHA256,
                      "firmware_rx": True, "only_synthetic_ram_writable": True,
                      "instruction_limit": BindingProbe.MAX_INSTRUCTIONS, "timeout_us": BindingProbe.TIMEOUT_US,
                      "executed_native_functions": {name: ["0x%08X" % x for x in all_native[name]] for name in sorted(COVERAGE)},
                      "stubbed_services": ["Lua wrapper C05DB868", "strcmp C0013E2C", "synthetic alloc/free/realloc",
                                           "synthetic lock/unlock (no OS synchronization)",
                                           "private/global callbacks (capture; optional once-only tail-delegation to native unsubscribe/silent setter)"],
                      "original_lua_executed": False, "original_allocator_executed": False,
                      "original_ui_component_callbacks_executed": False,
                      "interleavings": "Deterministic pause/cancel/resume, not measured camera threading",
                      "runtime_ready": False, "camera_accessed": False, "hook_installed": False,
                      "observations": OBSERVATIONS}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
