#!/usr/bin/env python3
"""Build r31: r30 snapshot pipeline plus paced, non-dropping JSON retry."""

from __future__ import annotations

import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "fpgyrosup_releases"
BASE_NAME = "fpGyroSup-test-gcsv-stream-snapshot-v18-20260831-r30"
OUT_NAME = "fpGyroSup-test-gcsv-stream-json-guard-v19-20260831-r31"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"
ASM = ROOT / "fpgyrosup_r31_json_retry.S"

sys.path.insert(0, str(ROOT / "fpsup_repo" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402


PGEN_HEADER = struct.Struct("<4sIII")

BASE_SHA = {
    "AutoRun.txt": "184933dff8418f6fcf0bbc7f02177304eb544344e4fe864290ae6ef7cdc906af",
    "VSHL.BIN": "461272dae86156334e722fa995c04c1da74d79751f902090946c9627b889974b",
    "PGEN.BIN": "a64c47ea249cade9bd45a177a891bc895ad6a3b0a968de638292174c16720b0e",
}

PGEN_MAIN = 0x38C
PGEN_STREAM = 0x1764
OLD_BODY_SIZE = 0x1D4C
JSON_RETRY_BRANCH = 0x490
JSON_RETRY_ORIGINAL = 0x3AFFFFC5       # blo 0x3ac
JSON_RETRY_CLEANUP = 0x284
PGEN_COMMON_RETURN = 0x558


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


def patch_pgen(base: bytes) -> bytes:
    assert sha256(base) == BASE_SHA["PGEN.BIN"]
    magic, main, stream, body_size = PGEN_HEADER.unpack_from(base)
    assert (magic, main, stream, body_size) == (
        b"PGEN", PGEN_MAIN, PGEN_STREAM, OLD_BODY_SIZE
    )
    assert len(base) == PGEN_HEADER.size + OLD_BODY_SIZE

    body = bytearray(base[PGEN_HEADER.size:])
    assert word(body, JSON_RETRY_BRANCH) == JSON_RETRY_ORIGINAL
    assert branch_target(JSON_RETRY_ORIGINAL, JSON_RETRY_BRANCH) == 0x3AC

    helper_image = assemble(ASM)
    sym = symbols(ASM)
    helper_offset = sym["json_retry_wait"]
    cleanup_call = sym["json_retry_cleanup_call"]
    common_return = sym["json_retry_return"]
    assert helper_offset == OLD_BODY_SIZE
    helper = bytearray(helper_image[helper_offset:])
    assert len(helper) == 0x28

    # Resolve the two calls from the appended tail into the unchanged old PGEN.
    put_word(
        helper,
        cleanup_call - helper_offset,
        make_branch(cleanup_call, JSON_RETRY_CLEANUP, link=True),
    )
    put_word(
        helper,
        common_return - helper_offset,
        make_branch(common_return, PGEN_COMMON_RETURN, link=False),
    )

    # Every failed JSON attempt now leaves the queue item pending and takes the
    # paced return.  The old twelve-attempt drop counter path is unreachable.
    put_word(
        body,
        JSON_RETRY_BRANCH,
        make_branch(JSON_RETRY_BRANCH, helper_offset, link=False),
    )
    body += helper

    assert branch_target(word(body, JSON_RETRY_BRANCH), JSON_RETRY_BRANCH) == helper_offset
    assert branch_target(word(body, cleanup_call), cleanup_call) == JSON_RETRY_CLEANUP
    assert branch_target(word(body, common_return), common_return) == PGEN_COMMON_RETURN
    assert len(body) == OLD_BODY_SIZE + 0x28

    out = bytearray(PGEN_HEADER.pack(b"PGEN", main, stream, len(body)))
    out += body
    return bytes(out)


BUILD_ID = """fpGyroSup r31 non-dropping paced JSON finalization guard
Build date: 2026-08-31
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r30 writer-private raw snapshot pipeline

Observed reason for this build:
- r30 A001_001 recorded 673 continuous DNG frames and a complete newline-
  terminated GCSV with 59,261 gyro rows and 1,185 sparse accel rows.
- The GCSV had no malformed row, no timestamp reversal and no interval over
  0.994 ms, but A001_001.json was absent after a normal stop and shutdown.
- Static inspection found that the PGEN event queue retries JSON only twelve
  times back-to-back.  On the twelfth failure it consumes the event, decrements
  the pending count and consequently releases the recording/power lock exactly
  as if JSON had succeeded.

Only functional change from r30:
- The JSON-failure edge no longer enters the twelve-attempt drop path.
- It closes the temporary lens-query session, yields for 50 ms and returns with
  the same event pending.  The next cooperative writer pass retries it.
- Only a successful JSON build sets the JSON-complete bit and allows the event
  to be consumed.  A persistent failure therefore intentionally keeps the
  recording and shutdown protection active instead of silently losing JSON.

Explicitly unchanged:
- r30 VSHL writer-private 32 KiB snapshot and early producer-slot release.
- 2,500 Hz gyro capture, sparse approximately 50 Hz accel rows, 64 KiB GCSV
  writes, 5 ms writer yield, native clip lifecycle and task priorities.
- GCSV formatter, JSON builder, JSON success path and all media APIs.
- No GYR file, sensor decimation or recording-time diagnostic write.

Safety and binary verification:
- AutoRun.txt and VSHL.BIN are byte-for-byte identical to r30.
- The old PGEN `blo 0x3ac` at body+0x490 is the sole changed old instruction.
- A 40-byte tail performs the existing lens-session cleanup, one 50 ms yield
  and branches to the existing common return.  PGEN grows from 7,516 to 7,556
  bytes and remains far below its fixed 64 KiB loader window.
- Experimental hardware build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r31：r30 GCSV 管線＋JSON 不可靜默放棄測試

本版保留 r30 已通過短片測試的 writer snapshot 與完整 GCSV。唯一變更是 JSON
失敗不再連續重試 12 次後假裝完成；每次失敗會先讓步約 50 ms，保留同一任務與
錄影／關機鎖，直到 JSON 真正成功。

測試流程：
1. 拔電池冷開機，等待 fpSup!。
2. 錄製約 20～30 秒後正常停止。
3. 等待錄影鎖解除；JSON 若只遇到短暫不可用，可能比 r30 多等不到一秒。
4. 鎖解除後正常關機，再讀卡。

主要驗收：
- DNG 編號連續，GCSV 與 JSON 都存在且可完整解析。
- GCSV 只含四欄 gyro 與約 50 Hz 的七欄 accel，不得有超過 10 ms 的缺口。
- 只有 JSON 寫入成功並關檔後才能解除錄影與關機鎖。

停止條件：
- 若停止錄影後 30 秒仍無法再次錄影或正常關機，代表 JSON 有持續性前置條件
  失敗，不是瞬間競態。請不要繼續拍下一段；記下現象後以拔電池冷重置結束測試。
- 畫面凍結、錄影自行停止或卡燈異常長亮時同樣停止。

r30 是 GCSV／snapshot 回退基準。r31 必須成套安裝，請勿以其他版本的 PGEN
替換本版 PGEN。
"""


def build() -> None:
    for name, expected in BASE_SHA.items():
        data = (BASE / name).read_bytes()
        assert sha256(data) == expected, f"unexpected r30 {name}"

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copy2(BASE / "AutoRun.txt", OUT / "AutoRun.txt")
    shutil.copy2(BASE / "VSHL.BIN", OUT / "VSHL.BIN")
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
