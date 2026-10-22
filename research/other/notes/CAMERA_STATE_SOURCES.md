# SIGMA fp Ver.5.02 — Live Camera-State Sources for the USB Shell

Inventory of firmware memory/function sources for reading live camera state over the new USB shell
(`mem read <addr> <len>` primitive + allowlisted accessor-call ops). fp Ver.5.02, base `0xC0000000`,
`file_off = addr − 0xC0000000`. Every row cites prior RE notes; CONFIRMED = read from decomp/firmware
bytes, INFERRED = deduced, OTP-RUNTIME = code path confirmed but the number lives in per-unit flash.

> Two verifications done here (2026-08-19, capstone on `MAIN_c0000000.bin`): focus getter/driver/range
> function prologues, and the `FUN_c035ffc0` call-site arg setup. Everything else is cited from notes.

---

## Address-space legend & safety

| Space | Range | Nature | Raw-read over shell? |
|---|---|---|---|
| **FW code/rodata** | `0xC0000000–0xC0FFFFFF` | main-ARM ROM image | YES (always mapped) |
| **main-ARM RAM** | `0xC2xxxxxx / 0xC3xxxxxx` | heap/BSS/DRAM (state structs) | YES **only for addresses the firmware itself dereferences** — see trap below |
| **sub-ARM shared RAM** | `0x2E000000…` | OIS coprocessor RAM (gyro ring) | YES via mapped window (proven: `mem save 0x2E006000` worked) — distinct space |
| **raw DRAM framebuffer** | `0x50000000…` | sensor Bayer DMA target | YES (proven: `mem save 0x50000000`) — large blocks |
| **MMIO** | `0x30xxxxxx / 0x2x / 0x40xx` | AF/metering/sensor-timing regs | Read with care (side-effect risk); word-granular |
| **I2C sensor regs** | `0x3D, 0x05E1, …` | Sony IMX410 registers | **NOT memory** — only via `i2c r`, never `mem read` |

⚠️ **Unmapped-hole trap (GYRO_IMU_GYROFLOW.md "教訓"):** blind reads of `0xC31C0000–0xC31F0000`
**froze the camera** (unmapped addresses inside the C3 region). Rule: only read addresses reached by a
pointer the firmware derefs, or confirmed-live BSS. The read-interval table below is deliberately narrow.

---

## Master table

| # | Item | Address / getter | Space | Raw-read vs Call | Format | Conf | Source note |
|---|---|---|---|---|---|---|---|
| 1 | Gyro ring (3-axis) | ptr cell `0xC31E3FCC` → `P=0x2E006004`; `ring_base=*(P+0x60)=0x2E00644C`; ODR word `*(P+0x64)` | sub-ARM `0x2E…` (ptr cell is main-ARM) | **Raw** (2-step deref) or accessor `FUN_c01ec6f8` | ring: u32 head @base, then 600× `{i16 X,i16 Y,i16 pad=0,i16 Z}` LE, 8B/sample; `dps=raw/131` | CONFIRMED | GYRO_IMU_GYROFLOW / ARCHIVE |
| 1b | Accel (level) latest | `0xC377790C / …0E / …10` | main-ARM RAM | Raw | 3× i16, `g=raw/1024`, ~100Hz | CONFIRMED | GYRO archive |
| 1c | Body-motion flag | `FUN_c00d0800(obj=0xC31CC42C)` → `[+0x1c]||[+0x1d]` | main-ARM (obj) | Call (or raw the 2 bytes) | bool; gyro-thread sets it | CONFIRMED | AF_AE_INTERNALS ⑧ |
| 2 | IMX410 sensor/gain object | **`0xC343B588`** (getter/ctor `FUN_c03255f8`; vtable `+0xD0=0xC0B5FCC0`) | main-ARM RAM | **Raw only** | see §2; relative gain, analog code/ratio, digital, HCG | CONFIRMED static + LIVE | ISO_FIRMWARE_COMPLETE corrected; AF-fusion 2026-09-16 |
| 2a | RGB/digital-gain helper (not IMX410) | `0xC343A6A0` (getter `FUN_c0312ee0`, ctor `FUN_c0312e98`) | main-ARM RAM | Raw | helper state; do not apply IMX410 offsets | CONFIRMED static + LIVE disambiguation | AF-fusion 2026-09-16 |
| 2b | Sensor CG latch `0x05E1`, analog `0x3D/0x3E` | I2C regs (mirrored in corrected IMX410 object) | I2C space | Needs reviewed imager accessor; generic `i2c` has no imager device | 0x05E1: 0=LCG/1=HCG; 0x3D/3E: 12-bit analog code | CONFIRMED static; object mirror LIVE | ISO_FIRMWARE_COMPLETE §3; AF-fusion 2026-09-16 |
| 2c | AF-side AGC/ISO copies | `0xC32915B4` RGBgain, `0xC3291694` sens_af, `0xC329169C` af_shutter | main-ARM RAM | Raw | u32; RGBgain live: ISO100=117, ISO800=936 (linear ×8); other encodings open | CONFIRMED static + LIVE A/B | AF_AE_INTERNALS; AF-fusion 2026-09-16 |
| 3 | Raw/Bayer frame buffer | base `0x50000000`; LV ring `0x50000000 + idx·0x100000` (1MB/frame) | raw DRAM | **Raw** (scan for non-zero) | Bayer RGGB, bit per `smallraw_bit` {0:12,1:14,2:16,3:10,4:8}, endian per setting; full still 6000×4000 | CONFIRMED base, ptr-cell not pinned | RAW_GRAB / HDMI_RAW |
| 3b | Debug-out enable mask | `0xC343A624` bit2 (still_raw_dump) | main-ARM RAM | Raw/set | bitmask; UART prints `raw_addr %08x` | CONFIRMED | RAW_GRAB |
| 4 | Focus position (current abs) | **`FUN_c035fd48()`** (r0=none) | — | **Call** (zero-arg getter) | int, absolute lens position domain | CONFIRMED | FOCUS_POSITION_DOMAIN |
| 4b | Focus range min/max | `FUN_c02dffb0()` / `FUN_c02dffd0()` | — | Call | int/int, same domain | CONFIRMED | FOCUS_POSITION_DOMAIN |
| 4c | **Focus DRIVE (control)** | **`FUN_c035ffc0(r0=target_abs, r1=0, r2=0)`** | — | **Call (control op)** | drive to absolute target; clamp to [min,max] yourself | CONFIRMED sig (this note) | FOCUS_POSITION_DOMAIN |
| 4d | Focus drive (mode-gated) | `FUN_c04ef7d0(target)` — requires mode==2 (LiveView) | — | Call | rejects if not LV / AF busy | CONFIRMED | PTP_FOCUS |
| 5 | AF-model singleton (AF state) | **`0xC3404678`**, vtable `0xC092B8D0`; body-motion result at `+0x04` | main-ARM RAM | Raw (fixed) | `this[1]` = body-motion predicate result | CONFIRMED | AF_AE_INTERNALS ⑧ |
| 5b | CAF sequencer state (0/1/6) | AF-thread obj `*param_1` (heap; via `FUN_c028c620`) | main-ARM heap | **Needs deref chain** (not fixed) | 0=idle,1=acquiring,6=Rocking-servo | CONFIRMED semantics, addr not pinned | AF_AE_INTERNALS ⑧ |
| 5c | Drift-monitor `M` | **`0xC33D1958`** (`FUN_c028a360`); grid `M+0x0`, det-rects `M+0x220`, timers `M+0x21c` | main-ARM RAM | Raw | see §5 | CONFIRMED | FACE_EYE_AF ⑧ |
| 6 | Face/eye detection results | **DetectionResultMgr `0xC37CCA9C`**; face groups at `+0x10`, stride `0x9C` (3×0x34) | main-ARM RAM | **Raw** (fixed) | see §6 layout; up to 5 faces | CONFIRMED | FACE_EYE_AF ② |
| 6b | AF-facing output rect | `0xC37CCA9C + 0x3E0` xs / `+0x3E4` ys / `+0x3E8` w / `+0x3EC` h; mode `+0x3D0` | main-ARM RAM | Raw | i16/i32 rect; mode 1=track/2=lost/3=stop | CONFIRMED | FACE_EYE_AF ④ |
| 6c | FD/eye work buffers | FD_WORK `0xC37CD754` (0x38400), state mgr fields `+0x334`/`+0x3D0` | main-ARM RAM | Raw | status 0/1/2/3 | CONFIRMED | FACE_EYE_AF ① |
| 7 | AAT tracking box (current) | **`0xC3033E00` {x,y,w,h}**; quality/lock at `0xC3033E26` (>19 = locked) | main-ARM RAM | **Raw** (fixed) | i16 x,y,w,h; conf byte | CONFIRMED | AF_AE_INTERNALS ⑧ Q1 |
| 7b | AAT model / adaptive color | `_DAT_c37cdfa8` (0x2c bytes): semi-axes `+4/+6`, conf `+0xc`, ref YCbCr `+0x14/15/16` | main-ARM RAM | Raw (deref `_DAT_c37cdfa8`) | see FACE_EYE ④ | CONFIRMED | FACE_EYE_AF ④ |
| 7c | AAT_WORK | `0xC37CD3A0` (0x25800) | main-ARM RAM | Raw | tracker scratch | CONFIRMED | FACE_EYE_AF ① |
| 8 | AF contrast (live CDAF) | HIGH band `0xC32985E8[]`, LOW `0xC32986B4[]` (indexed by `_DAT_c3291534`) | main-ARM RAM | **Raw** | i32 contrast (span), magnitude ~1e4 | CONFIRMED | AF_AE_INTERNALS §②/⑦ |
| 8b | Peak search intermediates | target/g_afpos `0xC32914E0`; peak now/max/min `0xC32915C4/C8/CC`; step-state `0xC3291518`; peak-idx `0xC32915F2`; area0-ref `0xC32914FC` | main-ARM RAM | Raw | i32 (encoder-pulse & contrast domain) | CONFIRMED | AF_AE_INTERNALS §⑦/⑩ |
| 8c | Motor-position-at-exposure sweep history | `0xC3291958` (mposm, lag-compensated); current sweep-sample index `0xC329153C` | main-ARM RAM | Raw | up to 1000× i32 pulses; stale while idle | CONFIRMED static + LIVE idle | AF_AE_INTERNALS ⑥; `AfMgrProcessFast::v5`; AF-fusion 2026-09-16 |
| 8d | Coarse-sweep waypoints | `0xC32020E4 / …E8`; count `DAT_c2f172d4` (≤30) | main-ARM RAM | Raw | i32[] positions | CONFIRMED | AF_AE_INTERNALS ⑩ Q6 |
| 8e | Peak-history ring (AF-C predict) | `0xC33D0384`, 10 slots; idx `_DAT_c33d510c` | main-ARM RAM | Raw | `{+0x08 area,+0x0c mode,+0x10 dir,+0x14 time,+0x18 pos,+0x1c dist}` | CONFIRMED | AF_AE_INTERNALS ⑤ / FACE_EYE ⑧ |
| — | Capture-state singleton | `0xC3033834`; `+0x220` capture-state, `+0x7c` | main-ARM RAM | Raw | u16 state; Live View idle observed as 1 while MovieRecording=false, so do not label 0/1 generically | STATIC gate + LIVE value | PTP_FOCUS; AF-fusion 2026-09-16 |
| — | MovieRecording flag | `FUN_c035b2d0()` → obj `0xC347DF38`, byte `+0x157` | main-ARM RAM | Call or raw byte | bool | CONFIRMED | GYRO archive |
| — | Monotonic µs tick | `FUN_c002b6e0()` | — | Call | u32 µs, wraps ~71.6min | CONFIRMED | GYRO archive |

---

## §1 Gyro ring detail

Pointer chain (all CONFIRMED on-camera, GYRO_IMU_GYROFLOW):
```
0xC31E3FCC (main-ARM cell)  →  P = 0x2E006004        (sub-ARM shared RAM)
ring_base = *(P+0x60) = *(0x2E006064) = 0x2E00644C
ring_end  = 0x2E007710   (span 0x12C4 = u32 head + 600×8B payload)
ODR word  = *(P+0x64) = 2500  (≈2500 Hz, 400 µs/sample)
samples start at ring_base+4 = 0x2E006450
```
Sample: `struct { int16 x, y, padding(=0), z; }` LE, 8 bytes. `dps = raw_i16 / 131`. Latest sample =
the one just before the head/write pointer (`*ring_base`). **Raw-readable** through the mapped sub-ARM
window (never blind-scan 0xC31Cxxxx). Cal block at `0xC307B548` (0x244 B). Body-motion detector obj
`0xC31CC42C` (the AF "10-element decision ring" — do NOT confuse with the real 600-sample gyro ring).

## §2 IMX410 gain state — corrected live object `0xC343B588`

The actual `XC_ImageSensorIMX410` singleton is constructed by `FUN_c03255f8` at `0xC343B588`.
Its live vtable word at `+0xD0` is `0xC0B5FCC0`, matching the statically resolved IMX410 dispatch.
At ISO 12800, its first 0x40 bytes were:

```text
C2F1E654 00000008 00000008 00000034 00000034 00000034 00003A80 00003A80
00000F00 00000F00 00000F00 00000646 00000064 00010101 000000C8 0000410F
```

Fields jointly pinned by `XC_ImageSensorIMX410::v8/v10/v30`, the live dump, and the built-in converter:

| Abs addr | Object offset | Live ISO12800 | Meaning |
|---|---:|---:|---|
| `0xC343B5A0` | +0x18 | 14976 | clamped relative gain; equals `mode_now gain` and AF RGBgain |
| `0xC343B5A8` | +0x20 | 3840 (`0xF00`) | applied 12-bit sensor analog code |
| `0xC343B5B4` | +0x2C | 1606 | linear analog ratio ×100 |
| `0xC343B5B8` | +0x30 | 100 | overflow digital gain ×100; 100=unity |
| `0xC343B5BC` | +0x34 byte | 1 | HCG decision, 0=LCG / 1=HCG |
| `0xC343B5C0` | +0x38 | 200 | inter-node digital trim ×100 |

The v5 return-to-ISO100 capture (`2026-09-16-iso100-v5`, 60/60 coherent records, sequence 0–59)
confirmed `relative_gain=117`, `analog_code=985`, `analog_ratio_x100=131`, and HCG byte 0.
A separate 64-byte object read also confirmed overflow digital=100, trim=100, and force-LCG byte=0.
These are live RAM observations from the firmware's sensor object; the physical I2C latch has not been
read directly.

### Corrected identity of `0xC343A6A0`

The older static map confused two classes. `FUN_c0312ee0` returns `0xC343A6A0`, but its ctor
`FUN_c0312e98` builds a smaller RGB/digital-gain helper; it is not the `param_1` passed to IMX410 v8.
A 2026-09-16 idle-Live-View probe read
the 16 words at `0xC343A6A0..DF` as:

```text
00000075 FFFFFFFF 00000000 00000000 FFFFFFFF 00000001 00000001 00000000
00000000 00000000 00000400 00000000 0003F4D0 00000000 00000008 00000001
```

A fixed-setting A/B then pinned the useful AF-side copy without rescuing the old G labels:

```text
setting   0xC32915B4 RGBgain   0xC3291694 sens_af   af_shutter   af_fno   G +0c/+18/+2c/+34
ISO 100          117                    219             8333       2164   0 / 1 / 0 / 0
ISO 800          936                    219             8333       2164   0 / 1 / 0 / 0
```

`936 / 117 = 8`, exactly matching the requested ISO ratio. Therefore `0xC32915B4` is confirmed as a
linear ISO/gain scale used by the AF pipeline; two points support `ISO ≈ raw × 100/117`. Do not yet call
117 a percent, APEX value, or sensor analog code: rounding and the LCG/HCG transition need more ISO points.
`sens_af` did not encode the selected ISO in this test. The four G offsets remained unchanged and remain
unmapped.

While ISO 800 was held, read-only `imager mode_now` reported mode 53 `MONIT1_60`, enum 8,
2016×1344 12-bit 60 fps full 3:2, `gain_state: through`, and `gain:936`. The exact match confirms
`0xC32915B4` is the imager's active gain-domain value. It reported sensor shutter 16663 µs while
`0xC329169C` remained 8333, so the AF-side shutter copy is not the literal main sensor exposure time in
this mode.

The generic `i2c` shell exposes no imager device, so it could not read `0x05E1` directly. The firmware's
`imager check_convert_abs_gain` under the then-current `through` state returned ISO800
`analog=3317,digital=100,high=0`, and bracketed a `high=0→1` transition between displayed ISO10939
and ISO10949. This is a diagnostic-session bracket, subject to gain mode/calibration/rounding, not a
universal Live View threshold or direct sensor-latch reading. Subsequent independent v5 captures
confirmed runtime HCG flag 1 at ISO12800 and 0 after the user's return to ISO100.

**Correction: these diagnostic commands mutate state.** `check_convert_abs_gain` (`FUN_c03ec308`)
calls the actual gain setter for each sample. It saves/restores the sensor mode and waits for mode
reconfiguration; it does not save the original gain, so complete exposure restoration is not guaranteed.
`high_gain_off` (`FUN_c03ec210`) with no argument writes force-LCG=0; its "normal" output does not
establish the previous value. Do not use either command for read-only monitoring. The original
force-LCG value before that prior command was not captured. Current direct RAM confirms it is 0.
Use the RAM addresses above and the separately reviewed `mode_now` information handler instead.

ROM descriptor `0xC0746728` points to 11 ISO calibration anchors, all nominal ISO ×1.17. This supports
the observed gain values 117/936/14976 and distinguishes selected ISO from calibrated relative gain.

In particular, the helper's `+0x18=1` is not a literal ISO and `+0x2C=0` is not the IMX410 analog ratio;
its first word is `0x75`, not a config pointer. Historical binary record v1 therefore exposes these only as
`legacy_gain_helper_raw`. Record v2/schema v5 reads the corrected `0xC343B588` object.

The following is retained as the **superseded wrong-object hypothesis**, not a live IMX410 map:

| Abs addr | Field | Meaning |
|---|---|---|
| `0xC343A6A0` | G[0] | ptr → OTP config/cal struct `S` |
| `0xC343A6AC` | byte 0x0c | **current gain_state / readout mode 0–8** (0 through / 4 movie_raw / 5-7 raw 8/10/12-bit / 8 digital-off) |
| `0xC343A6B8` | G[6] | last relative-gain% (**== ISO**, base 100) |
| `0xC343A6CC` | G[0xb] | linear analog gain ×100 |
| `0xC343A6D0` | G[0xc] | cap-overflow digital gain % |
| `0xC343A6D4` | byte 0x34 | **HCG flag** (1=HCG / 0=LCG) — the dual-native ISO state |
| `0xC343A6D7` | byte 0x37 | high_gain_off (force-LCG) |
| `0xC343A6D8` | G[0xe] | inter-node digital-trim % |

Sensor-side latches are CG select `0x05E1`, analog code `0x3D/0x3E` (+mirror `0x3F/0x40`), and
high-analog `0x05E2/0x041F`. They are I2C register addresses, not memory addresses; the generic shell's
`i2c list` does not expose an imager device, so direct live reads need a reviewed imager accessor. The
object fields above are already sufficient to observe the firmware-applied code and HCG decision.

## §5 AF state

- **AF-model singleton `0xC3404678`** (fixed, vtable `0xC092B8D0`). `this[1]` (`+0x04`) = latest
  body-motion predicate result (nonzero → AF-C wants Rocking servo). Raw-readable.
- **CAF sequencer state** (0=idle / 1=acquiring / 6=Rocking-servo) lives in the AF-thread object at
  `*param_1`, a heap object obtained via `FUN_c022bb00` (identity) inside `FUN_c028c620`; the ctx is
  passed by register, **not a fixed DAT** — needs a pointer-chain deref to pin. Live probe: dump the AF
  thread struct once found, or expose a small accessor. Not raw-pinned yet → **needs more RE**.
- **Drift monitor `M = 0xC33D1958`**: 16×16 luma grid at `M+0x0` (from AE buf `0xC3201B14+4`),
  detection-rect list `M+0x220` (256×16B), AF-eval drift% `M+0x20c`, timer base `M+0x21c`.

## §6 Face/eye result layout (DetectionResultMgr `0xC37CCA9C`, FACE_EYE_AF ②)

Up to 5 faces, each a `0x9C` group = `[face 0x34 | eyeA 0x34 | eyeB 0x34]`, base `+0x10`, stride `0x9C`.
Each `0x34` sub-record: `+0x10 X(top-left)`, `+0x14 Y`, `+0x18 W`, `+0x1C H` (square pre-aspect),
`+0x20 angle`, `+0x28 score`, `+0x30 valid(byte)`; group `+0x34 tracking-ID`, `+0x3C count-flag`.
Coordinate space = **320×213**, origin top-left (scaler picks 1620×1080 / 640×426 / 320×213). AF-facing
consolidated rect at `+0x3E0..+0x3EC`, mode `+0x3D0` (1 track / 2 lost-predict / 3 stop). Raw ISP record
(pre-parse) is `0x20`B: `+0x08 cx, +0x0C cy, +0x10 size, +0x14 score, +0x18 angle, +0x1C track-ID`.

## §8 AF calculation intermediates (all fixed main-ARM globals, raw-readable)

`0xC32985E8[]` HIGH-band contrast, `0xC32986B4[]` LOW-band (the `saf_jdat_h/l` sources; ctx copies these
into `ctx+0x21c0/+0x21c4` as span = value−scanmin). Index `_DAT_c3291534`. Peak now/max/min at
`0xC32915C4 / C8 / CC` (also `…D0`). Drive target / g_afpos accumulator `0xC32914E0`. Step-state
(highest=8/high=6/mid=4/middle=0/low=1) `0xC3291518`. Peak argmax index `0xC32915F2`. Area0 reference
peak `0xC32914FC` (~25000 strong-judge ref). mposm (exposure-center motor pos) `0xC3291958[]`, current
sweep-sample index `0xC329153C`. This index is distinct from H/L area index `0xC3291534`:
`AfMgrProcessFast::v5 @ 0xC025CD30` writes `mposm[uVar9]`, then `_DAT_c329153c = uVar9`.
Coarse-sweep waypoints `0xC32020E4/E8` (count `DAT_c2f172d4`, 28mm→30). AF-C peak-history ring
`0xC33D0384` (10×0x20).

---

## Proposed READ-INTERVAL table (named, safe, raw-readable now)

Narrow windows over addresses the firmware derefs / live BSS. Names for the shell allowlist:

| Name | Start | Len | Contains |
|---|---|---|---|
| `GYRO_PTRCELL` | `0xC31E3FCC` | `0x08` | mailbox ptr P + descriptor ptr |
| `GYRO_CAL` | `0xC307B548` | `0x244` | gyro/accel offsets + axis remap |
| `GYRO_RING_WIN` | `0x2E006000` | `0x1800` | P block + full 600-sample ring (sub-ARM) |
| `ACCEL_LATEST` | `0xC3777908` | `0x0C` | 3-axis accel cache |
| `IMX410_GAIN` | `0xC343B588` | `0xE0` | sensor object, gain fields +0x18/+0x20/+0x2C/+0x30/+0x34/+0x38 and vtable +0xD0 |
| `RGB_GAIN_HELPER` | `0xC343A6A0` | `0x40` | separate helper; retained only for digital/RGB pipeline research |
| `AF_MODEL` | `0xC3404674` | `0x10` | AF-model singleton head + body-motion flag |
| `AF_CONTRAST_HI` | `0xC32985E8` | `0x100` | HIGH-band contrast array |
| `AF_CONTRAST_LO` | `0xC32986B4` | `0x100` | LOW-band contrast array |
| `AF_PEAK_STATE` | `0xC32914E0` | `0x140` | target, peak now/max/min, step-state, argmax, area0-ref |
| `AF_MPOSM` | `0xC3291958` | `0xFA0` | up to 1000 exposure-center sweep-history positions; sample index `0xC329153C`, stale while idle |
| `AF_WAYPOINTS` | `0xC32020E0` | `0x100` | coarse-sweep waypoint arrays |
| `AF_PEAK_RING` | `0xC33D0384` | `0x150` | 10-slot AF-C peak history |
| `AF_DRIFT_MON` | `0xC33D1958` | `0x400` | drift-monitor grid/rects/timers (verify extent live) |
| `DET_RESULT_MGR` | `0xC37CCA9C` | `0x400` | face/eye groups + AF-facing rect + mode |
| `AAT_BOX` | `0xC3033E00` | `0x30` | current tracking box + confidence |
| `CAPTURE_STATE` | `0xC3033834` | `0x240` | capture-state (`+0x220`) etc. |
| `RAW_FB_PROBE` | `0x50000000` | `0x100000` | one LV small-raw frame (scan ring for the live one) |

**Deferred/needs live confirmation** (do NOT add until a probe proves them mapped & correct):
`AAT_MODEL` (`*_DAT_c37cdfa8` — deref first), `FD_WORK 0xC37CD754` size 0x38400 (large; confirm base),
raw-frame **pointer cell** (currently only UART-printed — probe `0x50000000` block boundaries live).

## Proposed ACCESSOR ALLOWLIST (reviewed call-ops, verified signatures)

Zero-/low-arg, side-effect-characterized firmware functions to expose as named call-ops. Signatures
verified by disassembly here unless noted.

| Name | Addr | Signature | Returns | Side effects | Conf |
|---|---|---|---|---|---|
| `focus_get_pos` | `0xC035FD48` | `()` | int abs position | none (getter) | CONFIRMED |
| `focus_get_min` | `0xC02DFFB0` | `()` | int | none | CONFIRMED |
| `focus_get_max` | `0xC02DFFD0` | `()` | int | none | CONFIRMED |
| `lens_scale` | `0xC035FEC8` | `(int sel=3)` | int scale | none | CONFIRMED |
| `bodymotion_flag` | `0xC00D0800` | `(obj=0xC31CC42C)` | bool | none | CONFIRMED |
| `movierec_flag` | `0xC035B2D0` | `()` | obj (read `+0x157`) | none | CONFIRMED |
| `tick_us` | `0xC002B6E0` | `()` | u32 µs | none | CONFIRMED |
| **`focus_drive_abs`** ⚠ | `0xC035FFC0` | `(r0=target_abs, r1=0, r2=0)` | — | **MOVES LENS** — clamp to [min,max] first | sig CONFIRMED, r1/r2 semantics INFERRED(=0 in the 0x9411 path) |
| `focus_drive_gated` | `0xC04EF7D0` | `(target)` | PTP rc | moves lens, rejects if not LiveView/AF-busy; safer | CONFIRMED |

Control ops (`focus_drive_*`) must be behind an explicit `--region control` capability + the host lease-lock
(per fp-task-abi-cracked safety contract). Prefer `focus_drive_gated` (self-gates on capture-state) for
first bring-up; use `focus_drive_abs` only after confirming r1/r2=0 is safe on a live lens.

---

## Summary

**Raw-readable NOW (fixed addresses, no call needed)** — the bulk of the ask:
- Gyro ring (2-step deref via `0xC31E3FCC`→sub-ARM), accel cache.
- IMX410 singleton `0xC343B588`: live-confirmed relative gain, applied analog code/ratio, overflow digital,
  HCG and inter-node trim fields. AF-side `0xC32915B4` exactly mirrors its relative gain
  (117@ISO100, 936@ISO800, 14976@ISO12800); `1694/169C/16B0` still need semantic A/B.
- AF contrast (HIGH/LOW band arrays), all peak-search intermediates, mposm, waypoints, peak ring — fixed
  `0xC329xxxx / 0xC33Dxxxx` globals.
- Face/eye result struct `0xC37CCA9C`, AAT box `0xC3033E00`, drift monitor `0xC33D1958`, capture state
  `0xC3033834`, AF-model singleton `0xC3404678`.
- Raw Bayer frame: read `0x50000000` region (scan for the live non-zero frame).

**Need an ACCESSOR CALL:**
- Focus position/range/drive (`FUN_c035fd48/c02dffb0/c02dffd0/c035ffc0`), tick, movie-rec, body-motion
  flag. All verified. Focus DRIVE is a control op (moves the lens) — gate it.
- Sensor CG/analog latches (`0x05E1`, `0x3D/3E`) are I2C, not memory. The generic shell has no imager
  device registration, so use the live object now and add a reviewed imager-register accessor only if needed.

**Need MORE RE:**
- CAF sequencer live state (0/1/6): it's a heap object reached by register-passed ctx (`FUN_c028c620`),
  not a fixed DAT. Either trace the AF-thread object to a fixed cell, or add a tiny reviewed accessor.
- Raw-frame **pointer cell** (address is UART-printed, not stored in a known fixed cell) → live-probe the
  `0x50000000` block boundaries to find the current frame offset.
- OTP per-unit gain numbers (`S+0x68/0x70/0x7c/0x84`) — dump sensor cal flash offset `0xC00` (510B) per
  `FUN_c03344b0`; needed to know exact dual-native switch ISO (OTP-RUNTIME).

**Recommended FIRST SET to wire in** (all raw-read, all fixed, all CONFIRMED, low risk):
1. `IMX410_GAIN` (`0xC343B588`, 0xE0) — decoded live sensor gain/HCG object.
2. `GYRO_PTRCELL` + `GYRO_RING_WIN` — gyro (already proven safe on-camera).
3. `DET_RESULT_MGR` (0xC37CCA9C) + `AAT_BOX` (0xC3033E00) — faces/eyes + tracking box.
4. `AF_CONTRAST_HI/LO` + `AF_PEAK_STATE` — live CDAF numbers.
5. Accessor `focus_get_pos/min/max` (read-only, zero-arg, zero side-effect) — safest calls to prove the
   call-op path before enabling any control op.

**Remaining live framebuffer probe** (run over the shell):
- `mem read 0x50000000 0x100` on several 1MB boundaries in LiveView → find the current Bayer frame; a
  non-zero textured block is the live one.

## Idle Live View ISO sweep — 2026-09-24

CINE standby, `imager mode_now` = mode 8 (MONIT1_60), `gain_state: through` throughout.
`menu SetIso <n>` then 1.5 s, then `0xC343B5A0..C3` read twice (identical every time).
With `SetIsoStep` = 0 only full stops are accepted; 1/3-stop values were silently refused.
ISO restored to 100 afterwards and read back unchanged.

| ISO | rel | code | analog ×100 | overflow dig | HCG | trim ×100 |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 117 | 985 | 131 | 100 | 0 | 100 |
| 200 | 234 | 2540 | 263 | 100 | 0 | 100 |
| 400 | 468 | 2540 | 263 | 100 | 0 | 200 |
| 800 | 936 | 3317 | 526 | 100 | 0 | 200 |
| 1600 | 1872 | 3706 | 1053 | 100 | 0 | 200 |
| 3200 | 3744 | 3900 | 2107 | 100 | 0 | 200 |
| 6400 | 7488 | 3965 | 3162 | 133 | 0 | 200 |
| 12800 | 14976 | 3840 | 1606 | 100 | 1 | 200 |

- High AR (code ≥ 0xDFD) from ISO 1600 in idle; 800 is Normal.
- From ISO 400 the idle path carries a fixed 2× inter-node trim, so 400's analog equals 200's.
- ISO 6400 hits the analog cap: 3162 = 31.62× ≈ 30 dB; the rest is overflow digital 1.33×.
- HCG only at 12800 (this unit's idle OTP switch, bracketed earlier at ISO 10939–10949).
  Implied HCG factor ≈ (1.3167 × 128 / 2) / 16.06 ≈ 5.22× (≈ 14.4 dB).
- **This is the idle CG/AR decision only.** Recording switches gain_state to movie / movie_raw
  (CG at 640 / 3200 by rule) and cannot be read from the host mid-take; it needs an on-camera hook.
