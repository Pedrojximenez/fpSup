#!/usr/bin/env python3
"""Build a card that boots the USB shell and the gyro logger together.

    ./codex/build_stage6_autorun.py

The shell's own builder knows how to place a payload in the cave and arm it; it
does not know or care that this one is a gyro logger.  Everything specific --
which source, which entry symbol, the parking stub the writer thread needs so
its code can be replaced without a power cycle -- lives here, in the project it
belongs to.
"""
import pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parent / 'fpSup' / 'fp_usb_shell' / 'build_autorun.py'

LOGGER = HERE / 'stage6_gyro_double_buffer_hook.S'
PARK   = HERE / 'park_stub.S'
PARK_AT = 0xC072EF00        # above the logger, below the shell's worker state

if __name__ == '__main__':
    sys.exit(subprocess.call([
        sys.executable, str(SHELL),
        '--payload', str(LOGGER),
        '--entry', 'stage6_hook',
        '--also', f'0x{PARK_AT:08X}:{PARK}',
        '--out', str(HERE / 'autorun' / 'AutoRun.txt'),
    ] + sys.argv[1:]))
