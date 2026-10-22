#!/usr/bin/env python3
"""Build a cold-boot USB-shell AutoRun for the 3032x2012 open-gate test.

The output combines the current canonical fp USB shell with only the patches
already verified on the live camera:

* mode 117 selected in all three FHD/29.97 picker tables;
* mode 117 VMAX changed from 2184 to 7280 (29.97003 fps);
* the proven C043A19C v4 canvas hook;
* profile-122 record/live H/V RWZM cells changed from 0x640 to unity 0x400.

The hook is emitted last.  No diagnostic hook is included.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import struct
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
SHELL_DIR = ROOT.parent.parent / "fpSup" / "fp_usb_shell"   # same restructure fix as FIRMWARE
SHELL_BUILDER = SHELL_DIR / "build_autorun.py"
SOURCE = HERE / "rowpatch_v4.S"
SOURCE2 = HERE / "dispfit.S"
DEFAULT_OUT = HERE / "mode98_autorun" / "AutoRun.txt"
DEFAULT_FRAGMENT = HERE / "mode98_autorun" / "open_gate_patch.fragment.txt"
DEFAULT_MANIFEST = HERE / "mode98_autorun" / "MANIFEST.txt"
# SIGMA_re/out, not projects/out: ROOT is projects/open-gate, so the tree root
# is two levels up.  Left behind by the 2026-09-13 restructure -- og3k_plan.py
# was corrected then and this one was not, which broke every OG3K build.
FIRMWARE = ROOT.parent.parent / "out" / "MAIN_c0000000.bin"

sys.path.insert(0, str(SHELL_DIR))
from armasm import assemble  # noqa: E402


CODE = 0xC072F800
HOOK = 0xC043A19C
HOOK_STOCK = 0xE1A00004
HOOK_BRANCH = 0xEB0BD597
LOG = 0xC072FA00

# dispfit: tell the live-view compositor its source is 3:2, not 16:9.
CODE2 = 0xC072F900
HOOK2 = 0xC0437ECC
HOOK2_STOCK = 0xE1A00002           # mov r0, r2
DESC = 0xC072FA20                  # 44-byte descriptor the hook hands back
DESC_WORDS = 11
HOOK2_BRANCH = 0xEB000000 | (((CODE2 - HOOK2 - 8) >> 2) & 0x00FFFFFF)
CAVE_END = DESC + DESC_WORDS * 4

# The CINE recording-format list shows string id 0314 for the slot this build
# hijacks.  Renaming it in place keeps the label honest without relocating the
# menu CSV.  Same length, so the record header stays valid.  String id 1279
# carries the same text elsewhere (HDMI output) and is deliberately left alone.
LABEL_ID = b"0314\x00"
LABEL_OLD = b"FHD 1920x1080"
LABEL_NEW = b"3:2 3032x2012"
FIRMWARE_BASE = 0xC0000000
FIRMWARE_BYTES = 49_482_954
FIRMWARE_SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"
PAYLOAD_SHA256 = "7d44029ee80b58f3fd09394f7f615643c60e233aad0122051feb0b2c8af4bb4a"
PAD_TO = 32_768

DIAGNOSTIC_HOOKS = (
    0xC031C79C,  # A7 content logger
    0xC031CC98,  # raw DMA transition logger
    0xC01BE5E4,  # retired producer logger
)

# Minimal causal set proven by the live experiment.  The movie/still menu-size
# tables are intentionally absent: earlier tests proved that they are downstream
# metadata/settings copies and do not control either the DNG canvas or producer.
#
# AutoRun's command language has no conditional, so the stock words are checked
# against the local Ver.5.02 image at build time and recorded for review.  The
# generated file is still firmware-specific and has no runtime version guard.
DATA_PATCHES = (
    (0xC0B59A28, 0x00040888, 0x00041C70, "mode117 VMAX 2184 -> 7280"),
    (0xC0B59544, 0x01BD01BD, 0x02DF01BD, "mode98 TAIL 445 -> 735"),
    (0xC0B59548, 0x0004082E, 0x00041516, "mode98 VMAX 2094 -> 5398"),
    (0xC0BE5888, 0x0000006A, 0x00000075, "picker table 1 idx7: mode106 -> 117"),
    (0xC0BE5A28, 0x0000006A, 0x00000075, "picker table 2 idx7: mode106 -> 117"),
    (0xC0BE5BC8, 0x0000006A, 0x00000075, "picker table 3 idx7: mode106 -> 117"),
    (0xC0BD9A34, 0x00000640, 0x00000400, "profile122 live RWZM H -> unity"),
    (0xC0BE1684, 0x00000640, 0x00000400, "profile122 record RWZM H -> unity"),
    (0xC0BD9EFC, 0x00000640, 0x00000400, "profile122 live RWZM V -> unity"),
    (0xC0BE1B4C, 0x00000640, 0x00000400, "profile122 record RWZM V -> unity"),
)

MEM_SET_RE = re.compile(
    r"^mem set 0x([0-9A-Fa-f]{8}) 0x([0-9A-Fa-f]{8})$"
)


def words(blob: bytes) -> tuple[int, ...]:
    if len(blob) & 3:
        raise SystemExit("rowpatch payload is not word aligned")
    return struct.unpack(f"<{len(blob) // 4}I", blob)


def firmware_word(image: bytes, address: int) -> int:
    offset = address - FIRMWARE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise SystemExit(f"firmware address outside image: 0x{address:08X}")
    return struct.unpack_from("<I", image, offset)[0]


def label_patches(image: bytes) -> tuple:
    """32-bit words that rewrite every copy of the id-0314 label, in place."""
    if len(LABEL_NEW) != len(LABEL_OLD):
        raise SystemExit("menu label length changed; the record header would lie")
    out = []
    start = 0
    while True:
        index = image.find(LABEL_ID, start)
        if index < 0:
            break
        start = index + 1
        declared = struct.unpack_from("<I", image, index - 4)[0]
        text_at = index + len(LABEL_ID)
        if declared != len(LABEL_OLD):
            continue
        if image[text_at:text_at + len(LABEL_OLD)] != LABEL_OLD:
            continue
        low = text_at & ~3
        high = (text_at + len(LABEL_NEW) + 3) & ~3
        patched = bytearray(image[low:high])
        patched[text_at - low:text_at - low + len(LABEL_NEW)] = LABEL_NEW
        for offset in range(0, high - low, 4):
            stock = struct.unpack_from("<I", image, low + offset)[0]
            value = struct.unpack_from("<I", bytes(patched), offset)[0]
            if stock != value:
                out.append((low + offset + FIRMWARE_BASE, stock, value))
    if not out:
        raise SystemExit("no id-0314 menu label records found in the image")
    return tuple(out)


def verify_firmware() -> None:
    if not FIRMWARE.is_file():
        raise SystemExit(f"missing reference firmware: {FIRMWARE}")
    image = FIRMWARE.read_bytes()
    digest = sha256(image)
    if len(image) != FIRMWARE_BYTES or digest != FIRMWARE_SHA256:
        raise SystemExit(
            "reference firmware is not the verified Sigma fp Ver.5.02 image: "
            f"bytes={len(image)} sha256={digest}"
        )

    expected = tuple((address, stock) for address, stock, _, _ in DATA_PATCHES)
    expected += ((HOOK, HOOK_STOCK), (HOOK2, HOOK2_STOCK))
    expected += tuple((a, stock) for a, stock, _ in label_patches(image))
    for address, stock in expected:
        actual = firmware_word(image, address)
        if actual != stock:
            raise SystemExit(
                f"firmware stock mismatch at 0x{address:08X}: "
                f"0x{actual:08X}, expected 0x{stock:08X}"
            )

    # This is the scratch cave used by the proven live payload.  Verify that the
    # reference image contains no firmware code/data anywhere we occupy.
    cave_start = CODE - FIRMWARE_BASE
    cave_end = CAVE_END - FIRMWARE_BASE
    if any(image[cave_start:cave_end]):
        raise SystemExit(
            f"reference firmware cave 0x{CODE:08X}..0x{CAVE_END:08X} "
            "is not empty"
        )


def patch_section(blob: bytes, blob2: bytes, labels: tuple) -> str:
    if CODE + len(blob) > LOG:
        raise SystemExit(
            f"rowpatch 0x{CODE:08X}..0x{CODE + len(blob):08X} overlaps "
            f"log 0x{LOG:08X}"
        )
    if CODE2 + len(blob2) > LOG:
        raise SystemExit(
            f"dispfit 0x{CODE2:08X}..0x{CODE2 + len(blob2):08X} overlaps "
            f"log 0x{LOG:08X}"
        )
    if CODE + len(blob) > CODE2:
        raise SystemExit("rowpatch and dispfit payloads overlap")
    lines = [
        "# --- TEST: 3032x2012 open gate @29.97, mode 117 / mode 98 A/B --------",
        "# Both sensor modes are retimed to 29.97 here; the three picker words",
        "# select which one is used.  0x75 = mode 117 (2x2 skipping, boot value),",
        "# 0x62 = mode 98 ACQ_12BIT_MIX.  Switch between takes with:",
        "#   mem set 0xC0BE5888 0x00000062",
        "#   mem set 0xC0BE5A28 0x00000062",
        "#   mem set 0xC0BE5BC8 0x00000062",
        "# then re-select the CINE resolution so the picker is read again.",
        "# Sigma fp firmware Ver.5.02 ONLY; there is no runtime version guard.",
        "# Cold-boot RAM patches only. Remove/rename AutoRun.txt and power-cycle",
        "# to return to stock. Use FHD 29.97 CinemaDNG for this test; the CINE",
        "# resolution list shows it as \"3:2 3032x2012\" once this is applied.",
        "",
    ]
    for address, stock, value, comment in DATA_PATCHES:
        lines.append(f"# {comment}; stock 0x{stock:08X}")
        lines.append(f"mem set 0x{address:08X} 0x{value:08X}")

    lines.extend((
        "",
        f"# CINE resolution label, string id 0314, {len(labels) // 4} localisations:",
        f"# {LABEL_OLD.decode()!r} -> {LABEL_NEW.decode()!r}, same length, in place.",
    ))
    for address, _, value in labels:
        lines.append(f"mem set 0x{address:08X} 0x{value:08X}")

    lines.extend((
        "",
        f"# clear v4 diagnostic words at 0x{LOG:08X}",
    ))
    for offset in range(0, 0x10, 4):
        lines.append(f"mem set 0x{LOG + offset:08X} 0x00000000")

    lines.extend((
        "",
        f"# proven v4 rowpatch, {len(blob)} bytes",
    ))
    for index, value in enumerate(words(blob)):
        lines.append(f"mem set 0x{CODE + index * 4:08X} 0x{value:08X}")

    lines.extend((
        "",
        f"# dispfit live-view payload, {len(blob2)} bytes",
    ))
    for index, value in enumerate(words(blob2)):
        lines.append(f"mem set 0x{CODE2 + index * 4:08X} 0x{value:08X}")

    lines.extend((
        "",
        f"# clear the dispfit descriptor buffer at 0x{DESC:08X}",
    ))
    for index in range(DESC_WORDS):
        lines.append(f"mem set 0x{DESC + index * 4:08X} 0x00000000")

    lines.extend((
        "",
        "# Arm the hooks last, geometry before display.",
        "# 0xC043A19C stock 0xE1A00004 (mov r0,r4).",
        f"mem set 0x{HOOK:08X} 0x{HOOK_BRANCH:08X}",
        "# 0xC0437ECC stock 0xE1A00002 (mov r0,r2).",
        f"mem set 0x{HOOK2:08X} 0x{HOOK2_BRANCH:08X}",
        "# --- END TEST open gate ---------------------------------------------",
        "",
    ))
    return "\n".join(lines)


def insert_before_done(base: str, section: str) -> str:
    marker = "# --- done "
    if base.count(marker) != 1:
        raise SystemExit("canonical shell AutoRun must contain one done marker")
    position = base.find(marker)
    if position < 0:
        raise SystemExit("canonical shell AutoRun has no done marker")
    if f"mem set 0x{HOOK:08X}" in base:
        raise SystemExit("canonical shell AutoRun already patches the open-gate hook")
    return base[:position] + section + base[position:]


def describe_minimal_usb_shell(base: str) -> str:
    old = """# firmware owns the descriptors, creates and enables the endpoints, and
# re-creates them after a record-mode reconfiguration.  A few words are changed
# so nothing competes for those pipes and so PTP's unused interrupt endpoint
# becomes a second bulk IN for streaming; the rest of this file is the worker.
#
#   EP 0x01 OUT  commands      EP 0x82 IN  replies      EP 0x83 IN  streaming"""
    new = """# firmware owns the descriptors, creates and enables the endpoints, and
# re-creates them after a record-mode reconfiguration. Only the interface-class
# word needed by the command shell is changed in this minimal test build.
# The optional EP 0x83 streaming patches are intentionally absent.
#
#   EP 0x01 OUT  commands      EP 0x82 IN  replies      EP 0x83 stock / unused"""
    if base.count(old) != 1:
        raise SystemExit("canonical USB-shell description changed unexpectedly")
    return base.replace(old, new)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_mem_sets(text: str) -> list[tuple[int, int]]:
    parsed = []
    for line in text.splitlines():
        match = MEM_SET_RE.fullmatch(line)
        if match:
            parsed.append((int(match.group(1), 16), int(match.group(2), 16)))
    return parsed


def validate_section(section: str, blob: bytes, blob2: bytes, labels: tuple) -> None:
    expected = [(address, value) for address, _, value, _ in DATA_PATCHES]
    expected += [(address, value) for address, _, value in labels]
    expected += [(LOG + offset, 0) for offset in range(0, 0x10, 4)]
    expected += [
        (CODE + index * 4, value)
        for index, value in enumerate(words(blob))
    ]
    expected += [
        (CODE2 + index * 4, value)
        for index, value in enumerate(words(blob2))
    ]
    expected += [(DESC + index * 4, 0) for index in range(DESC_WORDS)]
    expected += [(HOOK, HOOK_BRANCH), (HOOK2, HOOK2_BRANCH)]
    actual = parse_mem_sets(section)
    if actual != expected:
        raise SystemExit("generated test section does not match the reviewed order")


def validate_output(output: str, section: str, blob: bytes, blob2: bytes,
                    labels: tuple) -> None:
    validate_section(section, blob, blob2, labels)
    if output.count(section) != 1:
        raise SystemExit("test section is missing or duplicated")

    for site, branch in ((HOOK, HOOK_BRANCH), (HOOK2, HOOK2_BRANCH)):
        hook_line = f"mem set 0x{site:08X} 0x{branch:08X}"
        if output.count(hook_line) != 1:
            raise SystemExit(f"hook 0x{site:08X} must be armed exactly once")
        if output.find(hook_line) > output.find("# --- done "):
            raise SystemExit(f"hook 0x{site:08X} is not armed before the banner")

    prefix = output[:output.find(section)]
    for address, _ in parse_mem_sets(prefix):
        if CODE <= address < CAVE_END:
            raise SystemExit(
                f"canonical shell overlaps open-gate cave at 0x{address:08X}"
            )

    for address in DIAGNOSTIC_HOOKS:
        if f"mem set 0x{address:08X}" in output:
            raise SystemExit(f"diagnostic hook unexpectedly present: 0x{address:08X}")

    for unwanted in ("mem save", "display colorbar"):
        if any(line.startswith(unwanted) for line in output.splitlines()):
            raise SystemExit(f"unwanted command in AutoRun: {unwanted}")


def pad_bytes(text: str) -> bytes:
    raw = text.encode("utf-8")
    if len(raw) > PAD_TO:
        raise SystemExit(
            f"AutoRun is {len(raw)} bytes, past the {PAD_TO} byte fixed size"
        )
    filler = b"# pad: fixed size prevents a non-truncating overwrite leaving old commands\n"
    while len(raw) + len(filler) <= PAD_TO:
        raw += filler
    remaining = PAD_TO - len(raw)
    if remaining == 1:
        raw += b"\n"
    elif remaining > 1:
        raw += b"#" * (remaining - 1) + b"\n"
    if len(raw) != PAD_TO or not raw.endswith(b"\n"):
        raise SystemExit("fixed-size AutoRun padding failed")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--fragment", type=pathlib.Path, default=DEFAULT_FRAGMENT)
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    verify_firmware()
    labels = label_patches(FIRMWARE.read_bytes())
    blob = assemble(SOURCE)
    blob2 = assemble(SOURCE2)
    if words(blob2)[-1] != 0xE12FFF1E:
        raise SystemExit("dispfit payload does not end with bx lr")
    if CODE2 + len(blob2) > DESC:
        raise SystemExit("dispfit payload would reach the descriptor buffer")
    if len(blob) != 232:
        raise SystemExit(f"unexpected v4 payload size {len(blob)}; expected 232")
    if words(blob)[-2:] != (0xE1A00004, 0xE12FFF1E):
        raise SystemExit("payload does not end with displaced mov and bx lr")
    if sha256(blob) != PAYLOAD_SHA256:
        raise SystemExit(
            f"unexpected v4 payload sha256 {sha256(blob)}; "
            f"expected {PAYLOAD_SHA256}"
        )
    for code, site, branch in ((CODE, HOOK, HOOK_BRANCH),
                               (CODE2, HOOK2, HOOK2_BRANCH)):
        displacement = (code - site - 8) >> 2
        calculated_branch = 0xEB000000 | (displacement & 0x00FFFFFF)
        if calculated_branch != branch:
            raise SystemExit(
                f"hook 0x{site:08X} branch mismatch: "
                f"calculated 0x{calculated_branch:08X}, expected 0x{branch:08X}"
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.fragment.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="open-gate-autorun-") as temp_dir:
        base_path = pathlib.Path(temp_dir) / "AutoRun.base.txt"
        command = (
            sys.executable,
            str(SHELL_BUILDER),
            "--out", str(base_path),
            "--banner", "fpOGtest!",
            "--no-ep-patches",
            "--no-pad",
        )
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"canonical shell builder failed: {completed.returncode}")
        base = describe_minimal_usb_shell(base_path.read_text(encoding="utf-8"))

    section = patch_section(blob, blob2, labels)
    output = insert_before_done(base, section)
    validate_output(output, section, blob, blob2, labels)
    output_bytes = pad_bytes(output)
    args.out.write_bytes(output_bytes)
    args.fragment.write_text(section, encoding="utf-8")

    manifest = "\n".join((
        "Sigma fp 3032x2012 @29.97 open-gate TEST AutoRun",
        "",
        f"AutoRun.txt bytes={len(output_bytes)} sha256={sha256(output_bytes)}",
        f"rowpatch_v4 bytes={len(blob)} sha256={sha256(blob)}",
        f"dispfit bytes={len(blob2)} sha256={sha256(blob2)}",
        f"reference_firmware bytes={FIRMWARE_BYTES} sha256={FIRMWARE_SHA256}",
        "firmware=Sigma fp Ver.5.02 only; build-time check passed; runtime guard=none",
        f"hook=0x{HOOK:08X} stock=0x{HOOK_STOCK:08X} branch=0x{HOOK_BRANCH:08X}",
        f"code=0x{CODE:08X}..0x{CODE + len(blob):08X}",
        f"hook2=0x{HOOK2:08X} stock=0x{HOOK2_STOCK:08X} branch=0x{HOOK2_BRANCH:08X}",
        f"code2=0x{CODE2:08X}..0x{CODE2 + len(blob2):08X}",
        f"menu_label_words={len(labels)} id=0314 "
        f"{LABEL_OLD.decode()!r}->{LABEL_NEW.decode()!r}",
        "mode=117 boot / mode=98 via picker; size=3032x2012 fps=29.97003",
        "recording preset=FHD 29.97 CinemaDNG",
        f"causal_data_patches={len(DATA_PATCHES)}; downstream movie/still size tables omitted",
        "diagnostic_hooks=none",
        "USB while active=direct mem get/set only; never getfile/putfile/inject/callfn",
        "capture retrieval=fully power off, then use a card reader",
        "restore=remove or rename AutoRun.txt, then fully power-cycle",
        "",
    ))
    args.manifest.write_text(manifest, encoding="ascii")

    print(f"built {args.out} ({len(output_bytes)} bytes, fixed size)")
    print(f"sha256 {sha256(output_bytes)}")
    print(f"payload {len(blob)} bytes at 0x{CODE:08X}; hook armed last")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
