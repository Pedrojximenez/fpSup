# Z CAM E2-F6 vs SIGMA fp: IMX410 register writes (offline, 2026-10-20)

Source: `zcam_e2f6/out/rootfs/usr/bin/imvt_camera` (fw 1.0.13, read statically, nothing executed) and the decompile in
`zcam_e2f6/ghidra/imx410_drv.c`. Tools and data: `projects/imx410-lab/offline/zcam/`
(`zcam_extract.py <imvt_camera>` → `zcam_imx410_tables.json`, `zcam_init_sequence.csv`, `zcam_readout_regs.csv`,
`zcam_modes.csv`, `zcam_ae_registers.csv`; `zcam_compare.py` → `compare_readout_match.csv`, `compare_a_zcam_only.csv`,
`compare_b_fp_only.csv`, `compare_c_both.csv`). The re-extraction matches the older dump `zcam_e2f6/imx410_zcam_tables.json` byte for byte.
Tags: [C] read from code or data, [I] inference.

## 0. Main findings

1. **[C+I] The fp's "fast" AD set (classes 19/21/23) is Sony's 11-bit ADC mode.** Z CAM's readout table names Sony's
   modes (`MODE0`…`MODE22`, `MODE1A`…`MODE2D`) and gives each one an ADC bit depth (14/12/11). On all 86 Family-A registers
   (§21), Z's 14-bit / 12-bit / 11-bit readouts match the fp's 14-bit / normal / fast sets with **0 mismatches**
   (81 registers compared for fast, 37 for normal). Z CAM shows this to users as `rec.sensor.readout_fast`. Z caps the
   analog code at `0xEFD` (24 dB) in 11-bit readouts and at `0xF7E` (30 dB) otherwise (`sesnor_n3a_calc_again`). The fp
   runs its fast class 21 (mode 8) up to code 3965, and §5 measured the gain law holding there [M]. So Z's 24 dB cap is a
   policy, not a limit of the sensor [I].
2. **[C] Z uses classes the fp does not have: fast (11-bit) AD at 1×1.** Z modes in use: `MODE5` 4160×2160 at HMAX
   320–330 (90 fps), `MODE5C` 4160×1728 and `MODE5D` 4160×1188 at HMAX 330–400 (96–170 fps), and `MODE2D` 6064×2700 at
   HMAX 429/431 (60 fps). Every fp fast class is binned (2×2, 3×3 or 3×6), so the fp has no fast 1×1 class. These modes
   take the fp's fast Family A set unchanged, with Family B at vbin 1.
3. **[C+I] Z's 4K crop narrows the vertical-drive window and does not use the output window.** The fp's 4176×2174 modes
   leave the 07xx block at the full-height setting (`0728`=3B, `072A/B`=0x07E5) and crop with `0003`/`0022–0025`, or in
   the SoC. Z's `MODE3/4/5` write `0728/0729` = 0x03E7 (999) and `072A/072B` = 0x0439 (1081), and leave `0003` unwritten.
   Reading 0728/29 as the 16-bit first row and 072A/2B as the 16-bit row count ÷ 2 fits all three fp vbin columns
   (59/2021 → 4042 rows, 61/1008, 63/672) and Z's crop: 999 = 59 + (4042−2162)/2, and 1081×2 = 2162 rows, centred [I].
   This is how Z gets **4160×2160 at 72 fps (12-bit) and 90 fps (11-bit)**. A full-height drive at HMAX 445 tops out at
   ≈39 fps. Candidate for an fp UHD-crop high-frame-rate mode (to test).
4. **[C] `0001` values the fp never uses:** `2B` (14-bit 4160 crop), `2C` (12/11-bit 4160 crop), `31` (6064×672),
   `34/35/36` (2020×136/112/96), `3B` (3032×4040 = horizontal 2-bin, no vertical bin). `2A` also covers `MODE21/22`,
   6064×2012 = **vertical 2-bin with no horizontal bin**. That mode needs 6 extra registers that are 0 in every fp mode:
   `0242`=2C, `0278`=04, `0279`=01, `027B`=04, `08B6`=01, `08B7`=68. So `0001` sets the horizontal format / crop
   (2A full width, 2C 4160, 39/3B ÷2, 2F/30 ÷3), and Family B sets the vertical bin independently [I]. Z never uses these
   readouts (only `MODE3/4/5` and the 1A–2D variants).
5. **[C] One extra vertical-bin column: ÷12 (`MODE12/13`, 2020×336)**: `0793`=0C, `0792`=60, `0794`=0D, `0737/0738`=4,
   `0739/073A`=0A, `072C`=18, `0734`=5, `0736`=10, `078D`=10 (already in ZCAM_E2F6_FIRMWARE.md). `0003`=4, a window mode
   the fp never uses (the fp uses 0/1). Not used by Z.
6. **[C] HCG policy differs; the register values agree.** Z: total gain < ×5.5033 → LCG (`05A6/05A8` = 29/27); at or
   above it → HCG (`05E1`=1, `05A6/05A8` = 2A/29, analog = gain ÷ 5.3088). `041F`=0E (LCG) / 1D (HCG) and `05E2`=1 once
   the code is above 0xDFC. These are exactly the fp's §5 values and its 0xDFD threshold. **But Z turns HCG on at about
   ×5.5, while the fp waits until relative 7488–14976 (≈ISO 6400–12800).**
7. **[C] Z sets the sensor's own digital gain `0055` (DGAIN, 0–3).** The fp never writes `0055`: its digital gain is the
   CRCT in the SoC (§12). Z also writes `0009/000A` (SPL), always 0. It uses `0007/0008` (SVR) for exposures longer than
   one frame (svr = lines ÷ VMAX). The fp holds SVR at 0 and does this in the SoC (§2).
8. **[C] Apart from that, Z writes almost a subset of the fp's set.** 159 of the fp's 161 table registers are in Z's
   table, and all 13 of the fp's per-frame registers are in Z's AE list. Z adds only
   `0000`, `0009`, `000A`, `0055`, `00D9`, `00E9`. Of the 188 Sony-a7III-only registers it writes just `0000`=04 (same as
   Sony), plus `0009/000A` = 0. The 2020×1080 / 3×3 (`MODE6C`) set differs from fp class 20 only in `0016`
   (and the window).

## 1. Z CAM init sequence (`sensor_init` 0xB94990) [C]

Before this: `imvt_sensor_init_stage1` (ISP slave sync), then the SPI bus (`/dev/spidev`, mode 0x0B = CPOL|CPHA|LSB-first,
8 bit, 10 MHz; packet `81 aH aL v`, read `82 aH aL 00`). The table walk is `sensor_common_register_init`: the rows in
order, a row's value is skipped when 0xFFFF, and the driver sleeps `delay_ms` after the row.

| step | write | note |
|---|---|---|
| 0–2 | `00E9`=80, `00D9`=60, `04E6`=00 | 00E9/00D9 are Z-only (not in the fp or Sony lists) |
| 3 | wait 10 ms | |
| 4–7 | `00C5`=00, `00C6`=00, **`0000`=04**, `00CA`=01 | the fp writes C5/C6/CA in its table, same values |
| 8 | wait 1 ms | |
| 9–163 | per-readout block, 155 rows (`zcam_readout_regs.csv`) | starts `0001, 0003, 0005, 0016, 001C, 0022–25, 0042…`, then ascending through `08B7` |
| 164–165 | `00CE`=00, wait 1 ms | the fp also writes 00CE=0 after its table |
| AE | `0007 0008 0009 000A 0005 0006 003D 003E 003F 0040 041F 05E2 05A6 05A8 05E1 0055` | `sensor_n3a_register_init`; then stage2 (SoC slave sync: Hs = HMAX, Vs = HMAX·VMAX) |

Common rows (the same value in all 33 readouts): `00E9 00D9 04E6 00C5 00C6 0000 00CA`, `0016`=07, `0043`=02, `0058`=70,
`041B`=03, `044D`=00, `0590–0595`=01/03, `059A–059D`=02, `06D0/06D3/06D6`=01, `00CE`=00. The rest are per readout
(`zcam_init_sequence.csv`, column `kind`). Standby is `0000` bit 0 (`sensor_standby` |=1, `_cancel` &=FE).
The fp's stop/start `0011` is never written. Per frame, Z writes only the AE entries that changed (`FUN_00B932F8`). It
never writes the binning block at runtime.

**Delta table:** 0xFFFF means "leave the power-on value". In the 14-bit readouts Z writes 1 of the 86 Family-A
registers (`0569`). For 123 of the 136 registers that Z skips somewhere, the fp's value in the matching column is the
same everywhere [I: these are the IMX410 power-on values; the fp's 14-bit set ≈ power-on]. The 13 exceptions are the
fast-only registers `0094 0240 0244 0524`, which `MODE14–16` (tiny 11-bit ROIs) do not write, and the 07xx registers
that MODE8–16 leave alone. No reset is visible in the driver (sensor reset is in HiSilicon VI/MPI) [?].

## 2. Z CAM modes (59 modes → 13 of 33 readouts) [C]

`zcam_modes.csv`. Runtime VMAX = even(round(72 MHz·ratio / fps / HMAX)) (`FUN_00B93F38`). The table's `vmax` and
`inck_per_vs` fields are only stale hints: for example, mode 2 lists 6250 but runs at 6592.

| readout (Sony) | out | ADC | `0001` | vbin | Z modes (fps) | HMAX | fp equivalent |
|---|---|---|---|---|---|---|---|
| 1 `MODE1` | 6064×4040 | 12 | 2A | 1 | 23.98–30, 39 | 445–455 | class 17 (mode 97/3) |
| 23 `MODE1A` | 6064×3260 | 12 | 2A | 1 | 24–30, 48 | 443–480 | class 17 + window |
| 24 `MODE1B` | 6064×2560 | 12 | 2A | 1 | 24–60 | 443–480 | class 17 + window |
| 25 `MODE1C` | 6064×1728 | 12 | 2A | 1 | 48–90 | 450–500 | class 17 + window |
| 28 `MODE1D` | 6064×1188 | 12 | 2A | 1 | 96–120 | 450–480 | class 17 + window |
| 30 / 31 `MODE1E/1F` | 6064×2592 / 3132 | 12 | 2A | 1 | 48–60 | 440–454 | class 17 + window |
| 4 `MODE4` | 4160×2160 | 12 | **2C** | 1 (**07xx crop**) | 48–72 | 445–600 | none (fp crops in the SoC) |
| 5 `MODE5` | 4160×2160 | **11** | **2C** | 1 (07xx crop) | 90 | **320–330** | **none** |
| 26 `MODE5C` | 4160×1728 | **11** | 2C | 1 (07xx crop) + window | 90–120 | 330–400 | **none** |
| 29 `MODE5D` | 4160×1188 | **11** | 2C | 1 (07xx crop) + window | 150–170 | 330–384 | **none** |
| 32 `MODE2D` | 6064×2700 | **11** | 2A | 1 | 48–60 | 429–500 | **none** (fast 1×1) |
| 27 `MODE6C` | 2020×1080 | 12 | 2F | 3 (2 rows added) | 100–120 | 455–500 | class 20 (mode 134) |

Unused readouts that are in the table: 0/3 (14-bit full / crop), 2 (11-bit full), 6/7 (2020×1342 = fp 139/56),
8–11 (6064×672 and 2020×672, 07xx block not written = vbin-6 style), 12/13 (÷12), 14–16 (2020×136/112/96, 0001 34–36),
17/18 (3032×2012 = fp 98/58), 19/20 (3032×4040, 0001 3B), 21/22 (6064×2012 V-only 2-bin).
Full list: `compare_readout_match.csv`.

## 3. Comparison

### (a) Z writes, the fp never does [C]
| reg | Z value | context | name in Z |
|---|---|---|---|
| `0000` | 04 at init; bit 0 = standby | init / standby | (Sony a7III also 04) |
| `0009/000A` | 00 | AE init + per frame | SPL_L/H |
| `0055` | 0–3 by digital gain (0x2000–0x2FFF→1, 0x3000→2, 0x4000→3) | AE | DGAIN |
| `00D9` | 60 | init, before the 10 ms wait | — |
| `00E9` | 80 | init, first write | — |

### (b) the fp writes, Z never does [C]
| reg | fp | note |
|---|---|---|
| `0056/0057` | 02/06 in the 1×1 full-height and 3:2 modes (0, 97, 129, 130, 141, 142, 144, 145); else 00 | Z full-height `MODE1` leaves them at the default |
| `0011` | 0 → 1 around mode switches | Z uses `0000` bit 0 instead |
| `00D1/D2/D3` | 251/255/2 (mode 10), 250/255/2 | outside the fp table |

All 161 fp table registers except `0056/0057` are written by Z in at least one readout.
`0242 0278 0279 027B 0736 078D 08B6 08B7` are written only in unused readouts.

### (c) both write: differences by §21 family (used Z readouts, compared to the fp column with the same speed set / vbin) [C]
| family | reg | Z | fp | comment |
|---|---|---|---|---|
| A (AD speed) | all 86 | = fp | | 0 mismatches. 14-bit / 12 / 11-bit ADC = fp 14-bit / normal / fast |
| B (vertical drive) | `0058` | **70 in all readouts** | 20 in 1×1, 70 binned | §20 single-bit sweep shows no entry for 0058 b4/b6 (probably no effect) [I] |
| B | `0728/0729`, `072A/072B` | E7/03, 39/04 in 4160 crops | 3B/00, E5/07 | vertical-drive window (finding 3) |
| B | `0016` | **07 in every readout** | 0F/14/19/23/32 (07 only in modes 95, 11) | the Z CAM note's "vblank/2" reading is unconfirmed; Z doesn't vary it |
| C (format) | `0001` | 2A/2C/2F (+2B 31 34 35 36 3B unused) | 29 2A 2F 30 39 | finding 4 |
| C | `0089/008A` | EE/– normal; 66/– 4160 fast; **AA/66 6064-wide fast** | class 23 (3×6 fast) = AA/66, other fast = 66/22 | lane/data-rate code [I]; the fp has AA/66 only in 3×6 fast |
| C (window) | `0003`, `0022–0025` | 0003=1 + start/rows÷2 for every crop; unwritten for full / 4160×2160 | same encoding | Z `MODE1C` starts at 1191, `MODE5C` at 1105 for the same 1728 rows: not both centred [?] |
| const | `0729` | 03 (4160 crops) | 00 always | upper byte of the 0728 start row |
| const | others (`0043 00C5 00C6 00CA 041B 044D 04E6 0590–059D 06D0–06D6`) | = fp | | |

## 4. Names and strings in `imvt_camera` [C]

AE register list (`g_sensor_spec` → 0x132C698, +0x38 count = 16, entries {bus, ?, addr, flags, name}):

| addr | name | Z driver use |
|---|---|---|
| 0007/0008 | `SVR_L/H` | frames to extend the exposure (long exposure); fp: always 0 |
| 0009/000A | `SPL_L/H` | always 0 |
| 0005/0006 | `SHR_L/H` | = fp SHS: SHR = (VMAX·(svr+1) − lines)/2, clamped to [2, VMAX/2−2], warns above 0x3FFF |
| 003D/003E | `APGC_N_L/H` | analog code, normal pixels |
| 003F/0040 | `APGC_S_L/H` | same code ("S" pair; §14: per colour, not a second exposure) |
| 041F | `APGC_ADD1` | 0 / 0E (LCG, code > 0xDFC) / 1D (HCG, code > 0xDFC) |
| 05E2 | `APGC_ADD2` | 0 / 1 (code > 0xDFC) |
| 05A6 | `MGAIN_ADD1` | 29 LCG / 2A HCG |
| 05A8 | `MGAIN_ADD2` | 27 LCG / 29 HCG |
| 05E1 | `MCOVGAIN HCG` | HCG on at gain ≥ 5.5033; HCG factor 5.3088 |
| 0055 | `DGAIN` | sensor digital gain 0–3 |

Functions and strings: `sesnor_n3a_calc_again` (sic; code = (g−1)·4095/g, cap 0xF7E, or 0xEFD when
`sensor_mode_adc_is_11bits`), `sensor_n3a_get_max_again` (167.9× / 84.1× in 11-bit), `sensor_n3a_set_sensor_again`,
`sensor_n3a_set_sensor_dgain`, `sensor_n3a_calc_svr_shr`, `sensor_n3a_set_sensor_shutter_time`, `sensor_n3a_is_hcg_enable`,
`sensor_standby(_cancel)` (0000 b0), `sensor_spec_get_maximum_exposure_lines` = 0x8000, `sensor_spec_vlines_need_even` = 1,
`g_astImx410ModeTbl` fields `u32InckPerHs` (= HMAX) / `u32VertiLines`, `g_au16ResHMax`, `rec.sensor.readout_fast` /
`imvt_cam_set_fast_readout_enable` (picks the 11-bit readouts), the SLVS attributes `..._IMX410_12BIT_{6064x4040, 6064x2560,
5596W, 4096x2160, 2020x1342}_NOWDR_ATTR`, and the debug shell `imvt_sensor_debug_request` 1000–1007 (AE lock, AE register
dump, SVR/SHR and gain tables, HMAX override).
**No strings or code for DOL, Clear HDR, dual gain, PGA or BLKLEVEL.** "WDR" is ISP-side only: the HiSilicon
template's "2to1 line WDR mode" changes only ISP state, writes no sensor registers, and the F6 UI says "WDR is not
supported". Black level is ISP BLC (`sensor_blc_*`, default 0x100 per channel), not a sensor register.

## 5. Worth testing on the fp (proposals, not done)
- 4160-wide crop with `0001`=2C plus the Z 07xx window (`0728/0729`=E7/03, `072A/072B`=39/04): expect ≈2162 rows → UHD
  crop at 60–72 fps (normal) or 90 fps (fast set at HMAX ≈330).
- Fast (11-bit) Family-A set at vbin 1 (Z `MODE2D`/`MODE5`): a 1×1 class with HMAX 330–430.
- Vertical-only 2-bin (`MODE21`: 0001=2A, vbin-2 column, plus `0242 0278 0279 027B 08B6 08B7`) = 6064×2012.
