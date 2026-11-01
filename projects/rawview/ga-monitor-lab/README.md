# GA Monitor Lab — 2026-11-01

Independent, modified monitoring experiment for SIGMA fp firmware 5.02, based
on fpSup RAW-View v0.3.0 and the existing Loader v3 seven-MOD card. This is a
source-only research handover, not an upstream fpSup release or a Loader v4
upgrade. The production builders, loader, site and release catalogue are unchanged.

The latest local candidate is **ShadowLift2**, SHA256
`e6ea96b59823f86cdf1e57c51fad1d75e86a40486a7afbf16114133ba46f4c9b`.
It was installed with user permission and read-back verified on 2026-11-01;
its display preference test remains pending. See [the wrap-up](WRAPUP_JA.md)
and [validation record](VALIDATION.json) for the boundary between implemented,
host-verified and camera-observed behavior.

## Local reproduction

Python 3.10+, `clang` supporting `armv7-none-eabi`, and the repository's existing
`fpSup/fp_usb_shell/armasm.py` are required. No dependencies are installed or
downloaded by these scripts. Optional ARM checks use Unicorn 2.1.4, the version
used for this handover. Use a fresh output directory outside the checkout and
outside `/Volumes`; these tools never install anything on a card.

From this directory:

```sh
python3 -B test_generator.py
python3 -B build.py \
  --original /path/to/local/45RAWV.v030.orig.BIN \
  --cube /path/to/local/ARRI_LogC3-to-Gamma24_Rec709_D65-v1_33.cube \
  --out /path/to/new/local/ga-monitor-output
python3 -B verify.py /path/to/new/local/ga-monitor-output
python3 -B verify.py /path/to/new/local/ga-monitor-output --arm
python3 -B verify_preview_arm.py /path/to/new/local/ga-monitor-output
```

The two inputs must match the SHA256 pins in `build.py`. The original RAWV is
the user's unmodified v0.3.0 module, not an arbitrary current build. The script
rejects changed inputs, verifies all four historical output hashes, writes only
to a new directory and produces `build-receipt.json`. Its known offsets belong
only to that exact historical input. It does not replace the current product
builder or hand-edit a frozen release. Integrating the experiment into another
RAWV revision requires rebuilding from that revision's sources and revalidating
the layout; never transplant these offsets or weaken the input guard.

Outputs: `log-only/`, `arri-reference/`, `combined/`, `shadowlift2/`, each
containing one local `45RAWV.BIN`. Saved state is deliberately pinned for exact
reproduction: RAW On, Saturation 0; LogOnly saves SA, other stages save GA.
These files are **not an installer**. Do not use them to overwrite newer camera
settings without first saving the current module and confirming the settings.

## Reference and redistribution

Obtain the LogC3 LUT separately from the [official ARRI legacy LUT generator
page](https://www.arri.com/en/software/postproduction-software/legacy/lut-generator).
The inspected package is LogC3 LUT Package v1.2.1, dated 2025-07-10. Select
`ARRI_LogC3-to-Gamma24_Rec709_D65-v1_33.cube` (rendering v1, full-range, 33-point,
AWG3/LogC3 to Rec.709 D65 / Gamma 2.4). It is neither LogC4 nor Classic K1S1.
Its SHA256 is `241aff344709aa90b468f8658144888db38f29f9aa1b3c0d917cf327ca3b354e`.
LogC3 exposure encoding uses EI800, as documented in the [ARRI LogC3
specification](https://www.arri.com/resource/blob/31918/66f56e6abb6e5b6553929edf9aa7483e/2017-03-alexa-logc-curve-in-vfx-data.pdf).

The cube, package, PDFs, extracted neutral-axis values, generated curve tables,
derivative BINs, camera firmware, recordings and private machine paths are not
included. ARRI redistribution permission was not established; downloading the
official package is not treated as permission to republish it. Review its terms
for your use. The code reads the user's local cube; there is no automatic fetch.
Do not commit local inputs or outputs to this public repository.

This source is under GPL-3.0-or-later, subject to the applicable origin notices
in [LICENSE](../../../fpSup/LICENSE) and [NOTICE](../../../fpSup/NOTICE).
Upstream fpSup source copyright belongs to bei (ijigen); the shared assembler
is reused directly. The display constructor model was adapted from the local
RAW-View analysis model. The modified experiment's name is **GA Monitor Lab**;
it is not endorsed by the upstream author, SIGMA or ARRI. The code licence does
not grant rights in ARRI LUT data or SIGMA firmware.

## What it does

Only the GA monitoring path is changed. LogOnly replaces GA's 31 sampled rows
and disables the old GA Rec.709 toe for one record group. Display-code
calibration is applied once: `signal = 16.9/255 + .936*code/8190`, code limited
to 0…8170. This was checked against all 146 original SA samples; it is a model
of the processing signal, not a photometric LCD calibration.

The ARRI reference stage reads the cube's neutral diagonal, averages RGB, and
interpolates between its vertices. This corresponds to tetrahedral interpolation
on the neutral main diagonal; it is not equivalent to trilinear interpolation
or a full colour transform. A documented display-floor adaptation preserves
shadow steps and gray/white anchors; it intentionally differs from the official
LUT. SIGMA primaries are not assumed to be AWG3. No `.cube` file is loaded by the
camera. No Log recording or full 3D LUT rendering is implemented.

Combined adds a small lower-tone lift and a nominal 1.03 GA-only preview chroma
matrix. The helper is in the module allocation, dispatched from the relocated
resident through `P_BLOCK` and returns relative to relocated params. Its append
updates file length and scratch offset; original hooks/claims, SAT tables and
DNG CM buffer/tables are unchanged. Existing loader cache publication is reused;
no new loader, callback or global firmware patch site is introduced.

ShadowLift2 changes only 4340 bytes within the GA rows, `0x3ad0…0x5e2b`, relative
to combined. For old code `c < 2921`, `t=c/2921`:
`new = round(c + 350*(256/27)*t*(1-t)^3)`; other codes remain unchanged. The
maximum lift is 350 codes (4 model display-signal percentage points), with a
positive derivative and a smooth join at middle gray. The GA-only 1.03 colour
code, DNG data, SA, gray and highlights are byte-identical to combined.

Existing RAWV Saturation 0/+0.2 still selects both preview calibration and DNG
ColorMatrix-related data. The new nominal 3% GA boost is separate and
preview-only in the traced host path. That does **not** establish actual camera
DNG pixel or metadata invariance. Saturated colours may exceed the display gamut;
no new *tone* clipping does not mean no colour clipping.

## Card compatibility and recovery

[integration.json](integration.json) records the seven-MOD layout and hash
identities, including the same Desqueeze module (Off / 1.33x / 1.6x / 2.0x).
These files are not redistributed here and are not regenerated by this tool.
Every GA revision after r2 requires only the RAWV replacement on the already
compatible card; AutoRun, the six other modules and settings must be preserved.
No SD operation is performed by this repository change.

The r2 card removed only the two legacy early AutoRun writes of `0x7080` to
`0xC0B9BEDC` and `0xC0BA0354`. They bypassed the RCLM guard/journal. The unchanged
RCLM guards the stock 7200-second words, claims the resource, writes 28800 and
uses the loader journal for restoration. This is 2h → 8h, not unlimited. Do not
edit a different AutoRun by analogy or transplant an old bootstrap.

For a previously approved compatible test card, recovery means normal power-off,
saving its current RAWV, then restoring only the desired known-good RAWV from
the original private backup (preferred) or a verified local reproduction. Check
the hash, sync and read back before using the Mac's eject action. LogOnly saves
SA, so select GA explicitly when comparing. No format or firmware update is
required. This description is not permission for an automated card write.
