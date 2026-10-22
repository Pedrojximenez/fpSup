# SIGMA fp native body-calibration audit

Read-only audit, 2026-09-24. No camera operation, foreign-camera calibration, new DNG generation, or modification of existing DNGs.

## Outcome

The fp's private `CameraCalibration` tag 0x11F is a diagonal **sensor/body adjustment**, not the current shot's white balance. The native DNG writer already folds its inverse into ColorMatrix1 and ColorMatrix2. Existing `C_firmware_normal.DNG` reproduces that native convention exactly using the fp's own normal ROM matrices and this body's adjustment. **Do not add a second per-body correction to C.**

This establishes firmware provenance and reproducibility, not measured colorimetric accuracy or a complete Resolve decoding specification.

## Source chain

Source paths below are under `/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/`; binary addresses refer to `/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin`, base 0xC0000000.

1. `blk_c02.c:107591`, `FUN_c02ad018`: obtains sensor-adjustment data through `FUN_c0055510(0xC3074950)` and `FUN_c0055538`. If record word 0 is 1, takes calibration R/G/B from record words 1/2/3. Otherwise uses `[300,512,700]`. `FUN_c02acf60` copies these into AWB-state fields at byte offsets 0, 8, 12 (word 1 is separately fixed at 512), repeated in five initial state blocks. `FUN_c02ad1e0` invokes this initializer.
2. `blk_c00.c:62428`, `FUN_c0055510`, initializes a pointer wrapper using `FUN_c0055650`; `FUN_c0055538` returns the stored pointer. Thus `0xC3074950` holds a pointer, not the inline calibration record.
3. `blk_c00.c:62515`, `FUN_c0055650`, and `:62594`, `FUN_c00557e8`: obtain/validate an `XC_AdjustDataSensor` block, block ID 8, reserved size 0x80000, with payload beginning after a 0x20-byte header; malformed block is reinitialized. `FUN_c0055860` validates block ID, length and checksum. `blk_c01.c:155382`, `FUN_c01f9a60`, also returns 0x80000 for block ID 8. **0x80000 is a block size, not a proved physical flash address.**
4. `blk_c05.c:21526`, `ImgData` export branch 0x44C, calls that same `FUN_c0055510`/`FUN_c0055538` getter and labels its payload `SensAdj` (string at 0xC051EFC8). This establishes the firmware's own adjustment-resource name. The manufacturing measurement procedure, calibration illuminant, and physical nonvolatile address were not traced.
5. `blk_c02.c:109342`, `FUN_c02b0118`, zeroes nine float32 values, obtains three adjustment counts through `FUN_c04d2038`, dispatches vtable slot +0x20, and writes group 5/private tag 0x11F, type FLOAT, count 9.
6. `blk_c04.c:158653`, `FUN_c04d2038`, calls `FUN_c04d4ed8` (`:160177`), which selects AWB state words 0, 2, 3, i.e. byte offsets 0, 8, 12.
7. `blk_c02.c:110623`, `FUN_c02b23b0`, installs vtable 0xC096BB68. Its slot +0x20 points to **0xC02B22A0**, absent as a function in the bulk decompilation. Direct ARM disassembly proves it divides the three unsigned counts by float32 constants 323, 511, 672 (literal addresses 0xC02B2300/04/08), writing only float offsets 0, 0x10, 0x20. Off-diagonals remain zero from the caller.

Therefore:

`D_body = diag(float32(calR/323), float32(calG/511), float32(calB/672))`

The constants are a fixed firmware normalization reference, distinct from the invalid-record fallback `[300,512,700]`. Their physical measurement origin was not recovered.

## Current-shot white balance is separate

`blk_c02.c:110328` and `:110343`, `FUN_c02b18d0`, passes the base AWB state to private-calibration writer `FUN_c02b0118`, but **state + 0x864** to the AsShotNeutral writer `FUN_c02b1330`.

`blk_c02.c:110004`, `FUN_c02b1330`, uses the ROM rational template at 0xC096BE2C, exactly `[256,0,512,512,256,0]`, replacing the two zero denominators with current-WB words 0 and 3. Therefore:

`AsShotNeutral = [256/shotWbR, 512/512, 256/shotWbB]`

This proves distinct state fields and semantics. It does not establish the full upstream WB algorithm or assert that its calculations never use the body adjustment. Do not remove any contribution from AsShotNeutral based on this audit.

The older parent note `research/imaging-hw/notes/COLOR_SCIENCE.md:74` calls private calibration “as-shot WB”; that description is incorrect. It was left unmodified in this read-only audit.

## Native ColorMatrix folding and direction

`blk_c02.c:123706`, `FUN_c02c4a50`, reads private 0x11F, computes its 3x3 inverse, and uses `FUN_c02c9860` to left-multiply the selected ROM matrix:

`CM_stored = inverse(D_body) @ CM_ROM`

Each result is converted to signed rational numerator by truncating `value*10000` toward zero, denominator 10000. Normal ROM addresses are CM1 0xC096FD2C / CM2 0xC096FC9C; OFF ROM addresses are CM1 0xC096FD74 / CM2 0xC096FCE4.

Ignoring rational quantization, the inverse is `inverse(CM_stored) = inverse(CM_ROM) @ D_body`: the adjustment is already present when the stored matrix is inverted for a camera-to-colorimetric conversion. Inserting another body matrix, or blindly copying the private tag into standard DNG CameraCalibration1/2, would change the firmware-defined mapping. This audit does not prove how Resolve handles Sigma-private 0x11F; it proves that no extra correction is required to make C reproduce the native normal matrix writer.

## Existing-file verification

Machine-readable exact results and hashes: `body-calibration-verification.json` in this directory. Verification was computed against existing files, not inferred from filenames.

- A: `research/imaging-hw/colormatrix-ab-20260923/A_original.DNG`, genuine OFF cDNG.
- C: `research/imaging-hw/colormatrix-ab-20260923/C_firmware_normal.DNG`, previously generated CM-only candidate.
- Normal reference: `research/imaging-hw/color-characterisation/captures/_SDI5625.DNG`, same-body genuine PowderBlue still DNG.
- All three contain the same private float32 diagonal: `[1.0433436632156372,1,1.0193452835083008]`, exactly `[float32(337/323),float32(511/511),float32(685/672)]`.
- All three lack standard DNG CameraCalibration1 and CameraCalibration2 in root IFD. The observed `CameraCalibration` is Sigma-private, not one of those standard tags.
- A and C AsShotNeutral are exactly `[256/499,512/512,256/439]`. Genuine normal sample is `[256/556,512/512,256/444]` despite identical body adjustment.
- A's two matrices exactly reconstruct the native OFF writer. C's two matrices exactly reconstruct the native normal writer **and byte-match the genuine normal sample's matrix payloads**.
- C differs from A in only 46 bytes, all within the two ColorMatrix payload spans (144 bytes total). Every byte outside those spans is identical, including RAW, AsShotNeutral, private body calibration, OFF profile tone/HSM, and other metadata.
- A and C concatenated RAW-strip SHA256 are identical: `8bee54820bf5d3b1e213d4076e7a7165a9efe9140865379b390e56cad4863336`.

Do not generalize this body's numerical diagonal or final CM values to a different fp. Recompute from each file's own adjustment where available, and validate missing/malformed private tags explicitly. C is a native-fp matrix baseline retaining the existing OFF look-profile metadata, not a full recreation of every normal-mode metadata field and not yet a measured calibration standard.
