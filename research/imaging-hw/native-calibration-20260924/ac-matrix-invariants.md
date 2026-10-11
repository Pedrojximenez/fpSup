# What an A/C TIFF comparison can test mathematically

2026-09-24. Source: the existing verified A/C DNG metadata and candidate report. This independent math audit does not inspect the newly exported TIFFs directly. The parent image analysis and user confirmation identify the second export as C; the first export is byte-identical to the earlier A TIFF.

## The useful invariant, and its conditions

Let `M_A` and `M_C` be the effective interpolated XYZ→camera ColorMatrix values. For the same camera vector `r`, a simplified **unadapted**, scene-linear decode would be `x_A = inv(M_A) r`, `x_C = inv(M_C) r`.

The prediction is therefore:

```text
T_XYZ = inv(M_C) M_A
x_C = T_XYZ x_A
```

If both exports use a common invertible, linear XYZ→output-RGB transform `P`, then `T_RGB = P T_XYZ inv(P)`. Changing the common output gamut changes matrix entries but not eigenvalues, determinant, or trace. Singular values, individual matrix entries, and row sums are **not** general basis invariants.

This makes eigenvalues a useful *conditional* check even when the exact linear gamut basis is unknown. It does not excuse unknown transfer functions, clipping, per-clip grading, highlight reconstruction, or nonlinear gamut/tone operations. Those can invalidate the global linear model. A low residual on held-out, non-clipped pixels is necessary before interpreting the fitted matrix.

## Why the bare matrix ratio is not a complete As Shot prediction

The DNGs retain the same AsShotNeutral:

```text
n = [0.5130260521, 1, 0.583143508]
```

But `inv(M_A) n` and `inv(M_C) n` are different XYZ white estimates. Thus the same As Shot camera-neutral metadata does not guarantee the same inferred CCT, interpolation fraction, chromatic-adaptation transform, or exposure normalization. Setting the same manual Kelvin/Tint can instead change camera gains and introduces another possible difference.

A fuller linear model is:

```text
x_i = P Q_i inv(M_i(t_i)) r
T_RGB = P Q_C inv(M_C(t_C)) M_A(t_A) inv(Q_A) inv(P)
```

Here `Q_i` collects profile-dependent white adaptation and scalar normalization. A shared, additional camera-domain diagonal gain would cancel between the two maps; a profile-specific gain would not. `t_A` and `t_C` need not coincide when inferred from camera neutral. Two anchor matrices must not be averaged by an arbitrary arithmetic Kelvin rule and then treated as a verified Resolve implementation.

## Stronger neutral-preservation check

If both decodes map the same camera-neutral vector `n` to the same output-white vector `w`, with the same normalization, then:

```text
T_RGB w = w
```

Therefore one eigenvalue must be 1. In a linear RGB encoding where neutral white is `[1,1,1]`, the row sums must also be 1. A relative exposure scale `s` changes this to `T w = s w`; the white eigenvalue and row sums become `s`. This structural prediction does not require knowing the two interpolation weights.

Its absence does not immediately prove metadata is ignored: it can indicate different exposure conventions, white handling, incorrect assumed TIFF transfer function, clipping, or a nonlinear processing stage. Conversely, its presence does not demonstrate absolute color accuracy.

## Numerical examples, not Resolve emulation

The accompanying script evaluates common CM2 weights 0, 0.25, 0.5, 0.75, 1. It includes two deliberately distinguished models:

1. Bare `inv(M_C) M_A`, without white adaptation or normalization.
2. An illustrative Bradford model that maps each `inv(M_i) n` to a common white, including common-white magnitude normalization.

For the D65/CM2 endpoint:

| Model | Eigenvalues | Determinant |
|---|---|---|
| Bare CM ratio | 2.318849, 1.662225, 1.302213 | 5.019312 |
| Bradford + neutral normalization | 1.696586, 1.231299, 1 | 2.089006 |

At a shared 50% CM2 fraction, the illustrative neutral-preserving model instead yields approximately `1.673697, 0.912165, 1`. These differences demonstrate why a TIFF fit should not be rejected solely for failing to match the bare CM-ratio eigenvalues. Neither this chosen interpolation fraction nor Bradford normalization has been proved to be Resolve's exact algorithm.

The common target white and common output basis alter the adapted model by similarity; they do not alter its eigenvalues when adaptation is performed consistently. Thus choosing P3 D60 rather than sRGB is not itself a reason the eigenvalues should differ.

### Relation to the confirmed A/C export pair

The separate image audit's spatial-holdout fit, when tentatively inverse-decoding TIFF values with the sRGB transfer function, reports eigenvalues `1.69106580, 1.22308241, 0.99987343`, with row sums `0.99905993, 1.00018127, 0.99947156`. The non-neutral eigenvalues differ from the illustrative CM2-endpoint model by approximately −0.33% and −0.67%; the neutral eigenvalue is within 0.013% of 1. Observed determinant is about 2.06805 versus 2.08901 in that illustrative model.

This is broad numerical compatibility with an input-matrix change followed by neutral-preserving adaptation. It is not an exact reconstruction of the decoder. In particular, the image audit also obtains a reasonable fit directly in stored TIFF values, so this comparison does **not** uniquely identify the TIFF transfer function as sRGB. The unadapted endpoint ratio, with all eigenvalues substantially greater than 1, would be the wrong comparison for a white-normalized decode.

No interpolation fractions or adaptation parameters were tuned to fit those observed eigenvalues. The example remains a conditional diagnostic, not a claim that Resolve uses CM2 exclusively or the exact Bradford/normalization implementation above.

## Per-body calibration cancellation: exact but limited

Before integer serialization, firmware matrices have the form `M_i = inv(D) R_i`, where `D` is the same private body calibration and `R_i` the selected/interpolated ROM profile. Therefore:

```text
inv(M_C) M_A = inv(R_C) D inv(D) R_A = inv(R_C) R_A
```

This cancellation holds even for different A/C interpolation fractions, provided the same constant body calibration applies. Serialized DNG matrices are truncated to increments of 0.0001, so their numerical ratio differs slightly from the exact ROM ratio; the script records that difference.

The cancellation does **not** license ignoring `D` when solving white estimates: `inv(M_i) n = inv(R_i) D n`. White adaptation/interpolation can retain dependence on that calibrated camera neutral. Do not apply body compensation twice.

## Bounded conclusion

A controlled TIFF pair can establish that C is producing a reproducible linear color change consistent with an input-profile change, and can help distinguish linear gamut conversion from added nonlinear processing. It cannot establish that the scene's true colors are reproduced correctly without an independent reference. RAW-byte identity and manufacturer-profile provenance are already independently verified; a convincing TIFF fit adds evidence about decoder behavior, not a colorimetric ground truth.

Reproduction: run `predict_ac_matrix_invariants.py`; it reads the existing candidate-verification JSON and creates `ac-matrix-invariants.json` without overwriting an existing report or modifying any image.
