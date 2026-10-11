# SIGMA fp 5.02 RAW false-color RAM hooks

This design is for a USB-shell-loaded RAM module. It does not require an SD
card, AutoRun, or persistent firmware modification.

## Confirmed hook points

### RAW completion

`FUN_c0429f18 @ 0xc0429f18` is installed by `FUN_c0429910()` as output 0's
completion callback. Its argument is a word address. The stock callback:

1. increments `MovSigProcess + 0x1c`;
2. converts the argument to a cached CPU address as
   `0x40000000 + (argument << 2)`;
3. stores that address at `MovSigProcess + 0x24`;
4. performs the normal state transition checks.

The hook must call the original function, publish the converted address to the
mailbox, and return immediately. Geometry/format discovery must not run inside
this callback.

### OSD drawing

`FalseColorBarDrawer::v1 @ 0xc057db98` receives an indexed drawing surface, but
runtime probing proved that it is not the live-view false-color path. It is a
child of `UicGuiMenuFalseColor` and paints only the legend/bar in the
false-color adjustment menu. The stock implementation still proves:

- indexed pixels are one byte;
- row stride is `0x400` (1024 pixels);
- `FUN_c0529bd8()` constructs the drawing view;
- `FUN_c0529c80(view, {x,y})` returns a writable pixel address.

This function must not be the production overlay hook. The normal activation
chain is `SetFalseColorType -> FUN_c0402280 -> FUN_c005dba0 -> FUN_c00641e8`;
the full-frame live-view colorizer is controlled below ordinary OSD through the
AE/display-image path. A generic always-active draw/present hook must be used
to blit the RAW mask.

Runtime probe result: in 45 seconds of idle live view,
`FUN_c05276f0` counted 2936 cyclic callbacks (~65.2 Hz) and
`FUN_c0528700` counted 976 registered-drawer dispatches (~21.7 Hz). This is the
expected 3:1 cadence implemented by the cyclic callback. Registering a private
`XC_DrawInterface` with `CYC_DRAW` is now the preferred overlay architecture.

The stock setup method `FalseColorBarDrawer::v2 @ 0xc057db40` uploads the
256-entry palette stored at `0xc0d1b34c`. Indices 0..195 are populated; 196..255
are zero and unused by both stock false-color bars. The prototype preserves the
stock table and assigns RAW false-color entries 196..216.

## USB shell activation sequence

1. Allocate executable RAM and separate data RAM.
2. Upload the core, mailbox, OSD renderer, state and two hook trampolines.
3. Resolve and validate the original instruction words at both hook sites.
4. Read the live-view descriptor once; reject unsupported geometry/format.
5. Install the draw hook but leave rendering disabled. Confirm draw counters.
6. Install the RAW callback hook. Confirm monotonic RAW completion counters and
   addresses inside the expected RAM ranges.
7. Start the low-priority worker and enable overlay publication.

Disable in reverse order: stop publication, remove the RAW hook, wait for the
worker to become idle, remove the draw hook, restore the stock palette, then
free RAM. A watchdog counter must automatically stop rendering if RAW callbacks
or draw callbacks cease advancing.

## Remaining live checks

- Confirm output 0 is Bayer RAW in every intended normal movie mode.
- Read the active descriptor's width, height, format and Bayer phase after each
  mode change.
- Confirm the usable OSD image rectangle for LCD and HDMI separately; only the
  1024-byte stride is currently proven.
- Calibrate mode-specific black and saturation levels. Until then, clipping
  thresholds must be marked provisional.
