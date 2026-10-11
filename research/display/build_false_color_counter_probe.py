#!/usr/bin/env python3
"""Build the reversible SIGMA fp 5.02 RAW/false-color callback probe."""

from pathlib import Path
import struct
import subprocess
import tempfile

LOAD = 0xC072DE64
DRAW_OFFSET = 0x80
RAW_HOOK = 0xC0429F18
DRAW_HOOK = 0xC057DB98
RAW_ORIGINAL = 0xE92D48F0
DRAW_ORIGINAL = 0xE92D4EF0
STATE = 0xC072E500


def branch(source: int, target: int) -> int:
    displacement = target - source - 8
    if displacement % 4 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("ARM branch out of range or unaligned")
    return 0xEA000000 | ((displacement >> 2) & 0xFFFFFF)


def extract_text(obj: Path) -> bytes:
    data = obj.read_bytes()
    hdr = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    shoff, shentsize, shnum, shstrndx = hdr[6], hdr[11], hdr[12], hdr[13]
    sections = [struct.unpack_from("<IIIIIIIIII", data, shoff + i * shentsize) for i in range(shnum)]
    names_sec = sections[shstrndx]
    names = data[names_sec[4]:names_sec[4] + names_sec[5]]
    for sec in sections:
        end = names.find(b"\0", sec[0])
        name = names[sec[0]:end] if sec[0] else b""
        if name == b".text":
            return data[sec[4]:sec[4] + sec[5]]
    raise ValueError("no .text section")


def words(blob: bytes):
    blob += b"\0" * (-len(blob) % 4)
    return struct.unpack(f"<{len(blob)//4}I", blob)


def main():
    with tempfile.TemporaryDirectory() as td:
        obj = Path(td) / "probe.o"
        subprocess.run(["clang", "-target", "armv7-none-eabi", "-c", "false_color_counter_probe.S", "-o", str(obj)], check=True)
        code = extract_text(obj)
    if len(code) > STATE - LOAD:
        raise ValueError(f"probe overlaps state: {len(code):#x}")

    lines = [
        "# SIGMA fp Ver.5.02 RAW/false-color callback counter probe",
        "# 1 pulse=start; 2 pulses=hooks armed; one long pulse=test saved/restored.",
        "# RAM-only; records counters, never reads or modifies RAW pixels.",
        f"mem set {RAW_HOOK:#010x} {RAW_ORIGINAL:#010x}",
        f"mem set {DRAW_HOOK:#010x} {DRAW_ORIGINAL:#010x}",
        "display monitor 0 1",
        "display colorbar 1 0", "ctrl sleep 700", "display colorbar 0 0", "ctrl sleep 400",
    ]
    for i, word in enumerate(words(code)):
        lines.append(f"mem set {LOAD + 4*i:#010x} {word:#010x}")
    init = [0x31504346, 0, 0, 0, 0xFFFFFFFF, 0, 0, 0, 0, 0, 0, 0x00050201]
    for i, word in enumerate(init):
        lines.append(f"mem set {STATE + 4*i:#010x} {word:#010x}")
    lines += [
        f"mem save \\FCPCODE.BIN {LOAD:#010x},,{len(code):#x}",
        f"mem set {RAW_HOOK:#010x} {branch(RAW_HOOK, LOAD):#010x}",
        f"mem set {DRAW_HOOK:#010x} {branch(DRAW_HOOK, LOAD + DRAW_OFFSET):#010x}",
        "display colorbar 1 0", "ctrl sleep 500", "display colorbar 0 0", "ctrl sleep 300",
        "display colorbar 1 0", "ctrl sleep 500", "display colorbar 0 0",
        "# Observation window: leave Live View running and toggle stock False Color once.",
        "ctrl sleep 45000",
        f"mem set {RAW_HOOK:#010x} {RAW_ORIGINAL:#010x}",
        f"mem set {DRAW_HOOK:#010x} {DRAW_ORIGINAL:#010x}",
        "ctrl sleep 200",
        f"mem save \\FCPROBE.BIN {STATE:#010x},,0x40",
        "display colorbar 1 0", "ctrl sleep 1200", "display colorbar 0 0", "",
    ]
    out = Path("AutoRun_false_color_counter.txt")
    out.write_text("\n".join(lines), encoding="ascii")
    print(f"code_size={len(code):#x}")
    print(f"raw_hook={branch(RAW_HOOK, LOAD):#010x}")
    print(f"draw_hook={branch(DRAW_HOOK, LOAD + DRAW_OFFSET):#010x}")
    print(out)


if __name__ == "__main__":
    main()
