#!/usr/bin/env python3
"""Read-only dump of the flash defect buffer the firmware keeps in RAM (*0xC343A71C, 0x40000 B; DEFECT_CORRECTION §3).
Nothing is written. If the pointer is 0 the buffer is not loaded yet (it loads lazily on the first mode switch).

    defect_dump.py OUT.bin
"""
import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B

ptr = B.P().mem_get(0xC343A71C)[0]
if not ptr:
    raise SystemExit('defect buffer not loaded (pointer 0)')
B.P().mem_window(B.WIN, ptr, 0x40000, 1)                    # MEM1 reads need a window (read-only)
try:
    data = B.P().mem_read(ptr, 0x40000, label='defect')
finally:
    B.P().mem_window(B.WIN, ptr, 0x40000, 0)
pathlib.Path(sys.argv[1]).write_bytes(data)
print(f'buffer at 0x{ptr:08X}: {len(data)} B -> {sys.argv[1]}')
