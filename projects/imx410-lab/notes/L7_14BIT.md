# L7: 14-bit 2×2 readout — the SoC side (offline RE, 2026-10-20, not run on the camera)

Tags: **[C]** read in code or ROM tables · **[I]** inferred · **[M]** earlier measurement (cited).
Firmware 5.02, `out/MAIN_c0000000.bin`, data segment `out/seg1_c2ef6e00.bin`. Decompiler line numbers refer to
`out/decomp/full/`. Scratch scripts: `$SCRATCH/l7/` (`dasm.py`, `immscan.py`).

## 0. Answer in one paragraph

On the SoC side, only four things depend on bit depth: the receiver data-type register **`0x30100800`**, the
SLVS-EC PHY register **`0x300E10B4`**, the BUFA0 packing (**`0x3018210C`** and the line length **`0x30182114`**), and the HMAX the
14-bit ADC needs (911). The ISP clock divider (`0x30000A08`) changes too, but it follows pixel rate, not depth.
The receiver window (`0x3010000C/24`), the CRCT window and offset registers, the DCLP clamp table, and the
pedestal/gain/clip registers are the **same** for 12 and 14 bit. The CRCT already works in 14-bit units: `0x300F0318`
pedestal = 0x400, `0x300F0308` = 0x4000 − pedestal, all fields `& 0x3FFF`. In 12-bit modes the data is therefore
scaled into a 14-bit range [I]. The firmware does not pick these values by `raw_bit_enum`. It picks them by a per-mode
**link key** (0..7) from the mode list `0xC0B5B918`. Class 16 (14-bit) uses key 2, class 17 (12-bit 1×1) uses key 3.
On the sensor side, `0001` is the only register outside Family A that sets the output word length. BUFA can store
14-bit samples (enum 1, 16 px in 7 words). The format matches the firmware's own 14-bit getter, and
`decode14.py` reproduces that getter exactly.

## 1. Where a mode's SoC configuration is applied [C]

Sensor descriptor (runtime struct in the data segment) **`0xC2F1E654`**: `+0x00` timing table `0xC0B59500` (×0x46,
stride 0x20) · `+0x08` geometry `0xC0B59DC0` (stride 0x64; `+0x3C` = bit enum, getter `FUN_c032c898`) · **`+0x10`
mode list `0xC0B5B918` = {u32 link_key, u32 mode_id} × 0x46** · `+0x24` 0x28-stride crop/bin records `0xC0B5BB48`
(→ `FUN_c0636bc8`) · `+0x40` DCLP clamp table `0xC0B5C638` (stride 0x38) · `+0x48` `0xC0B5D588`.

Mode switch `FUN_c0314708` (blk_c03.c:15262), called from `FUN_c03149b0`:
1. stop CRCT/BUFA paths (`FUN_c0635e58`, `c0635ea8`, `c0636ce0(0)`, `c0636cf8(0)`);
2. `FUN_c0320ab0` → `FUN_c032d5e0`: DCLP clamp regions from `0xC0B5C638` (geometry only, no depth field: mode 0 and 97 records are identical);
3. sensor vtable `+0x20` = `setCmosModeParam` (`XC_ImageSensorIMX410::v6`, c03234a0) → `FUN_c03258c8` (161 regs + `00CE` + `00D1–D3`), `FUN_c0326d88`, `mode_reg` overrides;
4. **`FUN_c0320008(sensor, mode)` (blk_c03.c:21916)** builds `{u32 key = FUN_c031ffa0(mode), u16 x0, u16 x1, u16 y0, u16 y1}`
   from the timing record (+0xA/+0xC/+0xE/+0x10) and calls **`FUN_c0635ed8`** (blk_c06.c:46837), then `FUN_c0636048` (second channel `0x30100310/0x300F3xxx`);
5. later in `FUN_c03149b0`: `FUN_c0635cf8(1)`, `FUN_c0126560(0)`, then sensor vtable `+0x5c` (= `v21`: `FUN_c0128e68(0x29); FUN_c0128d60(1,0)`, the link enable).

Timing: `FUN_c0320740` / `FUN_c0320818` → **`FUN_c01265c0(hmax, vmax)`** (blk_c01.c:23164). It waits for a safe line, then writes
`0x30100004 = (H−1)|(H−1)<<16` and `0x30100020 = (V−1)<<16`. The tail comes from the table via `FUN_c0126128`. Nothing here depends on depth.

`FUN_c0635ed8(win)`:
- `0x3010000C = ceil((x1 − x0%12)/12) | (x0/12)<<16`, `0x30100024 = y0<<16 | y1`, `0x300F1084 = units+1`,
  `0x300F10C0[19:16] = x0%12`, `0x300F021C = 12 − remainder` (the ÷12 is in **pixels**, the same for 12 and 14 bit);
- `0x300F0C4C` bit 4 and `0x300F0010` = (width ≥ 7393). This depends on width, not depth;
- **`FUN_c0124f98(key)`** → `FUN_c01287c0` (receiver defaults: `0x30100000 = (x&0x600000)|0x201008`, `0x30100048..5C = 0`,
  `0x301001E0 = 0x1001010`, `0x300F10C8 = 0x10`, …), `FUN_c0128978(key)` (`0x300F1080[3:0]` = table `0xC07D1600` = **5 for every key**),
  **`FUN_c0128ad0(key)`**: the link/PHY setup (runs only when the key changes, when `0x30100B08 == 0`, or when the flag `0xC31D8E7D` is set; last key in `0xC2F14A50`).

`FUN_c0128ad0(key)`:
- `FUN_c01283e0` reads table `0xC07D1660` (stride 9 words) → `FUN_c0127c80`: PLL `0x30000034` (= 0x01018008 for every key, so no relock),
  **clock divider `0x30000A08[14:8]`**, `0x30000A0C[6:0]` = 0xF, `0x30000A10` = 0x02200000;
- `FUN_c0128448` reads table `0xC07D1780` (stride 25 words) → **`FUN_c0128b68`** (blk_c01.c:25146): `FUN_c0128d60(0)` (`0x30100B08 = 0`),
  `0x30000880` bit 16, `0x30001290 = 1`, **`0x30100800 = row[3]`**, `0x30100B00 = 0x100`, `0x300E1004..1020` = lane map nibbles
  (0x76543210, or 0x23451670 when `0x30080290` bit 0 is clear), `0x300E1030/103C..1044/1074/1078/108C..109C` (same for all keys),
  **`0x300E10B4 = row[14]`**, `0x300E10BC = 0xFFF88`, `0x300EA024..` = 1, `0x300EB004..` = 2, `0x30100980 |= 1`.
  (`FUN_c0128448` also copies table `0xC07D1AA0`, word 1 = 0x0801A013 / 0x08012011, but that buffer is never written to hardware: dead.)

### Link key per readout class (mode list `0xC0B5B918`) [C]

| class | key | divider `0x30000A08[14:8]` | `0x30100800` | `0x300E10B4` |
|---|---|---|---|---|
| 16 (14-bit 1×1: modes 0 6 95 100 122 129 141 144) | **2** | 0x1A | **0x00112013** | **3** |
| 17 (12-bit 1×1, incl. mode 10) | **3** | 0x0B | 0x00112011 | 2 |
| 18 (12-bit 2×2) | 6 | 0x17 | 0x00112011 | 2 |
| 19 (2×2 fast) | 7 | 0x10 | 0x00112011 | 2 |
| 20, 22 (3×3, 3×6) | 4 | 0x21 | 0x00112011 | 2 |
| 21, 23 (3×3, 3×6 fast; mode 8) | 5 | 0x17 | 0x00112011 | 2 |
| unused | 0 / 1 | 0x08 | 0x…13 / 0x…11 | 3 / 2 |

The divider roughly tracks 1/pixel rate: (div+1) × px/cycle ≈ 150–180 for every key [I]. It is a clock-rate setting, not a format.
It is read back by `FUN_c0129fc0` and blk_c06.c:39840 as an ISP clock = PLL / (div+1).

## 2. Every SoC register whose value depends on bit depth

| register | 12-bit | 14-bit | writer | source | tag |
|---|---|---|---|---|---|
| `0x30100800` receiver data type | 0x00112011 | 0x00112013 | `FUN_c0128b68` | `0xC07D1780[key]` word 3 | [C] (meaning of bit 1 = 14-bit: [I]) |
| `0x300E10B4` SLVS-EC PHY | 2 | 3 | `FUN_c0128b68` | `0xC07D1780[key]` word 14 | [C] (looks like (bits−8)/2: [I]) |
| `0x30100004` HMAX/tail | 445 (0x01BC01BC) | 911 (0x038E038E) | `FUN_c01265c0` | timing table +4 | [C]; needed by the 14-bit ADC, Family A [I] |
| `0x3018210C` BUFA0 format | 0 | 1 | `FUN_c06306e0` (c06306e0) | BUFA struct `+0xE` (enum: 0=12, 1=14, 2=16, 3=10, 4=8) | [C] |
| `0x30182114` BUFA0 line words | w·3>>3 | **w·7>>4** | same | width = `FUN_c01250e8(0)` | [C] |
| `0x30000A08[14:8]` ISP clock divider | 0x0B (key 3) | 0x1A (key 2) | `FUN_c0127c80` | `0xC07D1660[key]` word 2 | [C]; tracks pixel rate, not depth |

Not depth-dependent [C]: `0x3010000C`, `0x30100024`, `0x300F021C`, `0x300F1080` (5), `0x300F1084`, `0x300F10C0`,
`0x300F10C8`, `0x30100000`, the DCLP clamp table, `0x300F0308/030C` (white = 0x4000 − pedestal, `FUN_c03132b8`),
`0x300F0310` gain (`FUN_c0634508`, ×256/100), and `0x300F0318/031C` pedestal (`FUN_c0634580`; 0x400 or the DCLP loop clamped to 0x100..0x700).
These last ones always use 14-bit units. With the measured 12-bit BUFA black of 251–255 [M] against the 14-bit pedestal 0x400, the 12-bit BUFA output
is CRCT bits 13:2 [I]. The stock 14-bit DNG black of 1024 = 256<<2 agrees.

## 3. Sensor side: how the word length is chosen [C]

Class 16 against class 17 in the fp table differs in 43 registers. 37 of them are Family A (14-bit vs 12-bit normal ADC), constant
inside each class:
`0042=22 007E=60 007F=FC 0081=68 0083=10 0084=10 0085=14 0086=14 0089=66 008C=00 0403=22 042A=58 042D=98 0430=89
0441=89 0453=30 0482=03 0484=05 0487=60 0489=68 048B=58 04DC=6A 04DF=6C 04E1=6A 04E4=40 04F1=00 0511=84 0525=11
0571=22 0575=10 0576=10 0577=14 0578=14 057A=00 0585=7B 05D8=74 06D9=00` (14-bit values; the mode-10 values are
`88 46 C0 4E 23 23 19 19 EE 33 88 3E 7E 6F 7D 00 07 0B 46 4E 3E 5C 5E 5C 3A 70 6A 10 AA 12 12 19 19 33 6C 5E 02`).
The rest: `0001` (29/2A), and `0003/0016/0022–0025`, which differ only between pairs with different window or VMAX.
**Pairs with the same geometry and VMAX (0/97, 129/130) differ only in Family A + `0001`.** So the output word length is `0001`
alone. Z CAM agrees: the 11-bit ADC readouts keep the 12-bit word code (2A/2C/39), so the ADC width is Family A and the word length is `0001`.
Neither the fp nor Z CAM writes the black level `005C/5D`. It is already in 14-bit LSB (0x3FF ≈ 1024/4), so it needs no change.

Known `0001` codes: 29 = 6064/14, 2A = 6064/12, 2B = 4160/14, 2C = 4160/12, 2F = h3, 30/31 = ÷6, 34–36 strips, 39 = 2×2/12, 3B = h2.
Within a format, the 14-bit code is the 12-bit code − 1 (29/2A, 2B/2C), so **`38` is the 2×2/14 candidate**, with `3A` next [I].
No table anywhere (fp, Z CAM, ZWO, QHY, ToupTek) has a 14-bit binned readout.

## 4. BUFA0 can store 14-bit samples; decode14 [C]

`FUN_c06306e0` (kind 0, uncompressed): enum 1 → `0x3018210C = 1`, `0x30182114 = width·7 >> 4`. The firmware reader
`FUN_c031e370` sends enum 1 to **`FUN_c031e800`**: the same MSB-first bit stream inside LE 32-bit words as 12-bit, 16 px per 7 words.
**`decode14.py`** (new) unpacks it and its self-test matches a literal port of `FUN_c031e800` on random data.
The `decode12.py` call becomes `decode14(raw, rows, words_per_row)`, with `words_per_row` read back from `0x30182114` as now.
- **Width must be a multiple of 16** or the last ½ word of each line is truncated (`>>4`): 6064 fits (2653 words). 3032 gives
  1326.5 → 1326, so use a receiver x window of **4..3028 (3024 px, 1323 words)** for 2×2.
- Host tools hard-code enum 0: `bufa_probe.py` / `fastsweep.py` / `readout_test.py --rewindow` put `bytes(20)` as the window struct.
  For 14-bit, write byte `+0xE = 1` (`bytes(14) + b'\x01' + bytes(5)`, plus the callback word where used).
- Frame size grows by 7/6. Mode-10 window at 14 bit = 2022 × 2653 × 4 = **21.46 MB**, but `fastsweep.Session` allocates the
  12-bit size (18.4 MB) + 4 KiB. **A BUFA overrun into the heap is the main crash risk.** Allocate for the 14-bit size first.

## 5. Live recipe (not run)

Read-only checks first (zero risk; mode 8, then magnify → mode 10): `0x30100800` (expected 0x00112011), `0x300E10B4` (2),
`0x30000A08` ([14:8] = 0x17 in mode 8, 0x0B in mode 10), `0xC2F14A50` (last key: 5, then 3), `0x30100B00`, `0x30001290` (1).
If any of these disagrees, §1–2 are wrong and nothing below should be written.

**T0: 14-bit BUFA from a 12-bit stream (low risk).** In mode 10, arm BUFA0 with struct `+0xE = 1`, using a buffer of ≥ 21.5 MB plus a guard.
Expect `2114 = 2653`, black ≈ 1004–1020, and every value ≈ 4× the 12-bit frame. The low 2 bits show whether CRCT carries fractional bits (non-zero)
or the receiver only shifts the data left (zero). This proves `decode14` and BUFA 14-bit packing before the sensor is touched.

**T1 (L7a, no unknown codes): 14-bit vertical 2:1, 6064 × ~2012.** In a fast session in mode 10:
1. BUFA0 stop (`startstop 100`).
2. Sensor batch (70 writes): `0001=29` + the 37 Family-A 14-bit values above + the L3 vbin-2 set
   (`0005=03 001C=03 0717=04 071E=05 0720=05 0722=02 0723=02 0724=02 0725=02 0726=01 0728=3D 072A=F0 072B=03 072C=04 0734=05
   0735=05 0737=02 0738=02 0739=02 073A=02 0792=22 0793=02 0794=05 079C=3D`) + `0242=2C 0278=04 0279=01 027B=04 08B6=01 08B7=68`
   + `0003=00 0018=12`.
3. SoC timing: `0x30100004 = 0x038E038E` (HMAX 911), `0x30100020 = 0x08970000` (VMAX 2200 → 35.9 fps), with the low half kept as `readout_test.py` does.
4. Receiver depth, variant (a), minimal: `0x30100800 = 0x00112013`, `0x300E10B4 = 3`. If no frame arrives, use variant (b), the stock path:
   callfn `FUN_c0635ed8|1` with struct `<I key=2><H 8><H 6072><H y0><H y1>` (window + PHY key 2 + divider 0x1A), then
   `FUN_c0128e68|1(0x29)` and `FUN_c0128d60|1(1, 0)` (the stock link enable). All three are Thumb.
   L3's receiver window was 1500 rows; for the full V-2:1 field, y ≈ 40..2050 (measure the row count, as in L3).
5. BUFA0 window again (enum 1), size check against the buffer, arm, grab, `decode14`.
6. `poff 1` / fastreboot (the batch and the key-2 link state are not undone otherwise; leaving magnify would itself re-run `c0128ad0(3)` [C]).
Pass: black ≈ 1024 ± a few, OB rows present, CFA phases as in L3, and a value range up to ~16 k. The 2:1 horizontal step is done on the host
or in the CRCT Hbin tap (mux 3, untested).

**T2 (L7b, true 2×2): from mode 10 → the mode-98 table with 14-bit Family A.** Sensor batch (70 writes): the 33 mode-10→98
differences with `0001` replaced: `0001=38 0003=00 0005=03 0016=14 001C=03 0022=00 0023=00 0024=00 0025=00 0058=70 0717=04
071E=05 0720=05 0722=02 0723=02 0724=02 0725=02 0726=01 0728=3D 072A=F0 072B=03 072C=04 0734=05 0735=05 0737=02 0738=02
0739=02 073A=02 0790=00 0792=22 0793=02 0794=05 079C=3D`, plus the 37 Family-A 14-bit values. SoC: HMAX 911 (`0x038E038E`),
VMAX 2094 (`0x082D0000`, 37.7 fps), receiver x 4..3028 / y 20..2032 (`0x3010000C = 0x000000FC` for 3024 px,
`0x300F021C = 0`, `0x300F10C0[19:16] = 4`, `0x30100024 = 0x001407F0`; simplest is variant (b) with `{2, 4, 3028, 20, 2032}`),
then the receiver depth as in T1 step 4, then BUFA enum 1 (2032−20 = 2012 rows × 1323 words = 10.6 MB).
- **T2a first:** the same batch with `0001=39` (12-bit word) and the receiver kept at 12 bit. This checks the 14-bit ADC at HMAX 911 in
  2×2 without an unknown code (an 11-bit ADC with a 12-bit word works, §22, so a 14-bit ADC with a 12-bit word should too [I]).
- **T2b:** `0001=38` + 14-bit receiver; if there is no frame or the frame is garbage, try `3A`.
- Telling a 12-bit word from a 14-bit word: decode the same raw both ways. Only the right one gives smooth same-colour neighbours (dx2 ≈ a few DN,
  as in BUFA_FRONT_TAP) and black near 256 (12) or 1024 (14).

### Risks
- **Unknown `0001` (38/3A)** may select an undefined format or stall the sensor's output. Recovery is `poff 1` (all writes are RAM/sensor), or a power cycle
  if the sensor stays stuck. Never in the settings area.
- **BUFA overrun** when the 14-bit frame is larger than the buffer (T0, T1). Size first and keep the guard word.
- **HMAX 445 with the 14-bit Family A** will not finish lines (compare L2b at HMAX 330: every other line empty). Always write HMAX 911 in the same step.
- AE still computes SHS for mode 10 (HMAX 445): exposure ×2.05 at HMAX 911. Use `imager fixed_shutter` or accept the brighter image.
- Variant (b) re-initialises the PHY and resets the receiver defaults (`0x30100048` long-exposure count, etc.) while streaming, and zeroes the
  BUFA callback globals `0xC37CF8BC/8C0/8E0/8E4/92C/944`. Stop BUFA0 first. The link stays disabled (`0x30100B08 = 0`) until the
  `FUN_c0128d60(1,0)` call.
- Do not run any of this while recording; afterwards, do not leave key 2 in place: reboot.
- Inferred, not checked: whether `0x30100800` bit 1 and `0x300E10B4` alone switch unpacking. The registers were found from the key-2/key-3 table
  difference, not from documentation, so variant (b) is the fallback that reproduces the stock state exactly.

## 6. Live results (2026-10-20, `l7.py`)

- Read-only checks in mode 8 all as predicted (0x30100800 = 0x112011, 0x300E10B4 = 2, 0x30000A08[14:8] = 0x17, key 5).
- **T0 pass:** mode 10, BUFA0 struct +0xE = 1 → 2062 × 2653 words, decode14: ×3.996 the 12-bit frame (corr 0.9991),
  black 1019. Low 2 bits non-zero in 99.5 % → the CRCT carries 14-bit precision that the stock 12-bit BUFA output drops.
- **T1 pass — 14-bit ADC + vertical-only 2:1, 6064 wide:** 38-reg Family A (mode 0 values) + L3 vbin-2 set + `0001=29`,
  HMAX 911, receiver 14 (`0x30100800=0x00112013`, `0x300E10B4=3`), BUFA enum 1; **VMAX must stay 2700** (the AE shutter is
  computed for it; VMAX 2200 gave ~no exposure). Range to 16378; OB values use all four codes mod 4 (12-bit ADC data
  stored as 14 bit sits on 0/3 mod 4) → **true 14-bit**; OB noise 9.9 DN14 vs 21.4 DN14 for the 12-bit ADC (part of
  that is the 2:1 vertical sum).
- **T2 (true 2×2, h-bin 2 format) fails with the 14-bit ADC:** `0001=39` (12-bit word) → constant 4094/3837;
  `0001=38` and `3A` with the 14-bit receiver → constant 14611/13958. The same synthesis with the 12-bit Family A
  (`0001=39`, HMAX 445) works (control `t2ref`), so geometry and receiver are right: **the sensor has no 14-bit word in
  the horizontally binned format**. 14-bit "2×2" = sensor vertical 2:1 (T1) + horizontal 2:1 in the ISP/host.
