# SIGMA fp IMX410 sensor analysis

## Firmware tables recovered

The IMX410 mode container is at `0xc0b5fda4`:

- register-record pointer: `0xc0b5fdac`
- record count: `0x46` (70)
- register-record size: `0x288`
- 161 sensor writes recovered from `FUN_c03258c8`

All 70 mode IDs are unique, but their 161 programmed register values collapse
to 24 distinct physical configurations. A separate 0x64-byte metadata table at
`0xc0b59dc0` provides dimensions, crop geometry and timing-class fields.

Generated files:

- `analysis_imx410/imx410_modes.csv`
- `analysis_imx410/imx410_mode_geometry.csv`
- `analysis_imx410/summary.txt`
- `analyze_imx410_modes.py`

## Geometry families

The 70 logical modes reduce to 16 geometry families:

| Sensor/output raster | Final crop where specified | Notable metadata timing values |
|---|---:|---:|
| 6064 x 4042 | 6000 x 4000, margin 32/21 | 20, 30, 40 |
| 3032 x 2012 | 3000 x 2000, margin 16/6 | 78 |
| 6064 x 3412 | -- | 25, 30 |
| 5712 x 3216 | -- | 24 |
| 4176 x 2174 | -- | 24, 25, 30 |
| 3968 x 2640 | -- | 20, 40 |
| 3032 x 2012 | -- | 105 |
| 3032 x 1708 | -- | 60 |
| 2088 x 1174 | -- | 60 |
| 2016 x 1344 | -- | 60 |
| 2016 x 1136 | -- | 120 |
| 2016 x 672 | -- | 60, 240 |
| 1984 x 1320 | -- | 78 |
| 6064 x 2022 | -- | 60 |

The timing values are stored in metadata field `+0x40`; `FUN_c032c750` is the
dedicated getter for that field. Exact timing is independently reproduced by
the firmware equation used by `FUN_c0321160`:

`frame_cycles = HMAX * (VMAX - 1) + tail_cycles`

with a 72 MHz sensor timing clock. Thus `+0x40` is confirmed as the rounded
nominal frame-rate class rather than an unrelated mode number.

Selected exact results:

| Mode | Raster | Exact fps | Estimated active-row readout | Mode bit depth | Active-pixel rate |
|---:|---:|---:|---:|---:|---:|
| 97 | 6064x4042 | 39.157 | 24.98 ms | 12 | 11.52 Gbit/s |
| 3 | 6064x4042 | 29.974 | 24.98 ms | 12 | 8.82 Gbit/s |
| 10 | 6064x2022 | 59.925 | 12.50 ms | 12 | 8.82 Gbit/s |
| 11 | 3032x2012 | 105.402 | 9.22 ms | 12 | 7.72 Gbit/s |
| 58 | 3032x1708 | 119.880 | 7.83 ms | 12 | 7.45 Gbit/s |
| 134 | 2016x1136 | 119.880 | 7.02 ms | 12 | 3.30 Gbit/s |
| 12 | 2016x672 | 239.760 | 3.08 ms | 12 | 3.90 Gbit/s |

The bit-depth mapping is now recovered from mode metadata field `+0x3c`, which
is returned by `FUN_c032c898`. Firmware's own diagnostic command decodes this
enumeration as `0=RAW12`, `1=RAW14`, `2=RAW16`, `3=RAW10`, and `4=RAW8`.
Across the 70 IMX410 modes, 62 are RAW12 and eight are RAW14; none of the table
entries selects RAW10, RAW8, or RAW16. All modes above 30 fps are RAW12.

The eight RAW14 entries are modes 0, 6, 95, 100, 122, 129, 141, and 144. They
cover full raster or moderate crops at nominal 18--30 fps. Full-raster mode 0
is 6064x4042 at 19.127 fps and 6.56 Gbit/s of active pixels; full-raster mode
141 is 6064x4042 at 18.003 fps and 6.18 Gbit/s. Full-raster 30/40 fps modes 3
and 97 are explicitly RAW12, not RAW14.

## Immediate implications

1. The sensor tables contain substantially more readout modes than the normal
   still-photo path exposes.
2. Full-raster 6064 x 4042 has three timing classes (20/30/40 candidate fps).
3. High-speed cropped/binned classes include 120 and 240 candidate fps.
4. A 6064 x 2022 mode is a particularly interesting full-width, half-height
   candidate for lower rolling shutter.
5. Mode IDs 218--221 are not new sensor geometries; they reuse existing
   3032x1708 and 2088x1174 register configurations.

These facts do not imply that XZ01, memory bandwidth, HDMI, USB or recording
firmware can accept every sensor mode unchanged.

## Pre-RAW to DNG transform

`PRESHOT000.BIN` was decoded as tightly packed, MSB-first RAW14 (four pixels in
seven bytes). It matches `_SDI0042.DNG` at correlation 0.99998646.

- G1 and G2 are identical before and after `StillCreateRaw`.
- R and B receive small, broad spatial/intensity-dependent changes.
- The operation is not sparse and is not a PDAF-site replacement.
- Its green-anchor / red-blue-only signature is consistent with chromatic-plane
  registration or lateral-CA-like correction; the exact responsible stage is
  not yet proven.

## Border pixels

The DNG declares a 6000x3999 default crop inside the 6064x4042 raster, with 32
pixels on each horizontal side and approximately 21/22 rows vertically.
The excluded borders contain scene-dependent image signal, not a flat optical
black reference. Therefore they are overscan/crop margin image pixels and are
not directly useful as black-level calibration rows.

## RAW14 effective precision

The decoded ISO 100 pre-RAW uses all four possible values of the two least
significant bits at nearly equal frequency on every CFA plane. The stream is
therefore genuine 14-bit-coded data, not a 12-bit stream padded with two zero
bits. This fact alone does not mean that those bits contain recoverable scene
information.

In low-gradient patches, a second-difference estimate gave a per-pixel noise
scale of approximately 7.0 DN (R), 10.5 DN (G1/G2), and 7.8 DN (B), measured
in the 14-bit code space. Reducing the samples to a correctly rounded 12-bit
grid would add only 1.22 DN RMS quantization error (maximum 2 DN). Under an
independent-noise approximation, this would increase total RMS noise by only
about 0.7--1.5% in these patches.

Consequently, for this ISO 100 single-frame sample, RAW14 does not provide a
material visible colour or tonal-latitude advantage over well-rounded 12-bit.
It does not increase gamut, saturation capacity, or sensor full well. Its
practical benefit is preserving small fractional information for averaging,
stacking, calibration, repeated processing, and unusually aggressive shadow
recovery. A rigorous read-noise/ADC effective-number-of-bits result still
requires matched dark and uniform-flat frame sequences at several exposures;
the present scene frames are not stable enough for a photon-transfer test.

## Next offline work

1. Identify the remaining metadata fields `+0x44..+0x60`; `+0x3c` is now
   confirmed as RAW bit-depth enumeration and `+0x40` as nominal frame rate.
2. Recover frame/line timing equations from the IMX410 methods and associate
   them with registers `0x0001`, `0x0016`, `0x001c`, `0x0022..0x0025`.
3. Trace the R/B-only transform callsite and determine whether it is sensor
   channel registration, lens CA correction or another RAW conversion stage.
4. Rank modes by expected data rate before considering any camera experiment.

The generated `analysis_imx410/imx410_timing.csv` now contains HMAX, VMAX,
tail cycles, exact fps, active-row readout estimate, bit-depth enumeration,
decoded bit depth, and active-pixel data rate for all 70 logical modes.
