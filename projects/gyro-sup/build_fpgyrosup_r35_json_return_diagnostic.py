#!/usr/bin/env python3
"""Build r35: exact r34 plus immediate JSON-return FPJ2 diagnostics."""

from __future__ import annotations

import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "fpgyrosup_releases"
BASE_NAME = "fpGyroSup-test-json-path-diagnostic-v22-20260901-r34"
OUT_NAME = "fpGyroSup-test-json-return-diagnostic-v23-20260901-r35"
BASE = RELEASES / BASE_NAME
OUT = RELEASES / OUT_NAME
ZIP_PATH = RELEASES / f"{OUT_NAME}.zip"
ASM = ROOT / "fpgyrosup_r35_json_return_diag.S"

sys.path.insert(0, str(ROOT / "fpsup_repo" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402


BASE_SHA = {
    "AutoRun.txt": "184933dff8418f6fcf0bbc7f02177304eb544344e4fe864290ae6ef7cdc906af",
    "VSHL.BIN": "d7e58e26175b4fc38b2c77f65b3b305cb48b214b658d6910e12e706ee0db8196",
    "PGEN.BIN": "86ea644c918d0409b0c73b9c80329a4c1764b33100a02587132bf80e6d256781",
}

PGEN_HEADER = struct.Struct("<4sIII")
PGEN_MAIN = 0x38C
PGEN_STREAM = 0x1764
OLD_BODY_SIZE = 0x20FC
JSON_CALL = 0x0458
CONSUME_CALL = 0x0518
ORIGINAL = {
    JSON_CALL: 0xEB00067E,       # bl r34 json_attempt_probe
    CONSUME_CALL: 0xEB00067A,    # bl r34 diagnostic_before_consume
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def word(blob: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def put_word(blob: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", blob, offset, value)


def make_branch(address: int, target: int, *, link: bool) -> int:
    delta = target - (address + 8)
    assert delta % 4 == 0
    immediate = delta // 4
    assert -(1 << 23) <= immediate < (1 << 23)
    return (0xEB000000 if link else 0xEA000000) | (immediate & 0xFFFFFF)


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
    for offset, expected in ORIGINAL.items():
        assert word(body, offset) == expected, f"unexpected r34 word at {offset:#x}"

    helper_image = assemble(ASM)
    sym = symbols(ASM)
    helper_offset = sym["json_attempt_probe_v2"]
    assert helper_offset == OLD_BODY_SIZE
    helper = bytearray(helper_image[helper_offset:])
    assert len(helper) == 0x3C4

    helper_links = {
        "json_attempt_call_builder_v2": (0x0D88, True),
        "diagnostic_copy_tail_v2": (0x173C, False),
        "diagnostic_uint_tail_v2": (0x14C8, False),
    }
    for name, (target, link) in helper_links.items():
        address = sym[name]
        put_word(
            helper,
            address - helper_offset,
            make_branch(address, target, link=link),
        )

    replacements = {
        JSON_CALL: sym["json_attempt_probe_v2"],
        CONSUME_CALL: sym["diagnostic_before_consume_v2"],
    }
    for address, target in replacements.items():
        put_word(body, address, make_branch(address, target, link=True))

    body += helper
    assert len(body) == OLD_BODY_SIZE + 0x3C4
    assert len(body) < 0x10000

    for address, target in replacements.items():
        assert branch_target(word(body, address), address) == target
    for name, (target, _) in helper_links.items():
        address = sym[name]
        assert branch_target(word(body, address), address) == target

    return PGEN_HEADER.pack(b"PGEN", main, stream, len(body)) + body


BUILD_ID = """fpGyroSup r35 r34-base immediate JSON-return diagnostic
Build date: 2026-09-01
Camera/firmware: SIGMA fp Ver.5.02
Build type: release AutoRun, no USB shell
Base: exact r34 JSON path diagnostic

Observed before this build:
- A normal 11m34s r34 take stayed in SD-writing protection for several minutes.
- Its GCSV closed cleanly, but neither JSON nor r34's JDG existed.
- r34 wrote JDG only at final queue consumption.  A builder failure followed
  by lifecycle/stream early return could therefore bypass the probe entirely.
- The same take independently proved one producer drop_batch of 150 gyro
  samples.  That recording-time back-pressure issue is not changed here.

Only functional changes from r34:
- The body+0x458 JSON call now uses an appended FPJ2 wrapper.  It times the
  unchanged builder and snapshots lifecycle and stream state immediately when
  the builder returns.
- Immediately before the first builder call it writes a reason-0 breadcrumb.
  If the builder itself never returns, that breadcrumb remains on card.
- On the first failed builder return, before the old main loop can early-return,
  it overwrites the same-basename JDG once.  Attempts 2..11 do not routinely
  add media opens.
- A later return writes only when it exposes an invalid lifecycle/stream gate
  or a builder call taking at least one second, avoiding twelve extra media opens.
- Every builder success overwrites reason 0.  Thus reason 0 remaining means the
  builder never returned (unless the later JDG overwrite itself failed), while
  reason 8 with no JSON exposes a writer/close/directory-commit discrepancy.
- At kind-2 auto-completion or twelve-failure consumption, the final outcome
  overwrites that JDG.
- The diagnostic F_CTOR now receives the event volume in r1.  r34 accidentally
  left r1 pointing into its text buffer, so its JDG open path was not valid.
- FPJ2 format:
    FPJ2;reason=N;kind=N;volume=N;attempts=N;phase=N;elapsed_us=N;lifecycle=N;stream=N

Reasons:
  0 pre-builder breadcrumb; builder had not returned yet
  1 kind-2 auto-completion; builder was not called
  2 twelve JSON failures exhausted
  3 first JSON builder return was failure
  4 a later failed builder call took at least one second
  5 builder failure returned after lifecycle changed away from 1
  6 builder failure returned while stream state was nonzero
  7 builder succeeded but took at least one second
  8 builder reported success in under one second

Phases inherited from r34:
  1 entered builder
  2 lifecycle disabled before metadata
  3 rate/mode zero
  4 width zero
  5 height zero
  6 lens query 0x0d failed
  7 lifecycle disabled after query 0x0d
  8 lens 0x0d block too short
  9 lens query 0x2d failed
 10 lifecycle disabled after query 0x2d
 11 lifecycle disabled before file writer
 12 file-writer gate/volume rejected
 13 JSON F_OPEN failed
 14 JSON F_WRITE returned zero
 99 JSON F_WRITE returned nonzero, followed by a later failure gate

Binary isolation:
- AutoRun.txt and VSHL.BIN are byte-for-byte identical to r34/r33.
- In the complete old r34 PGEN body, exactly two checked BL instructions change.
- The r34 phase hooks remain unchanged; a 964-byte tail contains all FPJ2 code.
- Therefore gyro callback, two-slot writer, GCSV formatting/writes, timestamp
  continuity and FPD1 probe are all byte-identical to r34.

Diagnostic limitation:
- If the JSON builder never returns, reason 0 remains.  If even the breadcrumb's
  JDG F_OPEN is refused by the media layer, the card can still contain neither
  JSON nor JDG.  Unlike r34, a normal returned metadata/lifecycle failure is
  captured before queue early exit.
- If final command 3 fails or the seven-entry post queue is already full, no
  JSON event reaches this PGEN wrapper, so no FPJ2 can be created.
- FPJ2 deliberately adds one tiny pre-builder and one result media transaction.
  It is a diagnostic build and may slightly perturb post-stop timing; it adds
  no recording-time callback, format or media work.
- Experimental diagnostic build; not fp-gyro-sup-v1.1.
"""


TESTING = """fpGyroSup r35：JSON builder 返回點診斷

1. 拔電池冷開機，等待 fpSup!。
2. 先錄 20～30 秒，正常停止並等待鎖解除。
3. 再錄 1～3 分鐘，正常停止並等待鎖解除。
4. 若停止後超過 30 秒仍鎖住，記下大約等待時間；不要連續開新錄影。
5. 正常關機後讀卡。

判讀：
- JSON 存在、JDG reason=8：builder 在一秒內成功。
- JSON 存在、JDG reason=7：builder 最後成功，但本身耗時至少一秒。
- JDG reason=0：builder 沒有返回，或後續 JDG 覆寫也失敗。
- JSON 與 JDG reason=8/7 且 attempts>1：前面曾失敗，後續重試成功。
- JSON 不存在、JDG 存在：依 FPJ2 reason/phase/elapsed/lifecycle/stream 定位。
- 兩者皆不存在：builder 未返回，或連 JDG 的 F_OPEN 也不可用。

GCSV 仍會輸出 r33/r34 的 #FPD1；r35 沒有修 writer back-pressure。
"""


def build() -> None:
    for name, expected in BASE_SHA.items():
        assert sha256((BASE / name).read_bytes()) == expected, f"unexpected r34 {name}"

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
