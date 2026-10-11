"""Read-only, bounded host sampling of the audited fp background H path.

This is conditional scheduler-progress checking, not a sensor-frame counter,
seqlock, optical settling proof, or DFD validation. See the maintained
research/autofocus/notes/FP_AF_STATS_FRESHNESS_2026-09-16.md.
Uses fixed memory/context reads, audited native getters and, when installed,
the fixed camera-side H/L copy. The caller owns the exclusive RAM lease;
the snapshot RPC writes only that lease's parameters/results, not settings.

The budget is checked before/after every I/O operation.  A transport call that
ignores its own deadline cannot be preempted here; an over-budget return is
rejected, never accepted as a valid observation.  No native wait function is
called, and errors never trigger movement or camera cleanup from this module.
"""

from dataclasses import dataclass
import copy
import math
import re
import statistics
import time


U32_MAX = 0xFFFFFFFF
SETTINGS = ("menu SetFocusPosition", "menu SetFocusMode", "menu SetFocusArea",
            "menu SetFocusAreaSize")
SCHEDULER = 0xC31F8CB4
OBSERVER = 0xC3206700
TIMING_SELECTOR = 0xC2F14A38
TIMING_CACHED = 0xC31D89BC
TIMING_MMIO = 0x30100048
RAW_SUBCYCLE = 0x30100588
AREA_METADATA = 0xC3291514
ROI_COUNT = 0xC3298918
H_ADDRESS = 0xC32985E8
L_ADDRESS = 0xC32986B4
GAIN_BASE = 0xC343B5A0
EXPOSURE_BASE = 0xC3291694
HPF_BASE = 0xC343B7BC
AF_DRIVE = 0xC32065A0
AF_AREA = 0xC32046A4
AF_PROCESSING_FLAG = 0xC3206680
CAPTURE_BUSY = 0xC30338C8
CAPTURE_SEQUENCE = 0xC3033A6C


@dataclass(frozen=True)
class SamplerConfig:
    # The first hardware prototype spaces every USB exchange by >=5 ms.
    # Native-reference calls and full context guards therefore need a longer
    # bounded observation budget; this is not an exposure/frame timeout.
    timeout_s: float = 8.0
    settle_s: float = 0.150
    poll_s: float = 0.005
    sample_count: int = 3
    max_relative_spread: float = 0.10

    def __post_init__(self):
        for name in ("timeout_s", "settle_s", "poll_s", "max_relative_spread"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(name + " must be finite")
        if not 0.150 < self.timeout_s <= 8.0:
            raise ValueError("timeout_s must be >150 ms and <=8 s")
        if not 0.150 <= self.settle_s < self.timeout_s:
            raise ValueError("settle_s must be >=150 ms and below the deadline")
        if not 0.005 <= self.poll_s <= 0.020:
            raise ValueError("poll_s must be 5..20 ms")
        if type(self.sample_count) is not int or not 3 <= self.sample_count <= 9:
            raise ValueError("sample_count must be 3..9")
        if not 0 < self.max_relative_spread <= 0.10:
            raise ValueError("relative spread threshold must be in (0, 0.10]")


class SamplingError(RuntimeError):
    def __init__(self, reason, evidence=None):
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


class SamplingCancelled(SamplingError):
    pass


class SamplingTimeout(SamplingError):
    pass


class UnsupportedObservation(SamplingError):
    pass


class UnstableObservation(SamplingError):
    pass


def _integer(value, name):
    if type(value) is not int:
        raise UnsupportedObservation(name + " is not an integer")
    return value


def _signed(value):
    return value - 0x100000000 if value & 0x80000000 else value


class SettledSampler:
    def __init__(self, io, bridge, cancel=lambda: False, event=lambda item: None,
                 *, clock=time.monotonic, sleep=time.sleep, config=None):
        self.io = io
        self.bridge = bridge
        self.cancel = cancel
        self.event = event
        self.clock = clock
        self.sleep = sleep
        self.config = SamplerConfig() if config is None else config
        if not isinstance(self.config, SamplerConfig):
            raise ValueError("config must be SamplerConfig")
        self._deadline = None
        self._evidence = None

    def _check(self):
        if self.cancel():
            raise SamplingCancelled("cancel_requested")
        if self.clock() >= self._deadline:
            raise SamplingTimeout("settled observation deadline expired")

    def _invoke(self, fn, *args):
        self._check()
        result = fn(*args)
        self._check()
        return result

    def _read(self, address, count=1):
        if address & 3 or not 1 <= count <= 41:
            raise ValueError("sampler reads must be aligned and at most 41 words")
        result = self._invoke(self.io.read, address, count)
        if not isinstance(result, (list, tuple)) or len(result) != count:
            raise UnsupportedObservation("incomplete memory response")
        if any(type(word) is not int or not 0 <= word <= U32_MAX for word in result):
            raise UnsupportedObservation("invalid memory word")
        return list(result)

    def _settings(self):
        result = self._invoke(self.bridge.settings)
        if not isinstance(result, dict) or set(result) != set(SETTINGS):
            raise UnsupportedObservation("missing or additional focus settings")
        if any(not isinstance(result[name], str) or not result[name].strip() for name in SETTINGS):
            raise UnsupportedObservation("invalid focus setting response")
        result = dict(result)
        if result[SETTINGS[1]].strip() != "0" or result[SETTINGS[2]].strip() != "0":
            raise UnsupportedObservation("only AF-S mode 0 and single area 0 are supported")
        roi_text = result[SETTINGS[0]].strip()
        if re.fullmatch(r"\d+(?:\s+\d+){3}", roi_text) is None:
            raise UnsupportedObservation("unrecognized focus rectangle")
        x, y, width, height = map(int, roi_text.split())
        if not (0 <= x <= 1024 and 0 <= y <= 682 and 0 < width <= 1024 and 0 < height <= 682):
            raise UnsupportedObservation("focus rectangle outside supported coordinate domain")
        if re.fullmatch(r"\d+", result[SETTINGS[3]].strip()) is None:
            raise UnsupportedObservation("unrecognized focus-area size")
        if isinstance(getattr(self.bridge, "baseline", None), dict) and result != self.bridge.baseline:
            raise UnstableObservation("focus settings differ from bridge lease baseline")
        return result

    def _state(self):
        state = self._invoke(self.bridge.read_state)
        if not isinstance(state, dict):
            raise UnsupportedObservation("invalid native state")
        if state.get("native_done") is not True or state.get("capture_idle") is not True:
            raise UnsupportedObservation("native completion or capture idle not confirmed")
        if state.get("af_route") != 14:
            raise UnsupportedObservation("AF route is not the supported idle route 14")
        for name in ("position", "min_position", "max_position"):
            _integer(state.get(name), name)
        if not state["min_position"] <= state["position"] <= state["max_position"]:
            raise UnsupportedObservation("native position outside reported bounds")
        if "focus_flags" in state and state["focus_flags"] != 3:
            raise UnsupportedObservation("native completion flags disagree")
        if "lens_ready" in state and state["lens_ready"] != 1:
            raise UnsupportedObservation("lens controller is not ready")
        if "property_predicate" in state and state["property_predicate"] != 0:
            raise UnsupportedObservation("unsupported native-lens property")
        if "lens_sync_flags" in state and state["lens_sync_flags"] & 1 == 0:
            raise UnsupportedObservation("native lens synchronization is not ready")
        if any(state.get(name, False) for name in ("still_exposing", "still_saving", "movie_saving",
                                                 "still_processing", "movie_recording")):
            raise UnsupportedObservation("capture activity conflicts with idle state")
        if state.get("shutter_sequence", 0) != 0:
            raise UnsupportedObservation("active shutter sequence")
        return copy.deepcopy(state)

    def _position(self):
        response = self._invoke(self.bridge.call, 0)
        if not isinstance(response, (tuple, list)) or not response:
            raise UnsupportedObservation("invalid cached-position response")
        value = response[0]
        if type(value) is not int or not 0 <= value <= U32_MAX:
            raise UnsupportedObservation("invalid cached-position word")
        return _signed(value)

    def _guard(self):
        started = self.clock()
        phase_before = self._read(SCHEDULER)[0]
        selector_before = self._read(TIMING_SELECTOR)[0]
        scheduler = self._read(SCHEDULER, 11)
        observer = self._read(OBSERVER, 4)
        mode = scheduler[1]
        if mode not in (1, 3):
            raise UnsupportedObservation("scheduler mode is not the audited divisor-1 mode 1/3")
        if (scheduler[6:9] != [OBSERVER, 0xC090F0AC, 0xC090F2EC]
                or scheduler[9] & 0xFF != 1):
            raise UnsupportedObservation("slot-0 observer/table/enable mismatch")
        if (observer[0] != 0xC09185A4 or observer[1] != 2
                or observer[2] != 0xC09185F8 or observer[3] & 0xFF == 0):
            raise UnsupportedObservation("background H publisher is not ready")
        # C0127DD0 explicitly handles -1; C0126010 uses MMIO for any !=1.
        # Keep a narrow enum whitelist including the observed native -1 state.
        if selector_before not in (0, 1, U32_MAX):
            raise UnsupportedObservation("timing selector outside supported -1/0/1")
        timing_raw = self._read(TIMING_CACHED if selector_before == 1 else TIMING_MMIO)[0]
        timing = timing_raw if selector_before == 1 else (timing_raw >> 16) & 0x7FF
        subcycle = self._read(RAW_SUBCYCLE)[0] & 0x7FF
        if timing != 0 or subcycle != 0:
            raise UnsupportedObservation("only effective timing 0 / raw subcycle 0 are supported")
        metadata = self._read(AREA_METADATA, 41)
        chosen, reference, route, rgb_gain = metadata[0], metadata[8], metadata[39], metadata[40]
        area_count = self._read(ROI_COUNT)[0]
        if chosen != 0 or reference != 0 or not 1 <= area_count <= 51 or route != 14:
            raise UnsupportedObservation("area-0/ROI-count/idle-route guard failed")
        gain_words = self._read(GAIN_BASE, 8)
        gain = [gain_words[0], gain_words[2], gain_words[5], gain_words[7] & 0xFF]
        if not (gain[0] > 0 and gain[1] <= 0xFFF and gain[2] > 0 and gain[3] in (0, 1)):
            raise UnsupportedObservation("invalid actual IMX410 gain context")
        exposure_words = self._read(EXPOSURE_BASE, 8)
        exposure = [rgb_gain, exposure_words[0], exposure_words[2], exposure_words[7]]
        if any(value == 0 for value in exposure):
            raise UnsupportedObservation("incomplete AF gain/sensitivity/shutter/f-number context")
        hpf = self._read(HPF_BASE, 2)
        drive = self._read(AF_DRIVE)[0]
        area = self._read(AF_AREA)[0]
        processing_flag = self._read(AF_PROCESSING_FLAG)[0] & 0xFF
        if area != 0:
            raise UnsupportedObservation("AF area mode changed from supported single area")
        busy = self._read(CAPTURE_BUSY, 3)
        capture_sequence = self._read(CAPTURE_SEQUENCE)[0]
        if busy[0] != 0 or busy[2] & 0xFF != 0 or capture_sequence != 0:
            raise UnsupportedObservation("capture/recording activity during observation")
        settings = self._settings()
        selector_after = self._read(TIMING_SELECTOR)[0]
        scheduler_after = self._read(SCHEDULER, 11)
        observer_after = self._read(OBSERVER, 4)
        if selector_before != selector_after:
            raise UnstableObservation("timing selector changed during guard")
        if (scheduler_after[1] != mode or scheduler_after[6:10] != scheduler[6:10]
                or observer_after != observer):
            raise UnstableObservation("scheduler/observer changed during guard")
        phase_after = scheduler_after[0]
        if any(value > 3 for value in (phase_before, scheduler[0], phase_after)):
            raise UnsupportedObservation("invalid scheduler phase")
        # Stable context intentionally excludes phase, time, H/L, position,
        # scheduler overrun latch, and all unrelated memory words read in blocks.
        context = ["fp-5.02/background-processing-mode-0/area-0", mode, selector_before,
                   timing, subcycle, chosen, reference, area_count, drive, area,
                   processing_flag, exposure, hpf, [settings[name] for name in SETTINGS],
                   "capture_idle", "not_optically_validated"]
        return {"phase": phase_after, "phase_before": phase_before,
                "phase_coherent": phase_before == scheduler[0] == phase_after and phase_after < 3,
                "mode": mode, "gain": gain, "context": context,
                "settings": settings, "started_at": started, "finished_at": self.clock()}

    def _pause(self):
        self._check()
        self.sleep(min(self.config.poll_s, max(0.0, self._deadline - self.clock())))
        self._check()

    def observe(self):
        start = self.clock()
        self._deadline = start + self.config.timeout_s
        evidence = {"method": "scheduler_progress_checked", "started_at": start,
                    "timeout_s": self.config.timeout_s, "minimum_settle_s": self.config.settle_s,
                    "observed_transitions": [], "samples": [], "discarded_samples": [],
                    "optical_focus_verified": False, "exposure_alignment_verified": False,
                    "usable_for_dfd": False}
        self._evidence = evidence
        try:
            initial_state = self._state()
            evidence["initial_state"] = initial_state
            position = self._position()
            if position != initial_state["position"]:
                raise UnstableObservation("position changed after native-completion read")
            baseline = self._guard()
            evidence["settings"] = baseline["settings"]
            evidence["gain"] = baseline["gain"]
            evidence["context"] = baseline["context"]
            settled_since = self.clock()
            last_phase = baseline["phase"] if baseline["phase"] < 3 else None
            transitions = 0
            last_sample_transition = -1

            def validate_guard(guard):
                if guard["gain"] != baseline["gain"] or guard["context"] != baseline["context"]:
                    raise UnstableObservation("gain/exposure/ROI/AF context changed")

            def track(phase, observed_at):
                nonlocal last_phase, transitions
                if phase >= 3:
                    return
                if last_phase is not None and phase != last_phase:
                    transitions += 1
                    evidence["observed_transitions"].append({"from": last_phase, "to": phase,
                                                             "time": observed_at})
                last_phase = phase

            def phase_pair():
                phase, mode = self._read(SCHEDULER, 2)
                if mode != baseline["mode"]:
                    raise UnstableObservation("scheduler mode changed around scalar read")
                if phase > 3:
                    raise UnsupportedObservation("invalid scheduler phase around scalar read")
                return phase, self.clock()

            while len(evidence["samples"]) < self.config.sample_count:
                self._pause()
                before = self._guard()
                validate_guard(before)
                track(before["phase"], before["finished_at"])
                if (transitions < 2 or transitions <= last_sample_transition
                        or self.clock() - settled_since < self.config.settle_s):
                    continue
                sample_position = self._position()
                if sample_position != position:
                    raise UnstableObservation("cached lens position changed during sampling")
                # Full context guards can span several scheduler phases.  Only
                # the scalar H/L reads need the short same-phase bracket; even
                # this is not a seqlock or proof of exposure alignment.
                bracket_reader = (self.bridge.read_h_bracket if getattr(self.bridge, 'snapshot_code', None)
                                  else getattr(self.io, 'read_h_bracket', None))
                if callable(bracket_reader):
                    bracket_invoked_at = self.clock()
                    bracket = self._invoke(bracket_reader)
                    if not isinstance(bracket, dict) or any(
                            type(bracket.get(key)) is not int or not 0 <= bracket[key] <= U32_MAX
                            for key in ('phase_before', 'mode_before', 'h', 'l',
                                        'phase_after', 'mode_after')):
                        raise UnsupportedObservation('invalid bounded H bracket')
                    if bracket['mode_before'] != baseline['mode'] or bracket['mode_after'] != baseline['mode']:
                        raise UnstableObservation('scheduler mode changed around scalar read')
                    phase_before, phase_after = bracket['phase_before'], bracket['phase_after']
                    if max(phase_before, phase_after) > 3:
                        raise UnsupportedObservation('invalid scheduler phase around scalar read')
                    bracket_start, bracket_end = bracket['started_at'], bracket['finished_at']
                    if (any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)
                            for t in (bracket_start, bracket_end)) or
                            not bracket_invoked_at <= bracket_start <= bracket_end <= self.clock()):
                        raise UnsupportedObservation('invalid bracket timestamps')
                    h, l = bracket['h'], bracket['l']
                    sample_start, sample_end = bracket_start, bracket_end
                    track(phase_before, bracket_start)
                    sample_transitions = transitions
                else:
                    # Deterministic/offline adapters may expose only read().
                    phase_before, bracket_start = phase_pair()
                    track(phase_before, bracket_start)
                    sample_transitions = transitions
                    sample_start = self.clock()
                    h = self._read(H_ADDRESS)[0]
                    l = self._read(L_ADDRESS)[0]
                    sample_end = self.clock()
                    phase_after, bracket_end = phase_pair()
                track(phase_after, bracket_end)
                after = self._guard()
                validate_guard(after)
                track(after["phase"], after["finished_at"])
                sample = {"h": h, "l": l, "position": sample_position,
                          "capture_method": (bracket.get('method', 'host_four_read')
                                             if callable(bracket_reader) else 'host_four_read'),
                          "bracket_timing_scope": (bracket.get('timing_scope', 'host_reads')
                                                   if callable(bracket_reader) else 'host_reads'),
                          "phase_before": phase_before, "phase_after": phase_after,
                          "bracket_started_at": bracket_start, "bracket_finished_at": bracket_end,
                          "started_at": sample_start, "finished_at": sample_end,
                          "observed_transition_count": sample_transitions,
                          "context_guard_before": [before["started_at"], before["finished_at"]],
                          "context_guard_after": [after["started_at"], after["finished_at"]]}
                if phase_before >= 3 or phase_before != phase_after:
                    evidence["discarded_samples"].append(dict(sample, reason="visible_phase_boundary"))
                    continue
                if not 0 < h < U32_MAX or l == U32_MAX:
                    raise UnsupportedObservation("zero or saturated H / saturated L")
                evidence["samples"].append(sample)
                last_sample_transition = sample_transitions
            final_state = self._state()
            evidence["final_state"] = final_state
            final_position = self._position()
            if (final_position != position or final_state["position"] != position
                    or any(final_state[name] != initial_state[name]
                           for name in ("min_position", "max_position"))):
                raise UnstableObservation("position or native bounds changed during observation")
            final_guard = self._guard()
            validate_guard(final_guard)
            noise = {}
            for name in ("h", "l"):
                values = [sample[name] for sample in evidence["samples"]]
                median = statistics.median(values)
                spread = max(values) - min(values)
                relative_spread = spread / median if median else (0.0 if spread == 0 else float("inf"))
                noise[name] = {"median": median, "min": min(values), "max": max(values),
                               "mad": statistics.median([abs(value - median) for value in values]),
                               "relative_spread": relative_spread}
                if relative_spread > self.config.max_relative_spread:
                    evidence["noise"] = noise
                    raise UnstableObservation(name.upper() + " spread exceeds conservative threshold")
            self._check()
            evidence["noise"] = noise
            evidence["finished_at"] = self.clock()
            evidence["elapsed_s"] = evidence["finished_at"] - start
            result = {"position": position, "min_position": initial_state["min_position"],
                      "max_position": initial_state["max_position"], "h": noise["h"]["median"],
                      "l": noise["l"]["median"], "gain": baseline["gain"],
                      "context": baseline["context"], "valid": True,
                      "method": "scheduler_progress_checked", "evidence": evidence,
                      "optical_focus_verified": False, "exposure_alignment_verified": False,
                      "usable_for_dfd": False}
            self.event({"event": "settled_observation", "observation": copy.deepcopy(result)})
            return result
        except Exception as exc:
            evidence["finished_at"] = self.clock()
            evidence["elapsed_s"] = evidence["finished_at"] - start
            if isinstance(exc, SamplingError):
                exc.evidence = copy.deepcopy(evidence)
                failure = exc
            else:
                failure = SamplingError("read-only observation failed: " + str(exc), copy.deepcopy(evidence))
            self.event({"event": "settled_sampling_failed", "reason": str(failure),
                        "evidence": copy.deepcopy(evidence)})
            if failure is exc:
                raise
            raise failure from exc
