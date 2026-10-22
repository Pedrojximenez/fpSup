#!/usr/bin/env python3
"""Read-only fixed-address CINE preview AF baseline; no key, setter or payload.

The fixed CameraMgr applied copy is C31F865C+40=C31F869C, initialized
under C31F8C90 by C0206E98. C0207088 returns that copy to C022B7F8 and
C028EAB8. Rec settings singleton C35A8F3C (guard C35A9530) stores source
UserSetting pointer at +4 and that destination at +8 (C03A9910); its +C
region is a distinct comparison snapshot. C03A9FB0(...,4)->C03AA6A8 copies
source +1BC..1FF into destination, with explicit exceptions. No pointer from
RAM is followed by this tool. The source-pointer cells are compared only.

Applied +1C0 is shared by ST PreAF and CINE FullTimeAfSupport (C00A3438 /
C00A34B8); C00A2DA0 filters the menu value against capture state. Its value
does not prove motor activity. All reads remain sequential, not atomic.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

import af_native_preflight as preflight

IDENTITY_RANGES = (
    ("menu_storage_guard", 0xC31AE3A8, 1),
    ("stored_record_mode", 0xC31C01B0, 1),
    ("camera_manager_init_guard", 0xC31F8C90, 1),
    ("camera_manager_setting_callback", 0xC31F8698, 1),
    ("applied_record_mode", 0xC31F86E0, 1),
    ("user_setting_init_guard", 0xC3075234, 1),
    ("user_setting_current_pointer_raw", 0xC3075230, 1),
    ("rec_settings_init_guard", 0xC35A9530, 1),
    ("rec_settings_source_destination_raw", 0xC35A8F40, 2),
    ("native_af_init_guard", 0xC32067E8, 1),
    ("single_af_init_guard", 0xC33D5204, 1),
    ("capture_state_init_guard", 0xC3033FFC, 1),
)
WATCH_RANGES = (
    ("applied_focus", 0xC31F8858, 5),
    ("applied_face_mode", 0xC31F8784, 1),
    ("preaf_capture_context", 0xC3033A44, 4),
    ("preaf_tail_and_shutter", 0xC3033A68, 2),
    ("af_observers", 0xC32066F8, 6),
    ("af_drive_mode", 0xC32065A0, 1),
    ("af_cine_and_preaf_context", 0xC32065B0, 10),
    ("af_request_mode_source", 0xC3206730, 3),
    ("af_single_state_raw", 0xC33D51C0, 1),
    ("af_route_raw", 0xC32915B0, 1),
    ("af_current_contrast_copies", 0xC3206698, 2),
    ("af_area_and_sample_indices", 0xC3291534, 3),
    ("scheduler_phase_mode", 0xC31F8CB4, 2),
    ("scheduler_slot0", 0xC31F8CCC, 4),
    ("native_l_cached_position", 0xC3476418, 1),
    ("detection_runtime", 0xC37CCA04, 5),
    ("detection_runtime_guard", 0xC37CCA18, 1),
    ("face_group0", 0xC37CCAAC, 39),
    ("aat_backends_and_selector", 0xC37CD340, 10),
    ("aat_model_and_states", 0xC37CDFA8, 12),
    ("aat_manager_state_and_rectangle", 0xC37CCE6C, 9),
    ("aat_publication", 0xC3033E00, 10),
)


class BaselineError(RuntimeError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


def _verify_identity(blocks):
    def word(name):
        return blocks[name]["words"][0]
    guards = ("menu_storage_guard", "camera_manager_init_guard", "user_setting_init_guard",
              "rec_settings_init_guard", "native_af_init_guard", "single_af_init_guard",
              "capture_state_init_guard")
    if any(word(name) != 1 for name in guards):
        raise RuntimeError("CINE baseline initialization guard rejected")
    if word("stored_record_mode") != 1 or word("applied_record_mode") != 1:
        raise RuntimeError("CINE stored/applied mode must both remain 1")
    if word("camera_manager_setting_callback") != 0xC090EF10:
        raise RuntimeError("CameraMgr setting callback identity rejected")
    source = word("user_setting_current_pointer_raw")
    owner = blocks["rec_settings_source_destination_raw"]["words"]
    if source == 0 or source & 3 or owner != [source, 0xC31F869C]:
        raise RuntimeError("source/destination fixed-pointer identity rejected; no pointers followed")


def _verify_preflight(result, settings=None):
    if (result.get("status") != "read-complete" or result.get("settings_equal") is not True
            or result.get("capture_idle_at_both_observations") is not True
            or result.get("native_l_layout_matches") is not True
            or result.get("face_manager_vtable_matches") is not True):
        raise RuntimeError("native preflight rejected CINE baseline")
    if settings is not None and (result["settings"] != settings or result["settings_after"] != settings):
        raise RuntimeError("focus settings changed across baseline")


def collect(io, emit=lambda row: None, *, samples=8, probe=preflight.probe,
            sleep=time.sleep):
    """Caller holds the shared lock. At most 16 observations, no retries."""
    if type(samples) is not int or not 1 <= samples <= 16:
        raise ValueError("samples must be an integer from 1 to 16")
    original_emit = emit
    def emit(row):
        try:
            original_emit(row)
        except Exception:
            io._latch_transport_fault()
            raise
    result = dict(schema="fp.cine-preview-af-baseline/v1", status="preparing", observations=[],
                  cine_baseline_verified=False,
                  key_commands=0, settings_writes=0, direct_camera_ram_writes=0,
                  native_handler_internal_writes_audited=False, retries=0,
                  installation_performed=False, pointer_chasing_performed=False,
                  source_coherence_verified=False, optical_focus_confirmed=False,
                  continuous_af_activity_proven=False, recorded_stream_test=False,
                  geometry_eligible=False, motion_authorized=False)

    def read(label, address, count):
        words = []
        for offset in range(0, count, 8):
            base = address+4*offset
            take = min(8, count-offset)
            io.assert_motion_transport_healthy()  # Stop even read sessions after an anomaly.
            before = time.monotonic_ns()
            text = io.shell(f"mem get 0x{base:08X},,0x{take*4:X}", timeout_ms=1000)
            values = io._memory_words(text, base, take)
            emit(dict(event="memory_chunk", label=label, address=base, words=values,
                      host_before_ns=before, host_after_ns=time.monotonic_ns()))
            words.extend(values)
        return dict(address=f"0x{address:08X}", words=words,
                    bytes_hex=struct.pack(f"<{count}I", *words).hex(), coherent_snapshot=False)

    def identity(label):
        blocks = {name: read(label+"_"+name, address, count)
                  for name, address, count in IDENTITY_RANGES}
        _verify_identity(blocks)
        emit(dict(event="identity", label=label, blocks=blocks))
        return blocks

    def capture(label):
        busy = read(label+"_busy", 0xC30338C8, 3)
        shutter = read(label+"_shutter", 0xC3033A6C, 1)
        raw = busy["words"]
        if raw[0] != 0 or raw[2] & 0xff or shutter["words"][0] != 0:
            raise RuntimeError("capture/recording busy; this protocol covers CINE preview only")
        return dict(busy=busy, shutter=shutter, atomic_idle_lock=False)

    try:
        # Firmware/version/echo/capture are verified before extra fixed reads.
        result["preflight_before"] = probe(io, emit)
        _verify_preflight(result["preflight_before"])
        result["identity_before"] = identity("before")
        for index in range(samples):
            if index:
                sleep(0.25)
            row = dict(index=index, host_before_ns=time.monotonic_ns(), blocks={},
                       source_coherence_verified=False, geometry_eligible=False)
            row["capture_before"] = capture(f"sample_{index}_before")
            for name, address, count in WATCH_RANGES:
                row["blocks"][name] = read(f"sample_{index}_{name}", address, count)
            row["capture_after"] = capture(f"sample_{index}_after")
            applied = row["blocks"]["applied_focus"]["words"]
            row["raw_interpretation"] = dict(
                effective_focus_mode=applied[0], effective_full_time_preaf_byte=applied[1]&0xff,
                af_copy_focus_area_raw=applied[4],
                af_copy_area_is_not_menu_area_enum=True,
                full_time_byte_is_not_motor_activity=True,
                scheduler_phase_is_not_exposure_id=True,
                cached_lens_position_is_not_optical_position=True,
                aat_initialization_is_not_focus_confirmation=True)
            row["host_after_ns"] = time.monotonic_ns()
            result["observations"].append(row)
            emit(dict(event="observation", observation=row))
        result["identity_after"] = identity("after")
        if result["identity_before"] != result["identity_after"]:
            raise RuntimeError("fixed source/owner identity changed during CINE baseline")
        result["preflight_after"] = probe(io, emit)
        _verify_preflight(result["preflight_after"], result["preflight_before"]["settings"])
        result["status"] = "read-complete"
        result["cine_baseline_verified"] = True
        result["settings"] = result["preflight_before"]["settings"]
        result["settings_after"] = result["preflight_after"]["settings_after"]
        result["limits"] = [
            "CINE preview only; no recording or S1 event was requested.",
            "Stored menu, current UserSetting pointer and AF applied copy are distinct sources.",
            "AF copy area can differ from menu area; it is not the current UserSetting AAT gate.",
            "Initialization/identity guards and before/after equality are not a seqlock.",
            "Background AF can already be active without a host key event.",
            "Observer readiness/phase, contrast, route and cached lens changes are raw diagnostics.",
            "No atomic AF result/drive-end/subject pairing or DFD eligibility is inferred.",
            "AAT model/publication/group bytes can be stale or inactive; zeros are not tracking failure."]
        return result
    except BaseException as exc:
        result.update(status="failed", error=repr(exc), transport_faulted=io.transport_faulted,
                      transport_anomaly_count=io.anomaly_count)
        raise BaselineError("CINE read-only baseline stopped; no retry", result) from exc


def probe(io, emit=lambda row: None, *, samples=1):
    """Small verified baseline for a separately reviewed native S1 owner."""
    return collect(io, emit, samples=samples)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live-read", action="store_true")
    parser.add_argument("--samples", type=int, default=8, choices=range(1, 17))
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file, never overwritten")
    args = parser.parse_args(argv)
    if not args.run_live_read:
        parser.error("explicit --run-live-read required; this entrypoint never sends a key")
    with args.output.open("x", encoding="utf-8") as output:
        def emit(row):
            output.write(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(), **row))+"\n")
            output.flush()
        emit(dict(event="scope", key_commands=0, settings_writes=0, direct_camera_ram_writes=0,
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
        try:
            with open(preflight.LOCK, "a+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = collect(preflight.Transport(event=emit), emit, samples=args.samples)
            emit(dict(event="result", result=result))
            print(json.dumps(result, indent=2))
            return 0
        except BaseException as exc:
            result = getattr(exc, "result", dict(status="failed-before-read", error=repr(exc)))
            try:
                emit(dict(event="failed", result=result))
            except Exception:
                pass
            print(json.dumps(result, indent=2), file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
