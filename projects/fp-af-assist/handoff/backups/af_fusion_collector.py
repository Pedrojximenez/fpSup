#!/usr/bin/env python3
"""SIGMA fp AF-fusion snapshot collector and offline decoder.

The live path borrows the modern fp USB shell's ``echo`` handler, gathers one
fixed-size observation inside the camera, and receives it over the worker's
ordinary EP0x82 reply. By default no lens-drive or exposure setter is called.
The explicit ``--half-press-after`` option requests one original S1 half-press
and paired release while collecting; it may drive the lens and engage AE lock.
It never sends a full-press / capture command or changes menu settings.

Typical use::

    python3 af_fusion_collector.py inspect
    python3 af_fusion_collector.py collect --duration 10 --hz 20
    python3 af_fusion_collector.py decode captures/.../samples.bin

Live semantic validation is intentionally separate: the first camera run must
still establish ROI/index cadence and mposm exposure alignment before these
records are accepted for DFD fitting.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib
import json
from pathlib import Path
import signal
import socket
import struct
import sys
import time
from typing import BinaryIO, Iterator


SCHEMA = "sigma-fp-af-fusion/v5"
LEGACY_SCHEMA = "sigma-fp-af-fusion/legacy-record-v1"
RECORD_MAGIC = b"AFF1"
RECORD_TRAILER = b"AFFE"
RECORD_VERSION = 2
RECORD_SIZE = 0xD0
# The handler is 1000 bytes. The putfile template's F800..FA00 slot is only
# 512 bytes, so use the shell's reserved 1 KiB dumpdirect work slot instead.
# It is reloaded by its owner when needed and is safe to borrow only while the
# echo handler is verified free below.
CODE_ADDRESS = 0xC072FC00
CODE_END = 0xC0730000
RECORD_ADDRESS = 0xC072F700
SESSION_NONCE_ADDRESS = RECORD_ADDRESS + RECORD_SIZE
ECHO_SLOT = 0xC0BAC2F8
ECHO_ORIGINAL = 0xC03D99A0
FRAMEBUF_POINTER = 0xC3757A7C
COORD_WIDTH = 320
COORD_HEIGHT = 213
DEFAULT_SOCKET = "/tmp/fpshd.sock"
LOCK_PATH = "/tmp/fp-af-fusion.lock"

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "af_fusion_snapshot.S"
REPO_ROOT = HERE.parents[1]
DEFAULT_SHELL_DIR = REPO_ROOT / "fpSup" / "fp_usb_shell"
DEFAULT_CAPTURE_ROOT = HERE / "captures" / "af-fusion"


class RecordError(ValueError):
    """A binary snapshot failed its framing or integrity checks."""


def _u16(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<H", blob, offset)[0]


def _i16x4(blob: bytes, offset: int) -> tuple[int, int, int, int]:
    return struct.unpack_from("<hhhh", blob, offset)


def _u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def _i32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<i", blob, offset)[0]


def _valid_rect(rect: dict[str, int]) -> bool:
    return (
        rect["w"] > 0
        and rect["h"] > 0
        and rect["x"] < COORD_WIDTH
        and rect["y"] < COORD_HEIGHT
        and rect["x"] + rect["w"] > 0
        and rect["y"] + rect["h"] > 0
    )


def parse_record(
    blob: bytes,
    *,
    host_before_ns: int | None = None,
    host_after_ns: int | None = None,
) -> dict:
    """Decode and validate one ``AFF1`` record."""
    if len(blob) != RECORD_SIZE:
        raise RecordError(f"record is {len(blob)} bytes, expected {RECORD_SIZE}")
    if blob[:4] != RECORD_MAGIC:
        raise RecordError(f"bad magic {blob[:4]!r}")
    version, size = struct.unpack_from("<HH", blob, 4)
    if version not in (1, RECORD_VERSION) or size != RECORD_SIZE:
        raise RecordError(f"unsupported record version/size {version}/{size}")
    if blob[0xC4:0xC8] != RECORD_TRAILER:
        raise RecordError(f"bad trailer {blob[0xC4:0xC8]!r}")
    seq = _u32(blob, 0x08)
    if _u32(blob, 0xC8) != ((~seq) & 0xFFFFFFFF):
        raise RecordError("sequence complement mismatch")

    flags = _u32(blob, 0x0C)
    tick_start = _u32(blob, 0x10)
    tick_end = _u32(blob, 0x14)
    area_before = _u32(blob, 0x18)
    area_after = _u32(blob, 0x1C)
    area_used = _u32(blob, 0x20)
    sample_before = _u32(blob, 0x24)
    sample_after = _u32(blob, 0x28)
    sample_used = _u32(blob, 0x2C)

    ax, ay, aw, ah = _i16x4(blob, 0x74)
    aat = {
        "x": ax,
        "y": ay,
        "w": aw,
        "h": ah,
        "confidence_raw": _i32(blob, 0x7C),
    }
    aat["valid"] = _valid_rect(aat)
    aat["locked"] = bool(flags & 0x10) and aat["valid"]

    face = {
        "x": _i32(blob, 0x84),
        "y": _i32(blob, 0x88),
        "w": _i32(blob, 0x8C),
        "h": _i32(blob, 0x90),
        "mode": _i32(blob, 0x80),
        "face0_tracking_id": _i32(blob, 0x94),
        "face0_valid": bool(_u32(blob, 0x98)),
    }
    face["valid"] = bool(flags & 0x08) and _valid_rect(face)
    face["w_norm"] = face["w"] / COORD_WIDTH if face["valid"] else None

    if face["valid"]:
        selected = {k: face[k] for k in ("x", "y", "w", "h")}
        cue_source = "face"
        roi_confidence = None
    elif aat["locked"]:
        selected = {k: aat[k] for k in ("x", "y", "w", "h")}
        cue_source = "aat"
        roi_confidence = aat["confidence_raw"]
    else:
        selected = None
        cue_source = None
        roi_confidence = None

    host_mid_ns = None
    round_trip_ms = None
    if host_before_ns is not None and host_after_ns is not None:
        host_mid_ns = (host_before_ns + host_after_ns) // 2
        round_trip_ms = (host_after_ns - host_before_ns) / 1_000_000.0

    indices_stable = bool(flags & 0x04)
    area_valid = bool(flags & 0x01)
    sample_valid = bool(flags & 0x02)

    snapshot_coherent = indices_stable and area_valid and sample_valid

    if version == 1:
        gain_fields = {
            # Record v1 sampled the 0xC343A6A0 RGB/digital-gain helper,
            # mistakenly believed to be the IMX410 object.  Keep those bytes
            # explicitly legacy/raw when decoding historical captures.
            "legacy_gain_helper_raw": {
                "plus_0x0c": _u32(blob, 0x9C),
                "plus_0x18": _u32(blob, 0xA0),
                "plus_0x2c": _u32(blob, 0xA4),
                "plus_0x34": _u32(blob, 0xA8),
            }
        }
        record_schema = LEGACY_SCHEMA
    else:
        gain_fields = {
            "imx410_gain": {
                "relative_gain": _u32(blob, 0x9C),
                "analog_code": _u32(blob, 0xA0),
                "analog_ratio_x100": _u32(blob, 0xA4),
                "hcg": bool(_u32(blob, 0xA8)),
                "hcg_raw": _u32(blob, 0xA8),
            }
        }
        record_schema = SCHEMA

    return {
        "schema": record_schema,
        "record_version": version,
        "sequence": seq,
        "transport": {
            # Copied by the executing handler from a separate host-written
            # seed.  A delayed raw reply contains a live record pointer, so
            # writing the nonce directly into RECORD would relabel stale data.
            "session_nonce": _u32(blob, 0xCC),
        },
        "time": {
            "camera_tick_us_start": tick_start,
            "camera_tick_us_end": tick_end,
            "camera_snapshot_us": (tick_end - tick_start) & 0xFFFFFFFF,
            "host_before_ns": host_before_ns,
            "host_after_ns": host_after_ns,
            "host_mid_ns": host_mid_ns,
            "usb_round_trip_ms": round_trip_ms,
        },
        "integrity": {
            "framing_valid": True,
            "indices_stable": indices_stable,
            "area_index_valid": area_valid,
            "sample_index_valid": sample_valid,
            "snapshot_coherent": snapshot_coherent,
            # Coherence is necessary but not sufficient: in idle Live View the
            # sweep index and mposm entry remain stale while H/L keeps changing.
            # A session analyser must prove a new exposure-aligned sweep sample
            # before deciding DFD eligibility.
            "usable_for_dfd": None,
            "dfd_eligibility": "requires_sweep_motion_alignment",
        },
        "indices": {
            "af_area_before": area_before,
            "af_area_after": area_after,
            "af_area_used": area_used,
            "sweep_sample_before": sample_before,
            "sweep_sample_after": sample_after,
            "sweep_sample_used": sample_used,
        },
        "af": {
            "drive_mode": _u32(blob, 0x30),
            "area_mode": _u32(blob, 0x34),
            "route": _u32(blob, 0x38),
            "saf_h": _i32(blob, 0x3C),
            "saf_l": _i32(blob, 0x40),
            "peak_now": _i32(blob, 0x44),
            "peak_max": _i32(blob, 0x48),
            "peak_min": _i32(blob, 0x4C),
            "g_afpos": _i32(blob, 0x50),
            "mposm_zero": _i32(blob, 0x54),
            "mposm": _i32(blob, 0x58),
            "body_motion": _i32(blob, 0x5C),
            "drive_direction_vote": _i32(blob, 0x60),
            "drive_speed_lpf": _i32(blob, 0x64),
            "step_state": _i32(blob, 0x68),
            "peak_argmax": _i32(blob, 0x6C),
            "area0_reference": _i32(blob, 0x70),
        },
        "subject": {
            "coordinate_space": {"width": COORD_WIDTH, "height": COORD_HEIGHT},
            "cue_source": cue_source,
            "roi": selected,
            "roi_confidence": roi_confidence,
            # The consolidated face can differ from face group zero.  Do not
            # silently attach face0's ID to it until live matching proves that.
            "track_id": None,
            "face": face,
            "aat": aat,
        },
        "exposure": {
            **gain_fields,
            "af_metering_raw": {
                "rgb_gain": _i32(blob, 0xAC),
                "sensitivity": _i32(blob, 0xB0),
                "shutter": _i32(blob, 0xB4),
                "f_number": _i32(blob, 0xB8),
            },
            "capture_state_raw": _u32(blob, 0xBC),
            "movie_recording": bool(_u32(blob, 0xC0)),
        },
        "estimates": {
            "geometry_target": None,
            "geometry_confidence": None,
            "dfd_peak": None,
            "dfd_residual": None,
            "dfd_confidence": None,
        },
    }


def iter_binary_records(stream: BinaryIO) -> Iterator[bytes]:
    """Yield fixed records and reject a truncated tail."""
    while True:
        blob = stream.read(RECORD_SIZE)
        if not blob:
            return
        if len(blob) != RECORD_SIZE:
            raise RecordError(f"truncated final record: {len(blob)} bytes")
        yield blob


def build_mock_record(
    seq: int = 7, *, stable: bool = True, session_nonce: int = 0x12345678
) -> bytes:
    """Create a deterministic fixture for decoder tests; never used live."""
    blob = bytearray(RECORD_SIZE)
    flags = 0x01 | 0x02 | 0x08 | 0x10 | 0x20
    if stable:
        flags |= 0x04
    struct.pack_into(
        "<4sHHII", blob, 0, RECORD_MAGIC, RECORD_VERSION, RECORD_SIZE, seq, flags
    )
    struct.pack_into("<II", blob, 0x10, 100_000, 100_017)
    struct.pack_into("<IIIIII", blob, 0x18, 3, 3 if stable else 4, 3, 12, 12, 12)
    struct.pack_into("<III", blob, 0x30, 4, 2, 8)
    struct.pack_into("<iiiiiiiiiiiiii", blob, 0x3C,
                     12000, 7000, 11500, 13000, 3000, 5311, 5000, 5311,
                     0, 1, 22000, 6, 9, 25000)
    struct.pack_into("<hhhh", blob, 0x74, 30, 40, 100, 80)
    struct.pack_into("<i", blob, 0x7C, 24)
    struct.pack_into("<iiiiiii", blob, 0x80, 1, 50, 20, 64, 64, 42, 1)
    struct.pack_into("<IIIIIIIIII", blob, 0x9C,
                     4, 800, 250, 1, 100, 800, 48, 14, 2, 1)
    blob[0xC4:0xC8] = RECORD_TRAILER
    struct.pack_into("<I", blob, 0xC8, (~seq) & 0xFFFFFFFF)
    struct.pack_into("<I", blob, 0xCC, session_nonce)
    return bytes(blob)


def _load_shell(shell_dir: Path, socket_path: str):
    shell_dir = shell_dir.resolve()
    if not (shell_dir / "putfile.py").is_file():
        raise SystemExit(f"USB shell host module not found in {shell_dir}")
    sys.path.insert(0, str(shell_dir))
    putfile = importlib.import_module("putfile")
    putfile.SOCK = socket_path
    return putfile


def _read_exact_words(shell, address: int, count: int) -> list[int]:
    words: list[int] = []
    # A formatted mem-get line is much larger than its four data bytes.  Keep
    # each request well below the daemon's line buffer when verifying 952 B of
    # code, instead of relying on one near-8-KiB reply.
    for offset in range(0, count, 64):
        take = min(64, count - offset)
        piece = shell.mem_get(address + offset * 4, take, tries=8)
        if len(piece) != take or any(word is None for word in piece):
            raise RuntimeError(
                f"could not read {take} words at 0x{address + offset * 4:08X}"
            )
        words.extend(piece)
    return words


def _ensure_word(shell, address: int, value: int, *, attempts: int = 10) -> None:
    for _ in range(attempts):
        got = _read_exact_words(shell, address, 1)[0]
        if got == value:
            return
        shell.mem_set(address, value)
    got = _read_exact_words(shell, address, 1)[0]
    raise RuntimeError(
        f"0x{address:08X} is 0x{got:08X}, could not set 0x{value:08X}"
    )


def _assemble(shell) -> bytes:
    code = shell.assemble(SOURCE)
    if CODE_ADDRESS + len(code) > CODE_END:
        raise SystemExit(
            f"snapshot handler is {len(code)} bytes and exceeds "
            f"0x{CODE_ADDRESS:08X}..0x{CODE_END:08X}"
        )
    return code


def _verify_code(shell, code: bytes) -> bool:
    expected = list(struct.unpack(f"<{len(code) // 4}I", code))
    return _read_exact_words(shell, CODE_ADDRESS, len(expected)) == expected


@contextlib.contextmanager
def _exclusive_host_lock():
    lock = open(LOCK_PATH, "a+")
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(f"another AF-fusion collector holds {LOCK_PATH}") from exc
        yield
    finally:
        lock.close()


@contextlib.contextmanager
def installed_snapshot_handler(shell, code: bytes, session_nonce: int):
    """Install a verified handler and restore echo on every ordinary exit."""
    pool = _read_exact_words(shell, FRAMEBUF_POINTER, 1)[0]
    if not 0x40000000 <= pool < 0x50000000 - 0x2000 - RECORD_SIZE or pool & 3:
        raise SystemExit(f"invalid existing DMA-pool pointer: 0x{pool:08X}")
    slot = _read_exact_words(shell, ECHO_SLOT, 1)[0]
    if slot == CODE_ADDRESS:
        if not _verify_code(shell, code):
            raise SystemExit(
                "echo points at the shared code slot, but its bytes are not this "
                "collector; restore that tool before continuing"
            )
        _ensure_word(shell, ECHO_SLOT, ECHO_ORIGINAL)
    elif slot != ECHO_ORIGINAL:
        raise SystemExit(
            f"echo handler is 0x{slot:08X}, expected 0x{ECHO_ORIGINAL:08X}; "
            "another tool is using it"
        )

    shell.put(CODE_ADDRESS, code, "afsnap")
    if not _verify_code(shell, code):
        raise RuntimeError("snapshot handler failed read-back verification")
    _ensure_word(shell, RECORD_ADDRESS, 0)
    _ensure_word(shell, SESSION_NONCE_ADDRESS, session_nonce)
    _ensure_word(shell, ECHO_SLOT, CODE_ADDRESS)
    try:
        yield
    finally:
        # A failed restoration is not a warning: leaving a borrowed command
        # handler installed is a camera-safety failure and must make the run
        # non-successful.
        _ensure_word(shell, ECHO_SLOT, ECHO_ORIGINAL)


def _session_dir(base: Path) -> Path:
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S")
    return base / stamp


def _write_manifest(path: Path, manifest: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def _daemon_request(shell, request):
    """Bound host waits as well as the firmware's USB timeout."""
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(2.0)
        connection.connect(shell.SOCK)
        connection.sendall((request + "\n").encode())
        response = bytearray()
        expires = time.monotonic() + 2.0
        while True:
            remaining = expires - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("control daemon reply deadline exceeded")
            connection.settimeout(remaining)
            block = connection.recv(1024)
            if not block:
                break
            response.extend(block)
            if len(response) > 4096:
                raise RuntimeError("unexpectedly large control reply")
    return bytes(response)


def _send_key_edge(shell, command):
    """Preserve the success envelope; never retry an uncertain start."""
    if command not in ("key S1ON", "key S1OFF"):
        raise ValueError("only a half-press or its paired release is allowed")
    response = _daemon_request(shell, f"TMO 1000 SHL {command}")
    # key's success path prints nothing. Keep the OK envelope so a closed
    # connection with no response cannot be mistaken for silent success.
    if response != b"OK \n":
        raise RuntimeError(f"uncertain {command} reply: {response!r}")
    return response.decode("ascii")


def _trial_snapshot_reply(shell, timeout_ms):
    try:
        reply = _daemon_request(shell, f"TMO {timeout_ms} BULK {RECORD_SIZE} echo")
        if not reply.startswith(b"OKX "):
            return f"ERR invalid raw envelope {reply[:120]!r}"
        return bytes.fromhex(reply[4:].decode("ascii").strip()).decode("latin-1")
    except (OSError, ValueError, UnicodeError):
        return "ERR missing or malformed raw reply"


class HalfPressTrial:
    """One serial, bounded S1ON/S1OFF pair; never retry an uncertain start.

    The shell ACK is transport evidence, NOT evidence of focus completion or
    physical key state. Motion must be established from the saved telemetry.
    A disconnected camera can prevent cleanup; such failures are fatal.
    """

    def __init__(self, shell, after_s, hold_s, event_sink, *, clock=time.monotonic):
        self.shell = shell
        self.after_s = after_s
        self.hold_s = hold_s
        self.event_sink = event_sink
        self.clock = clock
        self.started = clock()
        self.pressed_at = None
        self.release_needed = False
        self.released = False
        self.logging_errors = []

    def _emit(self, event, *, cleanup=False):
        try:
            self.event_sink(event)
        except Exception as exc:
            if not cleanup:
                raise
            # A full disk or broken log must NEVER prevent S1OFF dispatch.
            self.logging_errors.append(repr(exc))

    def _command(self, command):
        event = {
            "command": command,
            "host_before_ns": time.time_ns(),
            "elapsed_s": self.clock() - self.started,
            "phase": "attempt",
        }
        # Save intent BEFORE dispatch: a lost reply cannot hide an attempted S1.
        cleanup = command == "key S1OFF"
        self._emit(dict(event), cleanup=cleanup)
        try:
            reply = _send_key_edge(self.shell, command)
        except BaseException as exc:
            event.update(phase="exception", error=repr(exc), host_after_ns=time.time_ns())
            self._emit(event, cleanup=cleanup)
            raise
        event.update(
            phase="reply", reply=reply, host_after_ns=time.time_ns(),
            transport_error=False, af_completion_confirmed=False,
        )
        self._emit(event, cleanup=cleanup)

    def step(self, records_written, latest_record, remaining_s=None):
        now = self.clock()
        if self.pressed_at is None:
            if now - self.started < self.after_s or records_written < 10:
                return
            if remaining_s is not None and remaining_s < self.hold_s + 0.5:
                return
            if not latest_record or not latest_record["integrity"]["snapshot_coherent"]:
                return
            if latest_record["exposure"]["movie_recording"]:
                raise RuntimeError("refusing an AF trial while movie recording is active")
            self.release_needed = True
            self.pressed_at = now
            self._command("key S1ON")
        elif self.release_needed and now - self.pressed_at >= self.hold_s:
            self.release()

    def release(self):
        if not self.release_needed:
            return
        self._command("key S1OFF")
        self.release_needed = False
        self.released = True


@contextlib.contextmanager
def _trial_controls(shell, args, outdir, manifest):
    if getattr(args, "half_press_after", None) is None:
        yield None
        return
    with (outdir / "events.jsonl").open("w", buffering=1) as events:
        def emit(event):
            events.write(json.dumps(event, separators=(",", ":")) + "\n")
        trial = HalfPressTrial(shell, args.half_press_after, args.half_press_hold, emit)
        try:
            yield trial
        finally:
            # Includes an exception DURING S1ON and interruption mid-press.
            try:
                trial.release()
            finally:
                manifest["half_press_attempted"] = trial.pressed_at is not None
                manifest["release_transport_completed"] = trial.released
                manifest["release_still_required"] = trial.release_needed
                manifest["control_logging_errors"] = trial.logging_errors
            if trial.logging_errors:
                raise RuntimeError("control cleanup succeeded but event logging failed")


def _collect(args: argparse.Namespace) -> int:
    if not Path(args.socket).exists():
        raise SystemExit(f"USB shell socket is absent: {args.socket}")
    shell = _load_shell(args.usb_shell, args.socket)
    code = _assemble(shell)
    session_nonce = time.time_ns() & 0xFFFFFFFF
    if session_nonce == 0:
        session_nonce = 1
    outdir = (args.output or _session_dir(DEFAULT_CAPTURE_ROOT)).resolve()
    outdir.mkdir(parents=True, exist_ok=False)
    jsonl_path = outdir / "samples.jsonl"
    binary_path = outdir / "samples.bin"
    manifest_path = outdir / "manifest.json"
    manifest = {
        "schema": SCHEMA,
        "mode": "live-original-af-trial" if args.half_press_after is not None else "live-read-only",
        "half_press_after_s": args.half_press_after,
        "half_press_hold_s": args.half_press_hold if args.half_press_after is not None else None,
        "semantic_validation": "pending",
        "started_at": dt.datetime.now().astimezone().isoformat(),
        "requested_hz": args.hz,
        "requested_duration_s": args.duration,
        "requested_samples": args.samples,
        "record_size": RECORD_SIZE,
        "handler_address": f"0x{CODE_ADDRESS:08X}",
        "handler_sha256": hashlib.sha256(code).hexdigest(),
        "handler_transport": "cpu-copy-to-worker-dma-buffer/v1",
        "source": str(SOURCE),
        "usb_shell": str(args.usb_shell.resolve()),
        "socket": args.socket,
        "session_nonce": f"0x{session_nonce:08X}",
        "records_written": 0,
        "invalid_replies": 0,
        "stale_session_replies": 0,
        "duplicate_records": 0,
        "out_of_order_records": 0,
        "camera_sequence_gaps": 0,
        "snapshot_coherent_records": 0,
        "invalid_reply_examples": [],
    }
    _write_manifest(manifest_path, manifest)

    stop = False

    def stop_after_signal(_signum, _frame):
        nonlocal stop
        stop = True

    prior_int = signal.signal(signal.SIGINT, stop_after_signal)
    prior_term = signal.signal(signal.SIGTERM, stop_after_signal)
    last_seq: int | None = None
    latest_record = None

    try:
        with _exclusive_host_lock(), installed_snapshot_handler(
            shell, code, session_nonce
        ), _trial_controls(shell, args, outdir, manifest) as trial:
            manifest["collection_started_at"] = dt.datetime.now().astimezone().isoformat()
            deadline = time.monotonic() + args.duration if args.duration is not None else None
            next_sample = time.monotonic()
            period = 1.0 / args.hz
            with jsonl_path.open("w", buffering=1) as jsonl, binary_path.open("wb") as binary:
                while not stop:
                    if args.samples is not None and manifest["records_written"] >= args.samples:
                        break
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    wait = next_sample - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                    elif -wait > period:
                        # A lost USB reply can cost several periods.  Resync
                        # once instead of issuing a burst of catch-up requests.
                        next_sample = time.monotonic()
                    next_sample += period

                    # An interrupt/deadline may have arrived during the sleep;
                    # it must not accidentally initiate a new half-press.
                    if stop or (deadline is not None and time.monotonic() >= deadline):
                        break

                    if trial is not None:
                        fresh_record = latest_record
                        if latest_record and time.time_ns() - latest_record["time"]["host_after_ns"] > 250_000_000:
                            fresh_record = None
                        trial.step(manifest["records_written"], fresh_record,
                                   deadline - time.monotonic() if deadline else None)

                    before = time.time_ns()
                    if trial is not None:
                        reply = _trial_snapshot_reply(shell, args.timeout_ms)
                    else:
                        reply = shell.sh(
                            "echo", retries=args.retries, raw=RECORD_SIZE,
                            timeout_ms=args.timeout_ms,
                        )
                    after = time.time_ns()
                    try:
                        blob = reply.encode("latin-1")
                        record = parse_record(
                            blob, host_before_ns=before, host_after_ns=after
                        )
                    except (RecordError, UnicodeEncodeError) as exc:
                        manifest["invalid_replies"] += 1
                        if len(manifest["invalid_reply_examples"]) < 8:
                            manifest["invalid_reply_examples"].append({
                                "host_after_ns": after, "error": str(exc),
                                "reply_length": len(reply), "prefix_repr": repr(reply[:120]),
                            })
                        continue

                    if record["transport"]["session_nonce"] != session_nonce:
                        manifest["stale_session_replies"] += 1
                        continue

                    seq = record["sequence"]
                    if last_seq is not None:
                        delta = (seq - last_seq) & 0xFFFFFFFF
                        if delta == 0:
                            manifest["duplicate_records"] += 1
                            continue
                        if delta >= 0x80000000:
                            manifest["out_of_order_records"] += 1
                            continue
                        if delta > 1:
                            manifest["camera_sequence_gaps"] += delta - 1
                    last_seq = seq
                    latest_record = record
                    binary.write(blob)
                    jsonl.write(json.dumps(record, separators=(",", ":")) + "\n")
                    manifest["records_written"] += 1
                    if record["integrity"]["snapshot_coherent"]:
                        manifest["snapshot_coherent_records"] += 1
    finally:
        signal.signal(signal.SIGINT, prior_int)
        signal.signal(signal.SIGTERM, prior_term)
        manifest["finished_at"] = dt.datetime.now().astimezone().isoformat()
        _write_manifest(manifest_path, manifest)

    print(outdir)
    if args.half_press_after is not None and not manifest.get("half_press_attempted"):
        return 3
    return 0 if manifest["records_written"] else 2


def _decode(args: argparse.Namespace) -> int:
    destination = open(args.jsonl, "w") if args.jsonl else contextlib.nullcontext(sys.stdout)
    try:
        with args.binary.open("rb") as source, destination as output:
            for blob in iter_binary_records(source):
                print(json.dumps(parse_record(blob), separators=(",", ":")), file=output)
    except RecordError as exc:
        raise SystemExit(f"decode failed: {exc}") from exc
    return 0


def _mock(args: argparse.Namespace) -> int:
    outdir = args.output.resolve()
    outdir.mkdir(parents=True, exist_ok=False)
    records = [build_mock_record(i) for i in range(args.samples)]
    (outdir / "samples.bin").write_bytes(b"".join(records))
    with (outdir / "samples.jsonl").open("w") as output:
        for blob in records:
            print(json.dumps(parse_record(blob), separators=(",", ":")), file=output)
    _write_manifest(
        outdir / "manifest.json",
        {"schema": SCHEMA, "mode": "mock", "records_written": len(records)},
    )
    print(outdir)
    return 0


def _inspect(args: argparse.Namespace) -> int:
    shell = _load_shell(args.usb_shell, args.socket)
    code = _assemble(shell)
    print(f"record_size={RECORD_SIZE}")
    print(f"handler_size={len(code)}")
    print(f"handler_sha256={hashlib.sha256(code).hexdigest()}")
    print("live_camera_touched=false")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--usb-shell", type=Path, default=DEFAULT_SHELL_DIR)
    common.add_argument("--socket", default=DEFAULT_SOCKET)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", parents=[common], help="assemble and inspect only")
    inspect.set_defaults(func=_inspect)

    collect = sub.add_parser("collect", parents=[common], help="collect from a live fp")
    collect.add_argument("--duration", type=float, default=10.0)
    collect.add_argument("--samples", type=int)
    collect.add_argument("--hz", type=float, default=20.0)
    collect.add_argument("--retries", type=int, default=3)
    collect.add_argument("--timeout-ms", type=int, default=200)
    collect.add_argument("--output", type=Path)
    collect.add_argument("--half-press-after", type=float,
                         help="opt in to one original S1 half-press after this many seconds")
    collect.add_argument("--half-press-hold", type=float, default=2.0)
    collect.set_defaults(func=_collect)

    decode = sub.add_parser("decode", help="decode a saved samples.bin")
    decode.add_argument("binary", type=Path)
    decode.add_argument("--jsonl")
    decode.set_defaults(func=_decode)

    mock = sub.add_parser("mock", help="write deterministic offline fixtures")
    mock.add_argument("--samples", type=int, default=3)
    mock.add_argument("--output", type=Path, required=True)
    mock.set_defaults(func=_mock)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "hz", 1) <= 0:
        raise SystemExit("--hz must be positive")
    duration = getattr(args, "duration", None)
    samples = getattr(args, "samples", None)
    if duration is not None and duration <= 0:
        raise SystemExit("--duration must be positive")
    if samples is not None and samples <= 0:
        raise SystemExit("--samples must be positive")
    if getattr(args, "half_press_after", None) is not None:
        if not 0.2 <= args.half_press_after <= 10:
            raise SystemExit("--half-press-after must be between 0.2 and 10 s")
        if not 0.1 <= args.half_press_hold <= 5:
            raise SystemExit("--half-press-hold must be between 0.1 and 5 s")
        if duration is None or duration < args.half_press_after + args.half_press_hold + 0.5:
            raise SystemExit("AF trial duration must include at least 0.5 s after release")
        if samples is not None:
            raise SystemExit("AF trial uses --duration; do not truncate it with --samples")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
