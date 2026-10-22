# fp 5.02 LCD colour route audit — offline, 2026-09-24

> 2026-10-09 update: the blanket tiled-ring interpretation below is superseded for the tested
> CINE MONIT1 configuration. An authorized native-ring read decodes as a complete 1620x911
> linear YUYV8 image at a 3240-byte row stride. The first develop descriptor is still empty;
> the second points into the rotating ring. RGB encoding, frame coherence and writable-buffer
> ownership remain unverified. See [capture analysis](../../projects/lut-sup/validation/20261009-native-preview-bytes-01/analysis.json).

No camera commands were issued. Sources are the local firmware image, extracted data segment, decompilation and existing measured notes. C function names with raw addresses are decompiler labels, not vendor semantic documentation.

## Conclusion

The firmware has a real display-end matrix and separate RGB gamma machinery, distinct from the image processor's tone tables. This is a plausible place for panel calibration and a small display-only colour correction. It is **not yet a proved location for a general monitoring transform**: active bank selection, image-versus-OSD coverage and clamp ordering must be measured before using it. It cannot recover colour already clipped upstream.

A better investigation separates (1) information lost in the ISP/preview source, (2) wrong matrix/range conversion or clamping at scanout, and (3) the LCD's physical gamut/transfer function. Existing OSD capture is not a screenshot of the developed live image.

## Concrete display-end path

| Stage | Static evidence | Scope and limitation |
|---|---|---|
| LCD driver | `XC_DisplayLcdJDI_LPM032M366C::v6 @ C0308658` packages three values and calls `C0625F68` | `out/decomp/full/blk_c03.c:6676`; actual panel class, stronger evidence than an OSD-only helper |
| RGB calibration values | `C0625F68` validates three integers in 0..511; calculates 3×3 YUV-to-RGB style coefficients; builds two matrix versions | `blk_c06.c:35355`; input neutral is 256, coefficient scale 256 |
| Matrix state | `C00FA8A8` stores nine coefficients, sets pending flag `C31D7170`; `C00FA808` stores the other matrix | `blk_c00.c:197959` and `:198009` |
| Display application | `C00DD6C8` reads active output state, selects matrix bank 0 or 2 via `C00DD6A8` | `blk_c00.c:168209` and `:168226`; LCD is not hardwired to one bank for every dual-output state |
| Hardware matrix writer | `C00E3948(param, bank)` | `blk_c00.c:174264`; bank 0 writes `30190870..30190898`, bank 1 writes `30190810..30190838`, bank 2 writes `30190C80..30190CA8`; offset/control words at `30190864`, `30190804`, `30190C74` |
| Gamma construction | `C00DDA20` takes display descriptor calibration at `+0x50`, then its data pointer at `+4`; reads 12 words from data `+0x38..+0x64` | `blk_c00.c:168410` |
| Gamma hardware | `C00DDB50` calls `C00E3AF0` | `blk_c00.c:168470`, `:174371`; selector byte at parameter `+0x34` chooses `30190940..3019096C` or `30190CB0..30190CDC` |
| Display-start reapplication | `C00FABD0` reapplies pending LCD matrix during panel start | `blk_c00.c:198201`; a blind one-time MMIO write may be overwritten later |

`C00DD300` builds matrix parameters for two output IDs, gamma parameters and selects banks according to output configuration (`blk_c00.c:168001`). This is explicit evidence of routing, and a reason to log the current route rather than assume the same registers are active in LCD-only, HDMI and EVF operation.

The three matrix hardware banks must **not** be casually labelled “LCD / HDMI / OSD”: static routing is conditional. No claim that every listed bank affects live image rather than a particular composite/format path is established here.

## Exact offline constants

Read from `out/MAIN_c0000000.bin` at virtual address minus `C0000000`, and `out/seg1_c2ef6e00.bin` at virtual address minus `C2EF6E00`.

`C0625F68` constants:

- `C0626304 = 256.0`, `C062630C = 1/256`.
- `C0626314 = -0.344`, `C062631C = -0.714`, `C0626324 = 1.772`, `C062632C = 1.402`.
- The second matrix uses `C062683C = -0.187`, `C0626844 = -0.468`, `C062684C = 1.856`, `C0626854 = 1.575`, calculated later in the same function (`blk_c06.c:35539`).

The default matrix at `C07C61E4` is:

```
mask 0x3FF
0x100  0x7A8  0x749
0x100  0x1C6  0
0x100  0      0x167
extra 0
```

Interpreting the negative coefficients as 11-bit signed and dividing by 256 yields rows `[1,-0.34375,-0.71484]`, `[1,1.77344,0]`, `[1,0,1.40234]`, consistent with G/B/R rows of a full-range 601-like YUV decoder. This does **not** establish that the current preview source is 601/full-range, nor the hardware's chroma centering or exact clamp rules. It gives a useful falsifiable range/matrix hypothesis.

`C00FAF00` assigns the LCD descriptor's `+0x50` to `C2EFF18C` (`blk_c00.c:198467`). In extracted initial data:

```
[C2EFF18C+4] = C2EFF2CC
[C2EFF2CC+0x38..0x64] =
  40302010 80706050 C0B0A090 FFF0E0D0
  40302010 80706050 C0B0A090 FFF0E0D0
  40302010 80706050 C0B0A090 FFF0E0D0
```

These are three identical packed sets of 16 bytes: `16,32,48,...,240,255`. The fallback in `C00DDA20` writes the same sequence. `&DAT_c0b0a090` in the decompiler is a misleading pointer rendering of the numeric packed constant **0xC0B0A090**, not an instruction to load gamma data from that address.

This supports a **coarse per-channel gamma table** candidate, likely 16 knots/channel. Exact input knot positions/interpolation remain unverified. These are boot/default constants; they are not a dump of the user's active camera calibration. Runtime defaults/adjustment data may differ.

Strings `PARAM_LCDCOLOR_RY/RU/RV`, G and B equivalents, and `PARAM_LCD{R,G,B}GAMMA_1..4` are present (`out/MAIN.strings.txt:5877`). String existence alone is weaker than the consumer chain above, and does not authorize persistent calibration edits.

## What existing tools can and cannot show

1. The previously measured geometry route is separate from the RAW recording geometry: profile 5 preview source → visible window → `C0437E98` output descriptor → `C0306EA0` fit. See `projects/open-gate/notes/LIVE_VIEW_DISPLAY_CHAIN.md:12` and `:26`. These geometry hooks do not prove independent colour processing from MOV.
2. `display capture` captures OSD layers. Main is 1024×682 ARGB4444; sub is 8bpp palette; verified in `research/display/notes/SPLASH_BAND.md:47`. A palette/YUV adjustment there can recolour the UI while leaving live image clipping unchanged. OSD ramps can test part of the final display chain but cannot stand in for a live-image ramp without proving shared coverage.
3. `display lcdTune` exists in the shell command table (`C0BB1434`, handler `C03E3288`, `blk_c03.c:159157`). Its provider `C03087F8` returns `DAT_C0B55190` (`blk_c03.c:6785`), whose value in the stock MAIN is **0**. The handler prints `not Support`. Therefore this is **not** an established usable gamma adjustment command. Do not run it as a harmless query; the decompilation does not clearly terminate after that message.
4. `display colorbar` calls `C00E1FF8` (`blk_c03.c:159208`). The callee (`blk_c00.c:172403`) sets `3019002C |= 0x3256` for on, clears its low 16 bits for off, and does not use the shell's second pattern argument. It is a hardware DIFM test-pattern, not an arbitrary CPU framebuffer. Existing shell research records visible colourbars. It may be useful to localize display problems after tracing its injection point relative to CSC/gamma, but cannot test the upstream ISP tone path. Normal-looking colourbars alone do not establish correct panel gamut, transfer or live-image colour.
5. `research/imaging-hw/notes/IMAGE_CHANNELS.md:30` documents the tiled scanout ring; interpreting it as ordinary YUYV produced garbage. The linear develop descriptor at `C375C05C`, buffer cell `C375C078`, is a candidate source (`:40`), but the recorded first standby probe was all-zero (`:52`). No assumption that a valid full-colour live source is immediately available.
6. HDMI output includes a quantization flag in mode structure `+0x0C`; see `research/interfaces/notes/HDMI_RAW_FORMAT.md:180`. That is not proof that LCD and HDMI have the same range or same final transform. HDMI capture can additionally change range, matrix and chroma resolution.

## Most useful next measurements

All below describe future, separately reviewed camera work; none was performed here.

1. Log active output IDs, preview profile/geometry, source buffer descriptors, all three display CSC banks and both gamma banks in one coherent snapshot. Record standby/half-press/record/HDMI states independently.
2. Present neutral and single-hue exposure ramps through the actual live image, retaining original RAW and an upstream developed image where available. Compare numeric source channels, HDMI decoded with explicitly verified matrix/range, and a controlled physical LCD measurement.
3. If the source keeps gradation but LCD collapses it, inspect display CSC output values *before* final clamping and compare 601/709 plus full/limited hypotheses. A wrong YUV decoder can clip coloured highlights even when Y itself is below white.
4. If source values are already on a plateau, move the transform before that clamp. Changing panel gamma after the plateau cannot restore distinctions. Linear tone may preserve a larger interval upstream but needs a sensible output rendering curve, otherwise the screen is dark and not colour-accurate.
5. If display CSC is the clipping point, a temporary display-only gain reduction can establish causality. It is a diagnostic, not necessarily the final appearance: common gain sacrifices screen brightness; independent gain can shift hue; arbitrary 3×3 matrices are not gamut compression.
6. For final viewing, use a smooth scene-to-display tone and gamut mapping before irreversible clamping, then panel calibration. The 16-knot RGB hardware table is potentially useful for transfer calibration, but by itself is too limited to implement a general hue-preserving gamut map.
7. Verify OSD coverage and ensure MOV/RAW output is unchanged before calling an implementation “monitor-only”. Test mode changes because native routines reapply state.

## Practical judgment

The display-end matrix/gamma route is worth instrumenting because it is concrete and near the LCD. It is not a justified first blind fix. First determine whether coloured highlights remain distinct at the display input. That one result decides whether a small LCD-path correction can solve the fault or whether the ISP preview rendering must be changed.
