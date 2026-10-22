#!/usr/bin/env python3
"""Build a minimal persistent firmware-task ABI probe AutoRun."""

import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from build_stage5_autorun import extract_and_relocate, words


ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / "camera" / "persistent_task_probe.S"
OUTPUT = ROOT / "dist" / "AutoRun_TaskProbe.txt"
LOAD = 0xC072E800
STATE = 0xC072E900
# Shell command-table handler slot for the `mem` command (name "mem\0" @0xC0BAC47C,
# handler word 4 bytes before; original value 0xC03F9C38). This is the ONLY table slot
# proven to be live-dispatched by the AutoRun shell (the `log` slot 0xC0BAC460 is NOT
# reached from this table). So we hijack `mem` -> starter, trigger it with a throwaway
# `mem save`, and the starter self-restores the real mem handler (0xC03F9C38) at entry so
# the second `mem save` (the real capture) works.
HANDLER_SLOT = 0xC0BAC478
MEM_HANDLER_ORIG = 0xC03F9C38


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        directory = pathlib.Path(temporary)
        obj = directory / "probe.o"
        subprocess.run(
            ["clang", "-target", "armv7-none-eabi", "-c", str(SOURCE), "-o", str(obj)],
            check=True,
        )
        code = extract_and_relocate(obj)
    if len(code) > 0x100:
        raise ValueError(f"task probe exceeds code slot: {len(code):#x}")
    lines = [
        "# FPShell persistent task ABI probe - SIGMA fp firmware 5.02",
        "# One flash=start; two flashes=probe snapshot saved.",
        "display monitor 0 1",
        "display colorbar 1 0",
        "ctrl sleep 500",
        "display colorbar 0 0",
    ]
    for index, word in enumerate(words(code)):
        lines.append(f"mem set {LOAD + index * 4:#010x} {word:#010x}")
    for offset in range(0, 0x40, 4):
        lines.append(f"mem set {STATE + offset:#010x} 0x00000000")
    lines.extend([
        f"mem set {HANDLER_SLOT:#010x} {LOAD:#010x}",
        # First mem command after the hijack lands in the starter: it restores the real
        # mem handler and creates the background task (this save writes no file).
        "mem save \\THRTRIG.BIN 0xC072E900,,0x40",
        "ctrl sleep 1500",
        # Mem handler is restored now -> this save actually captures the snapshot.
        "mem save \\THRPROBE.BIN 0xC072E900,,0x40",
        "display colorbar 1 0",
        "ctrl sleep 500",
        "display colorbar 0 0",
        "ctrl sleep 300",
        "display colorbar 1 0",
        "ctrl sleep 500",
        "display colorbar 0 0",
        "",
    ])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="ascii")
    print(f"code_size={len(code):#x}")
    print(f"output={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
