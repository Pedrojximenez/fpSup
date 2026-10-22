#!/usr/bin/env python3
"""One CINE standby native half-press observation; never starts file recording.

This observes original acquisition and release, not video CAF performance.
No settings setter, injected code, direct lens control or AAT start is used.
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

import af_cine_baseline as baseline
import af_native_preflight as preflight
from af_native_tracking_trial import NativeHalfPress, SamplingDeadline, send_key_edge

HOLD_S = 2.0
RANGES = (
    ("af_copy_focus", 0xC31F8858, 8),  # +1BC..1D8, includes half-release AF
    ("af_scheduler_raw", 0xC31F8CB4, 2),
    ("detection_runtime", 0xC37CCA04, 6),
    ("face_raw_header", 0xC37CCF10, 2),
    ("face_group0", 0xC37CCAAC, 39),
    ("aat_backends_and_selector", 0xC37CD340, 10),
    ("aat_model_and_states", 0xC37CDFA8, 12),
    ("manager_aat_state", 0xC37CCE6C, 1),
    ("aat_publication", 0xC3033E00, 10),
    ("native_l_cached_position", 0xC3476418, 1),
)


class AcquisitionError(RuntimeError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


def run_trial(io, emit=lambda row: None, *, probe=baseline.probe,
              sender=send_key_edge, clock=time.monotonic, sleep=time.sleep):
    """Caller holds the AF lock. One S1ON attempt and one required S1OFF attempt."""
    sink = emit
    def emit(row):
        try:
            sink(row)
        except Exception:
            io._latch_transport_fault()
            raise
    result = dict(schema="fp.cine-acquisition-trial/v1", status="preparing",
                  observations=[], half_press_hold_requested_s=HOLD_S,
                  scope="CINE standby native acquisition, not recorded-video CAF",
                  direct_camera_ram_writes=0, settings_writes=0, retries=0,
                  recording_started_by_tool=False, installation_performed=False,
                  geometry_eligible=False, optical_focus_confirmed=False,
                  source_coherence_verified=False, physical_key_state_verified=False)
    control = NativeHalfPress(io, emit, sender=sender, clock=clock)

    def read(name, address, count, deadline=None):
        words = []
        for offset in range(0, count, 8):
            take = min(8, count-offset)
            base = address+4*offset
            timeout, firmware_timeout = 2.0, 1000
            if deadline is not None:
                remaining = deadline-clock()
                if remaining < 0.20:
                    raise SamplingDeadline()
                timeout, firmware_timeout = 0.15, 100
            io.assert_motion_transport_healthy()
            started = clock()
            raw = io.request(f"TMO {firmware_timeout} SHL mem get 0x{base:08X},,0x{take*4:X}",
                             timeout=timeout)
            values = io._memory_words(io._decode_shell_reply(raw), base, take)
            emit(dict(event="memory_chunk", label=name, address=base, words=values,
                      host_started_monotonic_s=started, host_finished_monotonic_s=clock(),
                      coherent_snapshot=False))
            words.extend(values)
        return dict(address=address, words=words,
                    bytes_hex=struct.pack(f"<{count}I", *words).hex(), coherent_snapshot=False)

    def guard(label, deadline=None, *, holding=False):
        capture = read(label+"_capture", 0xC30338C8, 3, deadline)["words"]
        shutter = read(label+"_shutter", 0xC3033A6C, 1, deadline)["words"][0]
        storage = read(label+"_storage_guard", 0xC31AE3A8, 1, deadline)["words"][0]
        cine = read(label+"_stored_cinema", 0xC31C01B0, 1, deadline)["words"][0]
        copy_mode = read(label+"_af_copy_cinema", 0xC31F86E0, 1, deadline)["words"][0]
        echo = read(label+"_echo", preflight.ECHO, 1, deadline)["words"][0]
        ok = (capture[0] == 0 and capture[2] & 255 == 0 and
              shutter in ((0, 1) if holding else (0,)) and storage == 1 and
              cine == 1 and copy_mode == 1 and echo == preflight.ORIGINAL_ECHO)
        row = dict(event="cine_guard", label=label, capture=capture, shutter=shutter,
                   storage_guard=storage, stored_cinema=cine, af_copy_cinema=copy_mode,
                   echo=echo, owned_half_press_phase=holding, accepted=ok, atomic_lock=False)
        emit(row)
        if not ok:
            raise RuntimeError("CINE/capture/owned-half-press/echo guard changed")
        return row

    def checked_probe():
        value = probe(io, emit)
        if value.get("cine_baseline_verified") is not True or value.get("status") != "read-complete":
            raise RuntimeError("CINE baseline identity/state rejected")
        if value.get("settings") != value.get("settings_after"):
            raise RuntimeError("CINE settings changed during baseline")
        return value

    primary = release_error = None
    try:
        io.assert_motion_transport_healthy()
        result["before"] = checked_probe()
        result["guard_before_press"] = guard("before_press")
        control.press()
        deadline = control.pressed_at+HOLD_S
        result["status"] = "holding"
        for index in range(16):
            row = dict(index=index, blocks={}, complete=False, coherent_snapshot=False,
                       host_started_monotonic_s=clock())
            result["observations"].append(row)
            try:
                row["guard_before"] = guard(f"sample_{index}_before", deadline, holding=True)
                for name, address, count in RANGES:
                    row["blocks"][name] = read(f"sample_{index}_{name}", address, count, deadline)
                row["guard_after"] = guard(f"sample_{index}_after", deadline, holding=True)
                row["complete"] = True
            except SamplingDeadline:
                row["stopped_for_release_deadline"] = True
            row["host_finished_monotonic_s"] = clock()
            emit(dict(event="raw_observation", observation=row))
            if not row["complete"]:
                break
        remaining = deadline-clock()
        if remaining > 0:
            sleep(remaining)
    except BaseException as exc:
        primary = exc
    finally:
        try:
            control.release()
        except BaseException as exc:
            release_error = exc
        result.update(control.summary())
        result.update(transport_faulted=io.transport_faulted, transport_anomaly_count=io.anomaly_count)
    if primary is not None or release_error is not None or control.logging_errors or io.transport_faulted:
        result.update(status="failed", error=repr(primary), release_error=repr(release_error))
        raise AcquisitionError("CINE acquisition failed; no automatic retry", result) from (release_error or primary)
    try:
        # Native key ACK precedes asynchronous UI state publication. Observe a
        # bounded transition to zero; never re-dispatch S1OFF to force it.
        result["release_shutter_observations"] = []
        release_deadline = clock()+0.5
        for index in range(10):
            state = read(f"release_wait_{index}", 0xC3033A6C, 1)["words"][0]
            result["release_shutter_observations"].append(state)
            if state == 0:
                break
            if state != 1 or clock() >= release_deadline:
                raise RuntimeError("release ACK received but shutter state not confirmed clear")
            sleep(min(0.05, max(0, release_deadline-clock())))
        else:
            raise RuntimeError("release state observation budget exhausted")
        result["guard_after_release"] = guard("after_release")
        result["after"] = checked_probe()
        result["settings_equal"] = result["before"]["settings"] == result["after"]["settings"]
        if not result["settings_equal"]:
            raise RuntimeError("settings changed across trial; no blind setter restoration")
    except BaseException as exc:
        result.update(status="postcheck-failed", error=repr(exc), transport_faulted=io.transport_faulted)
        raise AcquisitionError("S1 release exchanged but postcheck failed", result) from exc
    result.update(status="complete", complete_observations=sum(r["complete"] for r in result["observations"]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live-half-press", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.run_live_half_press:
        parser.error("explicit --run-live-half-press required")
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}; release required")
    old = signal.signal(signal.SIGTERM, interrupted)
    try:
        with args.output.open("x", encoding="utf-8") as stream:
            def emit(row):
                stream.write(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(), **row))+"\n")
                stream.flush()
                os.fsync(stream.fileno())
            emit(dict(event="scope", native_s1_only=True, cine_standby_only=True,
                      sources_sha256={name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                          for name, path in (
                              ("af_cine_acquisition_trial.py", __file__),
                              ("af_cine_baseline.py", baseline.__file__),
                              ("af_native_preflight.py", preflight.__file__),
                              ("af_native_tracking_trial.py", Path(__file__).with_name("af_native_tracking_trial.py")),
                              ("af_fusion_collector.py", Path(__file__).with_name("af_fusion_collector.py")),
                              ("focus_bridge.py", preflight.ROOT/"projects/fp-af-assist/focus_bridge.py"))}))
            try:
                with open(preflight.LOCK, "a+") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    result = run_trial(preflight.Transport(event=emit), emit)
                emit(dict(event="result", result=result))
                print(json.dumps(dict(status=result["status"], complete_observations=result["complete_observations"],
                                      release_transport_completed=result["release_transport_completed"],
                                      settings_equal=result["settings_equal"])))
                return 0
            except BaseException as exc:
                result = getattr(exc, "result", dict(status="failed-before-trial", error=repr(exc)))
                try:
                    emit(dict(event="failed", result=result, retry_permitted=False))
                except Exception:
                    pass
                print(json.dumps(dict(status=result["status"], error=str(exc))), file=sys.stderr)
                return 1
    finally:
        signal.signal(signal.SIGTERM, old)


if __name__ == "__main__":
    raise SystemExit(main())
