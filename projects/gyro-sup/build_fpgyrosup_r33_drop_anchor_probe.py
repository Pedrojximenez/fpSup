#!/usr/bin/env python3
"""Build r33: exact r32 plus ground-truth drop/anchor diagnostics."""

from __future__ import annotations

import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "fpgyrosup_releases"
BASE_NAME = "fpGyroSup-test-gcsv-continuous-time-v20-20260831-r32"
OUT_NAME = "fpGyroSup-test-gcsv-drop-anchor-probe-v21-20260901-r33"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"
VSHL_ASM = ROOT / "fpgyrosup_r33_vshl_probe.S"
PGEN_ASM = ROOT / "fpgyrosup_r33_pgen_probe.S"

sys.path.insert(0, str(ROOT / "fpsup_repo" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402


BASE_SHA = {
    "AutoRun.txt": "184933dff8418f6fcf0bbc7f02177304eb544344e4fe864290ae6ef7cdc906af",
    "VSHL.BIN": "009ab6970c1f141d972e5fc61e4e77bb48ded36d819c4aeb8498b7aed59290d5",
    "PGEN.BIN": "7bdb6d4b22d03d55e100e3dbf039280f88c3f2c06171eda5cb030ee64122623b",
}

VBIN_HEADER = struct.Struct("<4sIII")
VBIN_SECTION = struct.Struct("<II")
PGEN_HEADER = struct.Struct("<4sIII")

LOGGER_DEST = 0xC072E064
OLD_LOGGER_SIZE = 0xE24
CONSERVATIVE_LOGGER_END = 0xC072EF00
PARK_DEST = 0xC072EFB4

VSHL_RESET = 0x19C
VSHL_BEFORE_HEAD = 0x320
VSHL_AFTER_HEAD = 0x33C
VSHL_BLOCK_START = 0x3EC
VSHL_ORIGINAL = {
    VSHL_RESET: 0xE58A0014,       # str r0,[sl,#0x14]
    VSHL_BEFORE_HEAD: 0xE5985000, # ldr r5,[r8]
    VSHL_AFTER_HEAD: 0xE1A09000,  # mov sb,r0
    VSHL_BLOCK_START: 0xE1A021A3, # lsr r2,r3,#3
}

PGEN_MAIN = 0x38C
PGEN_STREAM = 0x1764
OLD_PGEN_SIZE = 0x1DD4
PGEN_FINAL_FLUSH = 0x1BA8
PGEN_FINAL_FLUSH_ORIGINAL = 0xEB000015  # bl 0x1C04
PGEN_COPY_STRING = 0x173C
PGEN_PUT_UINT = 0x14C8
PGEN_FLUSH = 0x1C04


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def word(blob: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def put_word(blob: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", blob, offset, value)


def make_branch(address: int, target: int, *, link: bool, condition: int = 0xE) -> int:
    delta = target - (address + 8)
    assert delta % 4 == 0
    immediate = delta // 4
    assert -(1 << 23) <= immediate < (1 << 23)
    return ((condition << 28) | (0x0B000000 if link else 0x0A000000)
            | (immediate & 0xFFFFFF))


def branch_target(value: int, address: int) -> int:
    assert ((value >> 25) & 0b111) == 0b101
    immediate = value & 0xFFFFFF
    if immediate & 0x800000:
        immediate -= 0x1000000
    return address + 8 + immediate * 4


def split_vbin(blob: bytes) -> tuple[int, list[tuple[int, bytes]]]:
    magic, count, entry, body_len = VBIN_HEADER.unpack_from(blob)
    assert magic == b"VBIN" and count == 4 and len(blob) == 8192
    table_end = VBIN_HEADER.size + count * VBIN_SECTION.size
    cursor = table_end
    sections = []
    for index in range(count):
        destination, size = VBIN_SECTION.unpack_from(
            blob, VBIN_HEADER.size + index * VBIN_SECTION.size
        )
        sections.append((destination, blob[cursor:cursor + size]))
        cursor += (size + 3) & ~3
    assert cursor - table_end == body_len
    assert not any(blob[cursor:])
    return entry, sections


def join_vbin(entry: int, sections: list[tuple[int, bytes]]) -> bytes:
    table = bytearray()
    body = bytearray()
    for destination, payload in sections:
        table += VBIN_SECTION.pack(destination, len(payload))
        body += payload
        body += b"\0" * (-len(payload) % 4)
    result = bytearray(VBIN_HEADER.pack(b"VBIN", len(sections), entry, len(body)))
    result += table
    result += body
    assert len(result) <= 8192
    result += b"\0" * (8192 - len(result))
    return bytes(result)


def patch_vshl(base: bytes) -> bytes:
    assert sha256(base) == BASE_SHA["VSHL.BIN"]
    entry, sections = split_vbin(base)
    assert entry == 0
    assert [(address, len(payload)) for address, payload in sections] == [
        (LOGGER_DEST, OLD_LOGGER_SIZE),
        (PARK_DEST, 0x4C),
        (0xC03660E8, 4),
        (0xC00D0794, 4),
    ]

    logger = bytearray(sections[0][1])
    for offset, expected in VSHL_ORIGINAL.items():
        assert word(logger, offset) == expected, f"unexpected VSHL word at {offset:#x}"

    helper_image = assemble(VSHL_ASM)
    sym = symbols(VSHL_ASM)
    helper_offset = sym["probe_reset"]
    assert helper_offset == OLD_LOGGER_SIZE
    helper = helper_image[helper_offset:]
    assert len(helper) == 0x60

    patches = {
        VSHL_RESET: sym["probe_reset"],
        VSHL_BEFORE_HEAD: sym["probe_before_head"],
        VSHL_AFTER_HEAD: sym["probe_after_head_tick"],
        VSHL_BLOCK_START: sym["probe_block_start"],
    }
    for offset, target in patches.items():
        put_word(logger, offset, make_branch(offset, target, link=True))
    logger += helper

    for offset, target in patches.items():
        assert branch_target(word(logger, offset), offset) == target
    assert len(logger) == OLD_LOGGER_SIZE + 0x60
    assert LOGGER_DEST + len(logger) == 0xC072EEE8
    assert LOGGER_DEST + len(logger) <= CONSERVATIVE_LOGGER_END
    assert LOGGER_DEST + len(logger) < PARK_DEST

    sections[0] = (LOGGER_DEST, bytes(logger))
    out = join_vbin(entry, sections)
    _, check = split_vbin(out)
    assert check[0] == sections[0]
    assert check[1:] == sections[1:]
    return out


def patch_pgen(base: bytes) -> bytes:
    assert sha256(base) == BASE_SHA["PGEN.BIN"]
    magic, main, stream, body_size = PGEN_HEADER.unpack_from(base)
    assert (magic, main, stream, body_size) == (
        b"PGEN", PGEN_MAIN, PGEN_STREAM, OLD_PGEN_SIZE
    )
    assert len(base) == PGEN_HEADER.size + OLD_PGEN_SIZE

    body = bytearray(base[PGEN_HEADER.size:])
    assert word(body, PGEN_FINAL_FLUSH) == PGEN_FINAL_FLUSH_ORIGINAL
    assert branch_target(PGEN_FINAL_FLUSH_ORIGINAL, PGEN_FINAL_FLUSH) == PGEN_FLUSH

    helper_image = assemble(PGEN_ASM)
    sym = symbols(PGEN_ASM)
    helper_offset = sym["diagnostic_append_and_flush"]
    assert helper_offset == OLD_PGEN_SIZE
    helper = bytearray(helper_image[helper_offset:])
    assert len(helper) == 0x84

    helper_calls = {
        "diagnostic_copy_prefix": PGEN_COPY_STRING,
        "diagnostic_format_drop": PGEN_PUT_UINT,
        "diagnostic_copy_middle": PGEN_COPY_STRING,
        "diagnostic_format_delay": PGEN_PUT_UINT,
        "diagnostic_final_flush": PGEN_FLUSH,
    }
    for name, target in helper_calls.items():
        address = sym[name]
        put_word(helper, address - helper_offset, make_branch(address, target, link=True))

    put_word(
        body,
        PGEN_FINAL_FLUSH,
        make_branch(PGEN_FINAL_FLUSH, helper_offset, link=True),
    )
    body += helper

    assert branch_target(word(body, PGEN_FINAL_FLUSH), PGEN_FINAL_FLUSH) == helper_offset
    for name, target in helper_calls.items():
        address = sym[name]
        assert branch_target(word(body, address), address) == target
    assert len(body) == OLD_PGEN_SIZE + 0x84

    # The diagnostic extension is exactly one flexible-CSV field.  Current
    # Gyroflow telemetry-parser skips all one-field rows before numeric parsing.
    trailer = "#FPD1;drop_samples=217;max_block_head_tick_us=83035\n"
    assert "," not in trailer and trailer.count("\n") == 1
    assert len(trailer) < 128

    out = bytearray(PGEN_HEADER.pack(b"PGEN", main, stream, len(body)))
    out += body
    return bytes(out)


BUILD_ID = """fpGyroSup r33 r32-base drop/anchor ground-truth probe
Build date: 2026-09-01
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r32 honest cross-block timestamp continuity

Reason for this build:
- r32 A001_006 retained 1,355,667 gyro rows and 16,219 continuous DNG frames.
- All but two GCSV intervals were exactly 400 us.  The two block-start
  intervals were 4,093 us and 83,435 us.
- Those intervals can mean real producer drop_batch loss, but the existing
  logger snapshots the hardware ring head before it reads TickTimer.  A task
  preemption in that narrow window creates the same forward raw-anchor jump
  without losing samples.
- r32's 1,000-us policy cannot distinguish these causes, and the existing
  S_DROPPED counter was never persisted.

Only diagnostic changes from r32:
- At every non-empty gyro hook, one extra TickTimer read occurs immediately
  before the original ring-head load.  The original post-head TickTimer result
  remains the unmodified batch-end timestamp.
- Only callbacks that start a new raw block contribute to
  max_block_head_tick_us, because only those callbacks supply GCSV anchors.
- The original S_DROPPED sample counter remains unchanged.
- Take start clears the new last/max words at state+0x1E4/+0x1E8 together with
  S_DROPPED.
- Before command 3 performs its already-existing final GCSV flush, it appends:
    #FPD1;drop_samples=N;max_block_head_tick_us=N
  The trailer contains no comma and is therefore one flexible-CSV field.

Explicitly unchanged:
- r32 two-slot writer ownership, 32 KiB raw slots, 64 KiB complete-line writes,
  5 ms yield, sparse native-rate accel, timestamp policy and 2,500 Hz sensor.
- No additional file, F_OPEN, F_WRITE, flush, close or recording-time media call.
  The trailer rides in the existing final GCSV flush.
- Native lifecycle, JSON builder/queue, recording and shutdown locks.
- All old PGEN JSON bytes and all old VSHL writer/media instructions.

Interpretation:
- drop_samples > 0 proves the producer executed drop_batch; the number is the
  exact raw gyro sample count advanced without copying.
- drop_samples=0 excludes this producer drop_batch path, but not an upstream
  sensor pause or hardware-ring overwrite.
- An unusually large max_block_head_tick_us near a displayed GCSV local gap
  strongly supports head-to-TickTimer scheduling delay.  It is a take-wide
  maximum, so it does not by itself pair the measurement to a specific seam.
- Both nonzero means the take may contain both mechanisms; compare the exact
  GCSV seams with the two counters before changing buffering.

Safety and binary verification:
- AutoRun.txt is byte-for-byte identical to r32.
- Four checked VSHL instructions become bounded helper calls.  The 96-byte tail
  ends at 0xC072EEE8, 24 bytes below the conservative 0xC072EF00 boundary and
  204 bytes below the resident parking stub.
- One checked PGEN final-flush call is redirected through a 132-byte append
  helper which calls that same flush exactly once.  JSON code is unchanged.
- Experimental hardware diagnostic build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r33：分辨真實 drop_batch 與 timestamp anchor 假跳

本版沿用 r32 的錄影、GCSV、JSON、鎖定與寫卡流程，只在 GCSV 最後增加一行
不含逗號的診斷資料：

  #FPD1;drop_samples=N;max_block_head_tick_us=N

Gyroflow 現行 parser 會忽略單欄列，不會把它當成 gyro 或 accel 資料。

測試流程：
1. 拔電池冷開機，等待 fpSup!。
2. 先錄 20～30 秒，正常停止並等待鎖解除。
3. 確認可再次錄影後，錄約 5～10 分鐘，正常停止。
4. 正常關機後讀卡。

驗收與判讀：
- 每段必須都有 DNG、GCSV 與 JSON；GCSV 最後一行必須是 #FPD1 trailer。
- drop_samples=0 且 GCSV 有大接縫：可排除 producer 的 drop_batch；若
  max_block_head_tick_us 也異常大，便強烈支持 head→TickTimer 被延遲。
  這仍不能排除更上游的 sensor pause 或 hardware-ring overwrite。
- drop_samples>0：已直接證明 drop_batch；再依數值判斷缺多少筆。
- 短片先驗證 JSON 與鎖定均正常，才做長測。

停止條件：
- 缺 JSON、缺診斷 trailer、錄影自行停止、凍結或停止後鎖不解除。
- r33 是診斷版，不以其 trailer 作正式發布格式。
"""


def build() -> None:
    for name, expected in BASE_SHA.items():
        data = (BASE / name).read_bytes()
        assert sha256(data) == expected, f"unexpected r32 {name}"

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copy2(BASE / "AutoRun.txt", OUT / "AutoRun.txt")
    (OUT / "VSHL.BIN").write_bytes(patch_vshl((BASE / "VSHL.BIN").read_bytes()))
    (OUT / "PGEN.BIN").write_bytes(patch_pgen((BASE / "PGEN.BIN").read_bytes()))
    (OUT / "BUILD-ID.txt").write_text(BUILD_ID, encoding="utf-8")
    (OUT / "TESTING-README.txt").write_text(TESTING, encoding="utf-8")

    sums = []
    for name in ("AutoRun.txt", "VSHL.BIN", "PGEN.BIN"):
        sums.append(f"{sha256((OUT / name).read_bytes())}  {name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(f"{OUT_NAME}/", b"")
        for name in (
            "VSHL.BIN", "AutoRun.txt", "PGEN.BIN", "BUILD-ID.txt",
            "TESTING-README.txt", "SHA256SUMS.txt",
        ):
            archive.write(OUT / name, f"{OUT_NAME}/{name}")

    print(f"built {OUT}")
    print(f"built {ZIP_PATH}")
    print((OUT / "SHA256SUMS.txt").read_text(encoding="ascii"), end="")


if __name__ == "__main__":
    build()
