#!/usr/bin/env python3
"""mode 3 open gate:6064x4042 原生讀出 + RWZM 2.0x -> 3032x2020。

跟 mode98_autorun 的差別:

  - picker 指向 mode 3(MONIT1_30,6064x4042 1:1 全 3:2,安靜類比組)
  - RWZM 由 1.5625x 改成 2.0x,在進緩衝區之前就把 6064 縮成 3032
  - 幾何 payload 的輸出常數改成 3032x2020 / active 3000x2000

刻意精簡:沒有 dispfit、沒有選單標籤。上一版 199 行的 AutoRun 最後兩行 arm
沒有生效,懷疑是指令數上限;舊版 151 行則完全正常。這份只有 71 行。
"""
import pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_mode98_autorun as base
from armasm import assemble

OUT = HERE / "mode3_autorun"
SOURCE = HERE / "rowpatch_mode3.S"
CODE, LOG, HOOK = base.CODE, base.LOG, base.HOOK
HOOK_STOCK, HOOK_BRANCH = base.HOOK_STOCK, base.HOOK_BRANCH

DATA = (
    (0xC0B59564, 0x01BD01BD, 0x02DF01BD, "mode3 TAIL 445 -> 735; 29.97003 at 0 ppm"),
    (0xC0BE5888, 0x0000006A, 0x00000003, "picker table 1 idx7: mode106 -> 3"),
    (0xC0BE5A28, 0x0000006A, 0x00000003, "picker table 2 idx7: mode106 -> 3"),
    (0xC0BE5BC8, 0x0000006A, 0x00000003, "picker table 3 idx7: mode106 -> 3"),
    (0xC0BD9A34, 0x00000640, 0x00000800, "profile122 live RWZM H -> 2.0x"),
    (0xC0BE1684, 0x00000640, 0x00000800, "profile122 record RWZM H -> 2.0x"),
    (0xC0BD9EFC, 0x00000640, 0x00000800, "profile122 live RWZM V -> 2.0x"),
    (0xC0BE1B4C, 0x00000640, 0x00000800, "profile122 record RWZM V -> 2.0x"),
)


def section(blob):
    lines = [
        "# --- mode 3 open gate: 6064x4042 1:1 -> RWZM 2.0x -> 3032x2020 -------",
        "# Sigma fp firmware Ver.5.02 ONLY; no runtime version guard.",
        "# Cold-boot RAM patches only.  Remove AutoRun.txt and power-cycle to undo.",
        "# Use CinemaDNG / FHD / 29.97p.  Any other frame rate is NOT patched.",
        "#",
        "# The sensor reads every photodiode over the full 3:2 area and the",
        "# pipeline halves it before the buffer, so nothing overflows: at RWZM",
        "# unity a 6064-wide line does not fit a 3032-wide buffer and the camera",
        "# hangs.  That is what the 2.0x here prevents.",
        "",
    ]
    for a, s, v, c in DATA:
        lines.append(f"# {c}; stock 0x{s:08X}")
        lines.append(f"mem set 0x{a:08X} 0x{v:08X}")
    lines += ["", f"# clear the v4 telemetry words at 0x{LOG:08X}"]
    for off in range(0, 0x10, 4):
        lines.append(f"mem set 0x{LOG + off:08X} 0x00000000")
    lines += ["", f"# rowpatch for 3032x2020, {len(blob)} bytes"]
    for i, v in enumerate(base.words(blob)):
        lines.append(f"mem set 0x{CODE + i * 4:08X} 0x{v:08X}")
    lines += [
        "",
        "# Arm last: stock instruction is 0xE1A00004 (mov r0,r4).",
        f"mem set 0x{HOOK:08X} 0x{HOOK_BRANCH:08X}",
        "# --- END mode 3 open gate --------------------------------------------",
        "",
    ]
    return "\n".join(lines)


def main():
    image = base.FIRMWARE.read_bytes()
    if base.sha256(image) != base.FIRMWARE_SHA256:
        raise SystemExit("reference firmware is not the verified Ver.5.02 image")
    for a, s, _, c in DATA:
        got = base.firmware_word(image, a)
        if got != s:
            raise SystemExit(f"stock mismatch at 0x{a:08X}: 0x{got:08X} != 0x{s:08X} ({c})")
    if base.firmware_word(image, HOOK) != HOOK_STOCK:
        raise SystemExit("hook site is not the expected stock instruction")
    blob = assemble(SOURCE)
    if len(blob) != 232:
        raise SystemExit(f"unexpected payload size {len(blob)}")
    if base.words(blob)[-2:] != (0xE1A00004, 0xE12FFF1E):
        raise SystemExit("payload must end with the displaced mov and bx lr")
    if CODE + len(blob) > LOG:
        raise SystemExit("payload overruns the telemetry words")
    if any(image[CODE - base.FIRMWARE_BASE:LOG + 0x10 - base.FIRMWARE_BASE]):
        raise SystemExit("the cave is not empty in the reference image")
    disp = (CODE - HOOK - 8) >> 2
    if (0xEB000000 | (disp & 0xFFFFFF)) != HOOK_BRANCH:
        raise SystemExit("hook branch mismatch")

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mode3-") as tmp:
        p = pathlib.Path(tmp) / "AutoRun.base.txt"
        rc = subprocess.run((sys.executable, str(base.SHELL_BUILDER), "--out", str(p),
                             "--banner", "fpOG3!", "--no-ep-patches", "--no-pad")).returncode
        if rc:
            raise SystemExit(f"shell builder failed: {rc}")
        shell = base.describe_minimal_usb_shell(p.read_text(encoding="utf-8"))

    body = section(blob)
    out = base.insert_before_done(shell, body)
    n = sum(1 for l in body.splitlines() if l.startswith("mem set"))
    data = base.pad_bytes(out)
    (OUT / "AutoRun.txt").write_bytes(data)
    (OUT / "mode3_patch.fragment.txt").write_text(body, encoding="utf-8")
    (OUT / "MANIFEST.txt").write_text("\n".join((
        "Sigma fp mode 3 open gate 3032x2020 @29.97 TEST AutoRun",
        "",
        f"AutoRun.txt bytes={len(data)} sha256={base.sha256(data)}",
        f"rowpatch_mode3 bytes={len(blob)} sha256={base.sha256(blob)}",
        f"reference_firmware sha256={base.FIRMWARE_SHA256}",
        "sensor=mode 3 MONIT1_30 6064x4042 1:1 full 3:2, quiet analog group",
        "timing=hmax 445 tail 735 vmax 5398 -> 29.97003 fps, rolling 24.982 ms",
        "pipeline=RWZM 2.0x -> 3032x2020, active 3000x2000",
        f"fragment mem set lines={n} (previous build was 199 and its final arms did not take)",
        f"hook=0x{HOOK:08X} stock=0x{HOOK_STOCK:08X} branch=0x{HOOK_BRANCH:08X}",
        "dispfit=absent; menu label=absent",
        "restore=remove or rename AutoRun.txt, then fully power-cycle",
        "",
    )), encoding="ascii")
    print(f"built {OUT/'AutoRun.txt'} ({len(data)} bytes)  sha256 {base.sha256(data)}")
    print(f"fragment {n} mem set lines; payload {len(blob)} bytes at 0x{CODE:08X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
