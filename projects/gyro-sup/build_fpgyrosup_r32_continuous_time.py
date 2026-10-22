#!/usr/bin/env python3
"""Build r32: exact r29 plus honest cross-block timestamp continuity."""

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
OUT_NAME = "fpGyroSup-test-gcsv-continuous-time-v20-20260831-r32"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"
ASM = ROOT / "fpgyrosup_r32_continuous_time.S"

sys.path.insert(0, str(ROOT / "fpsup_repo" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402


PGEN_HEADER = struct.Struct("<4sIII")

BASE_SHA = {
    "AutoRun.txt": "184933dff8418f6fcf0bbc7f02177304eb544344e4fe864290ae6ef7cdc906af",
    "VSHL.BIN": "009ab6970c1f141d972e5fc61e4e77bb48ded36d819c4aeb8498b7aed59290d5",
    "PGEN.BIN": "a64c47ea249cade9bd45a177a891bc895ad6a3b0a968de638292174c16720b0e",
}

PGEN_MAIN = 0x38C
PGEN_STREAM = 0x1764
OLD_BODY_SIZE = 0x1D4C
OPEN_INIT_CALL = 0x1888
BLOCK_ANCHOR_CALL = 0x18D0
BLOCK_ANCHOR_NOP_1 = 0x18D4
BLOCK_ANCHOR_NOP_2 = 0x18D8
STORE_NEXT_CALL = 0x1B70

ORIGINAL = {
    OPEN_INIT_CALL: 0xE3A00001,       # mov r0,#1
    BLOCK_ANCHOR_CALL: 0xE5949008,    # ldr sb,[r4,#8]
    BLOCK_ANCHOR_NOP_1: 0xE59AB088,   # ldr fp,[sl,#0x88]
    BLOCK_ANCHOR_NOP_2: 0xE049900B,   # sub sb,sb,fp
    STORE_NEXT_CALL: 0xE0451006,      # sub r1,r5,r6
}
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


def choose_block_timestamp(
    corrected_next: int, raw_next: int, raw_anchor: int
) -> tuple[int, int]:
    """Reference model returning (chosen output start, raw-output bias)."""
    if corrected_next == 0:
        return raw_anchor, 0
    local_gap = max(0, raw_anchor - raw_next)
    chosen = corrected_next + (local_gap if local_gap > 1000 else 0)
    return chosen, raw_anchor - chosen


def patch_pgen(base: bytes) -> bytes:
    assert sha256(base) == BASE_SHA["PGEN.BIN"]
    magic, main, stream, body_size = PGEN_HEADER.unpack_from(base)
    assert (magic, main, stream, body_size) == (
        b"PGEN", PGEN_MAIN, PGEN_STREAM, OLD_BODY_SIZE
    )
    assert len(base) == PGEN_HEADER.size + OLD_BODY_SIZE

    body = bytearray(base[PGEN_HEADER.size:])
    for offset, expected in ORIGINAL.items():
        assert word(body, offset) == expected, f"unexpected PGEN word at {offset:#x}"

    helper_image = assemble(ASM)
    sym = symbols(ASM)
    helper_offset = sym["timestamp_continuity_init"]
    choose_offset = sym["timestamp_choose_block_start"]
    store_offset = sym["timestamp_store_next"]
    assert helper_offset == OLD_BODY_SIZE
    helper = helper_image[helper_offset:]
    assert len(helper) == 0x88

    put_word(body, OPEN_INIT_CALL, make_branch(OPEN_INIT_CALL, helper_offset, link=True))
    put_word(body, BLOCK_ANCHOR_CALL, make_branch(BLOCK_ANCHOR_CALL, choose_offset, link=True))
    put_word(body, BLOCK_ANCHOR_NOP_1, NOP)
    put_word(body, BLOCK_ANCHOR_NOP_2, NOP)
    put_word(body, STORE_NEXT_CALL, make_branch(STORE_NEXT_CALL, store_offset, link=True))
    body += helper

    assert branch_target(word(body, OPEN_INIT_CALL), OPEN_INIT_CALL) == helper_offset
    assert branch_target(word(body, BLOCK_ANCHOR_CALL), BLOCK_ANCHOR_CALL) == choose_offset
    assert branch_target(word(body, STORE_NEXT_CALL), STORE_NEXT_CALL) == store_offset
    assert len(body) == OLD_BODY_SIZE + 0x88

    # Boundary policy: normal seams collapse independently without accumulating.
    corrected, bias = choose_block_timestamp(0, 0, 409)
    assert (corrected, bias) == (409, 0)
    corrected_next = corrected + 3836 * 400
    raw_next = corrected_next + bias
    for seam in (535, 357, 490, 304, 524, 335, 401, 299, 520, 388, 312, 444):
        corrected, bias = choose_block_timestamp(corrected_next, raw_next, raw_next + seam)
        assert corrected == corrected_next
        corrected_next = corrected + 3836 * 400
        raw_next = corrected_next + bias
    # A real 40.545-ms adjacent-row interval is 40.145 ms beyond expected +400.
    corrected, bias = choose_block_timestamp(corrected_next, raw_next, raw_next + 40_145)
    assert corrected == corrected_next + 40_145
    # A backward raw anchor remains monotonic rather than fabricating a gap.
    corrected, _ = choose_block_timestamp(corrected_next, raw_next, raw_next - 100)
    assert corrected == corrected_next

    out = bytearray(PGEN_HEADER.pack(b"PGEN", main, stream, len(body)))
    out += body
    return bytes(out)


BUILD_ID = """fpGyroSup r32 r29-base honest cross-block timestamp continuity
Build date: 2026-08-31
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r29 sparse native-rate accelerometer GCSV

Observed reason for this build:
- Five r31 short clips retained every DNG frame and had no gyro interval over
  0.935 ms, but their nominal 400-us completeness was only 99.975979% to
  99.982341%.
- Inside every raw block all intervals were exactly 400 us.  Every excess was
  concentrated at a raw-block boundary: 3 to 17 forward-only seams per clip,
  totalling 1,179 to 5,354 us.
- r31 also produced no JSON in five of five clips.  This build therefore does
  not inherit r30/r31 writer snapshot or JSON experiments.

Only functional change from r29:
- Stream open clears three previously unused timestamp words at
  state+0x1D8..state+0x1E0.
- The first raw block keeps its original hardware-relative anchor.
- Later blocks compare their raw anchor with a separately retained uncorrected
  raw-anchor timeline.  This measures each seam locally, so removed jitter can
  never accumulate into a false large gap.
- A local forward discrepancy of at most 1,000 us is treated as ordinary slot
  hand-off jitter and the corrected previous-row+400-us timestamp is used.
- A local forward discrepancy over 1,000 us is added to the corrected output
  timeline.  Thus the known r29 40.545-ms back-pressure loss remains visible
  and is not relabelled as complete data.
- At the end of each block both corrected-next and raw-anchor-next are saved.

Explicitly unchanged from r29:
- r29 VSHL two-slot writer ownership, including keeping WRITING until the PGEN
  formatter/media call returns.
- Native lifecycle, JSON generation, event queue, recording/power locks and
  task priorities.  This restores the last configuration proven to emit JSON.
- 2,500 Hz callback, sparse approximately 50 Hz accel rows, 64 KiB complete-line
  writes, 5 ms yield, decimal formatters and GCSV header tscale.
- No writer-private snapshot, third slot, GYR file or sensor decimation.

Safety and binary verification:
- AutoRun.txt and VSHL.BIN are byte-for-byte identical to r29.
- Five checked old PGEN instructions become three helper calls plus two NOPs;
  all other old PGEN bytes are unchanged except the body-length header.
- The appended helper is 136 bytes.  PGEN grows from 7,516 to 7,652 bytes and
  remains far below the fixed 64 KiB loader window.
- Experimental hardware build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r32：回到 r29，只修 GCSV raw-block 接縫時間軸

本版完全撤回 r30/r31 的 writer snapshot 與 JSON 修改，恢復最後確認能生成 JSON
的 r29 lifecycle。唯一實驗是：正常 raw block 接縫不再重新向前跳時間；真正超過
1 ms 的資料缺口仍照實保留。

測試流程：
1. 拔電池冷開機，等待 fpSup!。
2. 先錄 20～30 秒，正常停止並等待鎖解除。
3. 再錄約 60 秒；兩段都正常後才進行 10 分鐘以上長測。
4. 正常關機後讀卡。

主要驗收：
- 每段都必須同時存在完整 GCSV 與 JSON；本版不建立 GYR。
- 沒有實際丟批的短片，所有相鄰 gyro timestamp 應精確相差 400 us，
  以相同 nominal 指標計算應為 100%。
- 若長測再次遇到 r29 類型的 40 ms back-pressure，缺口必須保留，不能被時間軸
  修正掩蓋；該問題留待下一個獨立版本處理。
- accel 仍只在新樣本到來時寫七欄列，平均約 50 Hz，不能出現假零。

停止條件：
- 缺 JSON、錄影自行停止、停止後鎖不解除或畫面凍結。
- 短片若仍有小於等於 1 ms 的 block 接縫，也先停止，不進行長測。

r29 是直接回退基準。r32 必須成套安裝，請勿混用其他版本的 PGEN。
"""


def build() -> None:
    for name, expected in BASE_SHA.items():
        data = (BASE / name).read_bytes()
        assert sha256(data) == expected, f"unexpected r29 {name}"

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
