# SIGMA fp pre-Still RAW PDAF pattern analysis

## Inputs

- `PRESHOT000.BIN`: memory captured after RAW DMA and before `StillCreateRaw`
- `_SDI0042.DNG`: DNG produced from the same exposure
- Geometry: 6064 x 4042, 14-bit Bayer

## RAW memory layout

The buffer is tightly packed RAW14 with MSB-first bit ordering:

- four pixels per seven bytes
- each consecutive 14-bit field is one raster-order pixel
- no per-line padding (`6064 * 14 / 8 = 10612` bytes per row)

The first seven bytes decode as `1195, 1411, 1212, 1413`, matching the
corresponding DNG pixels closely. Decoding the full frame gives a correlation
of `0.99998646` with the DNG raw plane.

## Pre-RAW versus DNG

- Both green CFA planes match the DNG exactly, pixel for pixel.
- Red and blue receive a small, broad, intensity/spatially dependent change.
- The R/B change affects most pixels in those planes and is not a sparse fixed
  coordinate correction characteristic of replacing PDAF sites.

## Unknown-pattern scan

A same-colour local predictor was formed from symmetric neighbours at offsets
2 and 4. Residuals were grouped by `(y mod P, x mod P)` independently for all
four CFA phases.

Tested periods: 4, 8, 12, 16, 20, 24, 28, 32, 40, 46, 48, 64, 92, 128.

- Local residual MAD is 8--12 DN depending on CFA plane.
- For periods through 64, the strongest residue-cell median displacement is
  only 0--1 DN.
- At periods 92 and 128, the maximum is 1--2 DN, still far below local noise
  and without a coherent repeated mask.

No repeating partially-masked-pixel signature was detected in the correctly
decoded pre-pipeline frame.

## Firmware cross-check

`PdafCorrect` calls sensor vtable slot 42 (`+0xA8`). The IMX410 implementation
is empty, while the IMX455 implementation calculates PDAF geometry and invokes
the correction backend. Thus the common fp/fp L framework does not contain an
IMX410 PDAF coordinate pattern to apply to this frame.

## Scope of conclusion

This rules out a readily observable repeating PDAF mask in the normal fp still
readout and rules out a hidden IMX410 PDAF table in this firmware path. It does
not prove that the silicon has no phase structure if the sensor suppresses or
corrects it internally before SLVS-EC output.
