# Shutter-angle nominal-FPS routing (SIGMA fp 5.02)

This is shared firmware knowledge. OpenGate-specific implementation and camera
acceptance material belong under `projects/open-gate/`.

## Finding

The shutter-speed and shutter-angle controls converge only after separate
property/event paths. In `FUN_c0208ec0`:

- the shutter-speed branch (`out/decomp/full/blk_c02.c:8207-8265`) uses the
  requested Tv/fraction directly and does not query sensor-mode `+0x40`;
- the shutter-angle branch (`blk_c02.c:8335-8370`) obtains the current mode and
  calls `FUN_c032c750(mode)` at ARM callsite `0xC02092CC`;
- `FUN_c032c750` (`out/decomp/full/blk_c03.c:28717-28728`) returns the selected
  mode record's integer field at `+0x40`;
- the later angle conversion is nominal-fps × 3600 / angle.

The stock word at `0xC02092CC` is `0xEB048D1F`, a `BL 0xC032C750`.
Mode 98's field is `0xC0B59EC8 = 78`, while the normal 29.97 movie mode 106
reports 30. A feature that reuses mode 98 with another timing must therefore
provide the selected nominal FPS to the angle branch or it will calculate the
wrong shutter time.

For 180° shutter, using 78 instead of the selected timing predicts:

| Actual FPS | Stock error |
|---:|---:|
| 23.976 | -1.702 EV |
| 24 | -1.700 EV |
| 25 | -1.642 EV |
| 29.97 | -1.380 EV |
| 48 | -0.700 EV |
| 50 | -0.642 EV |
| 59.94 | -0.380 EV |

Mode 117 already reports 100, so a 100 fps mode is a useful zero-correction
control.

## Safe interception boundary

Patch the single `0xC02092CC` callsite, not the global getter and not the shared
mode record. The getter has roughly 55 callers across AE, metadata, UI, and
sensor scheduling; mode 98 is also used by still capture. The narrow wrapper
should still call the stock getter first, preserving any synchronization or
lazy initialization, and then override only its return value.

If a feature changes the selected mode's timing record, the two complete timing
words are a stronger source than a separately published FPS latch. Require the
feature-active flag and an exact `(hmax|tail<<16, vmax|x<<16)` tuple from a
whitelist. A mixed, unknown, stock, or damaged tuple must return the stock
getter result. Update the two words as one interrupt-masked transaction and
restore the stock tuple before leaving the feature; a standalone latch can
otherwise remain valid while the format is already changing.

Restoring on a resolution change does not by itself prove that a CINE/STILL
mode transition invokes the same setter. Treat that transition as a separate
hardware-acceptance case; until proven, leave a feature that borrows a still
mode record before switching out of CINE.

## Exposure metadata caveat

DNG `ExposureTime` is written from a per-frame latched request ring, not from
the final sensor-quantized integration field. It is useful for confirming the
angle conversion, but actual exposure still needs RAW-level comparison. The
sensor-side quantized shutter is available separately at runtime.

## Gain path boundary

RAW12 gain-state routing is independent of this angle conversion. State 7 uses
the ISO 3200 HCG threshold; state 3 uses ISO 640. ISO 100 keeps both in LCG and
is therefore a weak discriminator. ISO 800 is the useful control: a state-3
regression has a large, brighter fingerprint, rather than a 1.3-2 EV darker
angle-only result.
