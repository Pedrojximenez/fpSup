# OpenGate UI recording A/B

Date: 2026-09-14 (Asia/Taipei)
Camera target: SIGMA fp firmware `5.02.0.V91`

This directory contains project-coupled recording regression material.  It is
not a product release.  The experiment isolates the native UI runtime from the
current OpenGate core without changing the USB loader, worker, boot sequence,
banner, or any shared OpenGate word.

## A — full UI candidate

Source directory: `../ui_runtime_candidate/`

- `AutoRun.txt`: SHA-256
  `3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53`
- `VSHL.BIN`: SHA-256
  `583190c93bc56aa5b1429d9a61a22d72d5dd6715314c5d26005c7fd32f22ab06`
- VSHL: 75 sections, entry `0xC072F188`, 14,492 used bytes

## B — core-only control

Generated with the existing project builder:

```text
build_og3k_gyro.py --no-gyro --out ui_recording_ab/core_only --banner OG3K-UI-test!
```

Re-run `../verify_og3k_ui_ab.py` after either package is rebuilt.  It decodes
both VSHL maps and enforces every invariant below; it does not install anything.

- `AutoRun.txt`: bit-identical to A, including its banner
- `VSHL.BIN`: SHA-256
  `a282522f727f4197038726bae9e586daf14e4b987dec1706c5a184afc66eda18`
- VSHL: 69 sections, entry `0xC072F188`, 4,688 used bytes

The A/B write maps were decoded independently after generation.  Every address
shared by A and B has the same value; B has no B-only words.  A is a strict
superset with 2,439 UI-only words in exactly these ranges:

```text
0xC05E5B58..0xC05E5B5B  UI string resolver hook
0xC05E6400..0xC05E6403  NBU record interpreter hook
0xC05E84D8..0xC05E84DB  NBR memory-loader hook
0xC0732700..0xC0732747  UI runtime state
0xC0732C84..0xC07343B7  UI runtime code and record table
0xC0793060..0xC0793EF3  private OG3K NBR pack
```

The B package does not hot-unhook A.  Switching either direction requires a
real cold boot: USB and external power disconnected, battery removed for at
least 30 seconds, boot without USB, then reconnect USB only after startup.

## Fixed test matrix

Use the same media, recording format, bit depth, frame rate, USB condition, and
duration for every cell.  On the currently installed SD card, cap UHD and OG3K
at about one second; sustained tests require faster media.  A remote recording
toggle is two complete button presses, and each complete press is
`MOVON` → about 120 ms → `MOVOFF`.  `MOVOFF` alone does not stop recording.

After the failure boundary is known, run at least three equal-duration takes per
cell in ABBA order:

1. B, core-only.
2. A, full UI, without opening Quick Set or Record Settings after boot.
3. A, full UI, after opening Quick Set and Record Settings so target UI records
   have been parsed.
4. B, core-only again.

If both B cells pass but either A cell freezes, the regression belongs to the
UI-only ranges above.  If only the post-UI A cell freezes, prioritize modified
record lifetime and the private NBR pack.  If A and B both freeze, investigate
OpenGate core, media, or the common USB worker instead of attributing it to UI.
Use a separate no-shell/manual-REC lane only when specifically isolating the USB
worker; mixing USB-connected and disconnected cells inside one ABBA invalidates
that comparison.

## Current evidence

- The user's first full-UI OG3K recording attempt created `CINEMA/A001_082`
  and then froze.  The user recovered by removing the battery.
- Card readback after recovery matched both A source files byte for byte.
- A cold boot loaded all three A hooks and its payload.
- A controlled, second-draw Quick Set probe loaded `OG3K_FONT.xci` at 150x38
  and `OG3K_QS.xci` at 86x49.
- Runtime state after that probe reported private pack ready, 24,411 stock NBU
  records, 164 exact copies, and the expected 164-bit active Quick Set set.
- The first attempted FHD control ran longer than intended because `MOVOFF` was
  initially mistaken for a dedicated stop event.  A second complete MOV press
  stopped it; it did not freeze.  This corrected a shared USB-control procedure.
- With the correct two-pulse control, A completed three OG3K takes at
  1.004/1.004/1.002 seconds between start and stop pulses and three UHD takes at
  about 1.005 seconds each.  The outer containers are `A001_084..A001_089`; all
  six post-checks reported `is_recording -> 0`.
- After all seven recording transitions, a clean Quick Set draw again loaded
  both OG3K assets.  Runtime state remained on the same context with pack ready;
  stock parser count advanced from 24,411 to 34,537 while exact copies and the
  active bitmap remained 164.
- A therefore passes immediate FHD/UHD/OG3K record transitions in this run.  It
  does not yet pass sustained writing or clip-content validation, and the
  original `A001_082` freeze remains non-reproduced.
- B was generated and structurally compared but was not installed because A no
  longer reproduced the fault.  Keep B for the next recurrence or a future
  faster-media duration run.
