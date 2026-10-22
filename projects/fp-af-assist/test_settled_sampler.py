import copy
import unittest

import settled_sampler as sampler


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


class FakeIO:
    def __init__(self, clock):
        self.clock = clock
        self.reads = []
        self.h_reads = 0
        self.l_reads = 0
        self.h_values = [1000, 1010, 990]
        self.l_values = [5000, 5050, 4950]
        self.stalled = False
        self.read_latency = 0
        self.hook = None
        self.phase_override = None
        self.memory = {
            sampler.SCHEDULER + 4: 1,
            sampler.SCHEDULER + 24: sampler.OBSERVER,
            sampler.SCHEDULER + 28: 0xC090F0AC,
            sampler.SCHEDULER + 32: 0xC090F2EC,
            sampler.SCHEDULER + 36: 1,
            sampler.OBSERVER: 0xC09185A4,
            sampler.OBSERVER + 4: 2,
            sampler.OBSERVER + 8: 0xC09185F8,
            sampler.OBSERVER + 12: 1,
            sampler.TIMING_SELECTOR: 0,
            sampler.TIMING_CACHED: 0,
            sampler.TIMING_MMIO: 0,
            sampler.RAW_SUBCYCLE: 0,
            sampler.AREA_METADATA: 0,
            sampler.AREA_METADATA + 32: 0,
            sampler.AREA_METADATA + 156: 14,
            sampler.AREA_METADATA + 160: 117,
            sampler.ROI_COUNT: 1,
            sampler.GAIN_BASE: 117,
            sampler.GAIN_BASE + 8: 985,
            sampler.GAIN_BASE + 20: 131,
            sampler.GAIN_BASE + 28: 0,
            sampler.EXPOSURE_BASE: 218,
            sampler.EXPOSURE_BASE + 8: 8333,
            sampler.EXPOSURE_BASE + 28: 2164,
            sampler.HPF_BASE: 1,
            sampler.HPF_BASE + 4: 1,
            sampler.AF_DRIVE: 2,
            sampler.AF_AREA: 0,
            sampler.AF_PROCESSING_FLAG: 0,
            sampler.CAPTURE_BUSY: 0,
            sampler.CAPTURE_BUSY + 8: 0,
            sampler.CAPTURE_SEQUENCE: 0,
        }

    def read(self, address, count=1):
        self.reads.append((address, count))
        self.clock.now += self.read_latency
        if self.hook:
            override = self.hook(address, count)
            if override is not None:
                return override
        result = []
        for current in range(address, address + count * 4, 4):
            if current == sampler.SCHEDULER:
                phase = 0 if self.stalled else int(self.clock.now / 0.020) % 3
                result.append(phase if self.phase_override is None else self.phase_override)
            elif current == sampler.H_ADDRESS:
                result.append(self.h_values[self.h_reads % len(self.h_values)])
                self.h_reads += 1
            elif current == sampler.L_ADDRESS:
                result.append(self.l_values[self.l_reads % len(self.l_values)])
                self.l_reads += 1
            else:
                result.append(self.memory.get(current, 0))
        return result

    def ensure(self, *args):
        raise AssertionError("sampler must never write")

    def shell(self, *args):
        raise AssertionError("sampler must never send arbitrary shell commands")


class FakeBridge:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.state_reads = 0
        self.settings_reads = 0
        self.position = 10000
        self.native_state = {"position": 10000, "min_position": 5900, "max_position": 11116,
                             "native_done": True, "capture_idle": True, "af_route": 14,
                             "focus_flags": 3, "lens_ready": 1, "property_predicate": 0,
                             "lens_sync_flags": 1, "movie_recording": False}
        self.baseline = {"menu SetFocusPosition": "448 277 128 128", "menu SetFocusMode": "0",
                         "menu SetFocusArea": "0", "menu SetFocusAreaSize": "3"}
        self.current_settings = dict(self.baseline)
        self.state_hook = None
        self.call_hook = None
        self.settings_hook = None

    def read_state(self):
        self.state_reads += 1
        if self.state_hook:
            self.state_hook()
        return dict(self.native_state)

    def call(self, operation):
        self.calls.append(operation)
        if operation != 0:
            raise AssertionError("no non-getter operation is permitted")
        if self.call_hook:
            self.call_hook()
        return self.position & 0xFFFFFFFF, [0, 0, 0]

    def settings(self):
        self.settings_reads += 1
        if self.settings_hook:
            self.settings_hook()
        return dict(self.current_settings)


class SettledSamplerTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.io = FakeIO(self.clock)
        self.bridge = FakeBridge(self.clock)
        self.events = []
        self.subject = self.make_sampler()

    def make_sampler(self, **kwargs):
        return sampler.SettledSampler(self.io, self.bridge, clock=self.clock,
                                      sleep=self.clock.sleep, event=self.events.append, **kwargs)

    def test_native_minus_one_selector_uses_mmio_not_cached_timing(self):
        self.io.memory[sampler.TIMING_SELECTOR] = sampler.U32_MAX
        self.io.memory[sampler.TIMING_CACHED] = 99
        result = self.subject.observe()
        self.assertTrue(result['valid'])
        self.assertIn((sampler.TIMING_MMIO, 1), self.io.reads)
        self.assertNotIn((sampler.TIMING_CACHED, 1), self.io.reads)

    def test_mode_one_valid_scalar_medians_and_evidence(self):
        result = self.subject.observe()
        self.assertTrue(result["valid"])
        self.assertEqual(result["method"], "scheduler_progress_checked")
        self.assertEqual(result["h"], 1000)
        self.assertEqual(result["l"], 5000)
        self.assertEqual(result["gain"], [117, 985, 131, 0])
        self.assertFalse(result["optical_focus_verified"])
        self.assertFalse(result["exposure_alignment_verified"])
        self.assertFalse(result["usable_for_dfd"])
        evidence = result["evidence"]
        self.assertGreaterEqual(len(evidence["observed_transitions"]), 2)
        self.assertEqual(len(evidence["samples"]), 3)
        self.assertGreaterEqual(evidence["samples"][0]["started_at"], 0.150)
        counts = [item["observed_transition_count"] for item in evidence["samples"]]
        self.assertTrue(all(right > left for left, right in zip(counts, counts[1:])))
        self.assertLess(evidence["elapsed_s"], 2.0)
        self.assertEqual(evidence["noise"]["h"]["relative_spread"], 0.02)
        self.assertEqual(self.bridge.state_reads, 2)
        self.assertTrue(all(operation == 0 for operation in self.bridge.calls))
        self.assertTrue(all(0 < count <= 41 and address % 4 == 0 for address, count in self.io.reads))
        self.assertTrue(all(0 < duration <= 0.005 for duration in self.clock.sleeps))

    def test_mode_three_supported_without_context_changing_on_phase(self):
        self.io.memory[sampler.SCHEDULER + 4] = 3
        first = self.subject.observe()
        second = self.subject.observe()
        self.assertEqual(first["context"], second["context"])
        self.assertGreater(len(first["evidence"]["observed_transitions"]), 2)

    def test_same_h_values_still_need_progress_and_can_be_valid(self):
        self.io.h_values = [1234]
        self.io.l_values = [5555]
        result = self.subject.observe()
        self.assertEqual(result["h"], 1234)
        self.assertEqual(result["evidence"]["noise"]["h"]["relative_spread"], 0)

    def test_stalled_phase_times_out_even_if_h_would_change(self):
        self.io.stalled = True
        with self.assertRaises(sampler.SamplingTimeout) as raised:
            self.subject.observe()
        self.assertGreaterEqual(self.clock.now, 2)
        self.assertEqual(self.io.h_reads, 0)
        self.assertEqual(raised.exception.evidence["samples"], [])

    def test_one_transition_is_not_enough(self):
        self.io.hook = lambda address, count: ([0 if self.clock.now < 0.03 else 1] +
                                               [self.io.memory.get(address + i * 4, 0)
                                                for i in range(1, count)]) if address == sampler.SCHEDULER else None
        with self.assertRaises(sampler.SamplingTimeout):
            self.subject.observe()
        self.assertEqual(self.io.h_reads, 0)

    def test_cancel_before_any_io(self):
        with self.assertRaises(sampler.SamplingCancelled):
            self.make_sampler(cancel=lambda: True).observe()
        self.assertEqual(self.io.reads, [])
        self.assertEqual(self.bridge.state_reads, 0)
        self.assertEqual(self.bridge.calls, [])

    def test_cancel_during_wait_does_not_get_h_or_move(self):
        with self.assertRaises(sampler.SamplingCancelled):
            self.make_sampler(cancel=lambda: self.clock.now > 0.025).observe()
        self.assertEqual(self.io.h_reads, 0)
        self.assertTrue(all(operation == 0 for operation in self.bridge.calls))

    def test_selector_one_uses_cached_timing_not_mmio(self):
        self.io.memory[sampler.TIMING_SELECTOR] = 1
        self.io.memory[sampler.TIMING_MMIO] = 7 << 16
        result = self.subject.observe()
        self.assertTrue(result["valid"])
        self.assertNotIn((sampler.TIMING_MMIO, 1), self.io.reads)
        self.assertIn((sampler.TIMING_CACHED, 1), self.io.reads)

    def test_nonzero_timing_and_subcycle_rejected(self):
        for address, value in ((sampler.TIMING_MMIO, 1 << 16), (sampler.RAW_SUBCYCLE, 1),
                               (sampler.TIMING_SELECTOR, 2)):
            with self.subTest(address=address):
                self.setUp()
                self.io.memory[address] = value
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()
                self.assertEqual(self.io.h_reads, 0)

    def test_nonzero_cached_timing_rejected_when_selected(self):
        self.io.memory[sampler.TIMING_SELECTOR] = 1
        self.io.memory[sampler.TIMING_CACHED] = 1
        with self.assertRaises(sampler.UnsupportedObservation):
            self.subject.observe()

    def test_selector_change_inside_guard_is_not_accepted(self):
        reads = [0]
        def hook(address, count):
            if address == sampler.TIMING_SELECTOR:
                reads[0] += 1
                return [0 if reads[0] == 1 else 1]
        self.io.hook = hook
        with self.assertRaises(sampler.UnstableObservation):
            self.subject.observe()

    def test_unsupported_identity_and_readiness_conditions(self):
        changes = [(sampler.SCHEDULER + 4, 4), (sampler.SCHEDULER + 24, 0),
                   (sampler.SCHEDULER + 28, 0), (sampler.SCHEDULER + 32, 0),
                   (sampler.SCHEDULER + 36, 0), (sampler.OBSERVER, 0),
                   (sampler.OBSERVER + 4, 1), (sampler.OBSERVER + 8, 0),
                   (sampler.OBSERVER + 12, 0)]
        for address, value in changes:
            with self.subTest(address=address):
                self.setUp()
                self.io.memory[address] = value
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()

    def test_route_area_and_roi_count_conditions(self):
        changes = [(sampler.AREA_METADATA, 0xFF), (sampler.AREA_METADATA + 32, 1),
                   (sampler.AREA_METADATA + 156, 3), (sampler.ROI_COUNT, 0),
                   (sampler.ROI_COUNT, 52), (sampler.AF_AREA, 1)]
        for address, value in changes:
            with self.subTest(address=address, value=value):
                self.setUp()
                self.io.memory[address] = value
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()

    def test_capture_activity_rejected(self):
        for address, value in ((sampler.CAPTURE_BUSY, 0x100),
                               (sampler.CAPTURE_BUSY + 8, 1), (sampler.CAPTURE_SEQUENCE, 1)):
            with self.subTest(address=address):
                self.setUp()
                self.io.memory[address] = value
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()

    def test_native_initial_done_and_idle_required(self):
        for key, value in (("native_done", False), ("capture_idle", False), ("af_route", 3),
                           ("focus_flags", 2), ("movie_recording", True)):
            with self.subTest(key=key):
                self.setUp()
                self.bridge.native_state[key] = value
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()

    def test_final_native_completion_required(self):
        def hook():
            if self.bridge.state_reads > 1:
                self.bridge.native_state["native_done"] = False
        self.bridge.state_hook = hook
        with self.assertRaises(sampler.UnsupportedObservation):
            self.subject.observe()

    def test_changed_final_position_and_bounds_rejected(self):
        for key, value in (("position", 10001), ("min_position", 5800), ("max_position", 11200)):
            with self.subTest(key=key):
                self.setUp()
                def hook():
                    if self.bridge.state_reads > 1:
                        self.bridge.native_state[key] = value
                self.bridge.state_hook = hook
                with self.assertRaises(sampler.UnstableObservation):
                    self.subject.observe()

    def test_cached_position_change_during_sampling_rejected(self):
        self.bridge.call_hook = lambda: setattr(self.bridge, "position", 10001) if self.clock.now > 0.15 else None
        with self.assertRaises(sampler.UnstableObservation):
            self.subject.observe()

    def test_signed_cached_positions(self):
        self.bridge.position = -100
        self.bridge.native_state.update(position=-100, min_position=-500, max_position=500)
        self.assertEqual(self.subject.observe()["position"], -100)

    def test_gain_exposure_hpf_or_context_change_rejected(self):
        addresses = [sampler.GAIN_BASE, sampler.GAIN_BASE + 8, sampler.GAIN_BASE + 20,
                     sampler.GAIN_BASE + 28, sampler.EXPOSURE_BASE, sampler.EXPOSURE_BASE + 8,
                     sampler.EXPOSURE_BASE + 28, sampler.AREA_METADATA + 160,
                     sampler.HPF_BASE, sampler.AF_PROCESSING_FLAG, sampler.AF_DRIVE]
        for address in addresses:
            with self.subTest(address=address):
                self.setUp()
                original = self.io.memory[address]
                def hook(read_address, count):
                    if self.clock.now > 0.03:
                        self.io.memory[address] = original + 1
                self.io.hook = hook
                with self.assertRaises((sampler.UnstableObservation, sampler.UnsupportedObservation)):
                    self.subject.observe()

    def test_focus_settings_change_and_wrong_modes_rejected(self):
        for name, value in ((sampler.SETTINGS[0], "500 277 128 128"),
                            (sampler.SETTINGS[1], "1"), (sampler.SETTINGS[2], "2"),
                            (sampler.SETTINGS[3], "2")):
            with self.subTest(name=name):
                self.setUp()
                self.bridge.settings_hook = lambda: self.bridge.current_settings.update({name: value}) if self.clock.now > 0.03 else None
                with self.assertRaises((sampler.UnstableObservation, sampler.UnsupportedObservation)):
                    self.subject.observe()

    def test_malformed_memory_and_settings_fail_closed(self):
        self.io.hook = lambda address, count: [False] if address == sampler.TIMING_SELECTOR else None
        with self.assertRaises(sampler.UnsupportedObservation):
            self.subject.observe()
        self.setUp()
        self.bridge.current_settings[sampler.SETTINGS[0]] = "unexpected"
        with self.assertRaises(sampler.UnsupportedObservation):
            self.subject.observe()

    def test_visible_phase_boundary_discards_scalar_sample(self):
        shifted = [False]
        def hook(address, count):
            if address == sampler.H_ADDRESS and not shifted[0]:
                shifted[0] = True
                self.clock.now += 0.020
        self.io.hook = hook
        result = self.subject.observe()
        self.assertGreaterEqual(len(result["evidence"]["discarded_samples"]), 1)
        self.assertEqual(len(result["evidence"]["samples"]), 3)

    def test_full_guards_can_span_frames_but_scalar_bracket_remains_tight(self):
        self.io.read_latency = 0.00125
        result = self.subject.observe()
        self.assertTrue(result["valid"])
        for sample in result["evidence"]["samples"]:
            start, end = sample["context_guard_before"]
            self.assertGreater(end - start, 0.020)
            start, end = sample["context_guard_after"]
            self.assertGreater(end - start, 0.020)
            self.assertLess(sample["bracket_finished_at"] - sample["bracket_started_at"], 0.020)
            self.assertEqual(sample["phase_before"], sample["phase_after"])
        counts = [item["observed_transition_count"] for item in result["evidence"]["samples"]]
        self.assertTrue(all(right > left for left, right in zip(counts, counts[1:])))
        self.assertLess(result["evidence"]["elapsed_s"], 2.0)

    def test_mode_change_in_scalar_bracket_rejected(self):
        def hook(address, count):
            if address == sampler.H_ADDRESS:
                self.io.memory[sampler.SCHEDULER + 4] = 3
        self.io.hook = hook
        with self.assertRaises(sampler.UnstableObservation):
            self.subject.observe()

    def test_transient_reset_phase_is_never_accepted_as_scalar_sample(self):
        reads = [0]
        def hook(address, count):
            if address == sampler.SCHEDULER and count == 2 and reads[0] < 2:
                reads[0] += 1
                return [3, 1]
        self.io.hook = hook
        result = self.subject.observe()
        self.assertTrue(result["valid"])
        self.assertEqual(result["evidence"]["discarded_samples"][0]["phase_before"], 3)
        self.assertTrue(all(item["phase_before"] < 3 for item in result["evidence"]["samples"]))

    def test_saturated_or_zero_h_and_saturated_l_rejected(self):
        for name, values in (("h_values", [0]), ("h_values", [sampler.U32_MAX]),
                             ("l_values", [sampler.U32_MAX])):
            with self.subTest(name=name, values=values):
                self.setUp()
                setattr(self.io, name, values)
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()

    def test_noise_above_ten_percent_rejected(self):
        for name, values in (("h_values", [900, 1000, 1101]),
                             ("l_values", [4500, 5000, 5501])):
            with self.subTest(name=name):
                self.setUp()
                setattr(self.io, name, values)
                with self.assertRaises(sampler.UnstableObservation) as raised:
                    self.subject.observe()
                self.assertIn("noise", raised.exception.evidence)

    def test_exact_noise_threshold_is_accepted(self):
        self.io.h_values = [950, 1000, 1050]
        self.assertTrue(self.subject.observe()["valid"])

    def test_transport_latency_cannot_produce_valid_over_budget_result(self):
        self.io.read_latency = 0.05
        with self.assertRaises(sampler.SamplingTimeout):
            self.subject.observe()
        self.assertFalse(any(item["event"] == "settled_observation" for item in self.events))

    def test_io_error_preserves_evidence_and_does_not_retry(self):
        count = [0]
        def hook(address, words):
            count[0] += 1
            raise OSError("read failure")
        self.io.hook = hook
        with self.assertRaises(sampler.SamplingError) as raised:
            self.subject.observe()
        self.assertEqual(count[0], 1)
        self.assertIsNotNone(raised.exception.evidence)

    def test_invalid_config_rejected_before_io(self):
        for change in ({"timeout_s": 9}, {"settle_s": 0.1}, {"poll_s": 0},
                       {"sample_count": 2}, {"sample_count": True},
                       {"max_relative_spread": 0.11}, {"timeout_s": float("nan")}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    sampler.SamplerConfig(**change)
        self.assertEqual(self.io.reads, [])

    def test_output_and_context_do_not_alias_event_payload(self):
        result = self.subject.observe()
        self.events[-1]["observation"]["context"][0] = "tampered"
        self.assertNotEqual(result["context"][0], "tampered")


class FakeBracketIO(FakeIO):
    """Models the fixed bracket result, not USB or the transport's burst timing."""

    def __init__(self, clock):
        super().__init__(clock)
        self.bracket_calls = 0
        self.bracket_latency = 0.0002
        self.bracket_hook = None
        self.brackets = []
        self.reads_at_bracket = []

    def read_h_bracket(self):
        # No address/count parameters: this is the optional fixed operation.
        self.bracket_calls += 1
        self.reads_at_bracket.append(len(self.reads))
        started = self.clock.now
        index = self.bracket_calls - 1
        phase_before = int(started / 0.020) % 3
        self.clock.now += self.bracket_latency
        result = {'phase_before': phase_before,
                  'mode_before': self.memory[sampler.SCHEDULER + 4],
                  'h': self.h_values[index % len(self.h_values)],
                  'l': self.l_values[index % len(self.l_values)],
                  'phase_after': int(self.clock.now / 0.020) % 3,
                  'mode_after': self.memory[sampler.SCHEDULER + 4],
                  'started_at': started, 'finished_at': self.clock.now}
        if self.bracket_hook:
            result = self.bracket_hook(result)
        self.brackets.append(copy.deepcopy(result))
        return result


class FixedBracketSamplerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.io = FakeBracketIO(self.clock)
        self.bridge = FakeBridge(self.clock)
        self.events = []
        self.subject = self.make_sampler()

    def make_sampler(self, **kwargs):
        return sampler.SettledSampler(self.io, self.bridge, clock=self.clock,
                                      sleep=self.clock.sleep, event=self.events.append, **kwargs)

    def assert_no_scalar_fallback(self):
        self.assertEqual(self.io.h_reads, 0)
        self.assertEqual(self.io.l_reads, 0)
        self.assertNotIn((sampler.H_ADDRESS, 1), self.io.reads)
        self.assertNotIn((sampler.L_ADDRESS, 1), self.io.reads)
        self.assertNotIn((sampler.SCHEDULER, 2), self.io.reads)
        self.assertTrue(all(operation == 0 for operation in self.bridge.calls))

    def assert_no_success_event(self):
        self.assertFalse(any(item['event'] == 'settled_observation' for item in self.events))

    def test_valid_fixed_brackets_produce_medians_and_exact_timestamp_evidence(self):
        result = self.subject.observe()
        self.assertTrue(result['valid'])
        self.assertEqual((result['h'], result['l']), (1000, 5000))
        self.assertEqual(self.io.bracket_calls, 3)
        samples = result['evidence']['samples']
        self.assertEqual(len(samples), 3)
        self.assertGreaterEqual(samples[0]['started_at'], 0.150)
        for sample, bracket in zip(samples, self.io.brackets):
            self.assertEqual(sample['h'], bracket['h'])
            self.assertEqual(sample['l'], bracket['l'])
            self.assertEqual(sample['bracket_started_at'], bracket['started_at'])
            self.assertEqual(sample['bracket_finished_at'], bracket['finished_at'])
            self.assertEqual(sample['started_at'], bracket['started_at'])
            self.assertEqual(sample['finished_at'], bracket['finished_at'])
            self.assertEqual(sample['phase_before'], sample['phase_after'])
        self.assertFalse(result['optical_focus_verified'])
        self.assertFalse(result['exposure_alignment_verified'])
        self.assertFalse(result['usable_for_dfd'])
        self.assert_no_scalar_fallback()

    def test_fixed_bracket_supports_audited_mode_three(self):
        self.io.memory[sampler.SCHEDULER + 4] = 3
        result = self.subject.observe()
        self.assertTrue(result['valid'])
        self.assertTrue(all(item['mode_before'] == item['mode_after'] == 3
                            for item in self.io.brackets))
        self.assert_no_scalar_fallback()

    def test_malformed_bracket_container_fails_once_without_fallback(self):
        for value in (None, [], (), 'not a bracket', 1):
            with self.subTest(value=value):
                self.setUp()
                self.io.bracket_hook = lambda result: value
                with self.assertRaisesRegex(sampler.UnsupportedObservation,
                                            'invalid bounded H bracket') as raised:
                    self.subject.observe()
                self.assertEqual(self.io.bracket_calls, 1)
                self.assertEqual(raised.exception.evidence['samples'], [])
                self.assert_no_scalar_fallback()
                self.assert_no_success_event()

    def test_every_uint_field_rejects_bool_noninteger_and_out_of_range(self):
        keys = ('phase_before', 'mode_before', 'h', 'l', 'phase_after', 'mode_after')
        values = (True, False, -1, sampler.U32_MAX + 1, 1.0, '1', None)
        for key in keys:
            for value in values:
                with self.subTest(key=key, value=value):
                    self.setUp()
                    self.io.bracket_hook = lambda result: dict(result, **{key: value})
                    with self.assertRaisesRegex(sampler.UnsupportedObservation,
                                                'invalid bounded H bracket'):
                        self.subject.observe()
                    self.assertEqual(self.io.bracket_calls, 1)
                    self.assert_no_scalar_fallback()

    def test_missing_required_uint_fields_are_not_retried(self):
        for key in ('phase_before', 'mode_before', 'h', 'l', 'phase_after', 'mode_after'):
            with self.subTest(key=key):
                self.setUp()
                self.io.bracket_hook = lambda result: {k: v for k, v in result.items() if k != key}
                with self.assertRaises(sampler.UnsupportedObservation):
                    self.subject.observe()
                self.assertEqual(self.io.bracket_calls, 1)
                self.assert_no_scalar_fallback()

    def test_invalid_scheduler_phase_is_rejected(self):
        for key in ('phase_before', 'phase_after'):
            for value in (4, sampler.U32_MAX):
                with self.subTest(key=key, value=value):
                    self.setUp()
                    self.io.bracket_hook = lambda result: dict(result, **{key: value})
                    with self.assertRaisesRegex(sampler.UnsupportedObservation,
                                                'invalid scheduler phase'):
                        self.subject.observe()
                    self.assertEqual(self.io.bracket_calls, 1)
                    self.assert_no_scalar_fallback()

    def test_changed_mode_on_either_side_invalidates_observation(self):
        for changes in ({'mode_before': 3}, {'mode_after': 3},
                        {'mode_before': 3, 'mode_after': 3}):
            with self.subTest(changes=changes):
                self.setUp()
                self.io.bracket_hook = lambda result: dict(result, **changes)
                with self.assertRaisesRegex(sampler.UnstableObservation,
                                            'scheduler mode changed') as raised:
                    self.subject.observe()
                self.assertEqual(self.io.bracket_calls, 1)
                self.assertEqual(raised.exception.evidence['samples'], [])
                self.assert_no_scalar_fallback()

    def test_visible_crossed_phase_is_discarded_before_three_good_brackets(self):
        def crossed_first(result):
            if self.io.bracket_calls == 1:
                return dict(result, phase_before=2, phase_after=0, h=1, l=1)
            return result

        self.io.bracket_hook = crossed_first
        result = self.subject.observe()
        evidence = result['evidence']
        self.assertEqual(self.io.bracket_calls, 4)
        self.assertEqual(len(evidence['samples']), 3)
        self.assertEqual(len(evidence['discarded_samples']), 1)
        self.assertEqual(evidence['discarded_samples'][0]['reason'], 'visible_phase_boundary')
        self.assertTrue(all(item['h'] > 1 for item in evidence['samples']))
        self.assertEqual(result['h'], 1000)
        self.assert_no_scalar_fallback()

    def test_transient_phase_three_bracket_is_discarded_even_when_both_sides_match(self):
        def reset_first(result):
            return dict(result, phase_before=3, phase_after=3) if self.io.bracket_calls == 1 else result

        self.io.bracket_hook = reset_first
        result = self.subject.observe()
        self.assertEqual(len(result['evidence']['discarded_samples']), 1)
        self.assertEqual(result['evidence']['discarded_samples'][0]['phase_before'], 3)
        self.assertTrue(all(item['phase_before'] < 3 for item in result['evidence']['samples']))
        self.assert_no_scalar_fallback()

    def test_continuously_crossed_phase_exhausts_deadline_without_valid_result(self):
        self.io.bracket_hook = lambda result: dict(result, phase_before=0, phase_after=1)
        subject = self.make_sampler(config=sampler.SamplerConfig(timeout_s=0.3))
        with self.assertRaises(sampler.SamplingTimeout) as raised:
            subject.observe()
        self.assertGreater(self.io.bracket_calls, 0)
        self.assertLess(self.io.bracket_calls, 61)
        self.assertEqual(raised.exception.evidence['samples'], [])
        self.assertEqual(len(raised.exception.evidence['discarded_samples']), self.io.bracket_calls)
        self.assert_no_scalar_fallback()
        self.assert_no_success_event()

    def test_malformed_timestamp_types_are_rejected(self):
        values = (True, False, None, '0.15', float('nan'), float('inf'), float('-inf'))
        for key in ('started_at', 'finished_at'):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.setUp()
                    self.io.bracket_hook = lambda result: dict(result, **{key: value})
                    with self.assertRaisesRegex(sampler.UnsupportedObservation,
                                                'invalid bracket timestamps'):
                        self.subject.observe()
                    self.assertEqual(self.io.bracket_calls, 1)
                    self.assert_no_scalar_fallback()

    def test_missing_timestamps_fail_closed_without_fallback(self):
        for key in ('started_at', 'finished_at'):
            with self.subTest(key=key):
                self.setUp()
                self.io.bracket_hook = lambda result: {k: v for k, v in result.items() if k != key}
                with self.assertRaises(sampler.SamplingError) as raised:
                    self.subject.observe()
                self.assertEqual(self.io.bracket_calls, 1)
                self.assertEqual(raised.exception.evidence['samples'], [])
                self.assert_no_scalar_fallback()

    def test_timestamp_order_and_observation_window_are_enforced(self):
        changes = (lambda result: dict(result, started_at=-0.001),
                   lambda result: dict(result, finished_at=result['started_at'] - 0.0001),
                   lambda result: dict(result, finished_at=self.clock.now + 0.001))
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                self.io.bracket_hook = change
                with self.assertRaisesRegex(sampler.UnsupportedObservation,
                                            'invalid bracket timestamps'):
                    self.subject.observe()
                self.assertEqual(self.io.bracket_calls, 1)
                self.assert_no_scalar_fallback()

    def test_timestamps_from_before_bracket_invocation_are_rejected(self):
        self.io.bracket_hook = lambda result: dict(result, started_at=0.0, finished_at=0.0)
        with self.assertRaisesRegex(sampler.UnsupportedObservation,
                                    'invalid bracket timestamps'):
            self.subject.observe()
        self.assertEqual(self.io.bracket_calls, 1)
        self.assert_no_scalar_fallback()

    def test_bracket_transport_error_is_never_retried_or_fallen_back(self):
        for error in (OSError('read failed'), TimeoutError('uncertain burst'), RuntimeError('bad reply')):
            with self.subTest(error=type(error).__name__):
                self.setUp()

                def fail(result):
                    raise error

                self.io.bracket_hook = fail
                with self.assertRaises(sampler.SamplingError) as raised:
                    self.subject.observe()
                self.assertIs(raised.exception.__cause__, error)
                self.assertEqual(self.io.bracket_calls, 1)
                self.assertEqual(raised.exception.evidence['samples'], [])
                self.assertEqual(len(self.io.reads), self.io.reads_at_bracket[0])
                self.assert_no_scalar_fallback()
                self.assert_no_success_event()

    def test_late_return_from_bracket_is_rejected_before_more_io(self):
        self.io.bracket_latency = 0.5
        subject = self.make_sampler(config=sampler.SamplerConfig(timeout_s=0.3))
        with self.assertRaises(sampler.SamplingTimeout) as raised:
            subject.observe()
        self.assertEqual(self.io.bracket_calls, 1)
        self.assertEqual(raised.exception.evidence['samples'], [])
        self.assertEqual(len(self.io.reads), self.io.reads_at_bracket[0])
        self.assert_no_scalar_fallback()
        self.assert_no_success_event()

    def test_cancel_before_observation_prevents_any_bracket_or_io(self):
        with self.assertRaises(sampler.SamplingCancelled):
            self.make_sampler(cancel=lambda: True).observe()
        self.assertEqual(self.io.bracket_calls, 0)
        self.assertEqual(self.io.reads, [])
        self.assertEqual(self.bridge.calls, [])

    def test_cancel_during_bracket_rejects_return_before_more_io(self):
        cancelled = [False]

        def cancel_inside(result):
            cancelled[0] = True
            return result

        self.io.bracket_hook = cancel_inside
        with self.assertRaises(sampler.SamplingCancelled) as raised:
            self.make_sampler(cancel=lambda: cancelled[0]).observe()
        self.assertEqual(self.io.bracket_calls, 1)
        self.assertEqual(raised.exception.evidence['samples'], [])
        self.assertEqual(len(self.io.reads), self.io.reads_at_bracket[0])
        self.assert_no_scalar_fallback()
        self.assert_no_success_event()

    def test_zero_saturated_and_noisy_fixed_bracket_scalars_still_fail_closed(self):
        for name, values in (('h_values', [0]), ('h_values', [sampler.U32_MAX]),
                             ('l_values', [sampler.U32_MAX]),
                             ('h_values', [900, 1000, 1101]),
                             ('l_values', [4500, 5000, 5501])):
            with self.subTest(name=name, values=values):
                self.setUp()
                setattr(self.io, name, values)
                with self.assertRaises((sampler.UnsupportedObservation, sampler.UnstableObservation)):
                    self.subject.observe()
                self.assert_no_scalar_fallback()
                self.assert_no_success_event()


if __name__ == "__main__":
    unittest.main()
