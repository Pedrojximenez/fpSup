# IMX410 mode registers — what the 161 writes mean

Ver.5.02. Source of every number: `out/seg0_c0000000.bin` + `out/seg1_c2ef6e00.bin`,
register table at `0xC0B5FDAC`, stride `0x288`, 70 rows of 162 words.

## The write path is proven, not inferred

`FUN_c03258c8` is **straight-line code with zero branches** between its first and
last sensor write. It issues exactly 161 calls:

```
FUN_c0322c70(<literal register>, [r0 + 4*k])     k = 1 .. 161
```

with the offsets running strictly `#4, #8, #0xC, …, #0x284`. So word *k* of a mode's
row goes to the *k*-th literal, always, for every mode. Verified by disassembly:
reg `0x0001`←word 1, `0x0003`←word 2, `0x0005`←word 3, `0x0016`←word 4, `0x001C`←word 5 …
`0x08B7`←word 161. A 162nd call writes the constant `0` to reg `0x00CE`.

The transport is I²C with a 16-bit register address:

```
FUN_c0322cb0(buf, reg, val):   buf[0] = reg >> 8;  buf[1] = reg;  buf[2] = val
```
(`ubfx r3, r4, #8, #8` / `strb`). `FUN_c0322c70` seeds a 4th byte from `0xC0B594FC`
and hands the packet to `0xC0126550`. Every value is 8-bit; the largest seen is 252.

## Method

161 registers × 70 modes is small enough to attack without a datasheet:

1. **Affine search.** Every 1/2/3-byte field (including big- and little-endian pairs
   at consecutive addresses) tested against hmax, tail, vmax, width, height, crop,
   merge, bit depth, nominal fps — accepting only relations exact across all 70 modes.
2. **Covariance grouping.** Each register induces a partition of the 70 modes
   (which modes share a value). Registers with the same partition move together and
   belong to one function. This is the part that pays: **161 registers collapse to
   only 24 distinct partitions**, 29 of them constant.

## Result 1 — frame geometry and timing are NOT in these registers

The affine search found **no** encoding of hmax, tail, vmax, width or height,
in any byte order, at any width. Those are programmed by some other path; the 161
mode registers are analogue/readout configuration only.

## Result 2 — the decoded registers

150 of 161 now have a function. Confidence is stated per entry; "covaries exactly"
means the partition matches over all 70 modes, which is strong evidence of
*association*, not proof of causation.

| register(s) | n | meaning | confidence |
|---|---|---|---|
| `0x001C` | 1 | **merge select**: `5`=1×, `3`=2×, `2`=3× | high — partition identical to the merge tuple |
| `0x0717` group | 9 | **2 × merge factor**: `2`/`4`/`6` (plus `0` on the three 672-line modes) | high — numeric relation, not just covariance |
| `0x0058` | 1 | merged or not: `32`=no, `112`=yes | high |
| `0x0016` | 1 | **vblank ÷ 2**, exactly: `7`→14, `15`→30, `20`→40, `25`→50, `35`→70, `50`→100 | high — exact affine over 6 values |
| `0x0001` | 1 | **mode class** = merge × depth: `41`=1×/14-bit, `42`=1×/12-bit, `57`=2×/12-bit, `47`/`48`=3×/12-bit | high |
| `0x0042 0x007F 0x008C 0x0403 0x0453 0x0525 0x0575 0x0576 0x057A 0x06D9` | 10 | **bit depth**, 12 vs 14 (e.g. `0x0525`=16/17, `0x0575`=18/16, `0x008C`=51/0) | high |
| `0x0062` group | 50 | **fast-readout switch**: `16` when hmax ≤ 395, `0` when hmax ≥ 445 | high — clean threshold, no overlap |
| `0x007E` group | 21 | **readout speed tier**: `60` (hmax 330–395), `70` (445–450), `96` (911, all 1× and 14-bit) | high |
| `0x0085` group | 5 | follows the same speed split (`20`/`25`) | medium |
| `0x0005 0x0716 0x0722 0x0724` groups | 21 | track the frame-height tier | medium |
| `0x0089` | 1 | covaries with the metadata fingerprint field | medium |
| 29 registers | 29 | identical in all 70 modes (`0x0590`–`0x0595` = 1,3,1,3,1,3; `0x059A`–`0x059D` = 2,2,2,2; …) | — |

Line rate makes the speed split concrete: the `0x0062`=0 group runs 79–162 kline/s,
the `=16` group 182–218 kline/s.

### Still unexplained — 11 registers

`0x0003` `0x0022` `0x0023` `0x0024` `0x0025` `0x0056` `0x0057` `0x008A` `0x0726` `0x0790` `0x079C`

`0x0003` is a flag set on exactly 9 modes (6, 10, 58, 95, 100, 122, 132, 133, 134),
and `0x0022`–`0x0025` are zero on the other 61 — so those five are one feature,
enabled together. What the feature *is* remains open (see the disproved guess below).

## Result 3 — modes 98 and 117 do NOT differ in their merge settings

This corrects an earlier claim. 98 and 117 differ in 78 registers, and every one of
them falls in a **readout-speed** group:

| group | differing |
|---|---|
| `0x0062` fast-readout group | 50 of 50 |
| `0x007E` speed-tier group | 21 of 21 |
| `0x0085` speed group | 5 of 5 |
| `0x0016` vblank | 1 |
| `0x0089` fingerprint | 1 |

Every merge register — `0x001C`, the `0x0717` group, `0x0058` — is **identical**
between the two. Their raster (3032×2012), merge tuple (2,2,2,2) and bit depth match;
what differs is hmax 445 → 330, i.e. 98 reads out at normal speed and 117 in the
fast tier.

So the observed difference in pixel-merging quality is not a different binning
setting on the sensor. Either the faster analogue timing degrades the merge, or the
difference is added later in CRCT (`vbin`/`hbin`/`hbin2`), which is configured from
the PARAM profile table and not from these eight tables at all. That is the next
thing to test, and CRCT is the more likely place to look.

## A guess that was tested and failed

The 9 modes with `0x0003`=1 all run at exact broadcast rates (29.97, 25, 23.98,
119.88, 100, 59.93), which looked like a "precise frame rate" flag. It is not:
45 of the 61 modes with `0x0003`=0 are also within 0.2 % of a broadcast rate.
`tail != hmax` and two predicates on the timing word were tested as well — all
three have false positives. Recorded here so it is not re-guessed.

## Correction — CRCT is ruled out, and the merge chain now closes

Added after the user pointed out that OG3K/OG2K do not run CRCT or RWZM. They are
right, and it is stronger than that:

⚠ **This section first said "CRCT binning is never switched on, for any profile."
That was wrong** — corrected 2026-09-22 after a reader misread the flow diagram as a
single chain. What is true is narrower, and the distinction matters.

CRCT is not a chain, it is a static eight-branch selector. Over the 306 profiles
(counts reproduced from the profile dump, matching `CRCT_PATH_SELECTOR_SOLVED.md` §8a):

| branch | profiles | what runs |
|---|---|---|
| B/D `Crmf` | **253** | no reduction at all — **Open Gate p43 and stock FHD p133–136 are here** |
| C `CrctHbin2ToBufA` | **36** | second-stage horizontal binning |
| E | **17** | RWZM ÷1.5625 **and** hbin÷3/vbin÷3 together, all UHD |
| F | 0 | dual pipeline, never reached |

**The trap that produced the wrong claim.** The dump's `reduction_enums` is the
*recording* hbin/vbin pair (`+0x5C`/`+0xC8`), and that pair really is zero in all 306.
But branch E's main pipeline does not read it — it reads the recording **RWZM** ratio
together with the **preview** hbin/vbin tap counts (`+0x58`/`+0xC4`), which are set to 1
on exactly those 17 profiles. Verified independently here: the word indices that are 1
on precisely the 17 branch-E profiles are 22 and 49, i.e. `+0x58` and `+0xC4`.

So "the recording hbin field is always zero" is true and "CRCT never bins" is false.

What survives unchanged: **Open Gate p43 is in the 253 that reduce nothing**, so an
Open Gate frame is the sensor output untouched, and stock FHD p133–136 are too — which
is why the merge chain below still holds.

So the guess at the end of the previous section — "CRCT is the more likely place" —
is wrong. On an Open Gate clip there is nothing between the sensor and the file, and
the only thing that differs between modes 98 and 117 is the readout-speed block.

### This closes the open question in `PIXEL_MERGE_MEASURED.md`

That note measured, from shot noise, how many photosites land in one output pixel,
and explicitly could not say at which stage the merging happened:

| | measured N_eff | sensor stage | RWZM | predicted |
|---|---|---|---|---|
| stock FHD 1936×1090 | **8.53** | mode 106, 2× merge → 4 | p133–136, ÷1.5625 | (2 × 1.5625)² = **9.77** |
| OG2K 2016×1344 | **4.10** | mode 139, 3× spacing but 2 taps → 4 | unity | **4** |

The merging is **sensor + RWZM, two stages**, CRCT contributing nothing. OG2K's
"only 4 of 9" is not the sensor being stingy — it is the absence of the RWZM stage
that the stock FHD path uses to go from 4 up to ~9.

That also re-frames the note's closing suggestion. Getting the 0.5 stop back does not
require changing the sensor's 3-tap behaviour; it requires the second stage. RWZM is
already proven to work (53 stock profiles use it) and is a single pair of PARAM words.

### The testable prediction this leaves

Modes 98 and 117 are both 3032×2012, both 2,2,2,2, both 12-bit, identical in every
merge register, and both served by p43 at RWZM unity. They differ only in the 76
readout-speed registers (hmax 445 vs 330). `PIXEL_MERGE_MEASURED.md` already showed
that the metadata merge value is a **spacing**, not a tap count — M139 is labelled 3×3
and averages 4 of 9. If the fast-readout tier drops a tap to hit 218 kline/s, then:

> **Prediction: on Open Gate, mode 98 measures N_eff ≈ 4 and mode 117 ≈ 2**
> (one stop noisier, sharper, more prone to aliasing).

This is directly measurable with the existing `pixmerge.py` — same ISO, same scene,
one clip each, no rig. If it holds, the readout-speed block is the mechanism behind
the merge-quality difference; if 98 and 117 measure the same, the difference is
somewhere neither the sensor registers nor the profile table describes.

## 旁證(2026-09-24):Z CAM E2-F6 的 IMX410 表格
Z CAM 的 2020×1080(3×3 合併)跟 fp 模式 134 只差 0x0016、0x0022/23、0x0024/25。
Z = 453 / 540(輸出 1080 行),fp 134 = 365 / 570(輸出 1136 行)
→ **0x0024/25 ≈ 輸出高度 ÷ 2**、**0x0022/23 ≈ 垂直起點**(假說,未驗證)。細節在 `zcam_e2f6/notes/ZCAM_E2F6_FIRMWARE.md`。
