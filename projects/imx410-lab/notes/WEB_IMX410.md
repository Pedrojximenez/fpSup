# IMX410: public research data from the web (offline, 2026-10-20)

This note collects published data on the Sony IMX410, so that we run fewer experiments on the fp.
It extends `ASTRO_IMX410.md`, `ZCAM_COMPARE.md` and `IMX410_RULES.md` and does not repeat them.
The camera was not touched.

**Tags**
- **[C]** confirmed: a primary document, data read directly from a published dataset, or the same value from two independent sources.
- **[V]** vendor claim.
- **[F]** forum or blog anecdote, or a third-party claim with no evidence shown.
- **[I]** my own inference or arithmetic from the data.

**Downloads** (untrusted; nothing was executed) are in
`/private/tmp/claude-501/-Users-dido-Developer-localized-SIGMAfp-re/295c224f-f775-4447-bb3e-3a0ce48a948a/scratchpad/web_imx410/`:
- `flyer/` holds the Sony IMX410CQK flyer PDF.
- `p2p/` holds the PhotonsToPhotos chart pages, whose data is embedded in the HTML.
- `rs/` holds Horshack's rolling-shutter table.
- `astrocam/` is a clone of `github.com/mikefsq/astrocam`, with the IMX455 and IMX571 profiles.
- `zwo/` holds the ASI2400 manual (its text is not extractable).

Parsers are in the sibling folder `scratchpad/scripts/`: `p2p.py`, `p2ptab.py` and `pdftxt.py`.

---

## 0. Most useful findings

1. **[C+I] Every one of Sony's 23 readout modes is an integer VMAX at one of four HMAX values (72 MHz clock).** The four values are **911** (14-bit), **445** (12-bit normal), **431** (11-bit at full width 6064) and **330** (11-bit at width ≤ 4160).
   - Each flyer max-fps figure satisfies 72 MHz / (HMAX · VMAX), with VMAX = output rows + 76 / 56 / 50 / 42 / 38 (§2).
   - Those are exactly the fp/Z CAM speed classes from `IMX410_RULES.md` §21 (911 / 445–450 / 330–395) and Z CAM's 11-bit `MODE2D` at HMAX 429/431.
   - This gives the **fps ceiling of every fp readout class**, and it shows that **odd-numbered flyer modes are the 11-bit "fast" set**.
2. **[C] Rolling-shutter numbers from four other bodies hit our HMAX classes almost exactly.**
   - **14-bit, 911 cycles = 12.65 µs per line.** Landingfield measured 12.65 µs on the Nikon Z6; Horshack has the Z6 still at 12.63 µs/line and 50.8 ms per frame.
   - **12-bit normal, ≈ 448 cycles = 6.22 µs per line.** Blackmagic publishes 25.08 ms for 4032 rows, 19.90 ms for 3200 rows and 15.67 ms for 2520 rows, all 6.22 µs per line.
   - **fp UHD:** CineD measured 20.8 ms, which is 3376 rows × 6.18 µs.
   - **fp FHD:** CineD measured 10.4 ms, which is 1688 binned lines × 6.18 µs.
   - **Readout-time model:** rolling shutter = rows × HMAX / 72 MHz. It is confirmed outside the fp.
3. **[C] PhotonsToPhotos (Bill Claff) data for the SIGMA fp stills (14-bit DNG): the HCG switch is at ISO 640** (read noise drops between ISO 503 and 636).
   - The a7 III and S5 also switch at 640; the Z6, S1 and SL2-S switch at 800.
   - fp ISO 100 is **4.86 e⁻/DN14** with a read noise of 1.39 DN14.
   - **Cross-check:** ZWO's gain 0 (analog code 0) is 6.35 e⁻/ADU, and 6.35 / 4.86 = ×1.31. Our measured fp ISO-100 analog code 985 gives 4095/(4095−985) = ×1.317.
   - So the public fp base gain agrees with our gain law and code table to within 1% [I].
4. **[C] Sony's flyer gives the pixel scale at 0 dB in 14-bit LSB:** saturation is at least **15105 LSB** (Tj 60 °C) and sensitivity is 6660 LSB typical (F5.6, 1/30 s).
   - With a black level of about 1024 (14-bit), 15105 + 1024 ≈ 16129, just under 16383. So **the pixel full well about equals the 14-bit ADC range at 0 dB**, and any positive analog gain makes the ADC the clip [I].
   - That fits ZWO's 100 ke⁻ at 6.35 e⁻/ADU (15.7k ADU).
5. **[C] Sibling sensors (IMX455 and IMX571, from the open-source astrocam driver, wire-verified against ZWO's SDK) use different addresses but the same register structure.**
   - The two parts that matter for us:
     - **The top-band coarse gain is a nibble in bits [7:4], in 6 dB steps (`(stage & 0xF) << 4`).** That supports ZWO's IMX410 `0055 = n<<4` against Z CAM's 0–3.
     - **The black level is written to two identical 16-bit pairs** (0x40/41 and the mirror 0x42/43). That predicts **`005E/005F` is the IMX410 mirror of `005C/005D`**; ToupTek zeroes both pairs.
   - **`0000` has the same meaning in all three:** b0 = STANDBY and b2 = "wakeup" (ZWO's SDK names are `CamSetStandby` and `CamSetWakeup`).
6. **[C] Each vendor's IMX410 variant, by chip marking:**
   - **IMX410AQL:** Sony a7 III. It has PDAF pixels in an irregular layout, every 4 columns, 6 or 12 rows apart.
   - **IMX410BQJ:** Nikon Z6. It has PDAF pixels at a regular 2-column × 12-row stride.
   - **IMX410BQT:** probably the Nikon D780.
   - **IMX410CQK:** the catalogue part, believed to have no PDAF. It suits the fp, which has contrast-detect AF only [I].
   - **Landingfield, who sniffed both the Sony and the Nikon variant, reports that "all the functional setting registers (mode, analog/digital gain, shutter, ROI) share the same address".**
   - So a7 III or Z6 knowledge transfers to the fp's register map [F+I].

---

## 1. Which cameras use the IMX410

| camera | evidence | tag |
|---|---|---|
| Sony a7 III | chip marking IMX410AQL (Landingfield). Also: P2P DCG switch at 640 and readout matches the flyer | [C] |
| Nikon Z6 | chip marking IMX410BQJ (Landingfield); Z6 still line 12.63 µs = 911 cycles at 72 MHz | [C] |
| Nikon Z6 II, Zf | same readout times as the Z6 in every mode (Horshack: 50.8 ms still, 22.1 ms 4K, 7.3 ms 1080) | [C] same die as the Z6 [I] |
| Nikon D780 | IMX410BQT packaging per Landingfield, "presumed" | [F] |
| Sony a7C | same readout as the a7 III in every mode (62.3 / 17.0 / 24.1 / 7.0 ms) | [C] same die [I] |
| SIGMA fp | the register tables match ZWO, QHY and ToupTek IMX410 tables register for register (`ASTRO_IMX410.md`). No public teardown names the part | [C] (our RE) |
| Z CAM E2-F6 | `imvt_camera` IMX410 tables (`ZCAM_COMPARE.md`); gist table | [C] |
| ZWO ASI2400MC Pro, QHY410C, ToupTek SkyEye24AC (also sold as Altair, Risingcam, Omegon and others) | SDK tables | [C] |
| Blackmagic Cinema Camera 6K / PYXIS 6K | 6048×4032, 36 fps max at 12-bit; readout 6.22 µs/line = 448 cycles; dual native ISO 400/3200 | [I] strong (timing fits exactly), [V] specs |
| Panasonic S1, S5, S5 II/IIx, S1H | P2P DCG at 800 (S1) or 640 (S5). The S5IIx still readout of 50.7 ms equals the Z6's 50.8 (Horshack) | [F] / [I] plausible |
| Leica SL2-S | "widely believed" (YMCinema); P2P DCG at ISO 800 | [F] |
| Sony FX9, Kinefinity Mavo LF / Edge 6K, DJI Ronin 4D 6K | listed only in a Threads post and a YMCinema article, with no evidence | [F] |
| SIGMA fp L | **no**: a 61 MP IMX455-class sensor | [C] |

---

## 2. Sony IMX410CQK flyer: full table, decoded [C flyer + I arithmetic]

Source: https://www.sony-semicon.com/files/62/pdf/p-13_IMX410CQK_Flyer.pdf (Ver. 1.0, 2018).

**Pixel array and package**
- **Total:** 6104×4142. **Effective:** 6072×4056. **Active:** 6064×4040.
- **Optical black:** H front 0 and rear 20 pixels; V front 32 rows and rear 0.
- **Chip:** 41.071 × 30.815 mm. **Pixel:** 5.94 µm. **Package:** 294-pin LGA.

**Electrical**
- 72 MHz input clock.
- +30 dB CDS/PGA.
- 11/12/14-bit ADC.
- 8-lane SLVS-EC output.
- "Rolling shutter function moving picture mode."
- "All-pixel readout mode 4K cropping."

**Image characteristics (Tj = 60 °C)**
- Sensitivity: typ. **6660 LSB** at F5.6, 1/30 s.
- Saturation: min. **15105 LSB** ("left for 1 s").

The HMAX and VMAX columns below are my arithmetic. VMAX = 72e6 / (fps · HMAX), and every row gives an integer (±0.5) for one of the HMAX values 911, 445, 431 or 330, and for no other.

| mode | active pixels | max fps | word | HMAX → line µs | VMAX (min) | VMAX − rows | ADC class [I] | fp / Z CAM equivalent |
|---|---|---|---|---|---|---|---|---|
| 0 | 6064×4040 | 19.20 | 14 | 911 → 12.65 | 4116 | 76 | 14-bit | fp class 16 (modes 0/6/95/100/129); Z MODE0 |
| 1 | 6064×4040 | 39.30 | 12 | 445 → 6.18 | 4117 | 77 | 12 normal | fp class 17; Z MODE1 |
| 2 | 6064×4040 | 40.58 | 12 | 431 → 5.99 | 4117 | 77 | **11-bit** | **fp: none**; Z MODE2 (unused) / MODE2D |
| 3 | 4160×2160 | 35.34 | 14 | 911 | 2236 | 76 | 14-bit | none (fp crops in the SoC) |
| 4 | 4160×2160 | 72.36 | 12 | 445 | 2236 | 76 | 12 normal | Z MODE4 (`0001=2C`) |
| 5 | 4160×2160 | 97.57 | 12 | 330 → 4.58 | 2236 | 76 | **11-bit** | Z MODE5; fp none |
| 6 | 2020×1342 | 116.23 | 12 | 445 | 1392 | 50 | 12 normal, 3×3 | fp class 20 (139/134) |
| 7 | 2020×1342 | 156.73 | 12 | 330 | 1392 | 50 | 11-bit, 3×3 | fp class 21 (**mode 8 = MONIT1_60**) |
| 8 | 6064×672 | 226.60 | 12 | 445 | 714 | 42 | 12 normal, V÷6 | Z readout 8 (unused) |
| 9 | 6064×672 | 233.96 | 12 | 431 | 714 | 42 | 11-bit | — |
| 10 | 2020×672 | 226.60 | 12 | 445 | 714 | 42 | 12 normal, 3×6 | fp class 22 (mode 140) |
| 11 | 2020×672 | 305.57 | 12 | 330 | 714 | 42 | 11-bit, 3×6 | fp class 23 (modes 12, 9) |
| 12 | 2020×336 | 432.61 | 12 | 445 | 374 | 38 | 12 normal | Z readout 12 |
| 13 | 2020×336 | 583.37 | 12 | 330 | 374 | 38 | 11-bit | Z readout 13 |
| 14 | 2020×136 | 1253.91 | 12 | 330 | 174 | 38 | 11-bit (AF strip?) | Z readout 14 (`0001=34`) |
| 15 | 2020×112 | 1454.54 | 12 | 330 | 150 | 38 | 11-bit | Z readout 15 (`0001=35`) |
| 16 | 2020×96 | 1628.22 | 12 | 330 | 134 | 38 | 11-bit | Z readout 16 (`0001=36`) |
| 17 | 3032×2012 | 78.23 | 12 | 445 | 2068 | 56 | 12 normal, 2×2 | fp class 18 (98, 106 …) |
| 18 | 3032×2012 | 105.50 | 12 | 330 | 2068 | 56 | 11-bit, 2×2 | fp class 19 (58, 103, 11, 89); sigma-fp-lab "mode 11" |
| 19 | 3032×4040 | 39.30 | 12 | 445 | 4117 | 77 | 12 normal, H 2:1 | Z readout 19 (`0001=3B`); fp none |
| 20 | 3032×4040 | 53.00 | 12 | 330 | 4117 | 77 | 11-bit, H 2:1 | Z readout 20; fp none |
| 21 | 6064×2012 | 78.23 | 12 | 445 | 2068 | 56 | 12 normal, V 2:1 | Z MODE21 |
| 22 | 6064×2012 | 80.78 | 12 | 431 | 2068 | 56 | 11-bit, V 2:1 | Z MODE22 |

**Notes on the table**
- The "word length 12" in the flyer is the output word. The 11-bit fast set (`ZCAM_COMPARE.md` §0.1) still outputs 12-bit words.
- The 11-bit set's HMAX floor depends on width: 431 at 6064 px and 330 at ≤ 4160 px.
  - [I] This is probably an SLVS-EC payload limit. At 6064 × 12 bit per 431 cycles, the link carries 12.2 Gbit/s. Eight lanes at 2.304 Gb/s with 8b10b coding give 14.7 Gbit/s.
- Landingfield saw 6104 × **4234** lines on the link in still capture. That is 92 more than the 4142-row array, probably embedded and dummy lines, against our VMAX margin of 76 [F/I].

---

## 3. Rolling shutter and readout, measured on other bodies

Model: readout time = rows read × HMAX / 72 MHz.

| camera / mode | measured | source | as rows × HMAX [I] | tag |
|---|---|---|---|---|
| Nikon Z6 / Z6 II / Zf, still (ES, 14-bit) | 50.8 ms (12.63 µs/line) | Horshack | 4024 × 909 ≈ class 16 (911) | [C] |
| Nikon Z6, line period in 14-bit still | 12.65 µs | Landingfield | 911 cycles exactly | [C] |
| Nikon Z6, live view and 12-bit still | 6.53 µs | Landingfield | 470 cycles (12-bit normal, Nikon's longer HMAX) | [C] |
| Nikon Z6, 4K 24/30 (FF, 6K oversampled) | 22.15 ms | Horshack | 3402 rows × 6.51 µs (HMAX ≈ 469) | [C] |
| Nikon Z6, 1080p 30/60 | 7.33 ms | Horshack | 1134 × 6.46 µs (3×3, HMAX ≈ 465) | [C] |
| Nikon Z6, 1080p120 | 5.15 ms | Horshack | 1125 × 4.58 µs = **HMAX 330** (3×3 fast, flyer mode 7) | [C] |
| Sony a7 III, still (ES) | 62.3 ms (≈1/16 s) | Horshack | 4040 × 15.4 µs → HMAX ≈ 1110, slower than the 911 floor | [C] |
| Sony a7 III, 4K24 | 24.65 ms | Horshack | 3376 × 7.30 µs (HMAX ≈ 526) | [C] / [I] |
| Sony a7 III, 4K30 | 17.21 ms | Horshack | 3376 × 5.10 µs (HMAX ≈ 367, **in the 11-bit range**) | [C] / [I] |
| Sony a7 III, 1080 (all rates) | 7.1 ms | Horshack | 1125 × 6.3 µs (3×3 normal) | [C] |
| SIGMA fp, UHD (CinemaDNG) | 20.8 ms | CineD | 3376 × 6.18 µs (HMAX 445) | [C] |
| SIGMA fp, FHD | 10.4 ms | CineD (they assumed line skipping) | 1688 × 6.18 µs (2×2 bin, class 18) | [C]; matches our 10.556 ms for mode 106 |
| SIGMA fp, stills 14 / 12-bit | ≈1/15 s / ≈1/30 s; flash "tuning speed" 1/30 s (1/15 s at 14-bit) | SIGMA spec; mirrorlesscomparison | 51 ms (class 16) / 25 ms (class 17) [I] | [V] |
| fpSup OG3K / OG2K | 12.44 ms / 8.3 ms | fpSup site | our own | — |
| BMCC 6K / PYXIS 6K | 3:2 25.08, 17:9 19.90, 2.4:1 15.67, 4K 6:5 25.08, 4K 4:3 19.10, 4K 17:9 15.13 ms | Blackmagic via YMCinema | all 6.22 µs/line = **HMAX 448**; all 1×1 windows, no binning | [V] / [C] |
| BMCC 6K, 6K DCI | 18.7 ms | CineD | 3000 × 6.22 µs | [C] |
| Z CAM E2-F6, 6K FF 17:9 (6064×3196) | 20.1 ms | CineD | 3196 × 6.29 µs (HMAX ≈ 453) | [C]; matches Z's HMAX 443–480 |
| Z CAM E2-F6, S35 4K (4096×2160) | 13.4 ms | CineD | 2160 × 6.2 µs | [C] |
| Panasonic S5 IIx | still 50.7, 4K30 21.5, 1080p120 5.24 ms | Horshack | the same three classes as the Z6 | [C] |

**Implications [I]**
- Every vendor's full-height 12-bit video sits at HMAX 445–470. Nobody runs the 11-bit set at full height for video, except possibly the a7 III at 4K30.
- The fastest public IMX410 rolling shutter in a full-frame video mode is the Z6's 1080p120 (5.15 ms, 3×3 fast).

---

## 4. Noise, gain and dynamic range per camera (PhotonsToPhotos, 14-bit stills) [C]

Sources: https://www.photonstophotos.net/Charts/RN_ADU.htm, `RN_e.htm` and `PDR.htm`. The data series are embedded in the page HTML; `p2ptab.py` reproduces this table.

The e⁻/DN14 row is RN(e⁻) / RN(DN). Claff measures it at base ISO and scales it by ISO, so above base it is ISO-derived, not a measured photon-transfer curve.

| camera | quantity | 100 | 200 | 400 | 503 | 636 | 800 | 1600 | 3200 | 6400 | 12800 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Sigma fp | RN (DN14) | 1.39 | 1.40 | 2.91 | 4.26 | 2.11 | 2.08 | 2.50 | 4.66 | 8.75 | 16.80 |
| Sigma fp | RN (e⁻) | 6.77 | 3.43 | 3.56 | 4.11 | 1.62 | 1.27 | 0.76 | 0.71 | 0.67 | 0.64 |
| Sigma fp | e⁻/DN14 | 4.86 | 2.45 | 1.22 | 0.97 | 0.77 | 0.61 | 0.30 | 0.15 | 0.08 | 0.04 |
| Sigma fp | PDR (EV) | 11.02 | 11.00 | 9.85 | 9.22 | 9.38 | 9.38 | 9.07 | 8.07 | 7.10 | 6.09 |
| Sony ILCE-7M3 | RN (DN14) | 1.09 | 1.83 | 3.39 | 4.20 | 1.56 | 1.82 | 3.71 | 6.82 | 12.91 | 23.43 |
| Sony ILCE-7M3 | RN (e⁻) | 6.41 | 5.39 | 4.99 | 4.92 | 1.44 | 1.34 | 1.37 | 1.26 | 1.19 | 1.08 |
| Sony ILCE-7M3 | e⁻/DN14 | 5.90 | 2.95 | 1.47 | 1.17 | 0.93 | 0.74 | 0.37 | 0.18 | 0.09 | 0.05 |
| Sony ILCE-7M3 | PDR (EV) | 11.60 | 10.70 | 9.73 | 9.40 | 9.80 | 9.49 | 8.46 | 7.47 | 6.51 | 5.48 |
| Nikon Z 6 | RN (DN14) | 1.32 | 2.30 | 4.06 | 5.03 | 6.23 | 2.48 | 4.17 | 7.73 | 14.72 | 28.05 |
| Nikon Z 6 | RN (e⁻) | 6.87 | 5.98 | 5.31 | 5.21 | 5.13 | 1.62 | 1.37 | 1.27 | 1.21 | 1.15 |
| Nikon Z 6 | e⁻/DN14 | 5.21 | 2.60 | 1.31 | 1.04 | 0.82 | 0.66 | 0.33 | 0.16 | 0.08 | 0.04 |
| Nikon Z 6 | PDR (EV) | 11.01 | 10.37 | 9.42 | 9.11 | 8.83 | 9.16 | 8.17 | 7.19 | 6.18 | 5.20 |
| Panasonic DC-S5 | RN (DN14) | 1.57 | 2.35 | 3.86 | 4.56 | 2.07 | 2.43 | 4.14 | 7.52 | 13.45 | 25.46 |
| Panasonic DC-S5 | RN (e⁻) | 8.94 | 6.68 | 5.50 | 5.13 | 1.87 | 1.73 | 1.47 | 1.34 | 1.21 | 1.14 |
| Panasonic DC-S5 | e⁻/DN14 | 5.70 | 2.85 | 1.42 | 1.13 | 0.90 | 0.71 | 0.36 | 0.18 | 0.09 | 0.04 |
| Panasonic DC-S5 | PDR (EV) | 11.34 | 10.47 | 9.57 | 9.31 | 9.66 | 9.36 | 8.33 | 7.37 | 6.41 | 5.40 |
| Panasonic DC-S1 | RN (DN14) | 1.14 | 1.97 | 3.46 | 4.26 | 5.17 | 1.95 | 3.66 | 6.92 | 12.73 | 23.75 |
| Panasonic DC-S1 | RN (e⁻) | 6.87 | 5.94 | 5.21 | 5.10 | 4.89 | 1.46 | 1.38 | 1.30 | 1.20 | 1.13 |
| Panasonic DC-S1 | PDR (EV) | 11.37 | 10.52 | 9.51 | 9.19 | 8.91 | 9.08 | 8.12 | 7.10 | 6.17 | 5.18 |
| Leica SL2-S | RN (DN14) | 2.01 | 2.77 | 4.23 | – | – | 2.73 | 4.14 | 7.21 | 12.64 | 23.59 |
| Leica SL2-S | RN (e⁻) | 12.13 | 8.34 | 6.36 | – | – | 2.06 | 1.56 | 1.36 | 1.19 | 1.11 |
| Leica SL2-S | PDR (EV) | 11.26 | 10.33 | 9.35 | – | – | 9.16 | 8.27 | 7.30 | 6.30 | 5.35 |

**DxOMark-derived values** (P2P `Sensor_Characteristics.htm`; the fp is not in DxOMark) [C]:

| camera | unity-gain ISO | FWC e⁻ (base) | QE % | min read noise e⁻ | ISO-invariant at |
|---|---|---|---|---|---|
| Sony ILCE-7M3 | 590 | 95,764 | 64 | 1.2 | 1690 |
| Panasonic DC-S1 | 602 | 95,817 | 59 | 1.1 | 1907 |
| Panasonic DC-S5 | 570 | 90,477 | 46 | 1.1 | 1768 |
| Leica SL2-S | 606 | 97,763 | 63 | 1.0 | 2729 |
| Nikon Z 6 | 523 | 83,698 | 57 | 1.0 | 2392 |
| Nikon Z 6 II | 508 | 75,392 | 55 | 0.9 | 2495 |

**Reading the fp rows [I]**
- **DCG switch at ISO 640 in stills.** The read noise in DN halves between ISO 503 and 636, and PDR rises from 9.22 to 9.38.
- **ISO 100–200 give identical raw noise (1.39–1.40 DN) and identical PDR (11.0).** So those three ISOs use one analog gain in stills. The e⁻ figures P2P prints for 125–200 are ISO scaling, not measurements.
- **ISO 636–1273 is likewise flat at about 2.08 DN.** Above 1600 the read noise in DN doubles each stop.
- **The fp's high-ISO e⁻ values (0.6–0.7 e⁻) are below every other IMX410 body (1.1–1.3 e⁻).** Trust the DN numbers and treat the fp e⁻ values above HCG as unreliable, probably because the fp ISO is inflated against Sony's.
- **The fp's base PDR is 0.6 EV below the a7 III's** (11.0 against 11.6). That fits the fp's base sitting at +2.4 dB analog (code 985) where the a7 III sits at about +0.6 dB (6.35 / 5.90 = ×1.076, code ≈ 290).
- **Read noise in the LCG band is 6.4–6.9 e⁻ at base on every body.** It is 1.1–1.4 e⁻ in HCG at high gain.
- **Base FWC is about 96 ke⁻ with Sony's own tuning.** Nikon chose a lower FWC.

**fp video [V]:** SIGMA claims a dual base ISO of 100 / 3200 for 12-bit CinemaDNG and RAW over HDMI, and 12.5 stops (https://www.sigma-global.com/en/special/fp-series/cinemacamera/).
- CineD measured 11.3 stops (SNR = 2) at ISO 100 and 9.25 stops at ISO 4000, UHD CinemaDNG 12-bit [C].
- **Our live-view sweep puts HCG between relative 7488 and 14976** (`IMX410_RULES.md` §5), which disagrees with SIGMA's "3200" if relative 117 ≈ ISO 100. One of the two is not on the ISO scale (see §7).

**Other dual native ISO claims [V]:**
- Blackmagic Cinema Camera 6K: 400 / 3200.
- Z CAM E2-F6: 400 / 2500.
- a7 III (P2P): 640.

The ratio between the two ISOs is set by each vendor's analog trim, not by the HCG ratio alone.

---

## 5. Astro-camera characterisation (adds to `ASTRO_IMX410.md` §4)

| item | value | source | tag |
|---|---|---|---|
| QHY410C full well, low gain 1×1 | 120 ke⁻ (deep well); "zero amp glow"; read noise 1.6 e⁻ at "low gain" | Astronomy magazine test (Feb 2022) https://www.astronomy.com/observing/astronomy-tests-the-qhy-410c-a-color-camera-without-the-noise/ | [F] |
| QHY410C dark current | about 0.002 e⁻/px/s at −20 °C; 0.01 at 0 °C | reseller spec sheets (search result) | [V] |
| ASI2400MC dark current | 0.00035 e⁻/px/s at −20 °C; ZWO's chart "DCvsT-2400(410)" | ZWO product page | [V] |
| QE peak | "above 80%" (ZWO's own estimate); about 80% (QHY user). **No measured IMX410 QE curve is published.** DxO-derived QE is 46–64% (broadband) | ZWO; Astronomy; P2P | [V] / [F] |
| HCG read noise | 1.1–1.5 e⁻ (ZWO 1.1, users 1.5) | ZWO; AstroBin | [V] / [F] |
| Horizontal dark shading | under 4.5 LSB (Sony spec quoted by ToupTek) | already in the ASTRO note | [V] |
| Banding / row noise | **no public reports** for ASI2400 / QHY410 / SkyEye24 darks | CN / AstroBin searches | — |
| PDAF striping | a7 III: green-channel striping in PDAF rows with off-axis flare (Kasson). The fp, with no PDAF, should be free of it | https://blog.kasson.com/a7riii/pdaf-striping-sony-a7riii | [F] |

---

## 6. Register-level information found (and not found)

- **No IMX410 datasheet or register table is public.** I searched Sony, Framos, Macnica, GitHub, CSDN/ntpcb-style Chinese forums, the Jetson forums and the Blackmagic forum (which returned 403). Framos sells the IMX410CQK-C and its datasheet is under NDA.
- **Landingfield (IMX410 SLVS-EC RE)**, https://landingfield.wordpress.com/2021/05/10/decoding-the-slvs-ec-protocol-from-imx410bqt/ [C]:
  - **Protocol:** 8 lanes, 2304 Mb/s (72 MHz × 32), alternative 1152 Mb/s, 8b10b coding.
  - **Packets:** 24-byte header (8 bytes ×3). The header carries SOF, EOF, line-valid, a 13-bit line index reset at the first XHS after XVS, an embedded flag, and a 16-bit ECC.
  - **Payload:** 224-byte chunks plus a 4-byte CRC.
  - **Packing:** 12-bit is 2 px in 3 bytes; 14-bit is 4 px in 7 bytes.
  - **Registers:** the Sony and Nikon variants share all functional register addresses, but the a7 III init alone gave empty data on the BQT part, so the init sequences differ.
- **Sibling register families, astrocam IMX455/IMX571** (`sensors/imx455.go`, `imx571.go`, wire-verified against ZWO and PlayerOne) [C].
  - The addresses differ from the IMX410, so **do not copy addresses across**. Names and semantics do transfer:

  | function | IMX455 | IMX571 | IMX410 (ours) | transfer |
  |---|---|---|---|---|
  | standby / wake | `0000` b0 = `CamSetStandby`, b2 = `CamSetWakeup` | same `0000` | `0000` b0 standby, b2 operate | **same address and bits** [C] |
  | stream gate | `019E` 1 = start, 5 = stop | `01EE` 1/5 | `00CA` 1/0 (+`00C5/C6`) | role only |
  | analog gain code | `002E/2F` + mirror `0030/31`; code = 4095·(1−10^(−dB/20)) | `0030/31` + mirror `0032/33` | `003D/3E` + `003F/40` | same law and the same two copies [C]. On the IMX410 the copies are per colour (§14) |
  | HCG select | `002D` b0 (b2 also set at higher gain) | `002F` | `05E1` | role |
  | top-band coarse gain | `003E` bits[7:4] = stage, 60 × 0.1 dB = **6 dB per step** | `0040` bits[7:4] | `0055` (ZWO writes n<<4) | **supports n<<4 (bits 7:4)** [I] |
  | high-gain config | `03A4/03A5/03A6` 0x11 → 0x23/0x2D at ≥ 18 dB HCG; `004D` per band | `067F` written at each gain update | `05A6/05A8`, `041F`, `05E2` change with gain | role [I] |
  | black level | `0040/41` + mirror `0042/43` | — | `005C/5D` (+ `005E/5F`?) | **predicts `005E/5F` = mirror** [I] |
  | shutter | `0016/17` SHS (2-line units in 1×1), clamp ≥ 3 | `0018/19` | `0005/06` SHR | same 2-line convention |
  | VMAX / HMAX | in the FPGA (slave mode) | FPGA | in the fp SoC | same architecture |
  | long exposure | ≥ 1 s: FPGA wait+trigger, SHS = 20 | same | — | method for the fp [I] |

- **IMX455 offset scale [C]:** ZWO writes offset·10, so 1 register LSB = 1 output DN (16-bit, ×1 at bin 1). That matches the IMX410's 1 LSB = 1 LSB14 (ASTRO note §1.1).

---

## 7. Known quirks (sensor or ISP)

| quirk | where | sensor or ISP? | tag |
|---|---|---|---|
| "Star eater": spatial filtering of exposures ≥ 4 s (3.2 s unaffected) | a7 III (LonelySpeck), https://www.lonelyspeck.com/sony-star-eater-and-how-to-fix-it/ | **ISP** (Sony firmware). It does not exist in the astro cameras on the same die | [F] / [I] |
| 12-bit drop in continuous drive with compressed RAW, or with LENR | a7R III family (Sony statement quoted on FredMiranda). a7 III ES readout is 1/16 s at 14-bit (Horshack); 12-bit roughly halves it (Kasson on a7R IV) | sensor class 17 vs 16 [I] | [F] |
| PDAF striping | a7 III, a9 (Kasson) | sensor (AQL PDAF rows) | [F] |
| CinemaDNG shadow flicker from a per-frame `BlackLevel` tag (frames differ by about 0.03) | SIGMA fp (pixls.us) https://discuss.pixls.us/t/overwriting-black-level-in-dng-metadata-to-fix-sigma-fp-s-cinemadng-shadow-flicker/41662 | **ISP**: the fp writes the measured OB/DCLP average per frame (our RE: `BlackLevel` from sensor state +0x208, <<2 at 14-bit; `IMX410_RULES.md` §4/§6) | [F] + [C ours] |
| FHD "line skipping" | SIGMA fp FHD (CineD) | actually 2×2 vertical-add binning (class 18) at 6.18 µs/line; CineD's guess is wrong [I] | — |
| Black level, a7 III | 512 in 14-bit ARW (typical Sony; confirmed for the a7R III by Iliah Borg, https://libraw.org/comment/reply/2514/5472) | — | [F] |
| White level, a7 III | 16383 nominal, about 15360 practical in some files (pixls.us) | — | [F] |

**Conflict to resolve [I]:** `ASTRO_IMX410.md` says the a7 III writes `005C/5D = 0x03FF` (1023 LSB14). Sony ARWs carry black 512.
- Either the a7 III ISP subtracts 511 before writing the ARW, or 0x03FF is not the stills value.
- The fp's 14-bit DNG black is about 1024 (256 << 2), which is consistent with an unmodified 0x3FF pedestal.

---

## 8. What this saves us / predicts for our register experiments

1. **Gain law check: done from public data. Skip a dedicated PTC run for the base gain.**
   - **The prediction:** at analog code c, e⁻/DN14 = 6.35 · (4095 − c) / 4095 in LCG.
   - **At code 985:** this gives 4.83, and P2P's fp ISO 100 is 4.86.
   - **Expected 12-bit cine numbers:** at code 985, 19.3 e⁻/DN12 at the 12-bit tap, with full well ≈ (4095 − 256) DN12.
   - A single flat-pair at ISO 100 can confirm this. No sweep is needed.
2. **HCG ratio.** The expected value is **×4.6–5.3**: ZWO ≈ ×4.95, Z CAM 5.3088, QHY ≈ ×4.6, ToupTek ≈ ×5.2.
   - Our ×3.71 (§5b) is almost certainly confounded by the CRCT digital stage, the `041F` trim and the `05A6/05A8` trims.
   - **Test:** HCG on/off at a mid code (≈2000) with every trim held fixed. Expect ×5.0 ± 0.3.
   - **Read noise:** expect 6.4–6.9 e⁻ → 1.1–1.5 e⁻ when it switches.
   - **Where the stock switch sits:** SIGMA's stills switch sits at ISO 640, between ISO 503 and 636, the same place as the a7 III.
   - **Check:** whether cine/live-view really switches 4 stops later (§5) or whether the relative scale is not ISO.
3. **Full well and clip.** At 0 dB the pixel saturates at ≥ 15105 LSB14 above black, and the ADC clips at about 15360 above black (black ≈ 1023).
   - **Prediction:** above about code 70 (gain > 15360/15105 = ×1.017) the ADC clips before the pixel.
   - **At code 985 (fp ISO 100):** the ADC clips at 15360 / 1.317 ≈ 11.7k LSB14 at 0 dB, which is about 74 ke⁻. The pixel holds about 96–100 ke⁻, so about 0.4 EV of the well is never used.
   - **Lever:** **an "ISO 75" mode at code ≈ 0–290 gains up to +0.4 EV of highlight**, as the a7 III does at code ≈ 290. Test: write code 0 and measure the clip.
4. **Black level.** Predictions:
   - Writing `005C/5D` moves the black by 1 LSB14 per register LSB (¼ DN at the 12-bit tap).
   - Writing `005E/5F` alone does nothing visible, or moves a second row/colour group as a mirror. Write both pairs together, as IMX455 drivers do.
   - The 1023 power-on pedestal explains the fp's 255–256 DN12 black.
5. **`0055` digital gain.** IMX455/571 put the coarse stage in bits [7:4] at 6 dB per step, and ZWO's IMX410 code does the same.
   - **Predictions:** `0055 = 0x10` → ×2.0, `0x20` → ×4.0, `0x30` → ×8.0 (+18 dB at most), and 0x01–0x03 does nothing.
6. **Readout modes the fp does not use, with their exact ceilings from §2:**

   | flyer mode | what it is | ceiling | VMAX / HMAX | what it would give the fp |
   |---|---|---|---|---|
   | 2 | 6064×4040 11-bit | 40.58 fps | VMAX 4117 / HMAX 431 | full open gate with a 24.8 ms readout; 12-bit (class 17) gives 25.4 ms |
   | 3 | 4160×2160 14-bit crop | 35.34 fps | — | 14-bit S35 video at 24/30 |
   | 4 / 5 | 4160×2160 crop | 72 / 97.6 fps | HMAX 445 / 330, rows 2236 | 4K S35 at 60 fps, and 90 fps on the 11-bit set; needs `0001=2C` and the 07xx crop (Z CAM MODE4/5) |
   | 19 / 20 | 3032×4040, H 2:1 | 39.3 / 53 fps | — | full-height half-width 3:2 at 53 fps (anamorphic-style) |
   | 21 / 22 | 6064×2012, V 2:1 | 78.2 / 80.8 fps | — | Z MODE21/22 |
   | 14–16 | 2020 × 136 / 112 / 96 | up to 1628 fps | HMAX 330 | AF strips; a high-rate strip for the DFD/AF work |

   - **Existing fp classes run below their ceilings:**
     - mode 8 (3×3 fast) could run at **156.7 fps** (VMAX 1392), against 59.94 today;
     - class 19 (2×2 fast) at 105.5;
     - class 18 at 78.2;
     - class 17 at 39.3.
   - Each needs only VMAX in the SoC (rows + 76/56/50).
7. **Rolling-shutter budget.** Readout (ms) = rows × HMAX / 72000.
   - Full height at 14-bit is 51.1 ms, 12-bit 25.0 ms, 11-bit 24.2 ms (full width).
   - A 4160-wide window drops to HMAX 330: 2160 rows → 9.9 ms.
   - **The cheapest rolling-shutter win is the narrower window (HMAX 330), not the ADC bits.** At full width 11-bit is only 3% faster.
8. **Long exposure.** Long exposures should follow the astro method: stretch VMAX with SHR at its minimum, or use a ≥ 1 s trigger mode.
   - Dark current is tiny when cooled. At 25–40 °C, which a body like the fp reaches, expect about 0.05–0.2 e⁻/s [I, extrapolated from ×2 per 5–6 °C], so 30 s exposures are clean.
9. **Experiments we can drop:**
   - a base-ISO PTC;
   - QE characterisation (no published curve exists; use the 46–64% DxO broadband figure);
   - a full-well search;
   - mapping fps limits per class;
   - checking whether FHD skips lines (it bins).

---

## 9. Sources

- Sony IMX410CQK flyer: https://www.sony-semicon.com/files/62/pdf/p-13_IMX410CQK_Flyer.pdf
- PhotonsToPhotos:
  - https://www.photonstophotos.net/Charts/RN_ADU.htm
  - https://www.photonstophotos.net/Charts/RN_e.htm
  - https://www.photonstophotos.net/Charts/PDR.htm
  - https://www.photonstophotos.net/Charts/Sensor_Characteristics.htm
- Horshack rolling-shutter database: https://horshack-dpreview.github.io/RollingShutter/
- Landingfield, IMX410 SLVS-EC: https://landingfield.wordpress.com/2021/05/10/decoding-the-slvs-ec-protocol-from-imx410bqt/
- Landingfield, "System on Camera" part one (says the IMX410 has PDAF pixels and that the CQK needs a new PCB): https://landingfield.wordpress.com/2023/09/11/system-on-camera-part-one/
- Blackmagic readout table (via YMCinema): https://ymcinema.com/?p=21549
- CineD lab tests:
  - SIGMA fp: https://www.cined.com/sigma-fp-camera-first-impression-sample-footage-and-lab-test-results/
  - BMCC 6K: https://cined.com/blackmagic-cinema-camera-6k-lab-test-rolling-shutter-dynamic-range-and-latitude/
  - Z CAM E2-F6: https://www.cined.com/?p=152634
- astrocam (IMX455/IMX571 profiles): https://github.com/mikefsq/astrocam (`sensors/imx455.go`, `sensors/imx571.go`)
- SIGMA fp cine specs: https://www.sigma-global.com/en/special/fp-series/cinemacamera/
- SIGMA fp flash sync and readout:
  - https://old.imaging-resource.com/PRODS/sigma-fp/sigma-fpDAT.HTM
  - https://mirrorlesscomparison.com/preview/sigma-fp-vs-fp-l/
- fp DNG black-level flicker: https://discuss.pixls.us/t/overwriting-black-level-in-dng-metadata-to-fix-sigma-fp-s-cinemadng-shadow-flicker/41662
- a7 III quirks:
  - https://www.lonelyspeck.com/sony-star-eater-and-how-to-fix-it/
  - https://blog.kasson.com/a7riii/pdaf-striping-sony-a7riii
  - https://www.fredmiranda.com/forum/topic/1514359/55/
- QHY410C test: https://www.astronomy.com/observing/astronomy-tests-the-qhy-410c-a-color-camera-without-the-noise/
- ZWO ASI2400MC Pro: https://zwoastro.com/product/asi2400mc-pro
- Camera lists (weak evidence):
  - https://ymcinema.com/2026/03/05/sony-imx410-sensor-powering-half-camera-industry/
  - https://gist.github.com/summershrimp/61fb5e86e50bd277c39121c3dbb8554d
- fpSup readout figures: https://ijigen.github.io/fpSup/
