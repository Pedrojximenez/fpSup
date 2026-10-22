#!/usr/bin/env python3
"""Build the cold-boot probe for the GUI resource-parser timing question.

The append observer is emitted before every USB-shell command.  That ordering is
the point of this probe: a zero-hit result is useful only when the hook was armed
as early as AutoRun can possibly arm it.  The shell is loaded afterwards from
fpSup.BIN so the log can be inspected once boot has finished.

By default build products stay with the reusable UI research.  A project can put
its concrete test card with its own integration material via --out-dir.
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
ROOT = HERE.parents[2]
SHELL_DIR = ROOT / "fpSup" / "fp_usb_shell"
SHELL_BUILDER = SHELL_DIR / "build_autorun.py"
SOURCE = HERE / "appendobs.S"
FIRMWARE = ROOT / "out" / "MAIN_c0000000.bin"
DEFAULT_OUT_DIR = ROOT / "research" / "ui" / "build" / "appendobs_boot_probe"

sys.path.insert(0, str(SHELL_DIR))
from armasm import assemble, symbols  # noqa: E402


FIRMWARE_BASE = 0xC0000000
FIRMWARE_BYTES = 49_482_954
FIRMWARE_SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"

CODE = 0xC0733000
SLOTP = 0xC07330F0
LOGBEG = 0xC0733100
LOGEND = 0xC0734000
SITE = 0xC05E2CA8
SITE_STOCK = 0x4605B530
SITE_BRANCH = 0xB9AAF150

PAD_TO = 32_768
COMMAND_LIMIT = 648
COMMAND_BUDGET = 560
MEM_SET_RE = re.compile(r"^mem set 0x([0-9A-Fa-f]{8}) 0x([0-9A-Fa-f]{8})$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words(blob: bytes) -> tuple[int, ...]:
    if len(blob) % 4:
        raise SystemExit(f"payload is not word aligned: {len(blob)} bytes")
    return struct.unpack(f"<{len(blob) // 4}I", blob)


def firmware_word(image: bytes, address: int) -> int:
    offset = address - FIRMWARE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise SystemExit(f"address outside firmware image: 0x{address:08X}")
    return struct.unpack_from("<I", image, offset)[0]


def thumb_bw(site: int, target: int) -> int:
    """Encode a Thumb-2 unconditional B.W (T4) as the camera reads the word."""
    offset = target - (site + 4)
    if not -(1 << 24) <= offset < (1 << 24) or offset & 1:
        raise SystemExit("Thumb B.W target is out of range or unaligned")
    s = (offset >> 24) & 1
    i1 = (offset >> 23) & 1
    i2 = (offset >> 22) & 1
    j1 = (~i1 ^ s) & 1
    j2 = (~i2 ^ s) & 1
    hw1 = 0xF000 | (s << 10) | ((offset >> 12) & 0x3FF)
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((offset >> 1) & 0x7FF)
    return hw1 | (hw2 << 16)


def parse_mem_sets(text: str) -> list[tuple[int, int]]:
    result = []
    for line in text.splitlines():
        match = MEM_SET_RE.fullmatch(line.strip())
        if match:
            result.append((int(match.group(1), 16), int(match.group(2), 16)))
    return result


def commands(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def probe_section(blob: bytes) -> str:
    lines = [
        "# --- GUI parser boot-timing observer; observation only ----------------",
        "# This must be the first executable section in AutoRun.",
        f"# appendobs.S: {len(blob)} bytes at 0x{CODE:08X}",
    ]
    for index, value in enumerate(words(blob)):
        lines.append(f"mem set 0x{CODE + index * 4:08X} 0x{value:08X}")
    lines += [
        "# Reset the write cursor; old bytes beyond it are deliberately ignored.",
        f"mem set 0x{SLOTP:08X} 0x{LOGBEG:08X}",
        "# Arm last. Stock is push {r4,r5,lr}; mov r5,r0.",
        f"mem set 0x{SITE:08X} 0x{SITE_BRANCH:08X}",
        "# --- END GUI parser boot-timing observer ------------------------------",
        "",
    ]
    return "\n".join(lines)


def verify_firmware(image: bytes) -> None:
    digest = sha256(image)
    if len(image) != FIRMWARE_BYTES or digest != FIRMWARE_SHA256:
        raise SystemExit(
            "reference firmware is not the verified Sigma fp Ver.5.02 image: "
            f"bytes={len(image)} sha256={digest}"
        )
    actual = firmware_word(image, SITE)
    if actual != SITE_STOCK:
        raise SystemExit(
            f"hook site 0x{SITE:08X} is 0x{actual:08X}, expected 0x{SITE_STOCK:08X}"
        )
    lo = CODE - FIRMWARE_BASE
    hi = LOGEND - FIRMWARE_BASE
    if any(image[lo:hi]):
        raise SystemExit(f"probe cave 0x{CODE:08X}..0x{LOGEND:08X} is not empty")


def verify_payload(blob: bytes) -> None:
    if CODE + len(blob) > SLOTP:
        raise SystemExit(
            f"payload 0x{CODE:08X}..0x{CODE + len(blob):08X} overlaps SLOTP"
        )
    entry = symbols(SOURCE).get("entry")
    if entry != 1:
        raise SystemExit(f"appendobs entry must be Thumb symbol at offset 0, got {entry!r}")
    branch = thumb_bw(SITE, CODE)
    if branch != SITE_BRANCH:
        raise SystemExit(
            f"Thumb B.W mismatch: calculated 0x{branch:08X}, expected 0x{SITE_BRANCH:08X}"
        )


def verify_vshl(blob: bytes) -> tuple[int, int]:
    if len(blob) != PAD_TO or blob[:4] != b"VBIN":
        raise SystemExit("fpSup.BIN is not the canonical fixed-size VBIN")
    _, count, entry, body_len = struct.unpack_from("<4sIII", blob)
    table_end = 16 + count * 8
    if table_end + body_len > len(blob):
        raise SystemExit("fpSup.BIN section table runs past the file")
    for index in range(count):
        address, size = struct.unpack_from("<II", blob, 16 + index * 8)
        if address == 0:
            continue
        if address < LOGEND and address + size > CODE:
            raise SystemExit(
                f"VSHL section {index} overlaps the probe cave: "
                f"0x{address:08X}..0x{address + size:08X}"
            )
        if address <= SITE < address + size:
            raise SystemExit(f"VSHL section {index} overwrites hook site 0x{SITE:08X}")
    return count, entry


def verify_output(text: str, section: str, blob: bytes) -> int:
    expected = [(CODE + index * 4, value) for index, value in enumerate(words(blob))]
    expected += [(SLOTP, LOGBEG), (SITE, SITE_BRANCH)]
    if parse_mem_sets(section) != expected:
        raise SystemExit("probe section does not follow payload -> cursor -> hook order")

    base = text[len(section):]
    for address, _ in parse_mem_sets(base):
        if CODE <= address < LOGEND or address == SITE:
            raise SystemExit(f"USB-shell base overlaps probe-owned address 0x{address:08X}")

    first = commands(text)[:len(expected)]
    wanted = [f"mem set 0x{address:08X} 0x{value:08X}" for address, value in expected]
    if first != wanted:
        raise SystemExit("probe is not the first executable section in AutoRun")
    hook_line = wanted[-1]
    if commands(text).count(hook_line) != 1:
        raise SystemExit("Thumb hook must be armed exactly once")

    command_count = len(commands(text))
    if command_count > COMMAND_BUDGET:
        raise SystemExit(
            f"{command_count} commands exceeds the conservative {COMMAND_BUDGET} budget "
            f"(measured hard limit {COMMAND_LIMIT})"
        )
    for unwanted in ("mem save", "ctrl sleep", "display colorbar"):
        if any(line.startswith(unwanted) for line in commands(text)):
            raise SystemExit(f"unwanted command in boot probe: {unwanted}")
    return command_count


def pad(text: str) -> bytes:
    raw = text.encode("utf-8")
    if len(raw) > PAD_TO:
        raise SystemExit(f"AutoRun is {len(raw)} bytes, past fixed size {PAD_TO}")
    filler = b"# pad: fixed size prevents a shorter overwrite leaving old commands\n"
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


def readme() -> str:
    return f"""# GUI resource-parser boot timing probe

This is an observation-only card for Sigma fp firmware Ver.5.02. It does not
install OG3K and does not change any capture setting. Its only question is
whether AutoRun can arm a hook before the one-time GUI resource parse.

## Card files

Copy `AutoRun.txt` and `fpSup.BIN` together. They are a matched pair; verify both
hashes against `MANIFEST.txt`. Back up and remove any existing card boot files
first instead of overwriting them in place.

## Run

1. Fully power off, remove the battery, and use a card reader to install the two
   files. This must be a cold boot, not a restart.
2. Boot with USB unplugged and wait for `UIBOOT!`.
3. Do not open Quick Set, change resolution, or switch screens before reading.
4. Attach USB and run from the SIGMAfp_re root:

   `python3 research/ui/tools/appendobs_ctl.py read`

The reader first verifies the complete {len(assemble(SOURCE))}-byte payload and
the hook word. Only then is the cursor interpreted:

- cursor above `0x{LOGBEG:08X}` on a 12-byte boundary: the observer saw boot-time
  resolution-array construction, so an append hook is viable;
- cursor exactly `0x{LOGBEG:08X}` with a valid payload and hook: AutoRun was too
  late for that construction pass;
- any payload, hook, or cursor mismatch: loading failed, so it is not a timing
  result.

The probe owns `0x{CODE:08X}..0x{LOGEND:08X}` and is mutually exclusive with the
other UI observer tools that use the same cave. Remove both files, restore the
backed-up card set, and cold boot to return to stock.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    image = FIRMWARE.read_bytes()
    verify_firmware(image)
    blob = assemble(SOURCE)
    verify_payload(blob)
    section = probe_section(blob)

    with tempfile.TemporaryDirectory(prefix="appendobs-boot-") as temp:
        temp_dir = pathlib.Path(temp)
        base_path = temp_dir / "AutoRun.txt"
        result = subprocess.run(
            (
                sys.executable,
                str(SHELL_BUILDER),
                "--out", str(base_path),
                "--banner", "UIBOOT!",
                "--no-ep-patches",
                "--no-pad",
                "--loader",
            ),
            check=False,
        )
        if result.returncode:
            raise SystemExit(f"canonical USB-shell builder failed: {result.returncode}")
        base = base_path.read_text(encoding="utf-8")
        vshl = (temp_dir / "fpSup.BIN").read_bytes()

    text = section + base
    command_count = verify_output(text, section, blob)
    section_count, entry = verify_vshl(vshl)
    autorun = pad(text)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "AutoRun.txt").write_bytes(autorun)
    (out_dir / "fpSup.BIN").write_bytes(vshl)
    (out_dir / "appendobs.fragment.txt").write_text(section, encoding="utf-8")
    (out_dir / "README.md").write_text(readme(), encoding="utf-8")

    manifest = "\n".join((
        "Sigma fp Ver.5.02 GUI resource-parser boot timing probe",
        "",
        f"AutoRun.txt bytes={len(autorun)} sha256={sha256(autorun)}",
        f"fpSup.BIN bytes={len(vshl)} sha256={sha256(vshl)}",
        f"appendobs.S bytes={len(blob)} sha256={sha256(blob)}",
        f"reference_firmware bytes={len(image)} sha256={sha256(image)}",
        f"commands={command_count} budget={COMMAND_BUDGET} measured_limit={COMMAND_LIMIT}",
        f"vshl_sections={section_count} entry=0x{entry:08X}",
        f"payload=0x{CODE:08X}..0x{CODE + len(blob):08X}",
        f"cursor=0x{SLOTP:08X} initial=0x{LOGBEG:08X}",
        f"log=0x{LOGBEG:08X}..0x{LOGEND:08X} slot=12 capacity={(LOGEND - LOGBEG) // 12}",
        f"hook=0x{SITE:08X} stock=0x{SITE_STOCK:08X} thumb_bw=0x{SITE_BRANCH:08X}",
        "effect=observation only; no OG3K or capture-setting patches",
        "order=appendobs payload, cursor initialisation, Thumb hook, USB-shell loader",
        "restore=remove both card files, restore the prior matched set, cold boot",
        "",
    ))
    (out_dir / "MANIFEST.txt").write_text(manifest, encoding="ascii")

    print(f"built {out_dir}")
    print(f"  appendobs {len(blob)} bytes  hook 0x{SITE_BRANCH:08X}")
    print(f"  AutoRun {len(autorun)} bytes  {command_count} commands")
    print(f"  fpSup.BIN {len(vshl)} bytes  {section_count} sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
