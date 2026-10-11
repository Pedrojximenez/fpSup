# Reduction method investigation — 2026-09-09

## What is established

The current 3K mode selects the native correction/RAW-zoom output called
`CrctRwzmToBufA`. The separate descriptor reduction enums remain 0/0, converted
to factors 1/1. The programmed ratios are 2048/2048 on a 1024-based scale, i.e.
2:1 in each direction. Earlier sensor/window verification establishes the
6064×4042 input configuration and the same table-fed sensor register sequence
as native full-height modes. The output raster is 3032×2020, visible 3000×2000.

This locates the reduction after the sensor in a RAW-domain hardware path.
It does not establish the hardware's spatial kernel or prove every input sample
contributes. Sensor table equality is not a complete sensor register datasheet.

## New native execution evidence

`tools/trace_reduction_method.py` executes the original descriptor constructor,
C031D988 through C031DCA0, native path selector C0325228, C032D9A0 and the actual
Thumb register drivers. Only descriptor acquisition/manager and sensor singleton
lookups are supplied by fixtures. Peripheral pages are bounded ordinary RAM.
No software pixel reducer is substituted for hardware. Firmware SHA is checked.

Three cases passed; the complete report is `native-trace.json`:

| Case | Recording enables A0/A7/A1 | RAW ratios | Recording route |
| --- | --- | --- | --- |
| Stock UHD24/profile429 | 0/0/1 | 1600/1600 | CrctRwzmToBufA |
| Current 3K24/profile429 | 0/0/1 | 2048/2048 | CrctRwzmToBufA |
| Stock UHD24 DC Crop/profile432 | 1/0/0 | descriptor1023, clamped1024 | CrctCrmfToBufA |

Debug strings are at C0B573CC (`bufa1 : CrctRwzmToBufA`) and C0B5716C
(`crct1_win_a0 : CrctCrmfToBufA`). Their actual selection branches were checked
at C031DF48..C031DF84 and C031DD08..C031DD50. These are not guessed block names.

For 3K, native C0633E60 writes:

- 300F0004 bit8 = 1, from sensor reduction record+2D. Its semantic meaning remains
  unknown; do not label it "interpolation enable" without evidence.
- 300F0900 = 1 (ratio block enabled).
- 300F0908 = 00000800 and 300F090C = 00000800. Low half is ratio2048;
  computed upper phase terms are zero. Stock1600 gives 00E00640 for both.
- Secondary ratio block300F2900 = 0.

The sensor descriptor is in DAT1 at C2F1E654. Its +114 pointer is C0B5F770,
containing TWO 56-byte reduction records, not one record per sensor mode.
The selector chooses record1 for current3K and stock full-widthUHD, record0 for
DC Crop. Record1's binning configuration is identical between3K and stockUHD;
only the ratio terms change in the reduction-driver arguments.

Crucially, the DC Crop case still programs the ratio hardware for preview.
A nonzero zoom register alone therefore cannot identify the recording path.
The DC Crop recording uses the earlier A0 output and is a useful control.

## Existing-image analysis

`tools/analyze_reduction_noise.py` uses original 12-bit packed RAW samples in
A001_021 and A001_022, frames11–50. No demosaic, image warp, or interpolation.
Each Bayer phase is processed separately. Adjacent-frame differences are divided
by sqrt(2), and per-pair means are removed within64×64 same-CFA tiles. Retained
flat tiles have signal>15DN, relative texture<0.08 and pair-mean drift SD<1DN.
Both clips report ISO3200, f/4.5, 1/50 second. Full results and tile statistics
are in `existing-clip-noise.json`.

For the two green phases,3K has median same-phase neighbor correlations roughly
0.01–0.03, while UHD is roughly0.09. UHD variance has a pronounced16-position
cycle consistent with1600/1024=25/16 resampling;3K is essentially constant across
that cycle. This supports a phase-dependent resampling interpretation for UHD.
The constant3K result is compatible with several integer-ratio kernels,
including nonoverlapping averaging AND sample selection. Low spatial noise
correlation is not proof of skipped pixels. Natural-scene temporal differences
also contain residual movement/light fluctuations and native processing.

The earlier still/video pair had ~0.698pixel median registration residual on
1500×1000 representations (about2.8 full-sensor pixels). It was taken across
boots with slight movement and different bit-depth/pipeline states. It cannot
uniquely distinguish individual input-pixel weights. Fitting a kernel to that
pair as if perfectly registered would give unjustified confidence.

## What remains unresolved and how to settle it

There is no verified kernel specification in the supplied firmware or the public
sources inspected. The register driver writes configuration; the silicon performs
the pixel arithmetic. Zero programmed phase is insufficient to infer nearest
neighbor, bilinear, area averaging, or a prefilter. Do not mark the user's
all-photosite goal achieved or call the method definitively skipping/binning.

Next is a same-CINE, same-ISO, two-exposure flat-field comparison of stock UHD
DC Crop and3K. The native trace supplies a RAW-zoom-bypass control without changing
the installed patch. Two exposure levels help separate signal-dependent noise
from read noise. Estimate per-CFA signal scaling, temporal variance slopes and
spatial covariance; account for native gain/readout differences before inferring
an effective contributor count. Normalized weights w have noise power
proportional to sum(w²), so equal four-sample averaging differs strongly from
single-sample selection, but noise alone does not uniquely identify every tap.

If that test is ambiguous, retain the conclusion as unresolved and proceed to a
fixed sharp target comparison or a bounded synthetic-input impulse test after
tracing buffer ownership. A synthetic one-input-pixel perturbation through the
actual hardware is the strongest way to identify tap support and all-phase
contribution; it has not yet been implemented. Do not emulate unknown hardware
with an assumed kernel and then present that as hardware evidence.

Return folders and the four-take camera instructions are prepared in
`diagnostics/reduction-method-return/TEST-INSTRUCTIONS.md`. No firmware package,
media file or camera setting was changed in this investigation.
