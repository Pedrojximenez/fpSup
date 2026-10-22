#!/usr/bin/env python3
"""Build r30: r29 sparse GCSV plus a writer-private 32 KiB raw snapshot."""

from __future__ import annotations

import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "fpgyrosup_releases"
BASE_NAME = "fpGyroSup-test-gcsv-stream-sparse-accel-v17-20260831-r29"
OUT_NAME = "fpGyroSup-test-gcsv-stream-snapshot-v18-20260831-r30"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"
ASM = ROOT / "fpgyrosup_r30_writer_snapshot.S"

sys.path.insert(0, str(ROOT / "fpsup_repo" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402


VBIN_HEADER = struct.Struct("<4sIII")
SECTION = struct.Struct("<II")

BASE_SHA = {
    "AutoRun.txt": "184933dff8418f6fcf0bbc7f02177304eb544344e4fe864290ae6ef7cdc906af",
    "VSHL.BIN": "009ab6970c1f141d972e5fc61e4e77bb48ded36d819c4aeb8498b7aed59290d5",
    "PGEN.BIN": "a64c47ea249cade9bd45a177a891bc895ad6a3b0a968de638292174c16720b0e",
}

LOGGER_DEST = 0xC072E064
OLD_LOGGER_SIZE = 0xE24
PGEN_TRAMPOLINE = 0xE10
WRITER_CALL = 0x9B4
OLD_CLEAR = 0xA00
OLD_RETURN = 0xA18
CONSERVATIVE_END = 0xC072EF00
PARK_DEST = 0xC072EFB4
NOP = 0xE1A00000


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
    return (condition << 28) | (0x0B000000 if link else 0x0A000000) | (immediate & 0xFFFFFF)


def branch_target(value: int, address: int) -> int:
    assert ((value >> 25) & 0b111) == 0b101
    immediate = value & 0xFFFFFF
    if immediate & 0x800000:
        immediate -= 0x1000000
    return address + 8 + immediate * 4


def split_vbin(blob: bytes) -> tuple[int, list[tuple[int, bytes]]]:
    magic, count, entry, body_len = VBIN_HEADER.unpack_from(blob)
    assert magic == b"VBIN" and count == 4 and len(blob) == 8192
    table_end = VBIN_HEADER.size + count * SECTION.size
    cursor = table_end
    sections = []
    for index in range(count):
        destination, size = SECTION.unpack_from(blob, VBIN_HEADER.size + index * SECTION.size)
        sections.append((destination, blob[cursor:cursor + size]))
        cursor += (size + 3) & ~3
    assert cursor - table_end == body_len
    assert not any(blob[cursor:])
    return entry, sections


def join_vbin(entry: int, sections: list[tuple[int, bytes]]) -> bytes:
    table = bytearray()
    body = bytearray()
    for destination, payload in sections:
        table += SECTION.pack(destination, len(payload))
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
    assert [(hex(a), len(b)) for a, b in sections] == [
        (hex(LOGGER_DEST), OLD_LOGGER_SIZE),
        (hex(PARK_DEST), 0x4C),
        (hex(0xC03660E8), 4),
        (hex(0xC00D0794), 4),
    ]

    logger = bytearray(sections[0][1])
    helper_image = assemble(ASM)
    helper_offset = symbols(ASM)["writer_snapshot"]
    assert helper_offset == OLD_LOGGER_SIZE
    helper = helper_image[helper_offset:]
    assert len(helper) == 0x50

    # Replace the original direct command-2 sequence with one helper call.
    assert word(logger, WRITER_CALL) == 0xE3A00002       # mov r0,#2
    assert word(logger, WRITER_CALL + 4) == 0xE1A01004   # mov r1,r4
    assert branch_target(word(logger, WRITER_CALL + 8), WRITER_CALL + 8) == PGEN_TRAMPOLINE
    put_word(logger, WRITER_CALL, make_branch(WRITER_CALL, helper_offset, link=True))
    put_word(logger, WRITER_CALL + 4, NOP)
    put_word(logger, WRITER_CALL + 8, NOP)

    # The helper has already cleared and released the producer slot.  Never run
    # r17's post-format clear against a slot the callback may now be filling.
    assert word(logger, OLD_CLEAR) == 0xE3A00000
    put_word(logger, OLD_CLEAR, make_branch(OLD_CLEAR, OLD_RETURN, link=False))
    logger += helper

    assert branch_target(word(logger, WRITER_CALL), WRITER_CALL) == helper_offset
    assert branch_target(word(logger, OLD_CLEAR), OLD_CLEAR) == OLD_RETURN
    new_end = LOGGER_DEST + len(logger)
    assert len(logger) == 0xE74
    assert new_end == 0xC072EED8
    assert new_end <= CONSERVATIVE_END
    assert new_end < PARK_DEST

    sections[0] = (LOGGER_DEST, bytes(logger))
    out = join_vbin(entry, sections)
    _, check = split_vbin(out)
    assert check[0][1] == bytes(logger)
    assert check[1:] == sections[1:]
    return out


BUILD_ID = """fpGyroSup r30 writer-private raw snapshot back-pressure test
Build date: 2026-08-31
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r29 sparse native-rate accelerometer GCSV

Observed reason for this build:
- r29 A001_008 recorded 18,958 continuous DNG frames over 632.566 seconds and
  wrote complete 35.97 MB GCSV plus JSON.
- It retained 1,584,098 gyro rows and 31,669 native-rate accel rows, but one
  real 40.545 ms gyro gap occurred at 329.936 seconds.
- The gap was the 217th of 416 raw-block boundaries and is the only interval
  over 1.08 ms.  It matches the r17 producer's drop_batch path when one raw
  half is READY and the writer still owns the other half across card latency.

Only pipeline change from r29:
- The producer remains the exact r17/r29 two-slot A/B logger.
- When the writer claims READY, it builds the existing header and copies the
  complete fixed 32 KiB raw slot to a writer-private snapshot at state+0x38000.
- It then clears and publishes the source slot EMPTY before calling the exact
  r29 formatter/media path on the private snapshot.
- The RAM copy is eight words per iteration, 1,024 bounded iterations once per
  roughly 1.52-second raw block.  It performs no formatting or media call.
- While the writer is blocked in F_WRITE, both producer slots can now absorb
  about 3.0 seconds of gyro instead of only one slot's roughly 1.5 seconds.

Explicitly unchanged:
- 2,500 Hz gyro callback, ring draining, A/B ownership and sequence ordering.
- Sparse approximately 50 Hz accelerometer rows and all r29 GCSV bytes.
- 64 KiB complete-line F_WRITE calls and the 5 ms cooperative yield.
- Native lifecycle, recording/power locks, JSON generation and task priority.
- No GYR file, third producer slot, formatter staging or sensor decimation.

Safety and layout verification:
- AutoRun.txt and PGEN.BIN are byte-for-byte identical to r29.
- The original writer call is redirected to an appended 80-byte helper; the
  old post-format slot clear is bypassed so it cannot corrupt a reused slot.
- The private snapshot occupies the previously verified free
  state+0x38000..+0x40000 window and does not overlap A, B, text or read areas.
- Resident logger grows from 3,620 to 3,700 bytes and ends at 0xC072EED8,
  40 bytes below the conservative 0xC072EF00 boundary.
- Experimental hardware build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r30：r29 稀疏 accel＋writer 私有 raw 快照測試

這版保留 r29 的 GCSV、A/B callback 與寫卡節奏。唯一變更是 writer 先把 READY
的 32 KiB raw 區塊複製到私有 RAM，立刻釋放來源槽，再從副本格式化與寫卡。
目的為消除 r29 十分半長測中唯一一次 40.545 ms back-pressure 缺口。

測試流程：
1. 冷開機等待 fpSup!。
2. 先錄 20～30 秒，確認可正常停止並生成 GCSV/JSON。
3. 再錄約 60 秒，確認沒有凍結、自動停止或超過 10 ms 的 gyro 缺口。
4. 前兩段正常後，錄至少 10～12 分鐘；可在錄影期間正常晃動相機。
5. 正常停止並等待鎖解除，最後正常關機後再讀卡。

立即停止條件：
- 錄影自行中止、畫面凍結或卡燈異常長亮。
- 停止後超過約 15 秒仍不能再次錄影或正常關機。

主要驗收：
- DNG 編號連續，GCSV/JSON 完整，本版不建立 GYR。
- GCSV 只含四欄 gyro 與約 50 Hz 的七欄 accel，沒有空欄或假零。
- 短片與一分鐘片不得出現超過 10 ms 的 gyro 缺口。
- 長測應消除 r29 的偶發 40 ms 級丟批；普通 raw 區塊交界仍可能出現約
  0.4～1.1 ms 的正常重新校時。
- GCSV/JSON 完成前，錄影與關機鎖必須繼續有效。

r29 是回退基準。請勿混裝 r29 與 r30 的 VSHL.BIN。
"""


def build() -> None:
    for name, expected in BASE_SHA.items():
        data = (BASE / name).read_bytes()
        assert sha256(data) == expected, f"unexpected r29 {name}"

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copy2(BASE / "AutoRun.txt", OUT / "AutoRun.txt")
    shutil.copy2(BASE / "PGEN.BIN", OUT / "PGEN.BIN")
    (OUT / "VSHL.BIN").write_bytes(patch_vshl((BASE / "VSHL.BIN").read_bytes()))
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
        for name in ("VSHL.BIN", "AutoRun.txt", "PGEN.BIN", "BUILD-ID.txt", "TESTING-README.txt", "SHA256SUMS.txt"):
            archive.write(OUT / name, f"{OUT_NAME}/{name}")

    print(f"built {OUT}")
    print(f"built {ZIP_PATH}")
    print((OUT / "SHA256SUMS.txt").read_text(encoding="ascii"), end="")


if __name__ == "__main__":
    build()
