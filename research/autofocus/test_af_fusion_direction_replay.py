"""Offline tests for exploratory direction diagnostics and their limitations.

The original four native-history files are read only.  Altered evidence and
CLI output are confined to disposable temporary directories; no USB is used.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import af_fusion_history_analyze
from af_fusion_direction_replay import analyze_curve, level_crossings, load_trial


HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent.parent / "research" / "autofocus"
CAPTURES = RESEARCH / "captures" / "af-fusion"
TRIAL_NAMES = (
    "2026-09-16-s1-right-b",
    "2026-09-16-repeat-a",
    "2026-09-16-repeat-b",
    "2026-09-16-repeat-c",
)
SOURCES = tuple(CAPTURES / name / "native-history.json" for name in TRIAL_NAMES)
SCRIPT = HERE / "af_fusion_direction_replay.py"
METRICS = ("h", "l", "h_over_l")


def run_cli(*arguments):
    environment = os.environ.copy()
    import_directory = str(Path(af_fusion_history_analyze.__file__).resolve().parent)
    environment["PYTHONPATH"] = os.pathsep.join(
        [import_directory, environment.get("PYTHONPATH", "")]
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in arguments)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        timeout=10,
    )


@contextmanager
def temporary_trial():
    with tempfile.TemporaryDirectory(prefix="af-direction-test-") as directory:
        root = Path(directory)
        for name in ("native-history.json", "manifest.json"):
            shutil.copyfile(SOURCES[0].parent / name, root / name)
        yield root / "native-history.json"


class CurveAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.histories = [
            af_fusion_history_analyze.analyze_history(json.loads(source.read_bytes()))
            for source in SOURCES
        ]
        cls.curves = [analyze_curve(history) for history in cls.histories]

    def setUp(self):
        self.history = deepcopy(self.histories[0])

    def test_all_four_captures_have_six_samples_and_one_excluded_pair(self):
        for name, result in zip(TRIAL_NAMES, self.curves):
            with self.subTest(trial=name):
                self.assertEqual(len(result["samples"]), 6)
                self.assertEqual(len(result["pairs"]), 5)
                self.assertEqual(result["crossing_pairs_excluded_from_agreement"], 1)
                for metric in METRICS:
                    self.assertEqual(result["metrics"][metric]["same_side_pair_count"], 4)

    def test_golden_totals_are_internal_reference_agreement(self):
        for metric, agreements in (("h", 16), ("h_over_l", 16), ("l", 12)):
            with self.subTest(metric=metric):
                stats = [result["metrics"][metric] for result in self.curves]
                self.assertEqual(sum(row["same_side_pair_count"] for row in stats), 16)
                self.assertEqual(
                    sum(row["same_side_agree_with_native_H_reference"] for row in stats),
                    agreements,
                )
                self.assertEqual(sum(row["same_side_abstain_count"] for row in stats), 0)
                self.assertEqual(sum(row["same_side_disagree_count"] for row in stats), 16 - agreements)

    def test_l_maximum_is_the_final_endpoint_in_every_capture(self):
        for result in self.curves:
            with self.subTest(peak=result["native_H_reference_peak"]):
                low = result["metrics"]["l"]
                self.assertTrue(low["argmax_has_endpoint"])
                self.assertEqual(low["sample_argmax_indices"], [5])
                self.assertEqual(low["sample_argmax_positions"], [result["samples"][-1]["position"]])

    def test_repeat_a_ratio_maximum_differs_from_h_maximum(self):
        result = self.curves[1]
        self.assertNotEqual(
            result["metrics"]["h"]["sample_argmax_indices"],
            result["metrics"]["h_over_l"]["sample_argmax_indices"],
        )

    def test_augmented_samples_keep_original_pairing(self):
        result = analyze_curve(self.history)
        for before, after in zip(self.history["samples"], result["samples"]):
            for key in ("k", "position", "h", "l", "aggregate"):
                self.assertEqual(after[key], before[key])
            self.assertEqual(after["position_minus_native_peak"], before["position"] - 10013)
            self.assertAlmostEqual(after["h_over_l"], before["h"] / before["l"])

    def test_analysis_does_not_mutate_its_history_report(self):
        before = deepcopy(self.history)
        analyze_curve(self.history)
        self.assertEqual(self.history, before)

    def test_reversing_sample_order_preserves_all_agreement_totals(self):
        forward = analyze_curve(self.history)
        self.history["samples"].reverse()
        reverse = analyze_curve(self.history)
        for metric in METRICS:
            for key in (
                "same_side_pair_count",
                "same_side_agree_with_native_H_reference",
                "same_side_abstain_count",
                "same_side_disagree_count",
            ):
                self.assertEqual(forward["metrics"][metric][key], reverse["metrics"][metric][key])
        self.assertEqual(reverse["crossing_pairs_excluded_from_agreement"], 1)

    def test_pair_direction_uses_position_change_not_capture_order(self):
        result = analyze_curve(self.history)
        first, final = result["pairs"][0], result["pairs"][-1]
        self.assertLess(first["delta_position"], 0)
        self.assertGreater(first["metrics"]["h"]["delta"], 0)
        self.assertEqual(first["metrics"]["h"]["gradient_direction"], -1)
        self.assertEqual(first["target_direction_from_second_point"], -1)
        self.assertEqual(final["metrics"]["h"]["gradient_direction"], 1)
        self.assertEqual(final["target_direction_from_second_point"], 1)

    def test_crossing_pair_has_no_direction_label(self):
        crossing = [pair for pair in self.curves[0]["pairs"] if pair["crosses_or_touches_native_peak"]]
        self.assertEqual(len(crossing), 1)
        self.assertEqual((crossing[0]["from_k"], crossing[0]["to_k"]), (3, 4))
        self.assertIsNone(crossing[0]["target_direction_from_second_point"])

    def test_pairs_touching_peak_are_also_excluded(self):
        self.history["peak"]["near_peak_position"] = self.history["samples"][3]["position"]
        result = analyze_curve(self.history)
        self.assertEqual(result["crossing_pairs_excluded_from_agreement"], 2)
        for metric in METRICS:
            self.assertEqual(result["metrics"][metric]["same_side_pair_count"], 3)

    def test_zero_l_yields_missing_ratio_and_adjacent_abstentions(self):
        self.history["samples"][1]["l"] = 0
        result = analyze_curve(self.history)
        self.assertIsNone(result["samples"][1]["h_over_l"])
        stats = result["metrics"]["h_over_l"]
        self.assertEqual(stats["same_side_pair_count"], 4)
        self.assertEqual(stats["same_side_abstain_count"], 2)
        self.assertEqual(stats["same_side_agree_with_native_H_reference"], 2)
        for pair in result["pairs"][:2]:
            self.assertIsNone(pair["metrics"]["h_over_l"]["delta"])
            self.assertIsNone(pair["metrics"]["h_over_l"]["gradient_direction"])

    def test_all_zero_l_has_no_ratio_peak_or_crossings(self):
        for row in self.history["samples"]:
            row["l"] = 0
        result = analyze_curve(self.history)
        stats = result["metrics"]["h_over_l"]
        self.assertEqual(stats["sample_argmax_indices"], [])
        self.assertEqual(stats["same_side_abstain_count"], 4)
        self.assertIsNone(stats["opposite_side_sample_range_overlap"])
        self.assertEqual(result["ratio_level_piecewise_linear_crossings"], {"positions": [], "flat_intervals": []})
        json.dumps(result, allow_nan=False)

    def test_flat_metric_abstains_instead_of_counting_a_direction(self):
        self.history["samples"][1]["h"] = self.history["samples"][0]["h"]
        result = analyze_curve(self.history)
        self.assertEqual(result["pairs"][0]["metrics"]["h"]["gradient_direction"], 0)
        self.assertEqual(result["metrics"]["h"]["same_side_abstain_count"], 1)

    def test_rejects_nonfinite_or_nonpositive_ratio_level(self):
        for level in (float("nan"), float("inf"), float("-inf"), 0, -0.19):
            with self.subTest(level=level), self.assertRaises(ValueError):
                analyze_curve(self.history, level)

    def test_requires_matched_native_interior_peak(self):
        for match in (False, None, 1, "true"):
            with self.subTest(match=match):
                self.history["peak"]["matches_near_peak"] = match
                with self.assertRaises(ValueError):
                    analyze_curve(self.history)

    def test_rejects_nonmonotonic_or_duplicate_positions(self):
        for position in (self.history["samples"][0]["position"], 12000):
            with self.subTest(position=position):
                self.history["samples"][1]["position"] = position
                with self.assertRaises(ValueError):
                    analyze_curve(self.history)

    def test_requires_three_samples_and_reference_bracketing(self):
        for count in (0, 1, 2):
            with self.subTest(count=count), self.assertRaises(ValueError):
                history = deepcopy(self.history)
                history["samples"] = history["samples"][:count]
                analyze_curve(history)
        for peak in (9809, 10409, 9000, 11000):
            with self.subTest(peak=peak), self.assertRaises(ValueError):
                history = deepcopy(self.history)
                history["peak"]["near_peak_position"] = peak
                analyze_curve(history)


class LevelCrossingTests(unittest.TestCase):
    def test_linear_intersections_in_both_position_directions(self):
        for points in ([(0, 0), (10, 1)], [(10, 1), (0, 0)]):
            with self.subTest(points=points):
                self.assertEqual(level_crossings(points, 0.25), {"positions": [2.5], "flat_intervals": []})

    def test_curve_can_cross_same_ratio_on_both_sides(self):
        result = level_crossings([(0, 0), (10, 1), (20, 0)], 0.5)
        self.assertEqual(result, {"positions": [5.0, 15.0], "flat_intervals": []})

    def test_shared_endpoint_intersection_is_not_duplicated(self):
        result = level_crossings([(0, 0), (10, 1), (20, 0)], 1)
        self.assertEqual(result["positions"], [10.0])

    def test_flat_level_returns_interval_without_unique_position(self):
        result = level_crossings([(20, 0.19), (10, 0.19)], 0.19)
        self.assertEqual(result, {"positions": [], "flat_intervals": [[10, 20]]})

    def test_no_extrapolation_or_bridging_missing_ratios(self):
        for points, level in (
            ([(0, 0), (10, 1)], 2),
            ([(0, 0), (10, 1)], -1),
            ([(0, 0), (5, None), (10, 1)], 0.5),
            ([(0, 0.2), (10, 0.2)], 0.19),
            ([], 0.19),
            ([(0, 0.19)], 0.19),
        ):
            with self.subTest(points=points, level=level):
                self.assertEqual(level_crossings(points, level), {"positions": [], "flat_intervals": []})


class TrialAndCommandLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.command = run_cli(*SOURCES)
        if cls.command.returncode != 0:
            raise AssertionError(cls.command.stderr)
        cls.report = json.loads(cls.command.stdout)

    def test_cli_totals_and_explicit_limitations(self):
        report = self.report
        self.assertEqual(len(report["trials"]), 4)
        self.assertEqual(report["crossing_pairs_excluded_from_agreement"], 4)
        for metric, count in (("h", 16), ("h_over_l", 16), ("l", 12)):
            self.assertEqual(report["totals"][metric]["same_side_pair_count"], 16)
            self.assertEqual(report["totals"][metric]["same_side_agree_with_native_H_reference"], count)
        self.assertEqual(report["mode"], "offline-exploratory")
        self.assertIs(report["camera_touched"], False)
        self.assertIs(report["optical_direction_validated"], False)
        self.assertIsNone(report["usable_for_dfd"])
        caveats = " ".join(report["limitations"])
        self.assertIn("not independent optical truth", caveats)
        self.assertIn("not held-out prediction accuracy", caveats)
        self.assertRegex(caveats, r"not a (?:learned )?controller threshold")

    def test_load_trial_records_exact_source_and_manifest_hashes(self):
        source = SOURCES[0]
        before = source.read_bytes()
        manifest = (source.parent / "manifest.json").read_bytes()
        result = load_trial(source, 0.19)
        self.assertEqual(result["source"], str(source.resolve()))
        self.assertEqual(result["name"], TRIAL_NAMES[0])
        self.assertEqual(result["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(manifest).hexdigest())
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual((source.parent / "manifest.json").read_bytes(), manifest)

    def test_legacy_or_missing_dma_transport_is_rejected(self):
        for transport in ("direct-code-cave-dma/v1", "legacy", None):
            with self.subTest(transport=transport), temporary_trial() as source:
                path = source.parent / "manifest.json"
                manifest = json.loads(path.read_bytes())
                if transport is None:
                    del manifest["handler_transport"]
                else:
                    manifest["handler_transport"] = transport
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "transport"):
                    load_trial(source, 0.19)

    def test_original_trial_and_complete_release_evidence_are_required(self):
        for key, value in (
            ("mode", "read-only-observation"),
            ("release_transport_completed", False),
            ("release_transport_completed", 1),
            ("release_still_required", True),
            ("release_still_required", 0),
        ):
            with self.subTest(key=key, value=value), temporary_trial() as source:
                path = source.parent / "manifest.json"
                manifest = json.loads(path.read_bytes())
                manifest[key] = value
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_trial(source, 0.19)

    def test_load_trial_revalidates_raw_history_structure(self):
        with temporary_trial() as source:
            raw = json.loads(source.read_bytes())
            raw["passes"][1]["mposm"]["words"][0] += 1
            raw["two_passes_equal"] = False
            source.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_trial(source, 0.19)

    def test_cli_rejects_duplicate_sources_and_same_trial_rereads(self):
        for arguments in ((SOURCES[0], SOURCES[0]),):
            command = run_cli(*arguments)
            self.assertEqual(command.returncode, 2)
            self.assertIn("same trial twice", command.stderr)
            self.assertEqual(command.stdout, "")
        with temporary_trial() as source:
            reread = source.with_name("native-history-reread.json")
            shutil.copyfile(source, reread)
            command = run_cli(source, reread)
            self.assertEqual(command.returncode, 2)
            self.assertIn("same trial twice", command.stderr)

    def test_cli_rejects_nonfinite_ratio_arguments(self):
        for level in ("nan", "inf", "-inf", "0", "-0.19"):
            with self.subTest(level=level):
                command = run_cli(SOURCES[0], "--ratio-level=" + level)
                self.assertEqual(command.returncode, 2)
                self.assertIn("finite and positive", command.stderr)
                self.assertEqual(command.stdout, "")

    def test_cli_preserves_existing_output_and_raw_evidence(self):
        with tempfile.TemporaryDirectory(prefix="af-direction-output-test-") as directory:
            target = Path(directory) / "already-exists.json"
            sentinel = b"existing output must survive\n"
            target.write_bytes(sentinel)
            command = run_cli(SOURCES[0], "--output", target)
            self.assertEqual(command.returncode, 2)
            self.assertIn("never overwrite evidence", command.stderr)
            self.assertEqual(target.read_bytes(), sentinel)
        original = SOURCES[0].read_bytes()
        command = run_cli(SOURCES[0], "--output", SOURCES[0])
        self.assertEqual(command.returncode, 2)
        self.assertEqual(SOURCES[0].read_bytes(), original)

    def test_cli_writes_new_json_output(self):
        with tempfile.TemporaryDirectory(prefix="af-direction-output-test-") as directory:
            target = Path(directory) / "direction-report.json"
            command = run_cli(SOURCES[0], "--ratio-level", "0.18", "--output", target)
            self.assertEqual(command.returncode, 0, command.stderr)
            self.assertEqual(command.stdout.strip(), str(target))
            result = json.loads(target.read_bytes())
            self.assertEqual(len(result["trials"]), 1)
            self.assertEqual(result["trials"][0]["illustrative_ratio_level"], 0.18)
            self.assertIs(result["optical_direction_validated"], False)


if __name__ == "__main__":
    unittest.main()
