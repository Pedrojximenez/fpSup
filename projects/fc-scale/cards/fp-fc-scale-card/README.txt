sigma-fp-lab: False Color / EL Zone toggle with the EL Zone scale
SIGMA fp, firmware Ver.5.02 only. Not the fp L.

Card contents: AutoRun.txt only. No VSHL.BIN, no USB shell. The code is
carried in the AutoRun and lives in RAM.

Setup
  1. Menu -> Custom -> button settings -> assign False Color to a button.
  2. Copy AutoRun.txt to the SD card root. Keep only one AutoRun.txt.
  3. Battery out for 10 s, battery in, power on with the card. Boot takes
     about 30 s longer than stock while the AutoRun runs.

Use, on the button assigned to False Color
  press 1  False Color / EL Zone on, and it stays on
  press 2  the EL Zone scale across the bottom of live view
  press 3  both off
  EL Zone or False Color is your own False Color Style setting.

The scale is the firmware's own: band positions and colours from the
FalseColorBarDrawer tables (0xC0D1B74C, palette 0xC0D1B34C), label glyphs
from the ElZoneScale scene, drawn on the 16-bit main OSD layer.

Reverting, and between builds
  Remove AutoRun.txt and cold boot with the battery out ~10 s. A soft power
  cycle does not clear RAM on this camera: always pull the battery when
  changing to a different AutoRun, or the previous build keeps running.

RAM-only, nothing is flashed. Do not use on a paid job.
