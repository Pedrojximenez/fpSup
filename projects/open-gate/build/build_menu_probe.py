#!/usr/bin/env python3
"""選單第三列探針 AutoRun。

感光元件、picker、RWZM、畫布全部維持原廠——這份只做兩件事:

  1. 把 CINE 錄影格式清單就地換成三列版(89 bytes,長度不變)。
  2. 在 0xC043A19C 掛一支唯讀探針,記錄每次送進 FUN_c043a158 的 (寬,高)
     與 selector。

選第三列、錄一小段、回讀 log,就知道那一列產生的幾何是什麼——也就是
rowpatch 的守衛該改成比對什麼。dispfit 一併裝上,以免預覽干擾判讀。
"""
import pathlib, struct, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_mode98_autorun as base       # 共用已驗證的 helper
from armasm import assemble

OUT = HERE / "menu_probe_autorun"
SOURCE = HERE / "rowprobe.S"
CODE = base.CODE                          # 0xC072F800
PLOG = 0xC072FA60
PLOG_WORDS = 1 + 8 * 2
CSV = 0xC0F8E7EC
CSV_LEN = 89
BOM = b"\xef\xbb\xbf"
LABEL = b"OG 3032x2012"
NEW_CSV = (BOM + b"NO,TEXT,IMAGE,Enabled,Enabled2\r\n"
                 b"1,0313,blank,1,2\n"
                 b"2,0314,blank,1,2\n"
                 b"3," + LABEL + b",,1,2\n")


def csv_patches(image: bytes) -> tuple:
    """就地改寫 89 bytes 的清單。欄位少了 Popup、資料列用裸 \\n,剛好等長。"""
    if len(NEW_CSV) != CSV_LEN:
        raise SystemExit(f"new CSV is {len(NEW_CSV)} bytes, must be {CSV_LEN}")
    off = CSV - base.FIRMWARE_BASE
    if image[off:off + 3] != BOM or b"NO,TEXT,Popup,IMAGE" not in image[off:off + 48]:
        raise SystemExit("the stock menu CSV is not where it is expected")
    span = (CSV_LEN + 3) // 4 * 4
    buf = bytearray(image[off:off + span])
    buf[:CSV_LEN] = NEW_CSV
    out = []
    for k in range(0, span, 4):
        stock = struct.unpack_from("<I", image, off + k)[0]
        value = struct.unpack_from("<I", bytes(buf), k)[0]
        if stock != value:
            out.append((CSV + k, stock, value))
    if image[off + CSV_LEN:off + span] != bytes(buf[CSV_LEN:]):
        raise SystemExit("the patch would disturb the padding after the list")
    return tuple(out)


def section(blob: bytes, blob2: bytes, csv: tuple) -> str:
    lines = [
        "# --- PROBE: three-row CINE list + read-only geometry probe ----------",
        "# Sensor, picker, RWZM and canvas are all left stock.  Nothing here",
        "# changes what is recorded; the probe only observes.",
        "# Select row 3 in CINE, record one second, then read the log at",
        f"# 0x{PLOG:08X}: count, then 8 entries of (w<<16|h, selector).",
        "# Ver.5.02 ONLY.  RAM only; remove AutoRun.txt and power-cycle to undo.",
        "",
        f"# CINE recording-format list, {len(NEW_CSV)} bytes in place, three rows,",
        f"# row 3 label {LABEL.decode()!r}",
    ]
    for address, _, value in csv:
        lines.append(f"mem set 0x{address:08X} 0x{value:08X}")
    lines += ["", f"# clear the probe log at 0x{PLOG:08X}"]
    for i in range(PLOG_WORDS):
        lines.append(f"mem set 0x{PLOG + i * 4:08X} 0x00000000")
    lines += ["", f"# rowprobe, {len(blob)} bytes, read-only"]
    for i, v in enumerate(base.words(blob)):
        lines.append(f"mem set 0x{CODE + i * 4:08X} 0x{v:08X}")
    lines += ["", f"# dispfit live-view payload, {len(blob2)} bytes"]
    for i, v in enumerate(base.words(blob2)):
        lines.append(f"mem set 0x{base.CODE2 + i * 4:08X} 0x{v:08X}")
    lines += ["", f"# clear the dispfit descriptor buffer at 0x{base.DESC:08X}"]
    for i in range(base.DESC_WORDS):
        lines.append(f"mem set 0x{base.DESC + i * 4:08X} 0x00000000")
    lines += [
        "",
        "# Arm last.",
        "# 0xC043A19C stock 0xE1A00004 (mov r0,r4).",
        f"mem set 0x{base.HOOK:08X} 0x{base.HOOK_BRANCH:08X}",
        "# 0xC0437ECC stock 0xE1A00002 (mov r0,r2).",
        f"mem set 0x{base.HOOK2:08X} 0x{base.HOOK2_BRANCH:08X}",
        "# --- END PROBE ------------------------------------------------------",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    image = base.FIRMWARE.read_bytes()
    if base.sha256(image) != base.FIRMWARE_SHA256:
        raise SystemExit("reference firmware is not the verified Ver.5.02 image")
    for address, stock in ((base.HOOK, base.HOOK_STOCK), (base.HOOK2, base.HOOK2_STOCK)):
        if base.firmware_word(image, address) != stock:
            raise SystemExit(f"stock mismatch at 0x{address:08X}")
    csv = csv_patches(image)
    for address, stock, _ in csv:
        if base.firmware_word(image, address) != stock:
            raise SystemExit(f"CSV stock mismatch at 0x{address:08X}")
    blob, blob2 = assemble(SOURCE), assemble(base.SOURCE2)
    if base.words(blob)[-2:] != (0xE1A00004, 0xE12FFF1E):
        raise SystemExit("rowprobe must end with the displaced mov and bx lr")
    if CODE + len(blob) > base.CODE2:
        raise SystemExit("rowprobe overruns into dispfit")
    if PLOG + PLOG_WORDS * 4 > 0xC072FB00:
        raise SystemExit("probe log runs past the cave")
    cave = image[CODE - base.FIRMWARE_BASE:PLOG + PLOG_WORDS * 4 - base.FIRMWARE_BASE]
    if any(cave):
        raise SystemExit("the cave is not empty in the reference image")

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="menu-probe-") as tmp:
        path = pathlib.Path(tmp) / "AutoRun.base.txt"
        rc = subprocess.run((sys.executable, str(base.SHELL_BUILDER), "--out", str(path),
                             "--banner", "fpMENU!", "--no-ep-patches", "--no-pad")).returncode
        if rc:
            raise SystemExit(f"shell builder failed: {rc}")
        shell = base.describe_minimal_usb_shell(path.read_text(encoding="utf-8"))

    body = section(blob, blob2, csv)
    output = base.insert_before_done(shell, body)
    data = base.pad_bytes(output)
    (OUT / "AutoRun.txt").write_bytes(data)
    (OUT / "probe.fragment.txt").write_text(body, encoding="utf-8")
    (OUT / "MANIFEST.txt").write_text("\n".join((
        "Sigma fp three-row CINE list + read-only geometry probe",
        "",
        f"AutoRun.txt bytes={len(data)} sha256={base.sha256(data)}",
        f"rowprobe bytes={len(blob)} sha256={base.sha256(blob)}",
        f"dispfit  bytes={len(blob2)} sha256={base.sha256(blob2)}",
        f"reference_firmware sha256={base.FIRMWARE_SHA256}",
        f"menu_csv_words={len(csv)} at 0x{CSV:08X} len={CSV_LEN} rows=3 "
        f"label={LABEL.decode()!r}",
        f"probe_log=0x{PLOG:08X}..0x{PLOG + PLOG_WORDS * 4:08X}",
        "sensor/picker/RWZM/canvas=stock; this build records nothing new",
        "restore=remove or rename AutoRun.txt, then fully power-cycle",
        "",
    )), encoding="ascii")
    print(f"built {OUT/'AutoRun.txt'} ({len(data)} bytes)")
    print(f"sha256 {base.sha256(data)}")
    print(f"menu CSV {len(csv)} words; rowprobe {len(blob)} B; dispfit {len(blob2)} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
