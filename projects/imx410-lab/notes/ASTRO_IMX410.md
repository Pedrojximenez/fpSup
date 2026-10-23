# IMX410 in astronomy cameras — what their SDKs and firmware reveal (offline, 2026-10-20)

Cross-check of our fp RE (`IMX410_RULES.md`, `ZCAM_COMPARE.md`) against three independent IMX410 drivers.
The SIGMA fp was not touched.

Tags: **[C]** read directly from vendor code or data · **[I]** inferred · **[V]** vendor claim (web) · **[U]** user measurement (web).

## Sources

| driver | file (all from github.com/indilib/indi-3rdparty, master) | what it contains |
|---|---|---|
| ZWO ASI2400MC Pro | `libasi/x64/libASICamera2.bin` (x86-64, not stripped) | class `CCameraS2400MC_Pro`; four register tables `reglist_common`, `reglist_fullsize`, `reg_full_12bit`, `reglist_bin2` (rodata 0x301e60–0x3021fc); `WriteSONYREG(u16, u8)` calls in `SetGain`, `SetBrightness`, `SetExp`, `SetStartPos`, `Cam_SetResolution`, `Start/StopSensorStreaming` |
| QHY410C | `libqhy/firmware/QHY410.img` (Cypress FX3, ARM9) + `libqhy/x64/libqhyccd.bin` (has debug info) | The FX3 bit-bangs the sensor SPI itself: routine `0x4000377c(reg, val)` → `0x4000347c(0x81, reg, val)`, LSB-first on GPIO 0x15 (clock), 0x16 (data) and 0x18 (chip select), chip ID **0x81**, address high byte first. The host library only sends vendor requests (`LowLevelA0`…`B0`). |
| ToupTek (SkyEye24AC family) | `libtoupcam/x64/libtoupcam.bin` (stripped) | Six full IMX410 tables in two copies (file offsets 0x340c140… and 0x3490580…). Each entry is 4 bytes `{addr_hi, 0x10, val, addr_lo}`; `{FF FF, ms}` is a delay. Gain code was not traced: the stripped dispatch only showed generic property IDs. |

Extractions and comparison are in `offline/astro/`:
- `asi2400_tables.json`, `toup_tables.json` and `qhy410_writes.json` hold the raw extractions.
- `astro_tables.csv` lists every table in long format.
- `astro_vs_fp_zcam.csv` compares each register per readout class against the fp mode table and Z CAM.
- `astro_only_regs.csv` lists registers that neither the fp nor Z CAM writes.
- `astro_compare.py` regenerates all of the above; run it with `python3 -I`.

Web sources are listed at the end.

## 1. Most useful findings

1. **[C] `005C/005D` is a 16-bit black level, in 14-bit LSB.**
   - ZWO `SetBrightness(o)` writes `005C = (o·8) & 0xFF` and `005D = (o·8) >> 8`. QHY offset command A8 writes `o·16` the same way (5D high, 5C low).
   - The QHY FX3 init writes 10. ToupTek writes 0, and also writes `005E/005F = 0`, probably a companion field.
   - [U] An ASI2400 user reports offset 15 gives a bias of about 480 ADU in 16-bit scale. That is 120 in 14-bit, which equals 15 × 8. So one register LSB is one 14-bit LSB.
   - [I] Sony's a7 III writes `005C/5D = 0x03FF` (1023 in 14-bit, 255.75 in 12-bit). That matches the fp's black of about 250–256, which the fp never writes, so it is the power-on value.
   - This explains why §17 saw "no visible effect" from `005C=FF` alone: with `005D` already 03, the result is 0x03FF, the same as before.
   - **New fp lever:** we can set the black level/pedestal ourselves through `005C/005D`.
2. **[C] The 14-bit, 12-bit, 2×2 and 3×3 tables match the fp mode table register for register.**

   | class | fp class | registers compared | same | differ |
   |---|---|---|---|---|
   | 14-bit 1×1 | 16 | 188 | 188 | `0016`, `0058` |
   | 12-bit 1×1 | 17 | — | all | `0016`, `0058` |
   | 2×2 12-bit | 18 | 275 | 275 | `0016` |
   | 3×3 12-bit (`0001=2F`) | 20 | 182 | 182 | `0016` |

   This independently confirms Family A (ADC speed) and Family B (vertical drive) in §21, including `0737/0738` (0 in 1×1, 2 when binned), `0739/073A` and `0724/0725` = 2·(vbin−1), and the 0728/072A/072B drive-window values. ToupTek also writes the registers of the fast set and of the vertical 2:1 mode with their "off" values: `0062 0068 006A 0070 0094 0240 0242 0244 0278 0279 027B 08B6 08B7`.

   The only systematic differences:
   - **`0016`**: every astro driver and Z CAM write `07`; ToupTek's 14-bit table writes `02`. The fp writes 07/0F/14/19/23/32 depending on mode, and the a7 III writes 02. [I] It is not an image register and looks timing or sync related; the fp's per-mode values are its own choice.
   - **`0058`**: astro and Z CAM write `70` in every mode, including 1×1. The fp writes 20 in 1×1 and 70 when binned; the a7 III writes 30. §20 already found that `0058` b0 changes the pedestal.
3. **[C] Gain law, as ZWO's `SetGain(g)` codes it** (g in 0.1 dB, clamped to 0–620):
   - **g ≤ 139:** `05E1`=0, `0055`=0, and `3D/3E = 3F/40 = round(4095 − 4095·10^(−g/200))`.
   - **140 ≤ g ≤ 440:** `05E1`=1 (HCG), and the code uses (g−140) the same way.
   - **g > 440:** HCG on, and the extra gain goes to **`0055` = n<<4 (0x10/0x20/0x30, 6 dB per step)** with analog (g−140−60n). At the maximum, g = 620 gives n = 3 and analog 30 dB.

   This is exactly our law 4095/(4095−code). Analog 30 dB gives code 3965, which is the fp's maximum code.

   What ZWO's `SetGain` does and does not write:
   - It writes only `05E1`, `3D–40` and `0055` (3D/3E always equal to 3F/40).
   - It **never writes `041F`, `05E2`, `05A6` or `05A8`**. QHY and ToupTek never write them either. They are optional trims that the fp and Z CAM apply but the astro drivers leave at power-on.
   - **`0055` encoding conflict:** Z CAM writes 0–3, ZWO writes n<<4. The two drivers disagree; this should be tested on the fp [I].
4. **[C+V+U] HCG ratio — check the fp's ×3.71.**
   - ZWO makes e⁻/ADU continuous across the HCG switch at gain 140 (1.25 e⁻/ADU at both 139 and 140, read off ZWO's chart). With analog 0 dB at 140, that means HCG ≈ 13.9 dB ≈ ×4.95.
   - Z CAM's factor is 5.3088. QHY's curves give about ×4.6 and ToupTek's about ×5.2.
   - fp §5b measured ×3.71 at code 3965, with `05A6/05A8` and `041F` changing at the same moment and the CRCT digital stage active at the top. [I] The fp figure is probably confounded; re-measure at a mid code with the trims held.
5. **[C] QHY lets you choose LCG or HCG at any gain.** Read mode 0 is "LOW GAIN MODE" and read mode 1 is "HIGH GAIN MODE". The flag goes straight to `05E1` and is independent of the analog code.
   - Gain 0–100 maps to code `gain·40`, which is 0–**4000**. That is past Sony's 30 dB, since 4095/95 = ×43 or 32.7 dB [I].
   - Gain 100–170 is FPGA digital gain of (8 + gain − 100)/8.
   - White balance R/G/B is applied in the FPGA, not through the per-colour pairs 3D/3E and 3F/40, so nobody uses analog white balance (§14).
6. **[C] Exposure and long exposure.** Both QHY and ZWO use SHR in 2-line units, which matches the fp law in §3.
   - **QHY:** exposure = (VMAX − 2·SHR)·H, with SHR ≥ 1 and SHR ≤ VMAX/2.
   - **ZWO:** SHR = (L − lines)/2 with a minimum of 3. `0005` takes the low byte and `0006 = (2·SHR) >> 9` takes the high byte as a full 8 bits, up to SHR 0xFFFF. The fp clamps to 0x3FFE.
   - **[C] Neither driver uses SVR (`0007/0008`) or SPL (`0009/000A`).** The sensor runs as a slave: VMAX and HMAX live in the FPGA (QHY FPGA registers 0x16–0x19 hold VMAX as 32 bits; ZWO uses `SetFPGAVMAX` up to 0xFFFFFF).
   - Long exposures just stretch VMAX with SHR at its minimum. ZWO switches to an FPGA "wait/trigger" mode above 1 s, with exposures up to 2000 s.
   - [I] So long exposures on the fp could be done by stretching the SoC's VMAX/XVS. SVR is not needed.
7. **[C] Start and stop sequence, identical across the four drivers.**
   - **Power-up:** `00E9=80, 00D9=60, 04E6=00`, a wait of about 10 ms, then `00C5=00, 00C6=00, 0000=04, 00CA=01`.
   - **Stop:** `00CA=00`, then `00C5=03, 00C6=01`, then `0000=05` (ZWO) or `0000=06` (QHY, ToupTek).
   - ZWO's tables end with `0000=00` and `StartSensorStreaming` writes `0000=04`.
   - [I] `0000` b2 = operate. b0 = standby, as Z CAM says. b1 is a second standby or low-power bit.
   - [I] `00CA` = stream or master start, and `00C5/00C6` = a clock or PLL power-down pair.
8. **[C] QHY's sensor power-down command (vendor request 0xB0, with 1 to enter and 2 to leave).**
   - **Enter, in order:** `05D6` 04→05, `05A2` C3→41, `04F0` 20→22, `04D2` FF→00, `04D1` 00→01, `04DD` 00→C0, `00CA`=0, `00C5`=3, `00C6`=1, `0000`=06.
   - **Leave:** the same registers in reverse order.
   - [I] These are analog or bias power controls (power save between frames, or the "zero amp glow" feature). `04DD` was inert in our §17 screen at 0x01, which fits: it does nothing while streaming.
9. **[C] QHY writes only about 45 registers at init.** It writes `0001=29` (the 14-bit class) and the vbin-1 Family-B set, but **no Family-A registers** (no 0042, 007E…, 0433–043E…).
   - [I] So the IMX410 power-on defaults are the 14-bit full-resolution (MODE0) Family-A set. The fp and Z CAM write that set explicitly anyway.
10. **[C] Windowing.**
    - `0003=1` enables the window (QHY, ZWO, ToupTek, Z CAM).
    - **ZWO:** `0022/0023` = y_start + 0x3B (1×1) or + 0x3D (binned), and `0024/0025` = rows/2 (binned: rows/2 + 7).
    - **QHY:** start 0x44, `0024/0025` = (rows − 52)/2.
    - Horizontal crop is done in the FPGA only (`SetFPGAHBLK`), never on the sensor. This matches §7/§15: the window is in rows, in 2-row units.
11. **[C] Registers unknown to us** (written by the astro drivers but by neither the fp nor Z CAM):

    | register | written by | value | known elsewhere |
    |---|---|---|---|
    | `00DB/00DC` | ZWO `reglist_common` | 0x01BC = 444 | not in the a7 III set either |
    | `03E1` | ZWO `reglist_common` | 01 | not in the a7 III set either |
    | `03E2` | ZWO `reglist_common` | 0F | not in the a7 III set either |
    | `0002` | ZWO init, ToupTek | 00 | a7 III writes 00 or 04 |
    | `04D1 04D2 04F0 05A2 05D6` | QHY power-down only | see item 8 | — |

    These are candidates for an fp override sweep [I].

## 2. ZWO tables (`reglist_common`, then one mode table, then a stream start)

- `reglist_common`: `0043=01 0016=07 0043=02 0058=70 00C5=00 00C6=00 00CA=01 00E9=80 041B=03 044D=00 04E6=00 0569=09 0590–0595=01/03… 059A–059D=02 06D0/06D3/06D6=01 0716=01 0727=01 0795=01 0796=19 0797=10 0798=2C 079A=25 079E=08 079F=10 03E1=01 03E2=0F 00CE=00 00DB=BC 00DC=01 0000=00`
- Mode tables (each 63–64 entries): `reglist_fullsize` (14-bit, `0001=29`), `reg_full_12bit` (`0001=2A`) and `reglist_bin2` (`0001=39`). See the CSV.
- **Only these three modes exist.** ZWO's "high speed" is FPGA-side; the 11-bit fast set is never used.
- FPGA skip lines: 0x3D (14-bit) and 0x2B (bin2). Skip columns: 4.

## 3. ToupTek tables

- Three modes: 14-bit 1×1 (`0001=29`), 2×2 12-bit (`39`) and 3×3 12-bit (`2F`). Each has 153 entries and each appears twice (two camera models). The second copy also writes `005C–005F=00` at init.
- The init, stop and start fragments are the same as QHY's, with stop `0000=06`.
- ToupTek's "Low Noise" mode (half the frame rate, from the manual) is not a separate sensor table. [I] It is clock or FPGA side.

## 4. Web facts worth keeping (details in the sources)

- **[V] Sony IMX410CQK flyer:**
  - **Pixel counts:** 6104×4142 total, 6072×4056 effective, 6064×4040 active.
  - **Optical black:** 32 rows at the front, 20 columns at the rear.
  - **Electrical:** 72 MHz input clock; analog gain up to +30 dB; 11-, 12- and 14-bit ADC; 8-lane SLVS-EC.
  - **Readout modes:** 23 listed. Mode 0 is 14-bit full resolution at 19.2 fps. Modes 17 and 18 are 3032×2012 at 78.23 and **105.5 fps**, which is the sigma-fp-lab "mode 11". Modes 21 and 22 are 6064×2012 at 78.23 and 80.78 fps (vertical 2:1, as in Z CAM's MODE21/22).
  - https://www.sony-semicon.com/files/62/pdf/p-13_IMX410CQK_Flyer.pdf
- **[V] Horizontal dark shading:** Sony specifies under 4.5 LSB. ToupTek attributes it to the stitched exposure of the large die. https://www.touptek-astro.com/dl_manual/SkyEye24AC_en.pdf p.18
- **[V] ZWO ASI2400:**
  - HCG switches on automatically at gain 140; unity gain is 158; gain is in 0.1 dB.
  - Read noise is 6.35 e⁻ at gain 0, 4.9 e⁻ at 139 and 1.5 e⁻ at 140.
  - Full well is 100 ke⁻. 14-bit, with 12-bit used only for bin2/bin3.
  - https://i.zwoastro.com/zwo-website/manuals/ASI2400_Manual_EN_V1.2.pdf
- **[U] SharpCap analysis:**
  - Gain 0: 6.35 e⁻/ADU, read noise 6.27 e⁻, full well 104 ke⁻, 14.0 stops.
  - Gain 150: 1.10 e⁻/ADU, read noise 1.47 e⁻, full well 18.2 ke⁻.
  - https://www.cloudynights.com/topic/772896-zwo-asi2400mc-pro-views-on-settings-and-calibration/page-2
- **[V] QHY410C:**
  - Two modes, Low (LCG) and High (HCG), each with gain 0–100.
  - Low mode at gain 0: 7.3 e⁻/ADU, 6.1 e⁻ read noise, full well 119.6 ke⁻. High mode at gain 0: 1.6 e⁻ read noise.
  - PRO version: 19.2 fps at 16-bit and 40 fps at 12-bit, which are exactly Sony modes 0 and 2.
  - https://www.baader-planetarium.com/en/downloads/dl/file/id/1689/product/0/qhy410c_full_frame_35mm_format_back_illuminated_color_camera_photo_and_pro_versions.pdf
- **[V] ToupTek SkyEye24AC:**
  - HCG and LCG are selected manually.
  - LCG at 100%: 6.33 e⁻/ADU and 4.48 e⁻ read noise. HCG at 100%: 1.22 e⁻/ADU.
  - Same manual as above.
- **Amp glow and banding:** every vendor claims zero amp glow, and users agree it is absent. I found no specific reports of IMX410 row noise or banding.
  - https://www.cloudynights.com/forums/topic/921583-imx-410-or-imx571/
- **No leaked register datasheet was found.** The best public RE is Landingfield's SLVS-EC decode of the IMX410BQT (Nikon) and AQL (Sony): 24-byte header, 224-byte payload chunks, 12-bit packed 2 pixels in 3 bytes, 14-bit packed 4 pixels in 7 bytes.
  - https://landingfield.wordpress.com/2021/05/10/decoding-the-slvs-ec-protocol-from-imx410bqt/

## 5. Suggested fp follow-ups (not done; the camera was not touched)

1. Write `005C/005D` (for example 0x0200 and then 0x0600) and check that the black moves by 1 LSB per step in 14-bit scale (¼ LSB per step at 12-bit).
2. Test `0055` = 0x10 against 0x01 to settle the DGAIN encoding.
3. Re-measure the HCG ratio at a mid code with `05A6/05A8` and `041F` held constant.
4. Override sweep of `00DB/00DC`, `03E1/03E2` and `0016`; and `0058` = 70 in 1×1 against the fp's 20.
5. Long exposure by stretching VMAX with SHR at its minimum, the method QHY and ZWO use.
