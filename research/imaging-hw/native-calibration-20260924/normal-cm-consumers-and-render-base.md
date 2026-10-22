# SIGMA fp native profile: normal DNG CM vs render-base matrices

Offline audit, 2026-09-24. No camera access or firmware modification.

## Result

The normal ColorMatrix pair is an explicit manufacturer-supplied **DNG input-profile resource**. The only modeled consumers found in the complete local decompilation are in the DNG metadata writer, `FUN_c02c4a50`. This is stronger evidence for using the fp's own normal DNG pair than for borrowing another camera's matrix. It is not independent proof of measured color accuracy, nor proof that the profile contains no aesthetic optimization.

The separately traced render-base path feeds identity plus the already identified Standard creative RGB matrix into the image-processing state. This path does **not** establish that the normal DNG pair is the same matrix as the ISP matrix. It also does not prove there are no other upstream sensor-calibration stages.

## Normal DNG pair: direct evidence

Source: `/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:123705`.

`FUN_c02c4a50`:

- Reads private metadata tag `0x11f`, a 3×3 float CameraCalibration matrix; explicitly inverts it.
- For a selected color-mode code other than `0x24`, multiplies its inverse by `C096FD2C` for ColorMatrix1 and `C096FC9C` for ColorMatrix2.
- For `0x24` (OFF), substitutes `C096FD74` and `C096FCE4` instead.
- Writes standard tags `0xC621` / `0xC622` (50721 / 50722), TIFF type 10 (SRATIONAL), count 9. Numerators are scaled by 10000 and truncated through float-to-signed conversion.

Search of `out/decomp/full/*.c` for `c096fd2c` and `c096fc9c` yielded exactly these two uses, at lines 123785 and 123807 of `blk_c02.c`. The complete 72-byte arrays occur once each in the two mapped segment files checked (`seg0_c0000000.bin`, `seg1_c2ef6e00.bin`), at their named ROM addresses. This is a bounded source/data audit, not proof that computed-address or unmodeled references cannot exist.

Exact little-endian float64 ROM values:

```text
C096FD2C (normal CM1)
 1.52777208 -0.78369206 -0.53235740
-0.33300821  1.17111636 -0.06048574
-0.07630887  0.16665812  0.59807446

C096FC9C (normal CM2)
 0.86104544 -0.21332054 -0.18195931
-0.49615946  1.16486033  0.06317307
-0.11595160  0.16117894  0.36183215
```

These constants are not discovered by reversing a gamma curve; their code use is a linear 3×3 transform encoded as DNG metadata. Retaining RAW pixels while changing only this profile does not itself bake a log or display-gamma curve into the RAW samples.

## Previously opaque upstream render-matrix call is resolved

1. `FUN_c02bdc20` stores `FUN_c0698590()` in object field `[5]` (`blk_c02.c:118929`).
2. `FUN_c0698590` constructs the singleton at `C3824258` and installs vtable `C2E38BE8` at its `+0x840` (`blk_c06.c:123994`).
3. `FUN_c02bfb28` obtains an 88-byte matrix-state structure from this object's vtable slot `+0xB0`, then calls `FUN_c02cfcf0` (`blk_c02.c:120373`).
4. Binary reading of `C2E38BE8+0xB0 = C2E38C98` gives `C0692A40`, named `PictureQualityCommonPrePst__v42` (`blk_c06.c:121186`). It looks up feature `0x29`, invokes slot `+0xAC`, and calls the two matrix packers `FUN_c01073a0` / `FUN_c0107548`.
5. Slot `+0xAC` is `C0690BA0`, `PictureQualityCommonPrePst__v41` (`blk_c06.c:120038`), which invokes `FUN_c0695178` when runtime flag `+0x11F` is zero.
6. `FUN_c0695178` copies 20-byte matrix payloads from active resource fields `+0xE8` and `+0xF0`, counts `+0xEC` / `+0xF4` (`blk_c06.c:122363`). Entry stride is 24 bytes: uint32 threshold key + 10 signed shorts. It selects the last threshold not exceeding runtime field `+0xFC`. The meaning of that runtime field is not established here; it must not be relabeled as CCT merely because it selects a matrix.
7. `FUN_c02cfcf0` (`blk_c02.c:131323`) preserves the resulting base state when effect strength, output-space selector, and effective mode are all zero; otherwise it replaces these matrices using the selected mode resources, with mode-strength blending. It also records the state later used to make private tag `0x34`.
8. The resulting state goes through `FUN_c032eea8` / `FUN_c032efa8` (`blk_c03.c:30652`, `30719`) to hardware pack/write helpers. Those helpers shown here write the `0x30210CB0`… register family. This audit does not equate that register family with the separately labeled `MAT_TOP_RGBLMAT` block at `0x30115100`.

## Concrete native base resources

`FUN_c02bf6d8` (`blk_c02.c:120181`) passes root `FUN_c02d5de0() = C0B38ACC` to the base constructor. Two other constructors select `C0B3EFDC` and `C0B3F83C`; these use RAM copies explicitly initialized from the first root.

| Root | Matrix field +E8 | Matrix field +F0 | Counts |
|---|---|---|---|
| C0B38ACC | C0B390E8 | C0B39100 | 1, 1 |
| C0B3EFDC | C3424E98 | C3424EB0 | 1, 1 |
| C0B3F83C | C3425240 | C3425258 | 1, 1 |

Copy initializers are in `FUN_c02d6c08` near `blk_c02.c:136183` and `FUN_c02d7000` near `blk_c02.c:136370`. The second and third roots are not extra independently calibrated matrix sets merely because their addresses differ.

ROM first entry, key 100:

```text
C0B390E8: 512, 0, 0, 512, 0, 0, 512, 0, 0, 0
C0B39100: 632, -92, -28, 646, 0, -134, 566, 0, -54, 0
```

The native coefficient ordering places each row's principal term first. Reordering the latter nine coefficients as `[0,1,2; 4,3,5; 7,8,6]` and dividing by 512 gives:

```text
1.234375 -0.1796875  -0.0546875
0         1.26171875 -0.26171875
0        -0.10546875  1.10546875
```

This is exactly the previously extracted Standard private `0x124` matrix. The first table is identity. Neither is a newly recovered, independently established sensor→XYZ transform.

## Consequence for the practical test

The bounded source work supports **recovering the fp's existing normal DNG input profile and testing its interpretation in Resolve**, while keeping pixel data and other controls fixed. The existing `C_firmware_normal` candidate has now been rendered by the user; A/C analysis supports an actual Resolve response to the changed ColorMatrix payloads. It is not necessary to transplant Z CAM/Sony metadata. See `resolve-ac-observation.md` for the managed-output limitations, `existing-raw-capture-comparison.md` for the new still-RAW evidence, and `cinemadng-raw-sink-audit.md` for the bounded video writer trace.

What remains unproven is whether that normal pair alone is the desired colorimetric characterization for OFF RAW, how much the accompanying manufacturer profile/look contributes, and whether Resolve applies the tested metadata exactly as expected. Comparing the normal input profile against the separate Standard look is meaningful; multiplying them together without a proven basis/order would mix distinct layers and cannot be called a recovered calibration.
