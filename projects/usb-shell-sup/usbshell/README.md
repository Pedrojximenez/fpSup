# USB shell

A command channel to the SIGMA fp over USB, built on the camera's **own PTP
gadget**. The firmware builds the descriptors, creates and enables the endpoints,
and re-creates them after a record-mode reconfiguration — so the channel is not
torn down by recording, which is what killed the previous design.

Two words of firmware are changed. Everything else is our code.

## What the patch does

| address | from → to | why |
|---|---|---|
| `0xC0CF3740` | `03 06 01 01` → `03 ff ff ff` | The PTP interface template's `{bNumEndpoints, class, subclass, protocol}`. Lengths and the endpoint set are untouched; this only stops the host's PTP stack from claiming interface 0 first. |

To undo: delete that `mem set` line from the AutoRun and reboot.

### Why the class handler is left alone

Removing it looks free — `FUN_c04dbc10` answers only the PTP class control
requests `0x64`/`0x66`/`0x67` on EP0 and never touches a bulk endpoint. It is
not. Registration (`FUN_c01e8658`) copies the handler table into globals, entry 4
landing at `0xC30257C0`, and the control path at `0xC01E8268` null-checks it and
takes `FUN_c01e3fa0` — a stall — when it is NULL.

Two boots confirmed it: with that slot NULL the link trains at SuperSpeed and
SOFs run, but the host never assigns an address (`DCFG` DEVADDR 0, `DALEPENA`
0x003), and that held for both the vendor and the PTP descriptor builders. A stub
returning 0 stalls the same way, so the handler has to stay.

## Endpoints

Taken from the PTP gadget, and checked against the firmware's own bulk transfer
routine at `0xC01E5BC0`, which arms them the same way:

```
EP 0x01 OUT bulk   logical 1   physical 2   TRB ptr @ 0xC31E3268
EP 0x82 IN  bulk   logical 2   physical 5   TRB ptr @ 0xC31E326C
EP 0x83 IN  interrupt — exists, untouched

physical      = (logical << 1) | (direction == IN)
TRB buffer    = CPU address - 0x40000000
TRB control   = 0x813
```

## Commands

One: `shl <line>`. It runs `<line>` in the firmware's own shell and returns what
it printed, so `mem set` and `mem save` come along for free and the worker needs
no memory commands of its own.

## Protocol

FPSH v1, 64-byte frames, little-endian.

```
+00 magic "FPSH"   +04 version   +05 command   +06 flags
+08 sequence       +0C payload_length          +0E status
+10 crc32 (whole frame with this field zeroed)
+14 payload, 44 bytes
```

* A reply may span several frames: **flags bit 0 means another frame follows**.
* A command may be longer than 44 bytes — the camera reads it as a
  NUL-terminated string and the OUT TRB is 1 KiB, so the text may run past byte
  64 of the same transfer. The CRC still covers only the first 64 bytes.

## On-screen state

Two commands are needed, and the second is the one that makes anything appear:

```
display text <token>      draws into the OSD surface; a single token, because
                          the shell splits on spaces and keeps only the first
display osd 1 <ARGB>      composites the layer and sets the text colour
display osd 0             turns the layer off — the text disappears with it
```

Text drawn while the layer is off is never shown, which is what made this look
like a repaint problem at first. The colour is the text colour, so `0x00000000`
is fully transparent and looks like a blank screen. Changing camera mode wipes
the layer, so this is a boot-time indicator, not a persistent marker.

| screen | meaning |
|---|---|
| `fpSup_LOADING` (amber) | the script is running — and if it stays, the load stopped early |
| `fpSup_FINISH` (green) | production script finished |
| `fpSup_ATTACH_USB` (amber) | diagnostic script is in its 45-second window; plug the cable in |
| `fpSup_DUMPED` (green) | diagnostic dumps are on the card; power off and read it |

Clear it by hand with `./fpsh display text` followed by `./fpsh display osd 0`.

## Running code on the camera

The shell can write memory but nothing can call it, so there is no `call`
command and no need for one. To run something, point an address the firmware
already calls at your routine, let it fire once, and put the original word back.
`oneshot.S` is that plumbing with a payload slot; `inject.py` writes it, arms the
call site and waits for it to report back. Neither the AutoRun nor the daemon is
involved — it is all `mem set` and `mem get` through the shell.

```sh
# edit the payload in oneshot.S, then
./inject.py oneshot.S
./fpsh mem get 0xC072F500,,0x20     # whatever the payload left behind
```

Verified 2026-08-25: 116 bytes injected, fired within a second, result correct,
call site restored, shell untouched.

The borrowed site is the gyro callback at `0xC00D0794` (50-90 Hz). The payload
runs in that callback's context, so treat it as interrupt-ish: do not block and
do not take a mutex. Work that needs task context should start a task from
there instead.

```
0xC072F500  parameters and results, 256 bytes
0xC072F600  the routine, up to 0xC0730000
```

## Files

```
worker.S            camera side, loaded at 0xC072E000
armasm.py           assembles ARM source and resolves its internal calls
build_autorun.py    assembles worker.S and emits the card script
oneshot.S           template for running a routine once, from the host
inject.py           writes a one-shot routine, arms it, waits for it
lsdesc.c / lsdesc   print the descriptor the host actually received
fpshd.c             host daemon, listens on /tmp/fpshd.sock
fpsh                client
dist/AutoRun.txt    what goes on the card
dist/AutoRun.diag.txt  same, plus a 45 s window and state dumps to the card
```

Nothing here imports from the old `fpshell_tool` tree.

## Camera memory

```
0xC072E000..0xC072E464   worker code
0xC072F000..0xC072F03F   state, 16 words
0xC072F040               capture length
0xC072F080..0xC072F47F   capture buffer, 1 KiB
```

`0xC072F480` upwards is free for hook-push routines.

Worker state, readable with `fpsh mem save \VSHL.BIN 0xC072F000,,0x40`:

```
+00 'VSHL'    +04 task id     +08 start result  +0C rounds
+10 OUT arm   +14 OUT wait    +18 IN arm        +1C IN wait
+20 served    +24 faults      +28 gate holds    +2C last USB_STATE
```

## Use

```sh
make                       # builds fpshd and both AutoRun scripts
make card CARD=/Volumes/fpSup            # production script
make card CARD=/Volumes/fpSup DIAG=1     # diagnostic script

# Boot with USB UNPLUGGED. The screen reads fpSup_LOADING while the script
# runs and fpSup_FINISH when it is done; then attach the cable.
./fpshd &
./fpsh ping
./fpsh mem save \\VSHL.BIN 0xC072F000,,0x40
```

Boot order matters: the gadget is built when USB is attached, so the patches have
to land first, and the patched words sit in code that has not run yet, so no
stale instruction-cache line can shadow them.

## Not migrated yet

The hook-push feature code (`../fpshell_tool/camera/*.S` for gyro, lens and
telemetry, and `../fpshell_tool/monitor/*`) still targets the old endpoint —
`CTX4_TBL 0xC31E3274` and `StartTransfer(9)`. On this gadget those become
`0xC31E326C` and `StartTransfer(5)`. Nothing in this directory depends on them.
