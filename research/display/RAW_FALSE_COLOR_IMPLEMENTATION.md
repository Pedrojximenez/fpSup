# SIGMA fp RAW-aware false color implementation

Status: host-tested RAW core, callback mailbox and indexed-OSD renderer. No SD
card or AutoRun payload has been generated.

## Confirmed firmware facilities

- `XC_LiveViewSmallRawManage` owns a non-cache RAW buffer and exposes a
  `XC_LiveViewRawMemInterface` implementation.
- `FUN_c0436418()` allocates that buffer from memory type 3.
- Live-view RAW geometry is described by `XC_LiveViewStateRawInfo`; the firmware
  already carries width, height, Bayer readout/binning, zoom and bit-depth data.
- `FUN_c0020830()` installs `FUN_c03d9630()` as the RAW allocation-size
  provider. The latter reads descriptor words 0/1/8 as width/height/format.
- For the ordinary (non-tiled) formats, `FUN_c0135db8()` proves the row packing:
  format 0 = RAW12 (1.5 bytes/pixel), 1 = RAW14 (1.75), 2 = RAW16 (2),
  3 = RAW10 (1.25), and 4 = RAW8 (1). Rows are 4-byte aligned; the allocation
  formula pads the final row's width to a multiple of 12 pixels.
- The existing `XC_DrawInterface` path can display an 8-bit palette surface and
  is used by `FalseColorBarDrawer`.

## Prototype design

`raw_false_color_core.c` reads sparse 2x2 Bayer cells from each tile. It does
not copy or modify the source RAW buffer. It produces one palette index per
tile and uses only integer arithmetic.

`raw_false_color_runtime.c` adds a seqlock-style single-producer/single-consumer
mailbox. The RAW-completion hook only publishes the latest address and returns;
a worker consumes the newest complete frame and silently drops stale frames.
This keeps false color out of the real-time SigProcess callback.

`raw_false_color_osd.c` provides the draw-thread half. The existing false-color
drawer uploads a 256-entry palette from `0xc0d1b34c`; entries 0..195 are used
and entries 196..255 are transparent/unused. The prototype preserves 0..195,
places its 21 RAW zone/clip colors at 196..216, and expands the tile mask into
the indexed OSD surface without division or allocation.

The initially proposed display hook was `FalseColorBarDrawer::v1 @
0xc057db98`. Runtime probing later showed zero calls while normal live-view
false color was toggled. Static re-check explains the result: this object is
owned by `UicGuiMenuFalseColor`, and `v1` draws the 464-pixel-wide legend/bar
inside the adjustment menu. It is not the live-view image colorizer and must
not be used as the production frame-present hook.

The verified activation seam is instead
`SetFalseColorType -> FUN_c0402280 -> FUN_c005dba0 -> FUN_c00641e8`. The
live-view colorizer itself is selected below OSD through the AE/display-image
path (`AeSettingFalseColorBase`, `AeFalseColorBase`,
`INTR_START_FALSE_COLOR`, and `INTR_STOP_FALSE_COLOR`). A continuously active
generic draw/present hook is still required for a RAW-derived OSD mask.

The follow-up runtime probe identified that hook/registration path. During a
45-second idle live-view test, `FUN_c05276f0` (the cyclic draw callback) ran
2936 times and `FUN_c0528700` (the generic registered-drawer dispatcher) ran
976 times: about 65.2 Hz and 21.7 Hz respectively. The near-exact 3:1 ratio
matches `FUN_c05276f0`'s firmware counter, which requests a draw pass every
third cyclic tick. The production module can therefore register its own
`XC_DrawInterface` with `CYC_DRAW` and receive a current layer surface at a
stable ~21.7 fps without depending on the false-color adjustment menu.

The implementation accepts both an unpacked little-endian 16-bit view and the
native packed RAW10/12/14/16/8 layout. The bit ordering is confirmed by the
firmware's own shell pixel dumper: `FUN_c031e370()` dispatches to
`FUN_c031e470/FUN_c031e6b0/FUN_c031e800/FUN_c031ea78`. Pixels are consecutive
MSB-first fields across 32-bit CPU words (for example RAW12 pixel 2 is the low
8 bits of word 0 followed by the high 4 bits of word 1). The prototype mirrors
this with `rfc_analyze_packed()`.

The classifier reports individual R/G/B clipping before exposure zones. Zones
are calculated from black-subtracted green photosites, avoiding white balance,
color-matrix, gamma and picture-mode effects.

## Required live checks before enabling the overlay

1. Validate the confirmed per-frame completion callback in each target mode.
   The constructor path is confirmed
   inside `src/library/SigProcess/src/MovSigProcess.cpp`: `FUN_c0428ab8()`
   obtains `XC_LiveViewSmallRawManage`, wraps it in `SigManTr`, then invokes its
   start method. `FUN_c0429910()` installs `FUN_c0429f18()` into output-0's
   completion descriptor. On every callback, `FUN_c0429f18()` increments the
   completed-frame counter, converts the supplied word address into a cached
   CPU address with `FUN_c0022fb8()` (`addr * 4 + 0x40000000`), and stores it at
   `MovSigProcess + 0x24`. This is the strongest hook candidate: it is after DMA
   completion and already carries the completed RAW address. We still need to
   prove whether output 0 is the desired Bayer plane in every normal fp movie
   mode before installing a hook.
2. Snapshot the active `XC_LiveViewStateRawInfo` and validate address, stride,
   width, height, bit depth and Bayer pattern against the callback buffer.
3. Read optical-black levels from the existing four-channel globals and find
   the mode-specific sensor white level.
4. Allocate two small palette masks and atomically swap completed masks.
5. Confirm the usable LCD and HDMI rectangles. The existing false-color drawer
   removes the need to register a new draw object.
6. Measure the worker budget and choose the initial analysis cadence.

The first USB-shell run should install counter-only hooks. Pixel reads and OSD
writes remain disabled until checks 1 and 2 pass.

The concrete firmware-5.02 hook and unload sequence is maintained in
`SIGMA_FP_V502_RAW_FALSE_COLOR_HOOKS.md`.
