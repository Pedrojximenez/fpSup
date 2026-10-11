#!/usr/bin/env python3
"""One bounded native S1 trial with fixed raw AAT reads, no injected code.

The caller must independently verify the expected AF-C / Tracking settings.
This tool neither sets them nor restores them. ACKs and sequential raw memory
reads do not establish optical focus, subject identity, or geometric scale.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import sys
import time

import af_native_preflight as preflight
from af_fusion_collector import HalfPressTrial

Transport = preflight.Transport
LOCK = preflight.LOCK
HOLD_S = 2.0
MIN_READ_REMAINING_S = 0.20
RELEASE_RESERVE_S = 0.05
# Fixed source addresses: manager is C37CCA9C, its AAT state is M+0x3D0.
# Native-L +4 is a cached position, not an optical/settlement observation.
RANGES = (
    ("detection_runtime", 0xC37CCA04, 5),
    ("detection_runtime_guard", 0xC37CCA18, 1),
    ("aat_backends_and_selector", 0xC37CD340, 10),
    ("aat_model_and_states", 0xC37CDFA8, 12),
    ("manager_aat_state", 0xC37CCE6C, 1),
    ("aat_publication", 0xC3033E00, 10),
    ("native_l_cached_position", 0xC3476418, 1),
)


class TrialError(RuntimeError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class SamplingDeadline(Exception):
    """No new read is dispatched when it could consume the release budget."""


def send_key_edge(io, command):
    """Collector's exact key ACK contract, through the shared paced transport."""
    if command not in ("key S1ON", "key S1OFF"):
        raise ValueError("only native S1ON / S1OFF are allowed")
    if command == "key S1ON":
        io.assert_motion_transport_healthy()
    raw = io.request(f"TMO 1000 SHL {command}", timeout=2.0)
    if raw != b"OK \n":
        io._latch_transport_fault()
        raise RuntimeError(f"uncertain {command} reply: {raw!r}")
    return raw.decode("ascii")


class NativeHalfPress(HalfPressTrial):
    """Use the maintained collector pairing with native guards supplied by caller.

    No AFF1 snapshot is constructed. Parent _command and release retain intent,
    exception, and cleanup logging behavior. The injected sender uses this
    session's paced Transport and exact ACK validation.
    """
    def __init__(self, io, emit, *, sender=send_key_edge, clock=time.monotonic):
        super().__init__(io, 0, HOLD_S, emit, clock=clock, key_sender=sender)
        self.io = io
        self.release_attempted = False

    def _emit(self, event, *, cleanup=False):
        # Mark a failing log as an anomaly without preventing the parent's
        # cleanup behavior, which deliberately absorbs S1OFF logging failures.
        original = self.event_sink
        def tracked(row):
            try:
                original(dict(event="key_edge", **row))
            except Exception:
                self.io._latch_transport_fault()
                raise
        self.event_sink = tracked
        try:
            return super()._emit(event, cleanup=cleanup)
        finally:
            self.event_sink = original

    def press(self):
        if self.pressed_at is not None or self.release_attempted:
            raise RuntimeError("single S1ON trial already consumed")
        self.io.assert_motion_transport_healthy()
        self.release_needed = True
        self.pressed_at = self.clock()
        self._command("key S1ON")

    def release(self):
        if not self.release_needed or self.release_attempted:
            return
        self.release_attempted = True
        super().release()

    def summary(self):
        return dict(half_press_attempted=self.pressed_at is not None,
                    release_attempted=self.release_attempted,
                    release_transport_completed=self.released,
                    release_still_required=self.release_needed,
                    control_logging_errors=list(self.logging_errors))


def _validate_expected(settings):
    if (not isinstance(settings, dict) or set(settings) != set(preflight.SETTINGS)
            or any(not isinstance(value, str) or not value.strip()
                   for value in settings.values())):
        raise ValueError("expected settings must contain the four exact native getter replies")
    if settings["menu SetFocusMode"] != "1" or settings["menu SetFocusArea"] != "3":
        raise ValueError("only the audited AF-C mode 1 / Tracking area 3 is accepted")


def _require_preflight(result, expected):
    if (result.get("status") != "read-complete"
            or result.get("settings_equal") is not True
            or result.get("capture_idle_at_both_observations") is not True
            or result.get("native_l_layout_matches") is not True
            or result.get("face_manager_vtable_matches") is not True
            or result.get("settings") != expected
            or result.get("settings_after") != expected):
        raise RuntimeError("preflight identity, capture guards or expected settings rejected")


def run_trial(io, expected_settings, emit=lambda row: None, *,
              probe=preflight.probe, sender=send_key_edge,
              clock=time.monotonic, sleep=time.sleep):
    """One trial; caller holds LOCK. No getters with lazy initialization are used.

    expected_settings is a reviewed exact snapshot, never inferred from zeros.
    The CLI persists/fsyncs every event, including S1ON intent. Tests may inject
    a sink and clock; no alternate payload installation path exists here.
    """
    _validate_expected(expected_settings)
    original_emit = emit
    def emit(row):
        try:
            original_emit(row)
        except Exception:
            io._latch_transport_fault()
            raise
    result = dict(schema="fp.native-tracking-trial/v1", hold_requested_s=HOLD_S,
                  expected_settings=dict(expected_settings), observations=[],
                  retries=0, direct_camera_ram_writes=0, installation_performed=False,
                  settings_writes=0, geometry_eligible=False, source_coherence_verified=False,
                  optical_focus_confirmed=False, physical_key_state_verified=False,
                  settings_restoration_permitted=False, status="preparing")
    trial = NativeHalfPress(io, emit, sender=sender, clock=clock)

    def read(label, address, count, deadline=None):
        values = []
        started = clock()
        for offset in range(0, count, 8):
            take = min(8, count-offset)
            base = address+4*offset
            timeout = 2.0
            timeout_ms = 1000
            if deadline is not None:
                remaining = deadline-clock()
                if remaining < MIN_READ_REMAINING_S:
                    raise SamplingDeadline()
                # Host timeout itself stays within the remaining hold budget.
                timeout = min(0.15, remaining-RELEASE_RESERVE_S)
                timeout_ms = min(100, int(timeout*1000))
            io.assert_motion_transport_healthy()
            command = f"mem get 0x{base:08X},,0x{take*4:X}"
            before = time.time_ns()
            reply = io._decode_shell_reply(io.request(
                f"TMO {timeout_ms} SHL {command}", timeout=timeout))
            words = io._memory_words(reply, base, take)
            emit(dict(event="memory_chunk", label=label, address=base, words=words,
                      host_before_ns=before, host_after_ns=time.time_ns(),
                      coherent_snapshot=False))
            values.extend(words)
        return dict(address=f"0x{address:08X}", words=values,
                    bytes_hex=struct.pack(f"<{count}I", *values).hex(),
                    host_started_monotonic_s=started, host_finished_monotonic_s=clock(),
                    coherent_snapshot=False)

    def still_guard(label):
        storage = read(label+"_storage", 0xC31AE3A8, 1)
        mode = read(label+"_recmode", 0xC31C01B0, 1)
        if storage["words"] != [1] or mode["words"] != [0]:
            raise RuntimeError("STILL storage guard/mode rejected")
        return dict(storage=storage, stored_record_mode=mode, physical_switch_verified=False)

    def idle_guard(label, deadline=None, *, owned_half_press=False):
        capture = read(label+"_capture", 0xC30338C8, 3, deadline)
        shutter = read(label+"_shutter", 0xC3033A6C, 1, deadline)
        c = capture["words"]
        # Native accepted S1 sets S+220 to 1 (C0480390 -> C04A4C68).
        # Only this trial's holding phase accepts that state; before/after must
        # be zero. State 2 or an unknown value is never an owned half-press.
        permitted_shutter_states = (0, 1) if owned_half_press else (0,)
        guard = dict(capture=capture, shutter=shutter,
                     owned_half_press_phase=owned_half_press,
                     capture_idle_observed=(
            c[0] == 0 and c[2] & 0xff == 0 and
            shutter["words"][0] in permitted_shutter_states),
            atomic_idle_lock=False)
        emit(dict(event="capture_guard", label=label, guard=guard))
        if not guard["capture_idle_observed"]:
            raise RuntimeError("capture/recording/shutter became busy; stopping trial")
        return guard

    primary = cleanup_error = None
    try:
        io.assert_motion_transport_healthy()
        result["still_guard_before_preflight"] = still_guard("before_preflight")
        result["preflight_before"] = probe(io, emit)
        _require_preflight(result["preflight_before"], expected_settings)
        result["still_guard_before_press"] = still_guard("before_press")
        result["guard_immediately_before_press"] = idle_guard("immediately_before_press")
        trial.press()
        deadline = trial.pressed_at+HOLD_S
        result["status"] = "holding"
        # A finite cap also bounds work if a faulty/injected clock stops advancing.
        for index in range(32):
            observation = dict(index=index, blocks={}, host_started_monotonic_s=clock(),
                               coherent_snapshot=False, geometry_eligible=False,
                               optical_focus_confirmed=False, complete=False)
            try:
                observation["guard_before"] = idle_guard(f"sample_{index}_before", deadline,
                                                         owned_half_press=True)
                for name, address, count in RANGES:
                    observation["blocks"][name] = read(f"sample_{index}_{name}", address, count, deadline)
                observation["guard_after"] = idle_guard(f"sample_{index}_after", deadline,
                                                        owned_half_press=True)
                observation["complete"] = True
            except SamplingDeadline:
                observation["stopped_for_release_deadline"] = True
            observation["host_finished_monotonic_s"] = clock()
            result["observations"].append(observation)
            emit(dict(event="raw_observation", observation=observation))
            if not observation["complete"]:
                break
        remaining = deadline-clock()
        if remaining > 0:
            sleep(remaining)
    except BaseException as exc:
        primary = exc
    finally:
        try:
            trial.release()
        except BaseException as exc:
            cleanup_error = exc
        result.update(trial.summary())
        result["transport_faulted"] = io.transport_faulted
        result["transport_anomaly_count"] = io.anomaly_count
        # No settings mutation exists here. This flag informs a separate owner
        # whether ordinary restoration may be considered after clean release.
        result["settings_restoration_permitted"] = (
            trial.released and not trial.logging_errors and not io.transport_faulted
            and primary is None and cleanup_error is None)
    if primary is not None or cleanup_error is not None or trial.logging_errors:
        result.update(status="failed", error=repr(primary), release_error=repr(cleanup_error))
        raise TrialError("native S1 trial failed; no automatic retry", result) from (cleanup_error or primary)
    # A failed release or latched anomaly never reaches another camera exchange.
    try:
        result["still_guard_after_release"] = still_guard("after_release")
        result["guard_after_release"] = idle_guard("after_release")
        result["preflight_after"] = probe(io, emit)
        _require_preflight(result["preflight_after"], expected_settings)
    except BaseException as exc:
        result.update(status="postcheck-failed", error=repr(exc),
                      settings_restoration_permitted=False, transport_faulted=io.transport_faulted,
                      transport_anomaly_count=io.anomaly_count)
        raise TrialError("S1 released but postcheck failed", result) from exc
    result.update(status="complete", complete_observations=sum(
        row["complete"] for row in result["observations"]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live-half-press", action="store_true")
    parser.add_argument("--expected-settings", type=Path, required=True,
                        help="Reviewed JSON object of all four exact getter replies; no setters")
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file; never overwritten")
    args = parser.parse_args(argv)
    if not args.run_live_half_press:
        parser.error("explicit --run-live-half-press is required")
    expected = json.loads(args.expected_settings.read_text())
    _validate_expected(expected)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}; paired S1 release required")
    old_handler = signal.signal(signal.SIGTERM, interrupted)
    try:
        with args.output.open("x", encoding="utf-8") as output:
            def emit(row):
                output.write(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(), **row))+"\n")
                output.flush()
                os.fsync(output.fileno())
            emit(dict(event="scope", half_press_hold_s=HOLD_S, direct_camera_ram_writes=0,
                      settings_writes=0, installation_performed=False, source_sha256=hashlib.sha256(
                          Path(__file__).read_bytes()).hexdigest()))
            try:
                with open(LOCK, "a+") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    result = run_trial(Transport(event=emit), expected, emit)
                emit(dict(event="result", result=result))
                print(json.dumps(result, indent=2))
                return 0
            except BaseException as exc:
                result = getattr(exc, "result", dict(status="failed-before-trial", error=repr(exc)))
                try:
                    emit(dict(event="failed", result=result, retry_permitted=False))
                except Exception:
                    pass
                print(json.dumps(result, indent=2), file=sys.stderr)
                return 1
    finally:
        signal.signal(signal.SIGTERM, old_handler)


if __name__ == "__main__":
    raise SystemExit(main())
