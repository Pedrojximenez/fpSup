#!/usr/bin/env python3
"""Build r34: exact r33 plus post-recording JSON-path diagnostics."""

from __future__ import annotations

import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "fpgyrosup_releases"
BASE_NAME = "fpGyroSup-test-gcsv-drop-anchor-probe-v21-20260901-r33"
OUT_NAME = "fpGyroSup-test-json-path-diagnostic-v22-20260901-r34"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"
PGEN_ASM = ROOT / "fpgyrosup_r34_json_path_diag.S"

sys.path.insert(0, str(ROOT / "fpsup_repo" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402


BASE_SHA = {
    "AutoRun.txt": "184933dff8418f6fcf0bbc7f02177304eb544344e4fe864290ae6ef7cdc906af",
    "VSHL.BIN": "d7e58e26175b4fc38b2c77f65b3b305cb48b214b658d6910e12e706ee0db8196",
    "PGEN.BIN": "347403e8946f108b13648e18a447b49f3dedb43b1ea61ea70e709de72a4d21f0",
}

PGEN_HEADER = struct.Struct("<4sIII")
PGEN_MAIN = 0x38C
PGEN_STREAM = 0x1764
OLD_PGEN_SIZE = 0x1E58

ORIGINAL_WORDS = {
    0x0458: 0xEB00024A,  # bl old JSON builder
    0x0518: 0xE28A4E2A,  # add r4,sl,#0x2a0
    0x0D94: 0x1A000132,
    0x0DA0: 0x0A00012F,
    0x0DB0: 0x0A00012B,
    0x0DB8: 0x0A000129,
    0x0DF4: 0x0A00011A,
    0x0E00: 0x1A000117,
    0x0E14: 0x3A000112,
    0x0E34: 0x0A00010A,
    0x0E40: 0x1A000107,
    0x1258: 0x1A000001,
    0x13BC: 0xE3A00000,
    0x13C4: 0xE3A00000,
    0x13E4: 0xE1A06000,
}


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
    opcode = 0x0B000000 if link else 0x0A000000
    return (condition << 28) | opcode | (immediate & 0xFFFFFF)


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
        b"PGEN", PGEN_MAIN, PGEN_STREAM, OLD_PGEN_SIZE
    )
    assert len(base) == PGEN_HEADER.size + OLD_PGEN_SIZE

    body = bytearray(base[PGEN_HEADER.size:])
    for offset, expected in ORIGINAL_WORDS.items():
        assert word(body, offset) == expected, f"unexpected PGEN word at {offset:#x}"

    helper_image = assemble(PGEN_ASM)
    sym = symbols(PGEN_ASM)
    helper_offset = sym["json_attempt_probe"]
    assert helper_offset == OLD_PGEN_SIZE
    helper = bytearray(helper_image[helper_offset:])
    assert len(helper) == 0x2A4

    helper_branches = {
        "json_attempt_call_builder": (0x0D88, True),
        "phase_store_failure_exit": (0x1264, False),
        "diagnostic_copy_tail": (0x173C, False),
        "diagnostic_uint_tail": (0x14C8, False),
    }
    for name, (target, link) in helper_branches.items():
        address = sym[name]
        put_word(
            helper,
            address - helper_offset,
            make_branch(address, target, link=link),
        )

    direct_calls = {
        0x0458: "json_attempt_probe",
        0x0518: "diagnostic_before_consume",
        0x13BC: "phase_file_open_return_zero",
        0x13C4: "phase_file_gate_return_zero",
        0x13E4: "phase_file_write_result",
    }
    for address, name in direct_calls.items():
        put_word(body, address, make_branch(address, sym[name], link=True))

    conditional_failures = {
        0x0D94: "phase_enabled_before",
        0x0DA0: "phase_rate_zero",
        0x0DB0: "phase_width_zero",
        0x0DB8: "phase_height_zero",
        0x0DF4: "phase_lens_query_0d",
        0x0E00: "phase_enabled_after_0d",
        0x0E14: "phase_lens_0d_short",
        0x0E34: "phase_lens_query_2d",
        0x0E40: "phase_enabled_after_2d",
        0x1258: "phase_enabled_before_file",
    }
    for address, name in conditional_failures.items():
        condition = ORIGINAL_WORDS[address] >> 28
        put_word(
            body,
            address,
            make_branch(address, sym[name], link=False, condition=condition),
        )

    body += helper
    assert len(body) == OLD_PGEN_SIZE + 0x2A4
    assert len(body) < 0x3000

    for address, name in direct_calls.items():
        assert branch_target(word(body, address), address) == sym[name]
    for address, name in conditional_failures.items():
        patched = word(body, address)
        assert patched >> 28 == ORIGINAL_WORDS[address] >> 28
        assert branch_target(patched, address) == sym[name]
    for name, (target, _) in helper_branches.items():
        address = sym[name]
        assert branch_target(word(body, address), address) == target

    return PGEN_HEADER.pack(b"PGEN", main, stream, len(body)) + body


BUILD_ID = """fpGyroSup r34 r33-base JSON path diagnostic
Build date: 2026-09-01
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r33 GCSV drop/anchor probe

Purpose:
- Diagnose why a normally stopped clip can unlock without creating JSON.
- This build does not claim to fix JSON or intermittent GCSV completeness.

Changes from r33:
- The existing JSON builder and twelve-retry policy remain intact.
- Each JSON attempt records the last reached phase in two previously unused
  state words; no recording-time GCSV path is changed.
- Immediately before a queue event is consumed without JSON, r34 tries to
  create a tiny same-basename .jdg file:
    FPJ1;reason=N;kind=N;volume=N;attempts=N;phase=N
- reason=1: kind 2 auto-completed without invoking the JSON builder.
- reason=2: a normal JSON event exhausted all twelve immediate attempts.
- A successful JSON event creates no .jdg file.

Phase values for reason=2:
  1 entered builder
  2 lifecycle disabled before metadata
  3 rate/mode was zero
  4 width was zero
  5 height was zero
  6 lens query 0x0d failed
  7 lifecycle disabled after query 0x0d
  8 lens 0x0d block was too short
  9 lens query 0x2d failed
 10 lifecycle disabled after query 0x2d
 11 lifecycle disabled immediately before JSON file writing
 12 file-writer gate or volume rejected
 13 JSON F_OPEN failed
 14 JSON F_WRITE returned zero
 99 JSON F_WRITE returned nonzero (normally followed by JSON completion)

Limits:
- If the same media failure also prevents the diagnostic .jdg from opening,
  both JSON and JDG may be absent; that result still points toward media open.
- r33's #FPD1 GCSV trailer remains enabled and unchanged.
- Experimental diagnostic build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r34：JSON 路徑診斷

1. 拔電池冷開機，等待 fpSup!。
2. 錄影 20～60 秒，正常停止，等待 SD 鎖解除。
3. 再錄第二段，正常停止並等鎖解除。
4. 正常關機後讀卡。

每段請檢查 DNG、GCSV、JSON，以及同檔名的 JDG：
- 有 JSON、無 JDG：正常。
- 無 JSON、有 JDG：把 JDG 內完整一行交回分析。
- 無 JSON、無 JDG：仍是有效結果，可能是診斷檔也無法開啟。

GCSV 仍應保留 r33 的 #FPD1 診斷尾行。本版只定位 JSON 消失路徑，
不把 GCSV 完整率視為已修復。
"""


def build() -> None:
    for name, expected in BASE_SHA.items():
        assert sha256((BASE / name).read_bytes()) == expected, f"unexpected r33 {name}"

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
