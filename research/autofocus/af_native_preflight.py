#!/usr/bin/env python3
"""Bounded fp 5.02 native observer preflight: existing shell, reads only.

No injection, echo invocation, allocation, pointer chasing, lens command,
setter, task control, endpoint access or automatic retry. Read intervals are
not atomic snapshots; task registers and raw subjects do not confer validity.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "projects/fp-af-assist"))
from focus_bridge import LOCK, Transport

BUILD_ID = "13aa621060efff11aaba9b21ad925005302605cf"
ECHO = 0xC0BAC2F8
ORIGINAL_ECHO = 0xC03D99A0
SITES = (("af", 0xC028E310, 0xEBFE7502), ("lens", 0xC0340458, 0xEB00B4BE),
         ("face", 0xC05AB348, 0xEBFFF96C), ("aat", 0xC05AB8C8, 0xEB002D0A))
RANGES = (
    ("worker_allocations", 0xC072F050, 3),
    ("legacy_logger_pool", 0xC3757A7C, 1),
    ("cave_bump_raw", 0xC072E060, 1),
    ("boot_timestamps_raw", 0xC072F6F4, 2),
    ("legacy_parameter_region_prefix", 0xC072F700, 4),
    ("legacy_handler_region_prefix", 0xC072FC00, 4),
    ("native_l_selector", 0xC3476408, 1),
    ("native_l_object", 0xC3476414, 23),
    ("face_manager_prefix", 0xC37CCA9C, 4),
    ("face_initialization_guard", 0xC37CCA8C, 1),
    ("face_group0", 0xC37CCAAC, 39),
    ("aat_model_and_states", 0xC37CDFA8, 12),
    ("aat_backends_and_selector", 0xC37CD340, 10),
    ("aat_publication", 0xC3033E00, 10),
)
# Optional fixed source-path diagnostics. No getters (some initialize lazily),
# pointer following, or settings changes. The display copies are distinct from
# the producer and are not treated as coherent or as proof a box is visible.
# Evidence: notes/FP_FACE_DISPLAY_SOURCE_2026-09-27.md and blk_c03 C03A0410.
SUBJECT_PATH_RANGES = (
    ("face_menu_storage_guard", 0xC31AE3A8, 1),
    ("face_menu_selector_before", 0xC31B954C, 1),
    ("face_menu_primary", 0xC31B3758, 1),
    ("face_menu_alternate", 0xC31B9020, 1),
    ("detection_configuration", 0xC358E260, 20),
    ("detection_configuration_guard", 0xC358E2B8, 1),
    ("face_manager_context", 0xC37CCDB8, 8),
    ("face_raw_header_and_first_record", 0xC37CCF10, 10),
    ("face_status_head", 0xC3033AC4, 42),
    ("face_status_context", 0xC3033DDC, 8),
    ("face_display_observer_head", 0xC3433C58, 42),
    ("face_display_observer_context", 0xC3433F70, 8),
    ("face_renderer_head", 0xC3434474, 42),
    ("face_renderer_context", 0xC343478C, 8),
    ("face_renderer_extra", 0xC34348E4, 1),
    ("face_renderer_object", 0xC3435A54, 9),
    ("face_display_suppression_word", 0xC30338E8, 1),
    ("face_display_observer_controls", 0xC3426318, 3),
    ("face_menu_selector_after", 0xC31B954C, 1),
)
# Small temporal diagnostic, not AF telemetry or a producer-atomic snapshot.
SUBJECT_WATCH_RANGES = (
    ("runtime_gate", 0xC37CCA04, 5),
    ("runtime_guard", 0xC37CCA18, 1),
    ("raw_header", 0xC37CCF10, 2),
    ("manager_header", 0xC37CCA9C, 4),
    ("face_slot", 0xC37CCAAC, 13),
    ("status_header", 0xC3033AC4, 3),
    ("renderer_header", 0xC3434474, 3),
)
SETTINGS = ("menu SetFocusPosition", "menu SetFocusMode",
            "menu SetFocusArea", "menu SetFocusAreaSize")
# ROM C0411520: zero suppresses stack-body dumping; task info/registers only.
TASKS = ("AfMgr", "LensFocs", "Tracking", "FdTsk", "EyeDtctn")


def static_guards():
    """Explicit ranges only from the checked-in four-site ROM contract."""
    path = ROOT / "fpSup/focus/geometry/native_hook_sites.json"
    document = json.loads(path.read_text())
    expected = {address: word for _, address, word in SITES}
    if len(document["sites"]) != 4:
        raise ValueError("unexpected hook manifest site count")
    guards = []
    for site in document["sites"]:
        if expected.get(int(site["address"], 16)) != int(site["expected_word"], 16):
            raise ValueError("hook manifest differs from fixed read plan")
        for key in ("context", "callee_entry_guard", "callee_return_guard"):
            guard = site[key]
            data = bytes.fromhex(guard.get("expected_bytes_le", guard.get("bytes_le", "")))
            address = int(guard["address"], 16)
            size = guard.get("length_bytes", len(data))
            if address & 3 or size % 4 or not 4 <= size <= 64 or len(data) != size:
                raise ValueError("invalid static guard")
            if not 0xC0000000 <= address <= 0xC0720000 - size:
                raise ValueError("guard outside fixed firmware code region")
            guards.append((site["id"] + "_" + key, address, data))
    return guards


def probe(io, emit=lambda row: None, *, subject_path=False, subject_samples=0):
    if type(subject_samples) is not int or not 0 <= subject_samples <= 16:
        raise ValueError("subject_samples must be an integer from 0 to 16")
    if subject_samples and not subject_path:
        raise ValueError("subject_samples requires subject_path")
    guards = static_guards()  # Validate local plan before any camera exchange.
    evidence = dict(schema="fp.native-observer.preflight/v1", camera_ram_writes=0,
                    camera_ram_writes_scope="direct host writes and injected payloads only",
                    native_handler_internal_writes_audited=False,
                    lens_commands=0, retries=0, installation_performed=False,
                    deployment_ready=False, memory_ownership_verified=False,
                    stack_headroom_verified=False, source_coherence_verified=False,
                    geometry_eligible=False, confirmation_authorized=False,
                    motion_authorized=False, blocks={}, tasks={}, settings={})
    evidence["subject_path_checked"] = subject_path

    def text(command):
        result = io.shell(command, timeout_ms=1000)
        emit(dict(event="native_reply", command=command, reply=result))
        return result

    def words(label, address, count):
        all_words = []
        for offset in range(0, count, 8):
            take = min(8, count - offset)
            base = address + 4 * offset
            before = time.monotonic_ns()
            reply = text(f"mem get 0x{base:08X},,0x{take * 4:X}")
            values = io._memory_words(reply, base, take)
            emit(dict(event="memory_chunk", label=label, address=base, words=values,
                      host_before_ns=before, host_after_ns=time.monotonic_ns()))
            all_words.extend(values)
        block = dict(address=f"0x{address:08X}", words=all_words,
                     bytes_hex=struct.pack(f"<{count}I", *all_words).hex(),
                     coherent_snapshot=False)
        evidence["blocks"][label] = block
        return all_words

    status = io.request("STATUS", timeout=2.0).decode("ascii")
    emit(dict(event="status", reply=status))
    if not status.startswith("OK ") or "camera=open" not in status:
        raise RuntimeError("no existing open camera")
    evidence["host_status"] = status
    version = text("version")
    evidence["version"] = version
    if not all(token in version for token in ("w71c1", "5.02.0.V91", BUILD_ID)):
        raise RuntimeError("unsupported camera/firmware build; no memory reads")
    if words("echo_before", ECHO, 1)[0] != ORIGINAL_ECHO:
        raise RuntimeError("unknown echo borrower; do not interleave")
    capture = words("capture_guard_before", 0xC30338C8, 3)
    shutter = words("shutter_gate_before", 0xC3033A6C, 1)[0]
    # C8..CB are four busy bytes; D0 is MovieRecording, not the whole D0 word.
    if capture[0] != 0 or capture[2] & 0xFF or shutter:
        raise RuntimeError("capture/recording guard active; preflight stopped")
    for name, address, expected in SITES:
        actual = words("hook_" + name, address, 1)[0]
        if actual != expected:
            raise RuntimeError(f"{name} callsite is not the audited original word")
    for name, address, data in guards:
        actual = words(name, address, len(data) // 4)
        if struct.pack(f"<{len(actual)}I", *actual) != data:
            raise RuntimeError(f"{name} firmware context mismatch")
    for name, address, count in RANGES:
        words(name, address, count)
    if subject_path:
        for name, address, count in SUBJECT_PATH_RANGES:
            words(name, address, count)
    evidence["subject_observations"] = []
    for index in range(subject_samples):
        if index:
            time.sleep(0.25)
        observation = dict(index=index, host_before_ns=time.monotonic_ns(), blocks={},
                           source_coherence_verified=False, geometry_eligible=False)
        for name, address, count in SUBJECT_WATCH_RANGES:
            label = f"subject_watch_{index:02d}_{name}"
            words(label, address, count)
            observation["blocks"][name] = evidence["blocks"][label]
        observation["host_after_ns"] = time.monotonic_ns()
        evidence["subject_observations"].append(observation)
        emit(dict(event="subject_observation", observation=observation))
    for command in SETTINGS:
        evidence["settings"][command] = text(command)
    for task in TASKS:
        evidence["tasks"][task] = text(f"tkos skdump {task} 0")
    if words("echo_after", ECHO, 1)[0] != ORIGINAL_ECHO:
        raise RuntimeError("echo owner changed during reads")
    evidence["capture_guard_after"] = words("capture_guard_after", 0xC30338C8, 3)
    evidence["shutter_gate_after"] = words("shutter_gate_after", 0xC3033A6C, 1)[0]
    evidence["settings_after"] = {command: text(command) for command in SETTINGS}
    evidence["settings_equal"] = evidence["settings"] == evidence["settings_after"]
    after = evidence["capture_guard_after"]
    evidence["capture_idle_at_both_observations"] = (
        after[0] == 0 and (after[2] & 0xFF) == 0 and evidence["shutter_gate_after"] == 0)
    allocations = evidence["blocks"]["worker_allocations"]["words"]
    evidence["worker_publication_raw"] = dict(pool=allocations[0], size=allocations[1], code=allocations[2])
    evidence["worker_and_legacy_pool_differ"] = allocations[0] != evidence["blocks"]["legacy_logger_pool"]["words"][0]
    evidence["native_l_layout_matches"] = (
        evidence["blocks"]["native_l_selector"]["words"][0] == 1 and
        evidence["blocks"]["native_l_object"]["words"][0] == 0xC0B8EEEC)
    evidence["face_manager_vtable_matches"] = evidence["blocks"]["face_manager_prefix"]["words"][0] == 0xC2DFAB00
    backends = evidence["blocks"]["aat_backends_and_selector"]["words"]
    evidence["aat_backend_vtables_match"] = backends[:2] == [0xC2DFC59C, 0xC2DFC5B8]
    evidence["status"] = "read-complete"
    evidence["limits"] = ["No pointer/size establishes a free allocation or DMA lease.",
        "No direct RAM writes or setters are sent; native command internals may update caches or locks.",
        "skdump with zero length reads task metadata/registers, not stack high-water or future headroom.",
        "Sequential mem-get chunks are not producer-atomic or exposure-aligned.",
        "No focus, settlement, subject identity or valid scale is inferred."]
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New JSONL transcript, never overwritten")
    parser.add_argument("--run-live-read", action="store_true")
    parser.add_argument("--subject-path", action="store_true",
                        help="Also read fixed detection configuration and display copies; no settings changed")
    parser.add_argument("--subject-samples", type=int, default=0, choices=range(17),
                        help="With --subject-path, take 0..16 bounded raw observations, separated by 250 ms")
    args = parser.parse_args(argv)
    if not args.run_live_read:
        parser.error("explicit --run-live-read required; this is not an offline replay")
    if args.subject_samples and not args.subject_path:
        parser.error("--subject-samples requires --subject-path")
    with args.output.open("x", encoding="utf-8") as output:
        def emit(row):
            output.write(json.dumps(dict(at=dt.datetime.now().astimezone().isoformat(), **row)) + "\n")
            output.flush()
        emit(dict(event="scope", camera_ram_writes=0, lens_commands=0, retries=0,
                  camera_ram_writes_scope="direct host writes and injected payloads only",
                  native_handler_internal_writes_audited=False,
                  subject_path_requested=args.subject_path,
                  subject_samples_requested=args.subject_samples,
                  sources_sha256={"af_native_preflight.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "focus_bridge.py": hashlib.sha256((ROOT / "projects/fp-af-assist/focus_bridge.py").read_bytes()).hexdigest()}))
        try:
            with open(LOCK, "a+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = probe(Transport(event=emit), emit, subject_path=args.subject_path,
                               subject_samples=args.subject_samples)
                emit(dict(event="result", result=result))
            print(json.dumps(result, indent=2))
        except Exception as exc:
            emit(dict(event="failed", error=repr(exc), retry_permitted=False))
            print(str(exc), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
