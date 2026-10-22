#!/usr/bin/env python3
"""Build the r29 sparse-accelerometer test release from the verified r17 image.

The r17 formatter keeps an accelerometer-text cache and marks it dirty whenever
it consumes a new timestamped accelerometer record.  r29 reuses that proven
path, but appends the cached ax/ay/az fields only while the dirty flag is set.
Rows without a new accelerometer sample end after gz, which Gyroflow's flexible
GCSV reader treats as a gyro-only row.

This is deliberately a checked binary transformation.  r17 was the best
hardware-tested buffering baseline, while its one-off generated assembly source
is not part of the repository.  Every original instruction being changed is
asserted below, and the new branches are decoded again before packaging.
"""

from __future__ import annotations

import hashlib
import shutil
import struct
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "fpgyrosup_releases"
BASE_NAME = "fpGyroSup-test-gcsv-stream-buffered-v5-20260831-r17"
OUT_NAME = "fpGyroSup-test-gcsv-stream-sparse-accel-v17-20260831-r29"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"

BASE_PGEN_SHA256 = "d5da3e0c958acbb492e03108624a8b7820367b5729f32aae667c2963a47a9332"
PGEN_HEADER = struct.Struct("<4sIII")

# Offsets from r17's gcsv_build entry.
OLD_COMMA_MOV = 0x29C
OLD_COMMA_STORE = 0x2A0
NO_NEW_ACCEL_BRANCH = 0x304
NEW_ACCEL_CALL = 0x308
ACCEL_TEXT_BUILDER = 0x3A4
NEWLINE = 0x328

NOP = 0xE1A00000
MOV_R0_COMMA = 0xE3A0002C
STRB_R0_R5_POSTINC = 0xE4C50001


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def arm_branch(word: int, address: int) -> int:
    """Decode an ARM-state B/BL destination."""
    assert ((word >> 25) & 0b111) == 0b101
    displacement = word & 0x00FFFFFF
    if displacement & 0x00800000:
        displacement -= 0x01000000
    return address + 8 + displacement * 4


def make_branch(address: int, target: int, *, link: bool, condition: int = 0xE) -> int:
    delta = target - (address + 8)
    assert delta % 4 == 0
    immediate = delta // 4
    assert -(1 << 23) <= immediate < (1 << 23)
    opcode = 0x0B000000 if link else 0x0A000000
    return (condition << 28) | opcode | (immediate & 0x00FFFFFF)


def read_word(blob: bytearray, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def write_word(blob: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", blob, offset, value)


def patch_pgen(base_blob: bytes) -> bytes:
    assert sha256(base_blob) == BASE_PGEN_SHA256, "r17 PGEN is not the verified base"
    magic, post_entry, gcsv_entry, code_len = PGEN_HEADER.unpack_from(base_blob)
    assert magic == b"PGEN"
    assert post_entry == 0x38C
    assert gcsv_entry == 0x1764
    assert code_len == len(base_blob) - PGEN_HEADER.size == 0x1D40

    code = bytearray(base_blob[PGEN_HEADER.size:])
    assert len(code) - gcsv_entry == 0x5DC

    # r17 always emitted a comma after gz.  Suppress it here; the small stub
    # below emits the comma only when a new accelerometer record was consumed.
    assert read_word(code, gcsv_entry + OLD_COMMA_MOV) == MOV_R0_COMMA
    assert read_word(code, gcsv_entry + OLD_COMMA_STORE) == STRB_R0_R5_POSTINC
    write_word(code, gcsv_entry + OLD_COMMA_MOV, NOP)
    write_word(code, gcsv_entry + OLD_COMMA_STORE, NOP)

    # Dirty == 0 skips both the accel fragment and its comma, landing directly
    # on the existing newline.  Dirty != 0 calls the appended comma stub, which
    # tail-branches into r17's unchanged accel-text builder and returns to the
    # unchanged fragment-copy loop.
    old_beq = read_word(code, gcsv_entry + NO_NEW_ACCEL_BRANCH)
    old_bl = read_word(code, gcsv_entry + NEW_ACCEL_CALL)
    assert old_beq == 0x0A000000
    assert arm_branch(old_bl, NEW_ACCEL_CALL) == ACCEL_TEXT_BUILDER

    stub = len(code) - gcsv_entry
    write_word(
        code,
        gcsv_entry + NO_NEW_ACCEL_BRANCH,
        make_branch(NO_NEW_ACCEL_BRANCH, NEWLINE, link=False, condition=0x0),
    )
    write_word(
        code,
        gcsv_entry + NEW_ACCEL_CALL,
        make_branch(NEW_ACCEL_CALL, stub, link=True),
    )
    code += struct.pack(
        "<III",
        MOV_R0_COMMA,
        STRB_R0_R5_POSTINC,
        make_branch(stub + 8, ACCEL_TEXT_BUILDER, link=False),
    )

    # Decode the final control flow, not merely the encoder inputs.
    assert arm_branch(read_word(code, gcsv_entry + NO_NEW_ACCEL_BRANCH), NO_NEW_ACCEL_BRANCH) == NEWLINE
    assert arm_branch(read_word(code, gcsv_entry + NEW_ACCEL_CALL), NEW_ACCEL_CALL) == stub
    assert arm_branch(read_word(code, gcsv_entry + stub + 8), stub + 8) == ACCEL_TEXT_BUILDER

    header = PGEN_HEADER.pack(magic, post_entry, gcsv_entry, len(code))
    return header + code


BUILD_ID = """fpGyroSup r29 sparse native-rate accelerometer GCSV test build
Build date: 2026-08-31
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r17 two-slot 32 KiB raw buffering + 64 KiB GCSV writes

Only functional change from r17:
- Every 2,500 Hz gyroscope sample still produces t,gx,gy,gz.
- A row appends ax,ay,az only when the r17 timestamp cursor consumes a new
  accelerometer record (normally about 47 Hz).
- Rows with no new accelerometer record end immediately after gz.  No empty
  comma fields and no synthetic zero accelerometer samples are emitted.
- The GCSV header remains t,gx,gy,gz,ax,ay,az; Gyroflow's flexible parser adds
  gyro for four-column rows and accelerometer only for seven-column rows.

Unchanged r17 boundaries:
- Two 32 KiB raw halves and their proven sequence/publication logic.
- The callback only copies raw samples; it formats nothing and calls no media API.
- One writer task, 64 KiB complete-line media writes and the 5 ms yield.
- 2,500 Hz gyro capture, native lifecycle, record/power locks and JSON generation.
- No GYR file, recovery conversion, decimation or sensor-rate change.

Expected effect:
- Preserve native accelerometer samples without repeating each value on about
  53 gyroscope rows.
- Remove almost all per-row accelerometer formatting/copy bytes, approaching
  the measured gyro-only size reduction while retaining accelerometer data.

Binary verification:
- AutoRun.txt and VSHL.BIN are byte-for-byte identical to r17.
- PGEN changes four checked r17 instructions and appends a 12-byte conditional
  comma stub; all branch destinations are decoded and asserted during build.
- PGEN pool code grows from 7,488 to 7,500 bytes; card file grows from 7,504 to
  7,516 bytes.
- Experimental hardware build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r29：r17 基底、原生頻率加速度計稀疏列測試

這版只改 GCSV 每列內容。Gyro 維持約 2,500 Hz；只有新的 accel 樣本才在
同一列追加 ax,ay,az，因此一般列是四欄、約 47 Hz 的列是七欄。沒有空欄，
也不會把空欄解析成 0。緩衝、寫卡大小、lifecycle、錄影／關機鎖都與 r17 相同。

測試流程：
1. 冷開機並等待 fpSup!。
2. 先錄 15～20 秒；刻意做一些平移、傾斜與較大搖晃後正常停止。
3. 確認處理完成後仍能錄下一段，再錄約 60 秒並正常停止。
4. 若正常，再錄約 120 秒；最後可錄短片後立即正常關機。
5. 相機完成關機後，把卡放回讀卡器並說「讀卡」。

立即停止測試的條件：
- 錄影自行中止、畫面凍結或卡燈異常長亮。
- 停止後超過約 15 秒仍無法開始下一段或正常關機。

主要驗收：
- 每段都有完整 GCSV 與 JSON，本版不建立 GYR。
- GCSV 數字資料列只能是四欄或七欄，不能出現五／六欄或尾端空欄。
- 四欄列保留完整 gyro；七欄列的 accel 時間戳單調，頻率應接近 47 Hz。
- Accel 不應在 2,500 Hz 每列重複；Gyroflow 應同時辨識 gyro 與 accel。
- 錄影不中斷，GCSV/JSON 完成前錄影與關機鎖仍有效。

r17 是回退基準。請勿混裝 r17 與 r29 的 PGEN.BIN。
"""


def build() -> None:
    for required in ("AutoRun.txt", "VSHL.BIN", "PGEN.BIN"):
        assert (BASE / required).is_file(), f"missing r17 {required}"

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    for unchanged in ("AutoRun.txt", "VSHL.BIN"):
        shutil.copy2(BASE / unchanged, OUT / unchanged)
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
        for name in ("VSHL.BIN", "AutoRun.txt", "PGEN.BIN", "BUILD-ID.txt", "TESTING-README.txt", "SHA256SUMS.txt"):
            archive.write(OUT / name, f"{OUT_NAME}/{name}")

    print(f"built {OUT}")
    print(f"built {ZIP_PATH}")
    print((OUT / "SHA256SUMS.txt").read_text(encoding="ascii"), end="")


if __name__ == "__main__":
    build()
