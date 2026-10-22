# SIGMA fp (Ver.5.02, Sony IMX410) — ISO / Gain Firmware, Complete Low-Level Logic

Exhaustive reverse-engineering of the gain/ISO pipeline: from "user/AE picks ISO N" to
"sensor analog-gain registers + conversion-gain registers are written and the ISP digital gain
is set." Every claim carries an evidence citation (`blk_c03.c:NNNNN` line, or firmware address)
and a confidence tag:

- **CONFIRMED** — read directly from decompiled code / firmware bytes.
- **INFERRED** — deduced from surrounding code; logic is sound but not a single line proves it.
- **OTP-RUNTIME** — the *code path* is confirmed, but the *numeric value* lives in the sensor's
  per-unit calibration flash (OTP). ROM does not contain it; a live dump is required.

Firmware base `0xC0000000`; file `out/MAIN_c0000000.bin` (offset = VA − base). Primary decomp
`out/decomp/full/blk_c03.c`. **This model = IMX410. The fp L = IMX455 shares the framework but is
a SEPARATE class** (`XC_ImageSensorIMX455__*`, e.g. v8 @ `c03278e0`, blk_c03.c:26423). Everything
below is the IMX410 path unless stated; IMX455 lines are called out only to disambiguate.

---

## 0. Objects, vtable, and the three data structures

- **IMX410 object `G` — corrected 2026-09-16.** Base ctor `FUN_c031fe08` (blk_c03.c:21828),
  IMX410 ctor `FUN_c03255b0`, singleton getter `FUN_c03255f8` returns **`0xC343B588`**.
  Live `G+0xD0=0xC0B5FCC0` confirms its vtable. This is `v8`'s `param_1`.
  The former address `0xC343A6A0` is a separate RGB/digital-gain helper `H`, returned by
  `FUN_c0312ee0` and initialized by `FUN_c0312e98`; do not apply sensor-object offsets to it.
  Field map (int-index → byte-offset), from the ctor and from `v8`:
  | G field | offset | meaning | evidence |
  |---|---|---|---|
  | `G[0]`   | 0x00 | pointer to **config/calibration struct `S`** (`*param_1` in v8) | ctor `*param_1=param_2` :21832 |
  | `G[6]`   | 0x18 | last relative-gain% (clamped) | v8 :24518 |
  | `G[0xb]` | 0x2c | linear gain ×100 (analog, post-cap) | v8 :24580 |
  | `G[0xc]` | 0x30 | **cap-overflow digital gain %** | v8 :24577 |
  | `G[0xd]` (byte 0x34) | 0x34 | **HCG flag** (1=HCG/0=LCG) | v8 :24520 |
  | byte 0x37 | 0x37 | **high_gain_off** force-LCG flag | `FUN_c0320ca0` :22354 |
  | `G[0xe]` | 0x38 | **inter-node digital-trim gain %** (from v31) | v8 :24523 |
  | `H+0x0c` (separate helper) | 0x0c | current **gain_state** (0-8); not `G+0x0c` | `FUN_c03131d0/31e0` :14430–14480 |
- **Sensor dispatch vtable = `0xC0B5FCC0`** (the "port vtable"). Verified by resolving the
  runtime dispatch offsets against firmware bytes: `+0x24→v7`, `+0x28→v8`, `+0x2c→v9`,
  `+0x30→v10`, `+0x80→v30`, `+0x84→v31` (all CONFIRMED by dumping `u32(0xC0B5FCC0+off)`).
  The Ghidra "56-slot vtable@c0b5fcc4" is the same table shifted by one slot header.
- **Config/calibration struct `S`** — filled from OTP by `FUN_c03344b0` (blk_c03.c:35117). `G[0]`
  points at it. All the per-unit gain calibration lives here (§6).
- **Sensor-manager object** — returned by `FUN_c0322020` (blk_c03.c:23308) = `*FUN_c0322e48(0)`.
  Holds the v31 digital-ladder node table and the `+0x95/+0x96` enable/calibrate flags (§5). This
  is a DIFFERENT object from `S`; do not conflate its `+0x84/+0x98…` with `S`'s.

Live cross-checks (`research/autofocus/captures/af-fusion/2026-09-16-iso12800-c` and
`2026-09-16-iso100-v5`): ISO100 has `G+0x18=117`, `+0x20=985`, `+0x2c=131`, `+0x34=0`;
ISO12800 has `14976`, `3840`, `1606`, `1`, respectively. AF RGBgain exactly mirrors `G+0x18`.
The UI ISO and calibrated relative-gain domain are therefore distinct on this unit.

---

## 1. Full call chain (top → sensor registers)

```
AE / user ISO selection
   │  ISO number  ── FUN_c04d01f8 ──▶ Sv = round(1024·log2(ISO/3.125))     [APEX, display/AE]
   │  FUN_c00b8860: calibrated relative gain (ROM anchors ISO ×1.17; ISO100→117)
   ▼
FUN_c030c878(_, gain%, flag)                                     blk_c03.c:10149  (public setter)
   └▶ FUN_c0312f18(H, gain%, flag)                               blk_c03.c:14282  APPLY entry
        │  flag!=0 → store rel% into H, recompute abs_gain:
        │     FUN_c03131e0(H, rel%)                              blk_c03.c:14441
        │        builds params {rel%, LCG_ref_code, HCG_ref_code, mode}   (:14461-14476)
        │        gets the separate sensor G via FUN_c0322e48(0)
        │        └▶ vtable +0x28 = XC_ImageSensorIMX410__v8      blk_c03.c:24480  GAIN COMPOSE
        │              ├▶ +0x80 = v30  (HCG/LCG decision)        blk_c03.c:24664  → G.HCGflag
        │              ├▶ FUN_c0320cd0 → +0x84 = v31 (digital    blk_c03.c:22365 / 24698
        │              │     inter-node trim ladder) → G[0xe],   feeds AeDigitalGainBase
        │              └▶ dB math → returns abs_gain = digital<<16 | analog_code
        │  split abs_gain:  digital% = (x&0x7fff0000)>>16 (floor 100),  analog = x&0xffff
        │  push digital% to AE digital-gain accumulator (ISP)          :14315-14322
        └▶ vtable +0x2c = v9 → +0x30 = XC_ImageSensorIMX410__v10  blk_c03.c:24604  WRITE REGS
              writes analog code → 0x3D/0x3E (+ mirror 0x3F/0x40),
              conversion-gain regs 0x05E1/0x05A6/0x05A8, high-analog 0x05E2/0x041F
```

The **sensor** only ever receives: the analog code (regs 0x3D/0x3E/0x3F/0x40), the
conversion-gain select + trims (0x05E1/0x05A6/0x05A8), and the high-analog readout regs
(0x05E2/0x041F). **All digital gain is applied downstream in the ISP** (AeDigitalGainBase,
unity=100), never as a sensor register. (CONFIRMED — v10 writes no gain-magnitude digital reg;
digital only flows through `FUN_c0320cd0`→`FUN_c032f578`(0xc320209c) and the FUN_c0312f18 ISP push.)

---

## 2. The exact gain math — `XC_ImageSensorIMX410__v8` @ `0xC0323580` (CONFIRMED)

Constants (dumped from ROM): `DAT_c03239b8 = 4095.0`, `DAT_c03239c0 = 100.0`.
Helpers: `FUN_c01f6f70` = log10; `FUN_c031fd98(x)=10^(x/20)`; `FUN_c031fdc8(x)=10^(−x/20)`
(blk_c03.c:21799 / 21815 — the `/20.0` and `/-20.0` are visible in the decomp).

`v8(param_1=G, param_2=&params)`, `params = {rel%, LCG_ref, HCG_ref, mode}`:

1. **Clamp relative gain** (:24511-24517):
   `local_6c = clamp(params[0], S+0x64 /*min*/, S+0x60 /*max*/)`. Store `G[6]=local_6c`.
2. **Conversion-gain decision** (:24519): `G.HCGflag = v30(G, local_6c, mode)` (→ §3b).
3. **Inter-node digital trim** (:24522): `FUN_c0320cd0(G,&local_6c,local_68,mode)` calls **v31**
   which (a) sets `local_68[0]` = digital-trim % and (b) **reduces `local_6c`** to the nearest
   lower analog node. `G[0xe]=local_68[0]` (→ §3c). (This is why the dB below uses the *reduced*
   `local_6c`.)
4. **Pick native reference analog code `uVar5`** (:24524-24550). Default `uVar5 = S+0xd0`. If
   `params[1]` (LCG) resp. `params[2]` (HCG, chosen by HCGflag) lies in `[S+0x58, S+0x54]`, use it.
   `params[1]/[2]` come from the per-mode config object `0xC3074950` (`piVar2[1]`=LCG_ref,
   `piVar2[0xf]`=HCG_ref, gated by `piVar2[0]==1`, blk_c03.c:14457-14472).
5. **dB composition** (:24553-24568):
   ```
   dB = −20·log10((4095 − uVar5)/4095)            # native reference analog-gain dB
        + 20·log10(local_6c / 100)                # requested relative-gain dB (base ISO100)
   if HCG:  dB −= *(double*)(S+0x7c)               # subtract HCG conversion-gain dB offset
   ```
   `log10(100.0)` is cached once in `_DAT_c343b578` (:24558, guarded init).
6. **Max-analog cap + digital overflow** (:24569-24583):
   ```
   maxAnalog = (double) S+0x68                     # dB cap (integer→double)
   digital   = (double) S+0x70                     # digital base (nominal 100)
   if maxAnalog < dB:                              # request exceeds analog headroom
        digital = digital · 10^((dB − maxAnalog)/20)
        dB      = maxAnalog                        # clamp analog dB at the cap
   G[0xc] = round(digital)                          # cap-overflow digital %
   G[0xb] = round(10^(dB/20) · 100)                 # linear analog gain ×100
   analog_code = round(4095 − 4095·10^(−dB/20))     # == round(4095·(1 − 1/linear_gain))
   ```
7. **Return abs_gain** (:24584): `return (G[0xc] << 16) | analog_code`.
   Bit layout: **`[15:0]=analog_code` (12-bit, ≤0xFFF), `[30:16]=digital %`**. CONFIRMED and it
   matches the unpack in `FUN_c0312f18` (`(x&0x7fff0000)>>16` and `x&0xffff`, :14304/14322).

**So the Sony analog-gain law is `linear = 4095/(4095 − code)` (12-bit, NOT 1024).** CONFIRMED by
both the compose (`4095·(1−1/linear)`) and the reference term `(4095−uVar5)/4095`.

Sanity: one stop = +6.0206 dB; 1/3 stop = +2.0069 dB = 341/1024 Sv. `code=0`→1.0×; `code=0xDFD`
(3581)→ 4095/514 = **7.966× = +18.03 dB** (≈ +3 stops over native); `code=0xFFF` is the asymptote.

---

## 3. The three gain layers, precisely

### 3a. Analog gain (CONFIRMED)
- **Register:** `v10` writes the 12-bit `analog_code` as low/high bytes to **0x3D (low 8b) / 0x3E
  (high 4b)**, then an identical copy to **0x3F / 0x40** (blk_c03.c:24652-24655). The two copies are
  the sensor's two per-frame gain contexts (long/short or the two CG readouts).
  ```
  FUN_c0322c70(0x3d, code & 0xff);   FUN_c0322c70(0x3e, (code & 0xfff) >> 8);
  FUN_c0322c70(0x3f, code & 0xff);   FUN_c0322c70(0x40, (code & 0xfff) >> 8);
  ```
- **`v7` @ c0323540 writes a DIFFERENT register 0x5C/0x5D** (blk_c03.c:24468). It is reached via
  vtable `+0x24`, and only from special/test routines with literal values 0x3FE/0x3FF/0xFFFF
  (blk_c03.c:14760, 15087-15095). **`v7`/0x5C-0x5D is NOT on the normal AE apply path** — the AE
  path is `FUN_c0312f18 → +0x2c=v9 → +0x30=v10 → 0x3D-0x40`. (This corrects the old note, which
  listed 0x5C/0x5D as the primary analog register.)
- **Cap:** analog dB is clamped to `S+0x68` (OTP-RUNTIME, §6). Above it, the surplus becomes ISP
  digital gain (step 6 above). The analog code is additionally bounded by the 12-bit field and by
  the reference-code window `[S+0x58, S+0x54]`.
- I2C writer `FUN_c0322c70(reg,val)` (blk_c03.c:24026): 16-bit reg + 8-bit data, big-endian reg
  bytes (`FUN_c0322cb0` :24040) — Sony sequential-write format.

### 3b. Conversion gain (dual-native ISO) — decision `v30` @ `0xC03239C8` (CONFIRMED)
```c
uVar2 = 0;                                        // default = LCG
if (S+0x78 != 0) {                                // CG feature enabled (OTP flag)
  if (mode == 0)          { if (S+0x84  < rel%) uVar2 = 1; }   // live view: OTP threshold S+0x84
  else if (mode<4 || mode-5<2) { if (FUN_c00b8860(0x280 /*640*/)  <= rel%) uVar2 = 1; }
  else if (mode-5 == 2)   { if (FUN_c00b8860(0xc80 /*3200*/) <= rel%) uVar2 = 1; }
  // mode 4 and mode>=8: NO HCG switch
}
if (G.byte_0x37 != 0) uVar2 = 0;                  // high_gain_off forces LCG
return uVar2;                                       // stored to G.HCGflag
```
- `rel%` numerically equals ISO, so the thresholds are literally **ISO 640** and **ISO 3200**
  (0x280/0xc80). `FUN_c00b8860` remaps the nominal % through the ROM analog-gain calibration curve
  (§6) — the threshold is compared in calibrated units.
- **Register writes (in `v10`, gated by `FUN_c03258b0()==0`, :24620):**
  | reg | LCG (HCGflag=0) | HCG (HCGflag=1) | meaning |
  |---|---|---|---|
  | **0x05E1** | 0 | 1 | FDG_SEL conversion-gain select |
  | 0x05A6 | 0x29 | 0x2A | black/bias trim |
  | 0x05A8 | 0x27 | 0x29 | black/bias trim |
  (blk_c03.c:24625-24634 low-analog branch; identical CG values in the high-analog branch
  :24638-24649.) HCG additionally subtracts `S+0x7c` dB in `v8` so the second native ISO becomes
  the new 0-dB reference.
- **Mode→native-switch map** (mode = gain_state 0-8, enum in §5):
  | gain_state | name | HCG switch point |
  |---|---|---|
  | 0 | through (live view) | OTP `S+0x84` (per-unit) |
  | 1,2,3 | acq / through_acq / movie | **ISO 640** |
  | 5,6 | movie_raw **8bit / 10bit** | **ISO 640** |
  | 7 | movie_raw **12bit** | **ISO 3200** |
  | 4 | movie_raw (generic) | **never** (stays LCG) |
  | 8 | digital_off | never |
  Low native is **ISO 100** for all (the base of the ladder). (CONFIRMED logic; the 4=generic-raw
  "never HCG" branch is a NEW finding vs the old note — see §9.)

### 3c. Digital gain — TWO contributions, both applied in the ISP (unity = 100)
1. **Inter-node trim** — `v31` @ `0xC0323A78` via `FUN_c0320cd0` (blk_c03.c:22365). Requires
   sensor-manager `+0x95 != 0`; if `+0x96 != 0` each node is remapped through `FUN_c00b8860` (OTP
   curve). It snaps `rel%` down to the nearest analog node and returns the residual as a small
   digital % (typically 100-125%), so every 1/3-stop ISO is exact even though analog gain is
   quantized. `FUN_c0320cd0` then pushes `(*digital% << 10)/100` (i.e. digital in 1/1024 units,
   1024 = 1.0×) into the AE digital-gain state `0xC320209C` via `FUN_c032f578` (:22377-22399),
   for one or two contexts depending on mode.
2. **Cap overflow** — `v8` step 6: only engages when requested `dB > S+0x68`. `digital = 100 ·
   10^((dB − maxAnalog)/20)`, carried in `abs_gain[30:16]`.
- **Apply / floor:** `FUN_c0312f18` extracts `[30:16]`, and `if (< 0x65) → 100` — i.e. **digital
  floored to 100 % = 1.0×** (blk_c03.c:14304-14307). It stores the digital state
  (`FUN_c0313340`) and pushes it to the ISP digital-gain object (`iVar2+0x38`, :14315-14322).
- **`AeDigitalGainBase::v0` @ `0xC020CC10`** (blk_c02.c:10845) is the unity(100) base provider.
- **`gain_state 8` (digital_off):** `v31` returns digital=100 (blk_c03.c:24976), and `v30` gives
  no HCG → pure analog. This is `imager set_gain_state 8`.

---

## 4. High-analog readout path (0x05E2 / 0x041F) — CONFIRMED

In `v10`, when the analog code `local_c >= 0xDFD` (3581 ≈ +18 dB ≈ ISO 800 above native), a
**different readout configuration** is selected (blk_c03.c:24636-24650):
```
FUN_c0322c70(0x5e2, 1);                       // high-analog readout enable
if (LCG) { 0x41f = 0x0E; 0x5a6=0x29; 0x5a8=0x27; 0x5e1=0; }
else     { 0x41f = 0x1D; 0x5a6=0x2a; 0x5a8=0x29; 0x5e1=1; }
```
Below 0xDFD it writes `0x41f=0, 0x5e2=0` and the normal CG trims (:24622-24634). This is an
**analog readout/bias mode change for high analog gain, orthogonal to the dual-native CG switch**
— it toggles on the analog *code* (0xDFD), not on the ISO 640/3200 CG thresholds, and it happens
inside both the LCG and HCG cases. Do not confuse the two. (CONFIRMED; matches the old note.)
Note `v10` skips the whole CG/high-analog block when `FUN_c03258b0()` (`DAT_c343b698`) is nonzero
— a register-update suppression latch (only the 0x3D-0x40 analog code is written then). Its setter
was not pinned down (open question).

---

## 5. Mode / bit-depth dependence

**gain_state enum (0-8)** — from the `set_gain_state` shell handler (blk_c03.c:168568-168610) and
the debug dumper (rawbit.c:1168-1210), both agree:

| value | name | role |
|---|---|---|
| 0 | through | live view |
| 1 | acq | still acquisition |
| 2 | through_acq | live→acq |
| 3 | movie | standard video |
| 4 | movie_raw | CinemaDNG raw, generic (INFERRED 14-bit / pre-bittype) |
| 5 | movie_raw_8bit | 8-bit CinemaDNG |
| 6 | movie_raw_10bit | 10-bit CinemaDNG |
| 7 | movie_raw_12bit | 12-bit CinemaDNG |
| 8 | digital_off | digital gain disabled |

The active value is read from `G[0x0c]` (or forced to **8** when the global override
`*(0xC343A78C+4) != 0`, via `FUN_c031a0f8`/`FUN_c031a170`, blk_c03.c:14458-14465). It is passed as
`mode` to both `v30` (CG switch point, §3b) and `v31` (digital ladder). Bit depth therefore steers
the dual-native point: **8/10-bit → 640, 12-bit → 3200, generic movie_raw → no HCG.** Bit-depth
selection lives in the `<rawbit>` / `cam_movie_raw_bittype` machinery (rawbit.c, `FUN_c02DA870`)
which resolves the capture into gain_state 5/6/7 (INFERRED mapping; the enum values are CONFIRMED).

**`v31` digital ladders** (nodes are relative-gain% = ISO; optionally OTP-remapped via
`FUN_c00b8860` when mgr `+0x96` set) — blk_c03.c:24698-25006:
- mode 0 (live): 2-point between mgr `+0x98`/`+0x9c`.
- modes 1,2: nodes 100,200,320,400,500,640,800,1000,1250 with a rise/dip trim profile (:24742-24811).
- modes 3,5,6: same node set, flatter profile (digital held at 100 across 100-200) (:24813-24883).
- mode 7 (12-bit): extended nodes 100,200,400,500,640,800,1600,2000,2500,3200,4000,4999 covering
  the wider LCG-to-3200 range (:24884-24975).
- mode 8: digital = 100 (:24976).
- else (4, ≥9): 2-point between mgr `+0xa0`/`+0xa4` (:24979-25003).

---

## 6. OTP calibration — `FUN_c03344b0` @ `0xC03344B0` (CONFIRMED path, values OTP-RUNTIME)

Reads the per-unit sensor blob from calibration flash: `FUN_c0355b98(dev, 0xC00, 0x1FE, buf)`
(offset **0xC00**, length **0x1FE=510 B**, blk_c03.c:35129), then deserializes fields sequentially
into `S` with width-specific readers (`FUN_c06ae6e8`/`_730`/`_7b8`). The gain-critical fields
(`S` = `G[0]`, exactly the struct `v8`/`v30` read):

| S offset | reader line | consumer | meaning | confidence |
|---|---|---|---|---|
| +0x64 | :35143 | v8 min clamp | minimum relative-gain% | OTP-RUNTIME |
| **+0x68** | :35145 | v8 :24569 | **max-analog dB cap** | OTP-RUNTIME |
| +0x6c | :35147 | :35295 (`S+0x222c = (+0x68!=+0x6c)`) | HCG-availability discriminant | OTP-RUNTIME |
| **+0x70** | :35149 | v8 :24570 | **digital base %** (nominal 100) | OTP-RUNTIME |
| +0x74 | :35151 | — | (paired w/ +0x70) | OTP-RUNTIME |
| **+0x78** | :35153 | v30 :24671 | **CG-enable flag** (0 ⇒ no dual native) | OTP-RUNTIME |
| **+0x7c** | :35155 | v8 :24567 | **HCG conversion-gain dB offset** (double) | OTP-RUNTIME |
| **+0x84** | :35157 | v30 :24673 | **live-view HCG threshold** (rel%) | OTP-RUNTIME |
| +0xd0/+0xd4 | :35197/35199 | v8 :24? ref default | default LCG/HCG reference analog code | OTP-RUNTIME |

`S+0x54/+0x58/+0x60` (the reference-code window and max-rel clamp used in v8) are **not** written by
this OTP reader; they are set by the per-mode setup (INFERRED). ROM contains no numeric defaults for
the +0x68/+0x70/+0x7c/+0x84 group — if the OTP read fails (`iVar3==0`, :35131) the fields simply
retain their ctor state and a fallback path (`FUN_c0334490`, :35296) writes 0xFFFF sentinels for
other fields. **Hence the exact dual-native dB, the analog/digital boundary, and the live-view
switch point can only be read from a live camera.** The `S+0x7c` type mismatch (stored 4-byte,
read as 8-byte double) suggests a post-read fixup or a decompiler width artifact (open question).

`FUN_c00b8860(x)` (blk_c00.c:143261) = `FUN_c00b8a38(curve, x)` = **piecewise-linear interpolation**
over a gain-linearization curve at `&DAT_c0746728` (**ROM**, model-level, blk_c00.c:143374-143404,
interp `FUN_c04d0a20`). It maps a nominal analog-gain% to the sensor's actual gain%. This curve is
in ROM (not per-unit); the per-unit part is the `S`-struct scalars above.

---

## 7. The ISO ladder — table @ `0xC0912454` (CONFIRMED, dumped)

43 `{Sv, ISO}` int32 pairs, stride 8. `Sv = round(1024·log2(ISO/3.125))` via `FUN_c04d01f8`
(blk_c04.c:157197; constants dumped: 1/3.125=0.32, ×1024, clamp 20480=20 stops). Full dump matches
byte-for-byte:

```
 #  Sv    ISO      #  Sv     ISO      #  Sv     ISO
 1  964    6       16 6144   200      31 11264  6400
 2  1389   8       17 6474   250      32 11594  8000
 3  1718   10      18 6838   320      33 11923  10000
 4  1988   12      19 7168   400      34 12288  12800
 5  2413   16      20 7498   500      35 12618  16000
 6  2742   20      21 7862  [640]     36 12947  20000
 7  3072   25      22 8192   800      37 13312  25600
 8  3437   32      23 8522   1000     38 13642  32000
 9  3766   40      24 8851   1250     39 13971  40000
10  4096   50      25 9216   1600     40 14336  51200
11  4461   64      26 9546   2000     41 14666  64000
12  4790   80      27 9875   2500     42 14995  80000
13  5120 [100]     28 10240 [3200]    43 15360 [102400]
14  5450   125     29 10570  4000
15  5814   160     30 10899  5000
```
- **Base native ISO 100** (Sv 5120). **ISO 6-80 (rows 1-12) are extended-low / pull** (below native;
  realized by holding analog at minimum and/or negative offset — no analog headroom exists below
  native, so these are effectively pull/digital-reduction points). INFERRED from the ladder shape.
- **Node ISOs** where `v31` places analog anchors (stills/std video): **100, 200, 320, 400, 500,
  640, 800, 1000, 1250** (from the v31 node list). **640 = the LCG→HCG conversion-gain node**;
  **3200 = the 12-bit HCG node.**
- **Clean vs digital:** an ISO is "analog+CG only" iff its requested dB lands ≤ `S+0x68` for the
  active CG *and* it coincides with an analog node. The 1/3-stop steps *between* nodes always carry
  a small `v31` inter-node digital trim (≈ +2-4%). So the truly digital-free ISOs are the node
  values (100/200/320/400/500/640/800/1000/1250 and, in 12-bit, up to 3200) and the two native
  points; everything else (and everything above the `S+0x68` cap) carries ISP digital gain.
  **The exact top of the analog range = ISO at which dB hits `S+0x68` — OTP-RUNTIME, needs a dump.**

**Second table @ `0xC0912318`** = `{gain%, APEX-step}` pairs (100→341, 110→683, 120→1024, …;
step = n·341 = 1/3-stop in the 1024=1-stop scale). It is the **gain% ↔ 1/3-stop APEX quantizer**
(snaps display/AE gain to thirds), NOT a sensor-gain table. (CONFIRMED role by the arithmetic;
corrects the "role undetermined" note.)

---

## 8. Edge cases & control hooks (CONFIRMED)

- **`imager high_gain_off 1`** → `FUN_c0320ca0` sets `G.byte_0x37 = 1` (blk_c03.c:22354); `v30`
  then forces LCG regardless of ISO (:24687). Strings "high gain force off" / "high gain ctrl
  normal", flag `[0:default 1:force_off]`.
  **No-argument form also writes 0**, per `FUN_c03ec210`; it is not a getter/help-only call.
- **`imager set_gain_state <0-8>`** → sets the readout mode; **8 = digital_off** (v31→100, no HCG).
  Handler blk_c03.c:168568; flags help text `[0 default_through / 1 acq / … / 4 movie_raw_5 … /
  8 digital_gain_off]`.
- **`check_convert_abs_gain`** (`FUN_c03ec308`) is a state-changing diagnostic, with argument order
  `<interval> <end> <start> <relative-or-ISO:0-or-1> [file-number]`. With arguments it pauses normal
  scheduling and calls `FUN_c030c878(...,gain,1)` for each sample, applying actual sensor/ISP gain.
  It saves/restores the sensor **mode ID** via `FUN_c030ce00` and waits for reconfiguration; it does
  not save the original gain. Mode setup uses the helper's current gain, which the sweep changed,
  so full original-exposure restoration is not guaranteed. No-argument form only prints usage.
  ISO mode calibrates input via `FUN_c00b8860` and converts back for printing via `FUN_c00b8840`;
  the ROM anchors are ×1.17, so nominal ISO and calibrated relative gain do not coincide at ISO100.
- **Direct `i2c w 0x05E1 <0|1>`** forces the FDG_SEL conversion-gain bit at the register level,
  bypassing `v30` (until the next `v10` write overwrites it).
- **Clamps/minima:** rel% clamped to `[S+0x64, S+0x60]` (v8 :24511); digital floored to 100
  (FUN_c0312f18 :14306); analog dB clamped to `S+0x68`; analog code is 12-bit; `v7` guards
  `param_2 < 0xFFFF` (:24467).

---

## 9. Corrections / refinements to `notes/research/imx410/ISO_HANDLING.md`

1. **`FUN_c0312f18` is the abs_gain APPLIER/DECODER, not the packer.** It splits abs_gain, floors
   digital to 100, pushes digital to the ISP, and calls `v9→v10` to write the sensor. The **packer
   is `v8`** (`digital<<16 | analog_code`, :24584). (Old note called `FUN_c0312f18` the packing fn.)
2. **Primary analog register is 0x3D/0x3E (mirror 0x3F/0x40), written by `v10`** on the AE path.
   **`v7`/0x5C-0x5D is a secondary/test path**, not the normal apply route. (Old note had 0x5C/0x5D
   primary and 0x3D-0x40 "another path".)
3. **Dispatch is via `v9` (vtable +0x2c) → `v10` (+0x30)**, not directly to `v7`. And the CG
   decision/digital ladder are reached at vtable `+0x80 (v30)` / `+0x84 (v31)` off the object's
   `+0xd0` port pointer (= `0xC0B5FCC0`). (Adds the exact dispatch offsets.)
4. **gain_state 4 (generic `movie_raw`) never switches to HCG**; only 1,2,3,5,6 use 640 and only 7
   uses 3200; 0 uses OTP `S+0x84`. (Old note said "everything else 640" — the 4/8 exclusions and
   the 5/6-vs-7 split are made explicit here.)
5. **Two distinct digital-gain contributions** (v31 inter-node trim + v8 cap-overflow), both ISP,
   both floored at 100 — the old note only described the cap-overflow one.
6. **`S+0x78` is the CG-enable master flag**; if 0, no dual-native at all. (Not previously noted.)
7. **OTP blob is offset 0xC00, len 0x1FE**; field offsets pinned (+0x64/+0x68/+0x6c/+0x70/+0x74/
   +0x78/+0x7c/+0x84/+0xd0/+0xd4). (Old note had the reader call but not the field map.)
8. **Second table `0xC0912318` = gain%↔1/3-stop APEX quantizer** (role identified).
9. Everything else in `ISO_HANDLING.md` (dual-native concept, 640/3200, dB formula, 4095 law,
   43-entry ladder, Sv formula, high-analog 0xDFD path, `high_gain_off`, per-unit OTP) is
   **CONFIRMED correct**.

---

## 10. Open questions / needs a live OTP dump

- **Numeric per-unit values (OTP-RUNTIME):** `S+0x68` max-analog dB cap, `S+0x70` digital base
  (expected 100), `S+0x7c` HCG dB offset, `S+0x84` live-view HCG threshold, `S+0xd0/+0xd4` default
  reference codes, `S+0x64` min rel%. These finalize (a) the exact ISO at which ISP digital gain
  first engages, (b) the precise second-native gain, (c) the live-view switch ISO. Dump sensor
  calibration flash offset **0xC00**, 510 bytes, and deserialize per `FUN_c03344b0`.
- **`S+0x7c` storage width:** OTP writes 4 bytes but `v8` reads an 8-byte double — is there a
  post-read fixup (packing +0x7c/+0x80) or is it a decompiler artifact? Resolve on a live struct.
- **`S+0x54/+0x58/+0x60`** (reference-code window + max-rel clamp) source — which per-mode setup
  writes them; are they mode config (ROM tables) or derived?
- **`FUN_c03258b0` / `DAT_c343b698`** register-update suppression latch — exact setter and the
  live-view condition under which `v10` skips CG writes.
- **gain_state 4 (`movie_raw`) exact bit depth** and whether it is user-reachable (vs an internal
  pre-bittype state) — confirm on hardware which CinemaDNG bit depth maps to gain_state 4 vs 5/6/7.
- **Native reference codes `piVar2[1]/[0xf]`** (object `0xC3074950`) per readout mode — dump to see
  the actual LCG/HCG native analog codes the sensor is anchored to.
