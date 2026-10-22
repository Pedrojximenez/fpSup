# Existing fp captures: OFF versus normal-mode RAW response

Read-only analysis, 2026-09-24. No camera access, new captures, DNG modification, or image rendering pipeline was used. Scene correspondence was visually checked in the four existing paired JPEGs; all quantitative results below come from undemosaiced DNG Bayer samples, not those JPEGs.

## Conclusion

The existing `_SDI0010–0013` sequence is useful evidence: despite clearly different rendered JPEG looks and OFF/normal ColorMatrix metadata, its spatially corresponding RAW channel levels remain very close. After black subtraction and estimated global translation, OFF-to-normal median per-channel signal ratios are within approximately **0.11% of unity**. Median R/G and B/G ratio changes are below **0.05%**.

This supports a shared RAW response across OFF, PowderBlue, TealAndOrange and Standard **for this sequence**. It does not prove byte-identical RAW, exclude subtle/nonlinear mode-dependent processing, establish absolute color accuracy, or establish that the same conclusion applies to CinemaDNG. These are four separate exposures, not one RAW buffer encoded four ways.

## Which captures are comparable?

All paths below are under `/Users/dido/Developer.localized/SIGMAfp_re/`.

| File | Mode | Exposure | White balance | Capture time |
| --- | --- | --- | --- | --- |
| `research/imaging-hw/color-characterisation/captures/_SDI0010.DNG` | OFF | Manual, ISO 800, 1/125 s, f/1.4 | Auto, ASN `[0.4942084942,1,0.5089463221]` | 2026-08-15 03:40:40 |
| `_SDI0011.DNG`, same directory | PowderBlue | Same | Same exact ASN | 03:40:46 |
| `_SDI0012.DNG`, same directory | TealAndOrange | Same | Same exact ASN | 03:40:51 |
| `_SDI0013.DNG`, same directory | Standard | Same | Same exact ASN | 03:40:55 |

The four frames show the same stationary room/door composition. All report the same 28mm F1.4 DG HSM Art lens, focal length 28 mm, zero exposure compensation, body calibration, 14-bit RGGB Bayer, raw 6064×4042, active area `[0,0,4042,6064]`, default crop origin `[32,21]` and size 6000×4000. Black levels are all 1024 and white level is 16383. RAW compression tag is 7. LibRaw reports its own aligned crop origin/size differently; this analysis deliberately uses `raw_image` and identical full Bayer coordinates, not its cropped/demosaiced output.

Less useful pairs:

- `_SDI5625.DNG` PowderBlue: ISO 2000, 1/60 s, f/4.5, aperture priority, Viltrox AF 28mm F4.5 L, Auto(Natural) ASN `[0.4604316547,1,0.5765765766]`, 2026-06-28 19:00:35.
- `_SDI5626.DNG` OFF: ISO 1250, same shutter/aperture/lens, aperture priority, different ASN `[0.4421416235,1,0.5601750547]`, 50 seconds later. Same 14-bit geometry and levels, but ISO/WB/time are confounded; these were inventoried, not treated as a controlled mode comparison.
- `research/imaging-hw/colormatrix-ab-20260923/A_original.DNG`: unrelated OFF CinemaDNG at 2026-08-17 22:26:11, manual ISO 100, 1/60 s, f/1.4, same Sigma 28mm lens as 0010–13, ColorTemp WB, ASN `[0.5130260521,1,0.583143508]`. Raw is **12-bit, 1936×1090**, uncompressed, crop origin `[8,5]` and 1920×1080 size, black level 255.9785156, white 4095. No matched normal-mode video capture exists in this requested subset. It cannot serve as a direct RAW mode-response pair with the still frames.

## Quantitative method and results

Reproducible script: `compare_existing_raw_captures.py` in this directory. Complete metadata, source-file and decoded-Bayer hashes, six pairwise comparisons and registration measurements: `existing-raw-capture-comparison.json`.

The script reads `rawpy.raw_image` only: no demosaic, ColorMatrix, profile tone/HSM, WB, automatic brightness or gamma. Each of four CFA planes has its recorded black level subtracted. For translation estimation, same-channel 2×2 samples are averaged (a 4×4-Bayer-pixel grid) and the two greens supply a luminance proxy. Windowed phase correlation estimates subpixel global translation in a fixed textured region. Each channel is resampled with that translation, then averaged into 32×32-Bayer blocks. Comparison excludes outer blocks and any block with a channel below 300 or above 13000 black-subtracted ADU. No gain is normalized away in the ratios below.

WB gains were not applied: the four AsShotNeutral values are exactly equal, so applying their common reciprocal gains would cancel in pairwise channel ratios. A per-channel least-squares gain is separately reported only to characterize residuals, not used to force the median ratios to unity.

Chromatic change is calculated exactly in each block as `(target_R / mean(target_G1,target_G2)) / (reference_R / mean(reference_G1,reference_G2))`, and likewise for B; the table reports the median of these blockwise ratios minus 1. It is not calculated by dividing an R-channel gain by an unweighted average of the two G-channel gains.

| Target / OFF 0010 | Median R | Median G1 | Median G2 | Median B | Median R/G change | Median B/G change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PowderBlue 0011 | 1.000651 | 1.000732 | 1.000556 | 1.000508 | +0.0132% | −0.0212% |
| TealAndOrange 0012 | 1.001026 | 1.001036 | 1.000912 | 1.000612 | +0.0043% | −0.0321% |
| Standard 0013 | 1.000224 | 1.000089 | 1.000045 | 0.999579 | +0.0187% | −0.0461% |

Method-check correction: the earlier calculation averaged the two green gains before normalizing R/B. Replacing it with the exact ratio-of-chromatic-ratios changes these six reported medians by less than 0.0004 percentage points; the maximum absolute change is now approximately 0.0461%, so the **below 0.05%** conclusion is unchanged. Script and JSON have been recomputed with the exact definition.

Estimated target shifts `(y,x)` in original Bayer pixels are respectively `(-0.178,+0.334)`, `(-0.140,+0.176)`, and `(-0.295,+0.341)`. Approximately 13,300 valid blocks contribute to each pair. A low-texture subset (~7,660 blocks) gives channel ratios within approximately 0.20% of unity.

**Do not interpret these tiny medians as per-pixel precision:** individual block ratio distributions are wider. For 0011/0010, 5th–95th percentiles across channels are approximately 0.965–1.038; for 0012/0010, 0.967–1.032; for 0013/0010, 0.985–1.014. Thus there is real spatial residual structure/noise not captured by one scalar channel ratio. The decoded Bayer hashes are all different, as expected for separate exposures.

## Limits and relevance to native calibration

No lighting monitor, repeated OFF baseline, randomized mode order, measured color chart or spectra accompany this sequence. Indoor light flicker, photon/read noise, residual misregistration, local object motion and nontranslation geometry are not separated. Only one exposure/ISO/lens/light/scene is sampled, and no saturation sweep or camera-noise model was fitted. Numerical medians alone cannot identify a causal firmware effect.

Nevertheless, the data do **not** show the large per-channel signal change that would be needed to explain the dramatic OFF-versus-normal JPEG appearance as a simple RAW gain change. Combined with the independently verified native metadata branch, the most supported working interpretation here is common RAW data characteristics with different downstream interpretation/look. A controlled video OFF/normal sequence or direct proof of the RAW writer's mode-independent source buffer is still needed before generalizing to all CinemaDNG paths.
