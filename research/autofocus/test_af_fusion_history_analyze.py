"""Offline regression tests for completed native Near AF history analysis.

All mutations use in-memory copies of the recorded fixture.  No collector,
camera transport, or USB module is imported by these tests.
"""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from af_fusion_history_analyze import analyze_history, native_round


_HERE = Path(__file__).resolve().parent
_NOT_GIVEN = object()
_FIXTURE_CANDIDATES = (
    _HERE.parent.parent
    / "research/autofocus/captures/af-fusion/2026-09-16-s1-right-b/native-history.json",
    _HERE.parent
    / "af-live-trial/captures/2026-09-16-s1-right-b/native-history.json",
    _HERE / "captures/af-fusion/2026-09-16-s1-right-b/native-history.json",
)
ARRAY_BLOCKS = (
    "mposm",
    "aggregate_contrast",
    "area0_h_history",
    "area0_l_history",
)
METADATA_LENGTHS = {
    "near_object": 38,
    "sweep_descriptor": 24,
    "af_globals": 24,
}
ADDRESSES = {
    "near_object": 0xC3206BE4,
    "sweep_descriptor": 0xC320680C,
    "af_globals": 0xC32914E0,
    "mposm": 0xC3291958,
    "aggregate_contrast": 0xC32938A8,
    "area0_h_history": 0xC329B128,
    "area0_l_history": 0xC32CCE08,
}


class NativeHistoryAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for fixture in _FIXTURE_CANDIDATES:
            if fixture.is_file():
                cls.golden = json.loads(fixture.read_text(encoding="utf-8"))
                break
        else:
            raise FileNotFoundError("Recorded 2026-09-16-s1-right-b fixture is missing")

    def setUp(self):
        self.data = deepcopy(self.golden)

    def set_word(self, block, offset, value):
        """Change the same word in both passes so stability cannot mask a gate."""
        assert offset % 4 == 0
        for capture in self.data["passes"]:
            capture[block]["words"][offset // 4] = value

    def set_array(self, block, values):
        for capture in self.data["passes"]:
            capture[block]["words"] = list(values)

    def assert_invalid(self, data=_NOT_GIVEN):
        with self.assertRaises(ValueError):
            analyze_history(self.data if data is _NOT_GIVEN else data)

    def assert_no_candidate(self):
        # Unsupported peak geometry may reject analysis or preserve the samples
        # with an explicit missing candidate.  Neither may invent a position.
        try:
            result = analyze_history(self.data)
        except ValueError:
            return
        self.assertIsNone(result["peak"].get("native_formula_candidate_position"))

    def test_recorded_capture_has_six_same_index_pairs_and_native_peak(self):
        result = analyze_history(self.data)
        self.assertEqual(result["metadata"]["valid_count"], 6)
        expected = [
            (0, 10409, 3130, 34983, 3130),
            (1, 10340, 4071, 36619, 4071),
            (2, 10207, 6404, 39593, 6404),
            (3, 10076, 8577, 41945, 8577),
            (4, 9943, 8525, 42946, 8525),
            (5, 9809, 7497, 43042, 7497),
        ]
        actual = [
            tuple(sample[key] for key in ("k", "position", "h", "l", "aggregate"))
            for sample in result["samples"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(result["peak"]["native_formula_candidate_position"], 10013)
        self.assertTrue(result["full_dump_stable"])
        self.assertTrue(result["history_stable"])

    def test_analysis_does_not_mutate_source(self):
        before = deepcopy(self.data)
        analyze_history(self.data)
        self.assertEqual(self.data, before)

    def test_rejects_non_object_or_missing_passes(self):
        for value in (None, False, [], "history", {}, {"passes": None}):
            with self.subTest(value=value):
                self.assert_invalid(value)

    def test_requires_exactly_two_passes(self):
        for count in (0, 1, 3):
            with self.subTest(count=count):
                data = deepcopy(self.golden)
                data["passes"] = [deepcopy(self.golden["passes"][0]) for _ in range(count)]
                self.assert_invalid(data)

    def test_requires_the_supported_probe_mode(self):
        for mode in (None, "live-telemetry", "read-only", True):
            with self.subTest(mode=mode):
                self.data = deepcopy(self.golden)
                if mode is None:
                    del self.data["mode"]
                else:
                    self.data["mode"] = mode
                self.assert_invalid()

    def test_requires_mapping_passes_and_blocks(self):
        for invalid in (None, [], 7, "block"):
            with self.subTest(invalid=invalid):
                data = deepcopy(self.golden)
                data["passes"] = [invalid, invalid]
                self.assert_invalid(data)
        for name in ADDRESSES:
            with self.subTest(block=name):
                data = deepcopy(self.golden)
                for capture in data["passes"]:
                    del capture[name]
                self.assert_invalid(data)
        for invalid in (None, [], 7, "block"):
            with self.subTest(block_value=invalid):
                data = deepcopy(self.golden)
                for capture in data["passes"]:
                    capture["near_object"] = invalid
                self.assert_invalid(data)

    def test_rejects_wrong_or_missing_addresses_in_either_pass(self):
        for name, address in ADDRESSES.items():
            for pass_index in (0, 1):
                for value in (hex(address + 4), None, "not an address", True):
                    with self.subTest(block=name, pass_index=pass_index, address=value):
                        data = deepcopy(self.golden)
                        if value is None:
                            del data["passes"][pass_index][name]["address"]
                        else:
                            data["passes"][pass_index][name]["address"] = value
                        data.pop("two_passes_equal")
                        self.assert_invalid(data)

    def test_every_block_requires_unsigned_32_bit_integer_words(self):
        for name in ADDRESSES:
            for value in (-1, 0x100000000, True, False, 1.5, "1", None):
                with self.subTest(block=name, value=value):
                    self.data = deepcopy(self.golden)
                    # Last words are deliberately chosen to test unused tails.
                    for capture in self.data["passes"]:
                        capture[name]["words"][-1] = value
                    self.assert_invalid()

    def test_metadata_word_lengths_are_exact(self):
        for name, length in METADATA_LENGTHS.items():
            for actual_length in (0, length - 1, length + 1):
                with self.subTest(block=name, length=actual_length):
                    self.data = deepcopy(self.golden)
                    for capture in self.data["passes"]:
                        words = capture[name]["words"]
                        capture[name]["words"] = (words + [0])[:actual_length]
                    self.assert_invalid()

    def test_words_must_be_arrays(self):
        for invalid in (None, "1234", {"0": 1}, 3):
            with self.subTest(words=invalid):
                self.data = deepcopy(self.golden)
                for capture in self.data["passes"]:
                    capture["mposm"]["words"] = invalid
                self.assert_invalid()

    def test_history_arrays_have_equal_lengths(self):
        for name in ARRAY_BLOCKS:
            with self.subTest(block=name):
                self.data = deepcopy(self.golden)
                self.set_array(name, self.golden["passes"][0][name]["words"][:-1])
                self.assert_invalid()

    def test_history_arrays_length_is_bounded(self):
        for length in (0, 129):
            with self.subTest(length=length):
                self.data = deepcopy(self.golden)
                for name in ARRAY_BLOCKS:
                    words = self.golden["passes"][0][name]["words"]
                    self.set_array(name, (words + [0] * length)[:length])
                self.assert_invalid()

    def test_exact_completed_prefix_is_sufficient(self):
        for name in ARRAY_BLOCKS:
            self.set_array(name, self.golden["passes"][0][name]["words"][:6])
        self.assertEqual(len(analyze_history(self.data)["samples"]), 6)

    def test_one_sample_and_zero_delay_are_structurally_valid(self):
        self.set_word("near_object", 0x3C, 0)
        self.set_word("near_object", 0x08, 0)
        self.set_word("sweep_descriptor", 0x08, 1)
        self.set_word("sweep_descriptor", 0x50, 0)
        for name in ARRAY_BLOCKS:
            self.set_array(name, self.golden["passes"][0][name]["words"][:1])
        result = analyze_history(self.data)
        self.assertEqual(result["metadata"]["valid_count"], 1)
        self.assertEqual(len(result["samples"]), 1)
        self.assertIsNone(result["peak"]["native_formula_candidate_position"])

    def test_zero_delay_uses_inclusive_raw_index(self):
        self.set_word("near_object", 0x3C, 5)
        self.set_word("near_object", 0x08, 0)
        self.set_word("sweep_descriptor", 0x50, 0)
        result = analyze_history(self.data)
        self.assertEqual(result["metadata"]["valid_count"], 6)
        self.assertEqual(result["samples"][-1]["position"], 9809)

    def test_prefix_shorter_than_last_completed_slot_is_rejected(self):
        for name in ARRAY_BLOCKS:
            self.set_array(name, self.golden["passes"][0][name]["words"][:5])
        self.assert_invalid()

    def test_maximum_capture_prefix_is_accepted(self):
        for name in ARRAY_BLOCKS:
            words = self.golden["passes"][0][name]["words"]
            self.set_array(name, words + [0] * (128 - len(words)))
        self.assertEqual(len(analyze_history(self.data)["samples"]), 6)

    def test_declared_equality_is_optional_but_must_be_truthful(self):
        del self.data["two_passes_equal"]
        self.assertEqual(len(analyze_history(self.data)["samples"]), 6)
        for value in (False, 0, 1, "true", None):
            with self.subTest(flag=value):
                self.data = deepcopy(self.golden)
                self.data["two_passes_equal"] = value
                self.assert_invalid()

    def test_false_equality_claim_cannot_hide_permitted_live_change(self):
        self.data["passes"][1]["af_globals"]["words"][7] += 1
        # The stale true flag describes full-pass equality and must be rejected.
        self.assert_invalid()

    def test_only_live_reference_word_may_change_between_passes(self):
        self.data["passes"][1]["af_globals"]["words"][7] += 1
        self.data["two_passes_equal"] = False
        result = analyze_history(self.data)
        self.assertFalse(result["full_dump_stable"])
        self.assertTrue(result["history_stable"])
        self.assertEqual(result["metadata"]["valid_count"], 6)
        self.assertEqual(result["peak"]["native_formula_candidate_position"], 10013)

    def test_any_other_word_change_rejects_even_outside_completed_prefix(self):
        for name in ADDRESSES:
            for index in range(len(self.golden["passes"][0][name]["words"])):
                if name == "af_globals" and index == 7:
                    continue
                with self.subTest(block=name, word_index=index):
                    data = deepcopy(self.golden)
                    data["passes"][1][name]["words"][index] ^= 1
                    data["two_passes_equal"] = False
                    self.assert_invalid(data)

    def test_accepts_completed_near_states_four_and_six(self):
        for state in (4, 6):
            with self.subTest(state=state):
                self.set_word("near_object", 0x18, state)
                self.assertEqual(len(analyze_history(self.data)["samples"]), 6)

    def test_rejects_other_near_states(self):
        for state in (0, 1, 2, 3, 5, 7, 0xFFFFFFFF):
            with self.subTest(state=state):
                self.set_word("near_object", 0x18, state)
                self.assert_invalid()

    def test_requires_near_vtable(self):
        self.set_word("near_object", 0x38, 0xC091F138)
        self.assert_invalid()

    def test_requires_completion_byte_equal_to_one(self):
        for completion in (0, 2, 0x100):
            with self.subTest(completion=completion):
                self.set_word("near_object", 0x28, completion)
                self.assert_invalid()

    def test_completion_is_a_byte_not_an_entire_word(self):
        self.set_word("near_object", 0x28, 0x11223301)
        self.assertEqual(len(analyze_history(self.data)["samples"]), 6)

    def test_requires_zero_near_history_offset(self):
        self.set_word("near_object", 0x10, 1)
        self.assert_invalid()

    def test_delay_and_raw_index_bounds(self):
        for raw_n, delay in ((0, 1), (6, 7), (1000, 1), (0xFFFFFFFF, 1), (6, 0xFFFFFFFF)):
            with self.subTest(raw_n=raw_n, delay=delay):
                self.data = deepcopy(self.golden)
                self.set_word("near_object", 0x3C, raw_n)
                self.set_word("near_object", 0x08, delay)
                self.set_word("sweep_descriptor", 0x50, delay)
                self.assert_invalid()

    def test_descriptor_count_must_equal_inclusive_valid_count(self):
        for count in (0, 5, 7):
            with self.subTest(count=count):
                self.set_word("sweep_descriptor", 0x08, count)
                self.assert_invalid()

    def test_delay_copy_must_match(self):
        self.set_word("sweep_descriptor", 0x50, 0)
        self.assert_invalid()

    def test_requires_all_expected_descriptor_pointers(self):
        pointers = {
            0x40: ADDRESSES["aggregate_contrast"],
            0x44: ADDRESSES["area0_h_history"],
            0x48: ADDRESSES["area0_l_history"],
            0x4C: ADDRESSES["mposm"],
        }
        for offset, pointer in pointers.items():
            with self.subTest(offset=hex(offset)):
                self.data = deepcopy(self.golden)
                self.set_word("sweep_descriptor", offset, pointer + 4)
                self.assert_invalid()

    def test_selected_and_live_area_must_both_be_zero(self):
        for offset in (0x34, 0x54):
            for area in (1, 50, 0xFFFFFFFF):
                with self.subTest(offset=hex(offset), area=area):
                    self.data = deepcopy(self.golden)
                    self.set_word("af_globals", offset, area)
                    self.assert_invalid()

    def test_zero_position_is_valid_and_signed_positions_are_decoded(self):
        positions = (300, 200, 100, 0, -100, -200)
        encoded = [value & 0xFFFFFFFF for value in positions] + [0] * 26
        self.set_array("mposm", encoded)
        result = analyze_history(self.data)
        self.assertEqual([sample["position"] for sample in result["samples"]], list(positions))
        self.assertEqual(result["metadata"]["valid_count"], 6)

    def test_final_completed_zero_position_is_not_trimmed(self):
        self.set_word("mposm", 5 * 4, 0)
        samples = analyze_history(self.data)["samples"]
        self.assertEqual(len(samples), 6)
        self.assertEqual(samples[-1]["position"], 0)

    def test_statistics_remain_unsigned(self):
        for name in ("aggregate_contrast", "area0_h_history", "area0_l_history"):
            self.set_word(name, 0, 0xFFFFFFFF)
        sample = analyze_history(self.data)["samples"][0]
        for key in ("aggregate", "h", "l"):
            self.assertEqual(sample[key], 0xFFFFFFFF)

    def test_peak_at_either_endpoint_has_no_interpolated_candidate(self):
        for values in ((9000, 8000, 7000, 6000, 5000, 4000), (4000, 5000, 6000, 7000, 8000, 9000)):
            with self.subTest(values=values):
                self.data = deepcopy(self.golden)
                for name in ("area0_h_history", "aggregate_contrast"):
                    self.set_array(name, list(values) + [0] * 26)
                self.assert_no_candidate()

    def test_tied_or_flat_maximum_has_no_interpolated_candidate(self):
        for values in ((3130, 4071, 6404, 8577, 8577, 7497), (8000,) * 6, (3130, 8577, 6404, 8577, 8525, 7497)):
            with self.subTest(values=values):
                self.data = deepcopy(self.golden)
                for name in ("area0_h_history", "aggregate_contrast"):
                    self.set_array(name, list(values) + [0] * 26)
                self.assert_no_candidate()

    def test_duplicate_or_reversing_positions_have_no_candidate(self):
        for positions in (
            (10409, 10340, 10076, 10076, 9943, 9809),
            (10409, 10340, 10207, 10076, 10100, 9809),
            (10409, 10500, 10207, 10076, 9943, 9809),
        ):
            with self.subTest(positions=positions):
                self.data = deepcopy(self.golden)
                self.set_array("mposm", list(positions) + [0] * 26)
                self.assert_no_candidate()

    def test_success_does_not_claim_dfd_readiness(self):
        result = analyze_history(self.data)
        self.assertIsNone(result["usable_for_dfd"])
        self.assertIsNone(result["freshness_confirmed"])
        self.assertIn("not full firmware replay", result["peak"]["scope"])

        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"dfd_usable", "usable_for_dfd", "dfd_ready", "ready_for_dfd"}:
                        self.assertIsNot(item, True)
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(result)

    def test_native_rounding_is_nearest_with_ties_away_from_zero(self):
        for value, expected in (
            (0.0, 0), (0.49, 0), (0.5, 1), (0.6, 1), (1.5, 2),
            (-0.49, 0), (-0.5, -1), (-0.6, -1), (-1.5, -2),
        ):
            with self.subTest(value=value):
                self.assertEqual(native_round(value), expected)


if __name__ == "__main__":
    unittest.main()
