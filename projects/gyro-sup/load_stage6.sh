#!/bin/sh
# Swap the gyro logger over the USB shell, without a reboot.
#
# The shell's AutoRun carries the shell.  Everything here -- the logger, the
# parking stub its writer thread needs so the code underneath it can be
# replaced -- is placed by this script, over USB, at development time.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SHELL_DIR="$HERE/../fpSup/fp_usb_shell"
POOL=$(cd "$SHELL_DIR" && python3 -c "
import sys; sys.path.insert(0,'.')
import putfile as P; print('0x%08X' % (P.mem_get(0xC3757A7C)[0] + 0x6000 + 0x7C))")
echo "  state 0x$(printf %s "$POOL" | sed 's/^0x//')"
cd "$SHELL_DIR"
exec ./load.py "$HERE/stage6_gyro_double_buffer_hook.S" \
    --entry stage6_hook --hook 0xC00D0794 \
    --resident-task S6GFWR --park-state "$POOL" \
    --park-stub "$SHELL_DIR/asm/park.S" --park-resume writer_resume "$@"
