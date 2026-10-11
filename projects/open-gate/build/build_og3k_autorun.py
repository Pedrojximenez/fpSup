#!/usr/bin/env python3
"""OG3K — 3032x2012 open gate,涵蓋 23.976 / 24 / 25 / 29.97 / 48 / 50 / 59.94。

做法不是把 picker 指向別的模式,而是**把那七個幀率原本用的模式本身改成 2012 行**。

它們跟 mode 98 的 648-byte 暫存器記錄只差兩個字(mode_id 與 +0x10 最小消隱)
—— 本來就是同一組感光元件設定:同樣的 2x 縮減、同樣的「安靜」類比組
(讀出雜訊 0.55 DN,mode 117 是 0.97)。唯一讓它們是 3032x1708 的,只有

    時序表 0xC0B59500  起始/結束行  172..1880  ->  20..2032
    幾何表 0xC0B59DC0  高度欄 x3    1708       ->  2012

每個模式 5 個字。用原廠自己的時序,所以每個幀率都是精確值,0 ppm。

不包含:100 fps 與 119.88(見 README),以及選單多一列(要先跑 menu probe)。
"""
import json, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_mode98_autorun as base
from armasm import assemble

OUT = HERE / "og3k_autorun"
WITH_DISPFIT = "--dispfit" in sys.argv
ROWPATCH = HERE / "rowpatch_v4.S"
DISPFIT = HERE / "dispfit_v2.S"
CODE, CODE2 = base.CODE, base.CODE2
HOOK, HOOK_STOCK, HOOK_BRANCH = base.HOOK, base.HOOK_STOCK, base.HOOK_BRANCH
HOOK2, HOOK2_STOCK, HOOK2_BRANCH = base.HOOK2, base.HOOK2_STOCK, base.HOOK2_BRANCH
DESC, LOG = base.DESC, base.LOG

RWZM = (
    (0xC0BD9A34, 0x00000640, 0x00000400, "profile122 live RWZM H -> unity"),
    (0xC0BE1684, 0x00000640, 0x00000400, "profile122 record RWZM H -> unity"),
    (0xC0BD9EFC, 0x00000640, 0x00000400, "profile122 live RWZM V -> unity"),
    (0xC0BE1B4C, 0x00000640, 0x00000400, "profile122 record RWZM V -> unity"),
)
RATES = json.loads((HERE / "mode98_allrates_patches.json").read_text())
DATA = tuple(tuple(x) for x in RATES) + RWZM


def section(blob, blob2):
    L = [
        "# --- OG3K: 3032x2012 open gate, every CinemaDNG rate up to 59.94 -----",
        "# Sigma fp firmware Ver.5.02 ONLY; no runtime version guard.",
        "# Cold-boot RAM patches only.  Remove AutoRun.txt and power-cycle to undo.",
        "#",
        "# The seven modes the FHD rates already use are turned into 2012-row",
        "# modes.  Their sensor register records differ from mode 98 in only the",
        "# mode id and the minimum-blanking field, so they are already the same",
        "# 2x reduction and the same quiet analog profile; only the row window",
        "# and the geometry height said 1708.  Timing is untouched, so every",
        "# rate stays exactly what SIGMA ships.",
        "#",
        "#   23.976 -> mode 109      48 -> mode 220      59.94 -> mode 27",
        "#   24     -> mode 218      50 -> mode 115",
        "#   25     -> mode 125   29.97 -> mode 106",
        "#",
        "# 100 fps and 119.88 are NOT patched: 2012 rows at hmax 445 need",
        "# 12.44 ms and the fastest 3032x2012 readout is 9.22 ms, so 119.88",
        "# (8.34 ms a frame) is impossible and 100 needs mode 117 instead.",
        "",
    ]
    for a, s, v, c in DATA:
        L.append(f"# {c}; stock 0x{s:08X}")
        L.append(f"mem set 0x{a:08X} 0x{v:08X}")
    L += ["", f"# geometry payload, {len(blob)} bytes"]
    for i, v in enumerate(base.words(blob)):
        L.append(f"mem set 0x{CODE + i * 4:08X} 0x{v:08X}")
    if WITH_DISPFIT:
        L += ["", f"# dispfit v2 live-view payload, {len(blob2)} bytes"]
        for i, v in enumerate(base.words(blob2)):
            L.append(f"mem set 0x{CODE2 + i * 4:08X} 0x{v:08X}")
    L += [
        "",
        "# Arm last, geometry before display.",
        "# 0xC043A19C stock 0xE1A00004 (mov r0,r4).",
        f"mem set 0x{HOOK:08X} 0x{HOOK_BRANCH:08X}",
    ]
    if WITH_DISPFIT:
        L += ["# 0xC0437ECC stock 0xE1A00002 (mov r0,r2).",
              f"mem set 0x{HOOK2:08X} 0x{HOOK2_BRANCH:08X}"]
    L += [
        "# --- END OG3K --------------------------------------------------------",
        "",
    ]
    return "\n".join(L)


def main():
    image = base.FIRMWARE.read_bytes()
    if base.sha256(image) != base.FIRMWARE_SHA256:
        raise SystemExit("reference firmware is not the verified Ver.5.02 image")
    for a, s, _, c in DATA:
        got = base.firmware_word(image, a)
        if got != s:
            raise SystemExit(f"stock mismatch 0x{a:08X}: 0x{got:08X} != 0x{s:08X} ({c})")
    for site, stock in ((HOOK, HOOK_STOCK), (HOOK2, HOOK2_STOCK)):
        if base.firmware_word(image, site) != stock:
            raise SystemExit(f"hook site 0x{site:08X} is not stock")
    blob, blob2 = assemble(ROWPATCH), assemble(DISPFIT)
    if base.words(blob)[-2:] != (0xE1A00004, 0xE12FFF1E):
        raise SystemExit("geometry payload must end with the displaced mov and bx lr")
    if base.words(blob2)[-1] != 0xE12FFF1E:
        raise SystemExit("dispfit must end with bx lr")
    if CODE + len(blob) > CODE2 or CODE2 + len(blob2) > DESC:
        raise SystemExit("payloads overlap or reach the descriptor buffer")
    if any(image[CODE - base.FIRMWARE_BASE:DESC + 44 - base.FIRMWARE_BASE]):
        raise SystemExit("the cave is not empty in the reference image")
    for code, site, br in ((CODE, HOOK, HOOK_BRANCH), (CODE2, HOOK2, HOOK2_BRANCH)):
        if (0xEB000000 | (((code - site - 8) >> 2) & 0xFFFFFF)) != br:
            raise SystemExit(f"hook 0x{site:08X} branch mismatch")

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="og3k-") as tmp:
        p = pathlib.Path(tmp) / "AutoRun.base.txt"
        rc = subprocess.run((sys.executable, str(base.SHELL_BUILDER), "--out", str(p),
                             "--banner", "OG3K!", "--no-ep-patches", "--no-pad")).returncode
        if rc:
            raise SystemExit(f"shell builder failed: {rc}")
        shell = base.describe_minimal_usb_shell(p.read_text(encoding="utf-8"))

    body = section(blob, blob2)
    n = sum(1 for l in body.splitlines() if l.startswith("mem set"))
    out = base.insert_before_done(shell, body)
    # The AutoRun interpreter drops commands off the tail past some limit.
    # Measured on hardware: 648 total commands ran complete (both hooks armed
    # themselves), 697 lost its last dozen.  Comments and blank lines are free.
    total = sum(1 for l in out.splitlines()
                if l.strip() and not l.lstrip().startswith("#"))
    if total > 680:
        raise SystemExit(
            f"{total} commands; 648 ran complete and 697 lost its tail, "
            "so this is too close to the cliff")
    print(f"  total commands {total}  (648 ok / 697 truncated on hardware)")
    data = base.pad_bytes(out)
    (OUT / "AutoRun.txt").write_bytes(data)
    (OUT / "og3k_patch.fragment.txt").write_text(body, encoding="utf-8")
    (OUT / "MANIFEST.txt").write_text("\n".join((
        "Sigma fp OG3K 3032x2012 open gate, 23.976 to 59.94",
        "",
        f"AutoRun.txt bytes={len(data)} sha256={base.sha256(data)}",
        f"rowpatch_v4 bytes={len(blob)} sha256={base.sha256(blob)}",
        f"dispfit_v2  bytes={len(blob2)} sha256={base.sha256(blob2)}",
        f"reference_firmware sha256={base.FIRMWARE_SHA256}",
        "rates=23.976 24 25 29.97 48 50 59.94, all exact (shipping timings)",
        "sensor=modes 109 218 125 106 220 115 27 widened to 2012 rows",
        "readout=12.435 ms (hmax 445) or 12.575 ms (hmax 450); quiet analog group",
        "not patched=100 fps (needs mode 117), 119.88 (impossible, cap is 108.4)",
        f"fragment mem set lines={n}",
        f"hook=0x{HOOK:08X} branch=0x{HOOK_BRANCH:08X}",
        (f"hook2=0x{HOOK2:08X} branch=0x{HOOK2_BRANCH:08X}  dispfit v2 (h := w*2/3)"
         if WITH_DISPFIT else "dispfit=absent; geometry tested alone this build"),
        "menu=label unchanged; the three-row list is a separate build",
        "restore=remove or rename AutoRun.txt, then fully power-cycle",
        "",
    )), encoding="ascii")
    print(f"built {OUT/'AutoRun.txt'} ({len(data)} bytes)  sha256 {base.sha256(data)}")
    print(f"fragment {n} mem set lines  ({len(DATA)} data words, "
          f"{len(blob)//4}+{len(blob2)//4} payload words, 2 arms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
