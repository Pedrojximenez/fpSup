# Reconstruction of the single-frame checkerboard HDR (§30): prior art and what we do

Status 2026-10-20. Implementation: `hdr_ml.py` (same CLI as `hdr_split2.py`). Output for 0738 = 20:
`captures/checker/hdr_ml_0x20*.png`. Comparison stock | v4 (`hdr_split2.py`) | v5 (`hdr_ml.py`), crops
card/rim/edge/dark from top to bottom: `captures/checker/crop_v4_vs_ml.png`.

## 0. Most important finding: the attenuated group is displaced by the 0738 value in rows

Before any algorithm: **the attenuated sample in output row y shows the physical row y + off**, with off equal to
the `0738` value in raw rows. Measured by block matching full vs attenuated samples of the same colour, in the same
row (clipped-log images, 48×48-cell blocks, sub-row parabola, 500 blocks per frame):

| 0738 | G offset (rows) | R offset top → bottom | B offset top → bottom |
|---|---|---|---|
| 10 | 16.7 → 16.8 | 13.4 → 17.4 | 13.9 → 17.8 |
| 20 | 32.4 → 32.2 | 28.6 → 33.8 | 29.2 → 34.6 |
| 40 | 63.9 → 64.1 | 60.4 → 65.6 | 61.7 → 66.3 |

- Green is exactly 0738 rows at every height. R and B drift by ~5 rows from the top of the frame to the bottom, the
  same amount at all three settings. That is unexplained (lateral CA cannot do it: full and attenuated R are
  compared with each other). `hdr_ml.py` fits a line per colour and moves each attenuated sample to its physical row
  (linear interpolation between same-colour rows, 2 apart).
- The full-gain samples are aligned with the stock frame (shift 0).
- This is exactly the artefact list of v1–v4: the **dark band** above the lower edges of bright areas is the
  attenuated image of the dark area 32 rows further down (attenuated samples ~20 DN where ~250 were expected, while
  the full samples were clipped); the **coloured rings on the beads** are the bead's attenuated image displaced by
  32 rows next to its clipped full image; part of the **comb** is the hand-over switching between two images that
  disagree. No blending rule can fix that; registration does.
- The top `off` rows have no attenuated data (their samples come from beyond the frame): there the full samples are
  kept even when clipped. The first two output rows of the attenuated group are junk and are not used.
- Mechanism (inference, not measured): `0738` is a row offset of the readout/shutter pointer of the attenuated
  pixel group; the exposure ratio also scales with it (k ≈ 0.11 / 0.059 / 0.034).
- Noise of the attenuated samples, from the frame/frame2 pair: read variance ~70 DN² (vs ~100 for full), shot
  variance only ~0.15 per DN against ~1.6–2 per DN for full, i.e. it behaves like a gain reduction of the same
  charge, not like fewer electrons. In full-equivalent units an attenuated sample has σ ≈ 8.4/k ≈ 120–150 DN of
  read noise plus the same shot noise as a full sample.

Second checkerboard-only defect found while doing this: **column phases col % 16 ∈ {1, 5, 9}** read wrongly at
strong vertical gradients (phase 5: −15…−17 % of the gradient, both edge directions; phases 1 and 9: about 1.2× more
outliers). This shows up in all three captures and never in the stock frame, and it made the period-16 "comb" that
hangs from bright edges. `hdr_ml.py` detects the phases from the frame and clamps those samples to the range of
their same-colour, same-gain neighbours 4 columns left and right.

Third: the att→full relation is not a straight line. With block means of adjacent full/attenuated pairs, the ratio
att/full falls steadily: R 0.085 at 100 DN, 0.077 at 1000 DN, 0.068 at 3500 DN, and G the same way. The
stock-vs-full comparison shows that the full samples are linear against stock (0.995 ± 0.003 up to 3500). So the
curvature is in the **attenuated** response, not a 10 % compression of the full one. This part of the task's premise
is not what the data show. `hdr_ml.py` uses a monotone LUT per colour, extrapolated with the slope of its top third
(top-range k: R 0.062, G 0.051, B 0.063 at 0738 = 20). How bright highlights come out therefore depends on that
extrapolation, which nothing in a single frame can check.

## 1. cr2hdr (Magic Lantern Dual ISO): the pipeline as written

Source: `modules/dual_iso/cr2hdr.c` and `chroma_smooth.c`, magiclantern_simplified `dev`, commit
`56ee1252b52d09e3ce61c7448220e05f57891c84` (2024-08-20):
<https://github.com/reticulatedpines/magiclantern_simplified/blob/dev/modules/dual_iso/cr2hdr.c>.
Canon Dual ISO alternates ISO every **2 rows**: each pair of rows is one full RGGB line, bright (high ISO) or dark
(low ISO). The pattern of y % 4 is auto-detected (`identify_bright_and_dark_fields`: green-only histograms of the
four row phases, compared at percentiles up to 99.8 %). All processing happens on 20-bit integers (14-bit × 64).
"EV" means `raw2ev[i] = log2(1 + (i − black)/64) · 65536`, with negative values mirrored.

### 1.1 Black and white levels
- `black_subtract`: per-row black from the left optical-black bar (median, separately for the two exposures),
  lightly averaged across rows with the same ISO; horizontal drift per channel and a fix for 8-pixel banding. After
  matching, `black_subtract_simple` re-reads the OB median ("to fix whatever our funky processing may do to blacks").
- `white_detect`: white level = the k-th largest sample minus a margin, separately for each exposure.
  `discard_pixels = {10, 50}`, `safety_margins = {100, 1500}` (14-bit). The 1500-DN margin on the bright
  exposure (~9 % of full scale) is there because of the nonlinear top end: "use a higher safety margin for the
  higher ISO".

### 1.2 Exposure matching: `match_exposures()`
1. Quick vertical interpolation on a 3×3 subsampled grid. For each native row y, the missing exposure is
   `(p[y−2] + p[y+2])/2`. Pairs where either neighbour is ≥ `clip = 0.95·(white−black)` are discarded ("there may
   be nonlinear response in very bright areas").
2. A robust line `dark = a·bright + b`:
   - origin: `(median(bright), median(dark))` over the unclipped pairs;
   - slope: only highlight pairs, bright between the **98th and 99.9th percentile**;
   - RANSAC-like scan: `for ev in 0 .. 6 step 0.002: a = 2^−ev, b = dmed − bmed·a`; score = number of highlight
     pairs with `|d − (a·b_ + b)| < 50` (16-bit units); the best score wins.
   - The comment says: "exposure matching is important to be correct in bright highlights … low percentiles are
     likely affected by noise … as ad-hoc as it looks, it's the only method that passed all the test samples so far."
3. Applied to the raw data: bright rows `p = (p − black)·a + black + b·a`, dark rows `p = p − b + b·a`. In other
   words, the bright exposure is darkened to dark-ISO units, and the black offset b is split between the two.
   `white_darkened = (white − black + b)·a + black` becomes the bright exposure's clip level from here on.
4. `factor = 1/a < 1.2` → "Doesn't look like interlaced ISO".

So: **one linear gain and one offset**, fitted where they matter (just below the bright exposure's clip),
robust to outliers. No curve.

### 1.3 Bad pixels: `find_and_fix_bad_pixels()` (before interpolation)
- Only same-colour, **same-exposure** neighbours within ±4 rows/cols are compared.
- Hot: `raw2ev[p] − raw2ev[max] > 1 EV` and `max > black + 8·dark_noise` → replaced by the 3rd-largest neighbour.
  Aggressive mode: > ¼ EV above the max, or > ½ EV above the 3rd max.
- Cold: `p < black − 8·noise`, or (near black) `raw2ev[max] − raw2ev[p] > 10 EV` → replaced by the neighbour median.
- Hot pixels are only searched in the dark exposure ("we don't have no hot pixels on the bright exposure"): the
  dark samples are the amplified ones.

### 1.4 Interpolating the missing half
Two methods (`interp_method`).
- **amaze-edge** (default):
  1. "Squeeze" each exposure into a half-height image of complete RGGB rows (greens halved to approximate WB) and
     run **AMaZE** on each, giving full RGB for each exposure.
  2. gray = G/2 + R/4 + B/4 for direction estimation.
  3. **Edge-directed** interpolation of each missing row: 11 directions (from ±2:1 slanted through 45° to
     vertical), each defined by a near pixel `a` (1 row away), a far pixel `b` (2 rows on the other side) and two
     check pixels. The direction minimises Σ_{j=−5..5} |p1−p2|+|p2−p3|+|p3−p4| in EV, plus a diagonal penalty
     `|d − d0|·EV/8`.
  4. The value is `(2·ev(a) + ev(b))/3` in EV. The final value averages the chosen direction and its two neighbours,
     `(2·pi0 + pip + pim)/4`, to "reduce aliasing".
  5. The full direction search only runs where it matters. When interpolating the bright exposure, it runs in deep
     shadows (`fullres_curve < 0.8`); when interpolating the dark exposure, it runs where the bright one is clipped.
     Everywhere else the interpolation is plain vertical.
- **mean23**: R/B = mean of y±2 (same colour, same exposure); G = mean of three greens (x±1 on the near row and x on
  the far row). Means are taken in EV, and any clipped input makes the result "white".

### 1.5 Horizontal stripe fix (`use_stripe_fix`)
For every row, the median of `bright − dark` over pixels where both are below `white_darkened` is added to the dark
row. It is skipped with fewer than 200 points or when it exceeds 200 (14-bit DN). This removes row-to-row offset
banding between the two exposures.

### 1.6 Two reconstructions, mixed
- **fullres** ("minimizes aliasing"): every pixel keeps its native sample. Bright rows: `f < white_darkened ? f :
  max(f, dark_interp)` ("if the brighter copy is overexposed, the guessed pixel for sure has higher brightness").
  Dark rows: the native dark sample. There is no interpolation where both exposures are valid, so it has full
  resolution but the noise of the dark rows.
- **halfres** ("minimizes noise and banding"): each pixel mixes the bright and dark images (native or interpolated)
  **in EV** with the mix curve
  `k = (1 − cos(π · clamp(ev − (max_ev − overlap), 0, overlap) / overlap)) / 2`, where `ev = log2(b − black) +
  corr_ev` of the **bright** value and `overlap = lowiso_dr − corr_ev`, then `overlap −= min(3, overlap − 3)`
  ("better colors, less noise, but a little more jagged edges if we underestimate the overlap"). This is a raised
  cosine over the top `overlap` EV below the bright clip. Below that, only bright data is used; at the clip, only
  dark data.
- `fullres_curve` (how much fullres to use, as a function of the bright value): a raised cosine from 2^4 to 2^8
  (`fullres_start = 4`, `fullres_transition = 4` EV above black), threshold `fullres_thr = 0.8`.

### 1.7 Chroma smoothing: `chroma_smooth_2x2/3x3/5x5`, default 2×2
Per RGGB cell: `ge = mean(ev(G1), ev(G2))`. Over the cell and its neighbours, `dr = ev(R) − ge` and `db = ev(B) − ge`
are collected. The 2×2 variant uses the 5-cell plus shape (`|i|+|j| == 4` excluded from a 3×3 cell window); 3×3
uses 9 cells and 5×5 uses 25. The output is `R = ev2raw(ge + median(dr))`, and B the same way. It is skipped where
`ge < 2 EV` ("looks ugly in darkness"). It is applied to both fullres and halfres, giving `fullres_smooth` and
`halfres_smooth`.

### 1.8 Alias map
- Computed only where `fullres_curve[bright] ≤ 0.8`. It is `min(e_lin/2, e_log/16)` with
  `e_lin = max(|fullres_smooth − halfres_smooth| − 1.5·dark_noise, 0)` and `e_log = |ev difference|`. The linear
  error downweights noise in the shadows and the log error serves the highlights.
- Filtering: the **5th largest of 37** samples in a radius-6 same-colour neighbourhood ("to filter isolated
  pixels"), then a Gaussian-like 7×7 blur, then the max over each 2×2 cell ("make it grayscale"), capped at
  `ALIAS_MAP_MAX = 15000` ("trial and error – too high = aliasing, too low = noisy").

### 1.9 Final blend, per pixel, in EV
```
f   = fullres_curve[bright]                          # signal-level preference for fullres
c   = max(alias_map/15000, ovf)                      # ovf = blurred overexposure map / 200
f   = max(f, c)                                      # detail or clipping -> fullres
fev = noisy_or_overexposed*ev(fullres_smooth) + (1-noisy_or_overexposed)*ev(fullres)   # n_o_o = max(ovf, 1-f)
f   = clamp(f, 0, (sig - black)/(4*dark_noise))     # no fullres in deep shadows ("fixes some black spots")
out = (1-f)*ev(halfres_smooth) + f*fev
```
The overexposure map is `bright ≥ white_darkened || dark ≥ white`, blurred with a 3×3 kernel. The blend is smooth
everywhere: "blend 'half-res' and 'full-res' images smoothly to avoid banding".

### 1.10 Banding and dark-band fixes in cr2hdr
None of these is named "dark band". The relevant ones are: the robust highlight-weighted gain (1.2); the 1500-DN
white safety margin on the bright exposure (1.1); the per-row stripe fix (1.5); the final black re-subtraction; and
doing every mix in EV with raised-cosine weights.

## 2. Other prior art (from memory, not re-read for this note)
- Nayar & Mitsunaga, *High dynamic range imaging: spatially varying pixel exposures*, CVPR 2000: a fixed mosaic of
  4 exposures. Saturated or under-exposed pixels are discarded and the rest are scaled to radiance. The image is
  rebuilt by "aggregation" (local polynomial / cubic fit of the valid samples), i.e. **mark unreliable → refit from
  reliable neighbours**. This is the order the coordinator asked for.
- Sony SME-HDR / interleaved-exposure (IMX 2×2 "Quad Bayer" and row-interleaved) demosaicking literature: the
  standard pipeline is the same three steps. Equalise exposures (gain and offset), estimate the missing samples
  from other-exposure same-colour neighbours (edge-directed, colour-difference), and blend by saturation and noise.
  It adds motion detection between exposures (not needed here: same exposure window). No paper we know of has our
  exact column-pair checkerboard, or a row offset between the two groups.

## 3. Mapping onto our geometry

Raw block (rows mod 2 × cols mod 4), F = full, a = attenuated:

```
row 0:  R a   Gr a  | R F   Gr F
row 1:  Gb F  B F   | Gb a  B a
```
- Same-colour **other-gain** neighbours of any pixel: (0,±2) and (±2,±2). Same-colour **same-gain**: (±2,0),
  (0,±4), (±2,±4). The vertical neighbours always have the same gain, so a pure vertical estimate from the other gain
  does not exist for R/B. It has to go through colour differences against green.
- Green has more: Gr's other-gain greens at (±1,−1) and (±1,+3); Gb's at (±1,+1) and (±1,−3). A centred vertical
  estimate is `0.75·mean(near column) + 0.25·mean(far column)`. Using the near column alone gives the one-pixel
  diagonal zig-zag that hdr_cd saw as a comb.
- Every 2×2 cell holds one full and one attenuated green; R and B alternate gain by cell column.

| cr2hdr step | our version | addresses |
|---|---|---|
| (none) | **register the att group by off_c(y)** (§0) | dark band, bead rings, most of the comb |
| match_exposures (robust line in the top range) | per-colour **monotone LUT** from block means (the response is curved) | residual hand-over brightness step |
| black_subtract / stripe fix | OB black; per-column-phase defect clamp (§0) | period-16 comb |
| find_and_fix_bad_pixels | hot + cold, same colour, same gain, 8 neighbours | white/black specks after ×1/k |
| bright/dark images + mix_curve | per-pixel confidence: full fades out 0.80→0.93 of clip (joint over 5×5, all colours) | colour switch at different places |
| fullres + alias map | att sample kept where it disagrees with the full-neighbour interpolation beyond noise (χ², per-sample clip 9, mean over ~14 att samples, threshold 2→4, dilated 3×5) | resolution in midtones without att noise |
| edge-directed interpolation | gradient-weighted H / centred V / diagonals for G; colour difference vs G for R/B | staircase, comb |
| chroma_smooth 2x2/3x3 | plus-5 cell median (3×3 where att-only), asinh domain | chroma speckle |
| work in EV | asinh domain for demosaic and chroma (linear < 24 DN, log above) | overshoot rings on point highlights |

## 4. The algorithm in `hdr_ml.py` (numpy only, ~8 s on 2022×6064)

```
raw, clip  = decode, subtract OB black
fits       = per colour c: block-match full vs att planes -> off_c(y) = a_c + b_c*y      # §0
raw[att]   = att plane of c resampled at row  y - off_c(y)  (linear between same-colour rows); attok mask
lut_c      = monotone binned medians of (att block mean -> full block mean), flat 16x32 blocks, full < 0.97 clip
M          = full: raw ; att: lut_c(raw)           # one radiance scale (full units)
M         *= scale_c (full -> stock units, median over flat blocks)
V          = full: 100 + 2 L ; att: 70/k_c^2 + 2 L
M          = hot/cold repair (8 same-colour same-gain neighbours, 4 sigma)
M          = clamp col%16 phases flagged in this frame to [min,max] of (0,+-4) neighbours
cF         = ramp(max full raw in 5x5; 0.80 clip -> 1, 0.93 clip -> 0); 0 if clipped; 1 where no att data
Eg         = green estimate from other-gain greens (H, centred V, D1, D2; w = 1/(grad/eps)^2)
alias      = clip((mean_14(min(chi2,9)) - 2)/2, 0, 1), dilated 3x5
keepA      = attok * (1 - fullnb*(1 - alias))       # fullnb = local mean of cF over full pixels
G1         = blend(native, Eg, keep) on greens;  Gh = green at R/B (gradient-weighted 4-neighbour)
Erb        = Gh + weighted mean over (0,+-2),(+-2,+-2) of (M - Gh), weights exp(-z^2/8) on green similarity
R          = keep*M + (1-keep)*E                    # keep = cF on full, keepA on att
R          = chroma median (cr2hdr 2x2; 3x3 where att-only), asinh domain
RGB        = Hamilton-Adams + colour-difference demosaic in asinh; chroma Gaussian (sigma 2) where att-only
```

## 5. Results (0738 = 20, `captures/checker/crop_v4_vs_ml.png`)
- **Dark band in the hand-over zone: gone.** It was the 32-row displacement, not the blend.
- **Vertical comb streaks: gone.** Two causes: the displaced att image, and the col % 16 = 5 (and 1, 9) phase defect.
- **Cyan fringe** that appeared when only an integer 32-row shift was used: gone once R and B got their own
  row-dependent offset.
- **Bead rings**: the blue/green rings of v4 are gone, and the beads are white and in the right place. A pink/green
  pixel-scale speckle remains inside the beads: a 4–6 px specular point sampled by half the pixels, unavoidable in
  one frame. The chroma median and blur reduce it but do not remove it.
- **Shadows**: as fine-grained as stock, with no blotches. Midtone resolution is kept: attenuated samples are used
  only where the alias test says they carry detail.
- **0738 = 10**: clean. **0738 = 40**: a pink/purple speckled band in the partial hand-over zone at the gray→white
  edge. There k ≈ 1/30, so the att samples are ~2× noisier than at 20; that zone needs a stronger chroma treatment
  or a later hand-over (t0/t1 are CLI options).

## 6. Remaining issues / open questions
- The R/B offset drift (~5 rows over the frame height, same at all 0738 values) is measured but not understood. A
  linear fit per colour is used; if it is really non-linear, edges at the very top and bottom may still fringe.
- The top `off` rows (16/32/64) have no attenuated data and stay clipped. Crop them in production.
- Highlight brightness above the full clip depends on the LUT extrapolation (top-third slope). A flat-field
  exposure series would pin the att response curve down.
- Small staircase along steep high-contrast edges in highlight areas (half-density sampling there).
- The mechanism of the col % 16 ∈ {1, 5, 9} defect is unknown; the clamp is empirical (it can also flatten real
  1-pixel vertical detail in those columns).
- On the camera, registration means the att group must be read 0738 rows ahead (or buffered). Any in-camera
  merge has to carry `off` rows of the other group.
