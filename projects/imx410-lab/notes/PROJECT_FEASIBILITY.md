> ⚠ 已過時：10-20 的可行性評估；部分數字已被 §42–§58 取代（例如 L2b 96 fps）。

# New readout project — feasibility against the IMX410 (updated 2026-10-20 after live tests L1–L6)

Evidence tags: [M] measured on the fp, [C] code/tables (fp, Z CAM, ZWO/QHY/ToupTek, Sony flyer), [I] inferred, [?] open.
Details: `IMX410_RULES.md` §21 (families), §30–§32 (spatial HDR), §31 (synthesised readouts), `L7_14BIT.md`.

## 1. Requirement → status

| requirement | status | evidence |
|---|---|---|
| Synthesise the readout; stock modes only as a check | **feasible** [C+M] | every table register depends on one attribute (§21); `readout_test.py` + `batch.S` run synthesised readouts live (§31) |
| Bit depth 12 / 11-bit fast | **done** [M] | 11-bit fast set works (L2b) |
| Bit depth 14 | **1×1 stock; 14-bit binned open** | SoC side decoded offline (`L7_14BIT.md`), live test L7 pending |
| Bit depth 10 / 8 | **not a sensor setting** [C] | output word is 12/14; 10/8 = recording-side packing/LUT |
| Stepless FPS | **done** [M] | fps = 72 MHz/(HMAX·VMAX); 6064×1010 1×1 at 140.6 fps intact (L1) |
| Vertical crop / offset | **done** [M] | output window `0022–0025` + receiver window `0x30100024` (§15, L1) |
| Horizontal crop | fixed sensor widths 6064 / 4160 (`0001`); finer = SoC side, no RS gain [M/C] | L2a: 4160 with 6 writes |
| Narrow 1×1 + fast ADC | **done** [M] | 4160×2160 11-bit at **HMAX 335 ≈ 96 fps**; 330 drops every other line; needs receiver width 4176 + BUFA re-window (L2b) |
| Vertical-only 1×2 | **done** [M] | Z MODE21 set + `0018=12` (36 dark rows so the CRCT clamp sees only dark rows) (L3) |
| Vertical-only 1×3 | **done** [M] — not in any Sony/Z CAM table | mode-139 Family B + the "no horizontal merge" set (L4) |
| Priority solver | **feasible** [I] | the three axes (ADC class, vertical reduction, window) are independent families |
| HDR temporal, alternating exposure | **done** [M] | alternating SHS (§16) |
| HDR temporal, alternating conversion gain | **feasible** [M] | per-frame alternation proven; only improves shadows |
| **HDR spatial (single frame)** | **done, with limits** [M] | see §2 |
| PC merge tool | **working** | `hdr_ml.py` (register → LUT → repair → one demosaic); calibrated LUTs per gain/V |

## 2. Spatial HDR — what it really is and how to present it

- Mechanism [M]: `0242 = 01` + `0738 = V` → 2×2-cell checkerboard; the attenuated half is the pixel of row y + V read
  at its own time through a second low-gain path with a **small voltage-swing ceiling** (≈ 1/5 of the 0 dB range,
  scales with analog gain, not with HCG) (§32).
- Geometry is fixed: attenuated rows are offset by exactly V; the coefficient comes from a calibration LUT per
  (analog gain, HCG, V) — no per-frame fitting.
- **Specify it at 2×2 output (half resolution each way)**: every 2×2 cell group holds 2 full + 2 attenuated real
  samples per colour, no interpolation. Against a stock 2×2 image:

  | ISO (stock gains) | highlights (colour / luma) | shadows | net colour latitude |
  |---|---|---|---|
  | ≤ 400 | 0 | −0.5 | **negative: do not offer** |
  | 800 | ≈ +0.7 / +1.4 [I] | −0.5 | ≈ +0.2 |
  | **3200** (26.4 dB, LCG) | **+2.2 / ≥ +3.8** [M] | −0.5 | **≈ +1.7** |
  | 6400 | ≈ +3.0 / +3.7 [I] | −0.5 | ≈ +2.5 |

- V trade-off at ISO 3200 [M]: V = 0x20 clean, +2.2 colour (ceiling reached); V = 0x40–0x80 ≥ +2.6 but visible
  chroma noise in the recovered highlights (attenuated samples ~100 DN) → default V = 0x20; larger V only with
  highlight chroma denoise (to do).
- 1×1 readout only (L6: in 3×3 binning the groups mix, ~1 EV split). Top V rows have no attenuated data → crop.
- UI wording: "high-ISO highlight recovery", enabled from ISO 800; strength 1–3 = V 0x20 / 0x40 / 0x80.

## 3. Rules for the solver (measured)

- RS = HMAX × covered rows ÷ vertical reduction ÷ 72 MHz; HMAX: 911 (14), 445–450 (12), 400 (11-bit, 6064 wide,
  receiver unchanged), **335 (11-bit, ≤ 4160 wide, receiver 4176)**.
- Every window change needs the SoC receiver window to match the rows the sensor sends (L1, L3: 2062 rows never
  complete when the sensor sends fewer).
- Vertical reduction cuts the OB rows (40 → 5): add `0018 = N` (2N dark rows) or the CRCT clamp eats image rows.
- Spatial HDR: 1×1 only, ISO ≥ 800, crop the top V rows, shutter ≥ V lines (shorter breaks the attenuated read).

## 4. Next steps (in order)

| # | item | type |
|---|---|---|
| 1 | L7: 14-bit live (read-only checks → 14-bit receive of stock data → 14-bit 2×2) | live, needs OK |
| 2 | Highlight chroma denoise in `hdr_ml.py` → make V = 0x40/0x80 usable | offline |
| 3 | Calibration LUT grid: analog gain {12, 18, 24, 26.4, 30} dB × HCG {0,1} × V {0x20, 0x40, 0x80} | live, ~30 min |
| 4 | Generator: mode tables from (ADC class, vbin, format, window) reproducing all 70 stock tables field by field | offline |
| 5 | In-camera path: buffer V rows for spatial HDR; IMXB inject mode for per-frame writes (temporal HDR, 023A) | design |
| 6 | Base-ISO latitude: 14-bit (shadows) + temporal exposure HDR (highlights) | after 1 |

None of the live items writes the settings area; everything is sensor/RAM state undone by a sensor reset.
