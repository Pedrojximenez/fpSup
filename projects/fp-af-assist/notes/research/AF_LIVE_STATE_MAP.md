# SIGMA fp Ver.5.02 — AF / Tracking / Face LIVE-STATE Address Map

Purpose: pin the **live, readable addresses + formats** for the AF / tracking / face subsystem so a
USB `mem read <addr> <len>` monitoring console can display state in real time **without calling
firmware** (raw reads preferred; accessor-call noted where a raw read is impossible). This is the
**live-state** companion to the peer's **algorithm** RE — see `AF_AE_INTERNALS.md`, `FACE_EYE_AF.md`,
`CAMERA_STATE_SOURCES.md` (general live-state map), `TASK_PRIORITY_MAP.md`.

- Base `0xC0000000`, `file_off = addr − 0xC0000000`. Address spaces & the **unmapped-hole trap**
  (never blind-read `0xC31C0000–0xC31F0000`) per `CAMERA_STATE_SOURCES.md` §legend — **froze the camera**.
  All AF globals below are in the heavily-used `0xC320xxxx / 0xC329xxxx / 0xC33Dxxxx / 0xC37Cxxxx`
  live-BSS regions the firmware derefs every frame → safe to raw-read.
- **CONFIRMED** = read from disasm/decomp/notes here. **INFERRED** = deduced. **PROBE** = needs a live
  `mem read` to confirm mapping/values.
- New verifications done in this note (2026-08-19, capstone on `MAIN_c0000000.bin`):
  - **AfMgr ctx singleton base = `0xC32044D8`** — lazy-init getter `FUN_c022ad58` returns it
    (`movw/movt 0xC320_44D8`, guard cell `0xC32067E8`, ctor `FUN_c022aaf8` memsets `0x2220` from it).
    Object header actually starts `0xC32044B4` (0x24-byte OS event-flag head; ctx fields use `+0x24`=`…44D8`).
  - AF-model singleton vtable `0xC092B8D0`: slot **+0x180 = `0xC02A42F8`** (body-motion predicate override),
    slot **+0x184 = `0xC029BA08`** (unconditional `return 0` → confirms fp is **CDAF-only**, PDAF path dead).
  - `af` shell subcommands = `print / dbg / msr / get` (UART diagnostics only, table `0xC0BAE008`).
  - `menu` AF setters (control) resolved to handler addresses (table `0xC0BBB0FC`) — see §5.

---

## Master table (per-item live addresses)

| # | Item | Address / chain | Space | Raw vs Call | Format / units | Cadence | Conf | Source |
|---|---|---|---|---|---|---|---|---|
| **1** | AfMgr ctx singleton base | **`0xC32044D8`** (getter `FUN_c022ad58`) | main-ARM BSS | **Raw** (fixed) | big struct, fields below | — | CONFIRMED (disasm here) | this note; AF_AE ③ |
| 1a | **AF drive/servo mode** (AF-S/AF-C gate) | ctx+0x20c8 = **`0xC32065A0`** | main-ARM | Raw | i32: 1,2=single-ish · **4/8=AF-C servo** · 9=Hybrid-armed | per AF tick | CONFIRMED | AF_AE ⑧ (`==4` gates body-motion), decomp l.32647/57349 |
| 1b | AF drive-mode source copy | ctx+0x2258 = **`0xC3206730`** | main-ARM | Raw | i32 (source of 1a) | per AF tick | CONFIRMED | decomp l.32647 |
| 1c | **AF area mode** | ctx+0x1cc = **`0xC32046A4`** | main-ARM | Raw | i32: 0 single-pt · 1 MF · 3 tracking/AAT-enabled · 5 global | on mode change | CONFIRMED | FACE_EYE ⑧ (`ctx+0x1cc==3`), decomp l.15892/32880 |
| 1d | AF route / strategy-phase state ("the state") | `_DAT_c32915b0` = **`0xC32915B0`** (also = *(ctx+0x21f4), cell `0xC32066CC`) | main-ARM | Raw | i32 NextRoute/route: 0 normal·1·3 re-search·6·**0xE Hybrid-init/re-drive** | per AF tick | CONFIRMED | AF_AE ⑥ NextRoute; decomp l.33185/42071/55690/86087 |
| 1e | CAF sequencer case-state (idle/acquiring/servo) | `*(*(AfMgrThreadObj+4))` via `XC_ThreadHandlerAfMgr__v1@0xC028EAA0`→`FUN_c028c620` | main-ARM heap | **Deref chain / accessor** | i32: 0 idle·1 acquiring·2·3·4·5 driving·**6 Rocking-servo** | per Vd | CONFIRMED semantics, addr NOT fixed | AF_AE ⑧; decomp l.86372+ |
| 1f | Body-motion predicate result (AF-C wants servo) | AF-model singleton **`0xC3404678`** +0x04 (`this[1]`); vtable `0xC092B8D0` | main-ARM | Raw (or call `FUN_c00d0800`) | nonzero → body moved (AF-C only) | per AF tick | CONFIRMED | AF_AE ⑧; verified vtable here |
| **2** | AF contrast HIGH band (`saf_jdat_h`) | **`0xC32985E8[]`** (idx `_DAT_c3291534`) | main-ARM | Raw | u32 processed accumulator; mode 1 adds 256; **not bandval−scanmin** | per eval frame | CONFIRMED | blk_c02:44236–44271,44363–44374 |
| 2a | AF contrast LOW band (`saf_jdat_l`) | **`0xC32986B4[]`** | main-ARM | Raw | u32 processed accumulator; separate scaling | per eval frame | CONFIRMED | blk_c02:44544–44597 |
| 2b | Live copies (into ctx) | ctx+0x21c0 = `0xC3206698` (h), +0x21c4 = `0xC320669C` (l) | main-ARM | Raw | current selected stats minus fixed mode offset, **not measured noise** | per eval frame | CONFIRMED | blk_c02:44422–44448 |
| 2c | Aggregate band/window values | `0xC32915C4 / …C8 / …CC / …D0` | main-ARM | Raw | small H / main H / small L / main L; **not now/max/min** | per eval frame | CONFIRMED | blk_c02:44278–44281,44388–44399 |
| 2d | Drive target / g_afpos accumulator | `0xC32914E0` (=*(ctx+0x2204)) | main-ARM | Raw | i32 encoder pulses | per tick | CONFIRMED | AF_AE ⑦; decomp l.33184-ish |
| 2e | Peak argmax index | `0xC32915F2` | main-ARM | Raw | i16/i32 waypoint index | per sweep | CONFIRMED | AF_AE ⑦ |
| 2f | Step-state (scan granularity) | `0xC3291518` | main-ARM | Raw | i32: 8 highest·6 high·4 midhigh·0 middle·1 low | per phase | CONFIRMED | AF_AE ②/⑦ |
| 2g | Area0 reference peak (strong-judge) | `0xC32914FC` | main-ARM | Raw | i32, ~25000 strong-judge ref | per frame | CONFIRMED | AF_AE ⑦ |
| 2h | Coarse-sweep waypoints + count | `0xC32020E4 / …E8`; count `DAT_c2f172d4` (≤30) | main-ARM | Raw | i32[] positions; count u32 | per sweep setup | CONFIRMED | AF_AE ⑩ Q6 |
| 2i | mposm (exposure-center motor pos, lag-comp) | `0xC3291958[]` | main-ARM | Raw | i32[] sweep history; **not a continuously current position** | per active sweep sample; stale while idle | CONFIRMED static + LIVE idle | AF_AE ⑥; AF-fusion 2026-09-16 |
| 2i-idx | Current mposm sweep-sample index | `0xC329153C` | main-ARM | Raw | u32, written from `uVar9` immediately after `mposm[uVar9]` | per active sweep sample; stale while idle | CONFIRMED static + LIVE idle | `AfMgrProcessFast::v5 @ 0xC025CD30` |
| 2j | AF-C direction vote (hysteresis −2..+2) | `_DAT_c33d5144` = `0xC33D5144` | main-ARM | Raw | i32 vote (≥3 same → flip) | per tick | CONFIRMED | AF_AE ⑥ CalcPdCafDriveDir |
| 2k | Drive-speed LPF state | `_DAT_c33d5148` = `0xC33D5148` | main-ARM | Raw | i32 pulses/eval (single-pole LPF) | per tick | CONFIRMED | AF_AE ⑥ |
| 2l | lensScale (pin=60) | `_DAT_c33c80e8` = `0xC33C80E8` | main-ARM | Raw | i32 (≡60 all fp rates) | per frame | CONFIRMED | AF_AE ⑩ Q9 |
| 2m | AF-C peak-history ring (predict) | `0xC33D0384`, 10 slots ×0x20; idx `_DAT_c33d510c`=`0xC33D510C` | main-ARM | Raw | slot {+8 area,+0xc mode,+0x10 dir,+0x14 time,+0x18 pos,+0x1c dist} | per frame push | CONFIRMED | AF_AE ⑤; FACE_EYE ⑧ |
| **3** | Face/eye result mgr (DetectionResultMgr) | **`0xC37CCA9C`**; groups `+0x10` stride `0x9C` | main-ARM | **Raw** | up to 5 faces, layout §3 | ~1/3 frame (FACECYC) | CONFIRMED | FACE_EYE ② |
| 3a | AF-facing consolidated rect | `0xC37CCA9C+0x3E0` xs/+0x3E4 ys/+0x3E8 w/+0x3EC h | main-ARM | Raw | i32 rect (LV px) | per frame | CONFIRMED | FACE_EYE ④ |
| 3b | AF-facing tracking mode | `0xC37CCA9C+0x3D0` | main-ARM | Raw | i32: 1 track·2 lost-predict·3 stop | per frame | CONFIRMED | FACE_EYE ④ |
| 3c | Face-module / eye-module status | mgr fields `+0x334` (face) / `+0x3D0` (eye) region | main-ARM | Raw | 0 idle·1 detecting·2 active·3 stop | per frame | CONFIRMED | FACE_EYE ① |
| 3d | FD_WORK / AAT_WORK scratch | `0xC37CD754` (0x38400) / `0xC37CD3A0` (0x25800) | main-ARM | Raw (large) | tracker/detector scratch | — | CONFIRMED (large→PROBE base) | FACE_EYE ① |
| **4** | AAT tracking box (current) | **`0xC3033E00`** {x,y,w,h} | main-ARM | **Raw** | i16 x,y,w,h (LV px) | per LV frame | CONFIRMED | AF_AE ⑧ Q1 |
| 4a | AAT confidence / lock gate | `0xC3033E26` (`>19` = locked/adopted) | main-ARM | Raw | u8 conf 0–100 | per LV frame | CONFIRMED | AF_AE ⑧ Q1; FACE_EYE ④ |
| 4b | AAT adaptive color model | `*_DAT_c37cdfa8` (deref cell `0xC37CDFA8`), 0x2c B | main-ARM | Raw (1 deref) | semi-axes +4/+6, conf +0xc, refYCbCr +0x14/15/16 | per frame | CONFIRMED (deref)→PROBE | FACE_EYE ④ |
| 4c | Drift-monitor `M` | **`0xC33D1958`** | main-ARM | Raw | grid `M+0`, det-rects `M+0x220` (256×16B), body-motion `M+0x218`, drift% `M+0x20c`, timer `M+0x21c` | CAF state-0 | CONFIRMED | FACE_EYE ⑧; CAMERA_STATE §5 |
| **5** | Focus control accessors | see §5 (call ops) | — | **Call** | drive / range / set-area | on demand | CONFIRMED sigs | CAMERA_STATE §accessors; this note (menu) |
| — | Capture-state (gates focus drive) | `0xC3033834`+0x220 | main-ARM | Raw | u16 (0=idle) | on state change | CONFIRMED | PTP_FOCUS |

---

## §1 — Firmware AF STATE (item 1)

The AF task is **master-table idx 26 = `AfMgr`, prio 14** (`TASK_PRIORITY_MAP.md` §2b), body
`XC_ThreadHandlerAfMgr__v1 @0xC028EAA0` → `FUN_c028c620`.

**AfMgr ctx singleton = `0xC32044D8`** (lazy-init getter `FUN_c022ad58`, guard `0xC32067E8`, ctor
`FUN_c022aaf8`). Everything the AF task reads as `*(ctx+off)` is therefore at a **fixed absolute
address** = `0xC32044D8 + off`. Live status fields (all raw-readable now):

| Field | Offset | Abs addr | Meaning |
|---|---|---|---|
| AF drive/servo mode | +0x20c8 | **0xC32065A0** | **1a** — 4/8 = AF-C servo (body-motion predicate & CAF loop gate on `==4`); other values = AF-S/single/Hybrid. Closest to "current AF mode". |
| drive-mode source | +0x2258 | 0xC3206730 | raw source copied into +0x20c8 |
| AF area mode | +0x1cc | **0xC32046A4** | **1c** — 0 single-point / 1 MF / 3 tracking(AAT) / 5 global |
| route/strategy state | via +0x21f4→ | **0xC32915B0** | **1d** `_DAT_c32915b0` — NextRoute/strategy phase (0/1/3/6/0xE). Written by the drive strategies each tick. |

**"Focusing / searching / locked" flag** = the CAF **sequencer case-state** (1e): `0 idle / 1
acquiring / 2 / 3 / 4 / 5 driving / 6 Rocking-servo`. It lives in the AF-thread **heap** object at
`*(AfMgrThreadObj+4)` (the `param_1` of `FUN_c028c620`), **not a fixed DAT** → needs a pointer-chain
deref or a tiny reviewed accessor. **Address still needs pinning** (PROBE): dump the AfMgr thread TCB
`exinf` once, or add a 1-line accessor `return *(*(FUN_c022ad58_thread+4))`. In the meantime
**`0xC32915B0` (1d)** + **`0xC32065A0` (1a)** give a good live proxy (route + servo-mode).

**In-focus result**: fp is CDAF-only (PDAF slot `+0x184` = `return 0`, verified). The per-area
"in-focus" latch is `CafMode5` state **6** in the per-area struct (counter `+0x50`, state `+0x60`,
N=3 consecutive small-defocus frames — AF_AE ⑨ Q12). That per-area struct hangs off the ctx far
region (`afctx+0x7d…`) and is **not yet pinned to a clean absolute** → PROBE (xref `FUN_c02804c8`
writes). For a live console the practical "focused?" signal is **3b tracking-mode** (faces) plus
**1d/1e** transitioning to idle/servo.

**Last AF trigger / body-motion** (1f): AF-model singleton `0xC3404678`, `+0x04` = latest
body-motion predicate result (nonzero ⇒ AF-C requested Rocking servo). vtable `0xC092B8D0` verified.

---

## §2 — AF CALCULATION status (item 2)

The CDAF contrast the loop computes each frame is the `saf_jdat` band arrays — **raw-readable at
fixed globals**:

- **HIGH band `0xC32985E8[]`**, **LOW band `0xC32986B4[]`** (indexed by `_DAT_c3291534 @0xC3291534`).
  Each cell is a u32 processed accumulation with band-specific scaling, conditional H correction,
  32-bit saturation and mode-dependent +256/0 offset; it is **not bandpass minus scan-min**.
- Current-frame copies into ctx: `0xC3206698`/`0xC320669C` subtract that fixed mode offset, not a noise floor.
- **Aggregate bands**: small H/main H/small L/main L `0xC32915C4/C8/CC/D0`; separate peak-search fields are
  argmax index `0xC32915F2`, drive-target
  accumulator `0xC32914E0`, step-state `0xC3291518`, area0 strong-judge ref `0xC32914FC`.
- **Evaluation-region / sweep**: coarse-sweep waypoints `0xC32020E4/E8` + count `DAT_c2f172d4` (≤30;
  28mm→30), exposure-center motor positions `0xC3291958[]`. The current sweep-sample index is
  **`0xC329153C`**, not the H/L area index at `0xC3291534`: `AfMgrProcessFast::v5` writes
  `mposm[uVar9]` and then `_DAT_c329153c = uVar9`. A coherent reader must sample the two indices
  separately and reject a record if either changes while its fields are gathered.
  **Live correction (2026-09-16):** during a 10-second idle run, H/L kept changing but the sweep index stayed
  3 and `mposm[3]` stayed 9622. Index stability proves only a coherent read; it does not prove a new DFD point.
- **AF "confidence" / direction**: direction hysteresis vote `_DAT_c33d5144 @0xC33D5144` (band
  −2..+2, ≥3 same-sign → flip), drive-speed LPF `_DAT_c33d5148 @0xC33D5148`, lensScale
  `_DAT_c33c80e8 @0xC33C80E8` (≡60). Per-area contrast history: AF-C peak ring `0xC33D0384` (10×0x20).

**Contrast interpret**: in-focus/clear peak ≈ 1e4–2.5e4; the acquisition threshold used by the loop
is `peak/128 + 70` (v26, stored ctx+0x34) and `peak/16 + 16` (v25). Units are dimensionless
bandpass-energy spans, encoder positions are pulses. Cadence: written every **CAF eval frame** — CAF
observer divisor **1 (~17 ms/Vd)** or **2 (~33 ms)** depending on readout (AF_AE ⑨ Q18); mode-6
divisor never set on Ver.5.02.

> Trap (FACE_EYE key-trap): the CAF-debug CSV globals labelled `FaceTopX0…` are **per-AF-area CDAF
> cells** (stride 0x11c, writer `FUN_c0242018`), **not literal face boxes** — don't confuse them with §3.

---

## §3 — Face / eye detection regions (item 3)

**EyeDtctn = master idx 32 (prio 17); Tracking = idx 33 (prio 17)** (`TASK_PRIORITY_MAP.md` §2b).
Output is the **DetectionResultMgr singleton `0xC37CCA9C`** — raw-readable, fixed:

- Up to **5 faces**, each a **`0x9C` group** = `[face 0x34 | eyeA 0x34 | eyeB 0x34]`, base `+0x10`,
  stride `0x9C`. Per `0x34` sub-record: **`+0x10 X`(top-left), `+0x14 Y`, `+0x18 W`, `+0x1C H`**
  (square pre-aspect), `+0x20 angle`, `+0x28 score`, `+0x30 valid(byte)`; group `+0x34 tracking-ID`,
  `+0x3C count-flag`.
- **Coordinate system = 320×213, origin top-left** (parser scaler picks 1620×1080 / 640×426 / 320×213;
  faces stored in 320×213). Convert to sensor px happens on the AF side (FACE_EYE ⑤).
- **AF-facing consolidated rect** `+0x3E0 xs / +0x3E4 ys / +0x3E8 w / +0x3EC h`; **mode `+0x3D0`**
  = 1 track / 2 lost-predict / 3 stop.
- Module status: face `+0x334`, eye `+0x3D0`-region: 0 idle / 1 detecting / 2 active / 3 stop.
- Raw ISP record (pre-parse, if you read the detector output) is `0x20` B: `+0x08 cx, +0x0C cy,
  +0x10 size, +0x14 score, +0x18 angle(16-bit), +0x1C track-ID`.

Detection engine itself is opaque ISP HW (ROI regs `+0x82C/+0x830`); you only read the parsed struct.
Cadence ~**1/3 frame** (FACECYC Cyc-thread, prio 500). Eye landmark work (12 pts + confidences, 0xA4 B)
is on-demand in the eye thread — not needed for the console's rectangle display.

---

## §4 — AAT / AF tracking box CURRENT state (item 4)

Ships with the **color** backend only (histogram compiled but `DAT_c37cd364=0`).

- **Current tracking box `0xC3033E00` = {i16 x, y, w, h}** (LV px); **confidence/lock `0xC3033E26`**
  (`>19` = locked & adopted by AF; `<20` = not locked). Raw-readable, fixed.
- **Tracking phase** = the AF-facing mode at `0xC37CCA9C+0x3D0` (§3b): 1 tracking / 2 lost-but-predict
  (held by AF-C) / 3 stop.
- **Reference/target used** = the adaptive color model `*_DAT_c37cdfa8` (deref cell `0xC37CDFA8`,
  0x2c B): semi-axes `+4/+6`, confidence `+0xc`, reference (Y,Cb,Cr) `+0x14/15/16`. One pointer deref
  (PROBE the pointer first).
- **Drift-monitor state `M = 0xC33D1958`** (the re-focus trigger the peer analyzed): 16×16 luma grid
  `M+0`, detection-rect list `M+0x220` (256×16B), body-motion/large-subject flag `M+0x218`, AF-eval
  drift% `M+0x20c`, timer base `M+0x21c` (elapsed vs `≤307` VD ticks ≈ 5.1 s@60fps / 10.2 s@30fps).
- Closed loop: AAT box size changing (subject depth change) → drift-monitor #1 (`FUN_c028ab20`,
  thr 2%/10%) → re-drive. AAT tracker runs **per LV frame** (`FUN_c05abec8`).

AAT_WORK scratch `0xC37CD3A0` (0x25800). Tracking task = idx 33.

---

## §5 — Focus CONTROL entry points (item 5 — CALL, not read)

Control ops must sit behind an explicit `--region control` capability + host lease-lock (fp-task-abi
safety contract). Signatures CONFIRMED by disasm unless noted.

| Op | Addr | Signature | Effect / units | Preconditions | Conf |
|---|---|---|---|---|---|
| `focus_get_pos` | `0xC035FD48` | `()` | → i32 abs lens position (pulse domain); note: sampled at **drive-END** only (stale mid-move) | none | CONFIRMED |
| `focus_get_min` / `focus_get_max` | `0xC02DFFB0` / `0xC02DFFD0` | `()` | → i32 range endpoints (same domain) | none | CONFIRMED |
| **`focus_drive_abs`** ⚠ | `0xC035FFC0` | `(r0=target_abs, r1=0, r2=0)` | **MOVES LENS** to absolute target; **clamp to [min,max] yourself** | none in fw — dangerous | sig CONFIRMED, r1/r2=0 INFERRED (0x9411 path) |
| `focus_drive_gated` (historical alias) | `0xC04EF7D0` | `(target)` | submits movement; `0x2001` is acceptance, **not completion**; no direct capture/recording check here | lens/property/worker readiness, range and request handshake; not proven universal AF-idle gate | SOURCE CONFIRMED predicates; standalone live safety NOT validated |
| `menu SetFocusPosition` | `0xC03FBFE0` | `x y width height` (decimal); no args = getter | set AF rectangle in 1024×682 workspace, **not lens position**; snaps/clamps, read back | LV/lens present | CONFIRMED |
| `menu SetFocusMode` | `0xC03FC0E0` | `<int>`; no args = getter | **set AF-S / AF-C / MF**, not an AF trigger by itself | — | CONFIRMED addr |
| `menu SetFocusArea` | `0xC03FC150` | `<int>`; no args = getter | **set AF area mode**, not point coordinates | — | CONFIRMED addr |
| `menu SetFocusAreaSize` | `0xC03FC1C0` | `<int>` | AF area size (single 32/64/128; region 119×73…833×511, work-space 1024×682) | — | CONFIRMED addr |
| `menu SetFaceDetectMode` | `0xC03FC398` | `<int>` | FaceEyeAuto / FaceOnly / off | — | CONFIRMED addr |
| `bodymotion_flag` | `0xC00D0800` | `(obj=0xC31CC42C)` | → bool (read-only helper) | none | CONFIRMED |

**Triggering an AF cycle (2026-09-16 verified)**: `key S1ON` / `key S1OFF` enqueue the original
half-press/release events (4/5); no S2 is sent. Success is silent and the shell ACK is not focus-complete
evidence. Always release in `finally`, including uncertain start replies; never retry an uncertain start.
`still startAF` / `still stopAF` are another matched pair (handlers `0xC040DEA0` / `0xC040DF00`,
RecMgr commands 1/2), statically verified but not used in this trial. Do not mix them with `still AFON/AFOFF`.
`af msr` is **not read-only**: it can enter an S2 capture loop; do not use it for this experiment.

The active UserSetting object is returned by `FUN_c0021c40` (pointer cell `0xC3075230`). Its
`+0xC8..0xD4` are **left, top, right-inclusive, bottom-inclusive**, not xywh. Use the four-argument
`SetFocusPosition` setter and save/restore the no-arg getter tuple. Getter applies native geometry
snap/clamp; setter's OK does not prove the exact requested position was applied. It notifies settings
observers, so AF-C/PreAF can react even though it does not directly call TouchAf. Never poke this live rect.

**Sweep index caveat (2026-09-16 live + static)**: `0xC329153C` is not universally last-written.
Fast::v5 writes the completed index, but Near::v6 (`0xC026B268`) publishes `k+1` before that position
slot is filled. A stable index pair therefore cannot establish exposure alignment. Idle histories remain
stale; H/L area slot 0 does not identify the screen coordinate. See the original-AF trial note for evidence.

---

## Proposed READ-INTERVAL additions (all raw-readable, main-ARM)

Names for the shell's read-interval table. All **read-only** for the console (do NOT expose write to any
AF interval — poking the AF ctx mid-drive can crash the AF task). Narrow windows over live BSS.

| Name | Start | Len | R/W | Contains |
|---|---|---|---|---|
| `AFMGR_CTX` | `0xC32044B4` | `0x2280` | RO | AfMgr ctx: area-mode(+0x220), drive/servo mode(+0x20ec-abs 0xC32065A0), state cells |
| `AFMGR_MODE` (narrow) | `0xC3204698` | `0x10` | RO | area-mode `+0x1cc`=0xC32046A4 (tight alt to full ctx) |
| `AFMGR_DRIVEMODE` (narrow) | `0xC320659C` | `0x10` | RO | drive/servo mode 0xC32065A0 + neighbours |
| `AF_STATE_ROUTE` | `0xC32915AC` | `0x10` | RO | route/strategy state `_DAT_c32915b0` (0xC32915B0) |
| `AF_PEAK_STATE` (legacy name) | `0xC32914E0` | `0x140` | RO | target/g_afpos, aggregate H/L window values, step-state, argmax, area0-ref, contrast-idx |
| `AF_CONTRAST_HI` | `0xC32985E8` | `0x100` | RO | HIGH-band `saf_jdat_h[]` |
| `AF_CONTRAST_LO` | `0xC32986B4` | `0x100` | RO | LOW-band `saf_jdat_l[]` |
| `AF_MPOSM` | `0xC3291958` | `0xFA0` | RO | up to 1000 exposure-center sweep-history positions; sample index `0xC329153C`, stale while idle |
| `AF_WAYPOINTS` | `0xC32020E0` | `0x100` | RO | coarse-sweep waypoints + count |
| `AF_DRIVE_TUNE` | `0xC33C80E8` | `0x08` | RO | lensScale(≡60) |
| `AF_DRIVE_DIR` | `0xC33D5144` | `0x10` | RO | dir-vote + speed-LPF state |
| `AF_PEAK_RING` | `0xC33D0384` | `0x150` | RO | 10-slot AF-C peak history |
| `AF_MODEL` | `0xC3404674` | `0x10` | RO | AF-model singleton head + body-motion flag(+0x04) |
| `AF_DRIFT_MON` | `0xC33D1958` | `0x400` | RO | drift-monitor grid/rects/timers (verify extent live) |
| `DET_RESULT_MGR` | `0xC37CCA9C` | `0x400` | RO | face/eye groups + AF-facing rect + modes |
| `AAT_BOX` | `0xC3033E00` | `0x30` | RO | current tracking box + confidence |
| `CAPTURE_STATE` | `0xC3033834` | `0x240` | RO | capture-state (+0x220) — gates focus drive |

**Deferred (PROBE before adding):** `AAT_MODEL` (`*0xC37CDFA8` — deref first), `FD_WORK 0xC37CD754`
(0x38400 large; confirm base), CafMode5 per-area in-focus struct (xref `FUN_c02804c8`), CAF sequencer
case-state cell (needs AfMgr-thread-TCB deref).

---

## Summary

**Raw-readable NOW (fixed absolute, no call) — the bulk of the ask:**
- **Item 1 AF state**: AF drive/servo mode `0xC32065A0` (AF-C=4/8), area mode `0xC32046A4`, route/strategy
  state `0xC32915B0`, body-motion `0xC3404678+0x04`. (AfMgr ctx base `0xC32044D8` pinned & verified here.)
- **Item 2 AF calc**: contrast HIGH `0xC32985E8[]` / LOW `0xC32986B4[]`; legacy
  aliases `peak_now/max/min` at `0xC32915C4/C8/CC` are actually aggregate small-H/main-H/small-L;
  D0 is main-L. Target `0xC32914E0`, step-state `0xC3291518`, argmax `0xC32915F2`, area0-ref
  `0xC32914FC`, dir-vote `0xC33D5144`, waypoints `0xC32020E4/E8`, peak ring `0xC33D0384`.
- **Item 3 face/eye**: DetectionResultMgr `0xC37CCA9C` (groups +0x10/stride 0x9C; AF rect +0x3E0; mode +0x3D0).
- **Item 4 AAT**: box `0xC3033E00` + conf `0xC3033E26`, drift-monitor `0xC33D1958`.

**Need an ACCESSOR CALL:** focus position/range/drive (`0xC035FD48 / C02DFFB0 / C02DFFD0 / C035FFC0`,
gated `0xC04EF7D0`), AF-area/mode setters (`menu SetFocus*` `0xC03FBFE0/C0E0/C150/C1C0`, SetFaceDetectMode
`0xC03FC398`), body-motion `0xC00D0800`. AAT color model needs one pointer deref (`*0xC37CDFA8`).

**Still need a LIVE PROBE / more RE (say which `mem read` to try):**
- **CAF sequencer case-state** (0/1/6 "focusing/locked"): heap obj, not fixed → add a tiny accessor
  `*(*(afMgrThread+4))`, or trace the AfMgr-thread TCB `exinf`. Interim proxy: read `AF_STATE_ROUTE`
  `0xC32915B0` + `AFMGR_DRIVEMODE` `0xC32065A0`.
- **Per-area in-focus latch** (CafMode5 state 6): xref writer `FUN_c02804c8`; `mem read` the ctx far
  region once the per-area base is pinned.
- **AAT model / FD_WORK**: `mem read 0xC37CDFA8 4` → follow pointer; `mem read 0xC37CD754 0x100` to
  confirm FD_WORK base is mapped before adding the big interval.

**Recommended FIRST SET to wire into the console** (all raw, fixed, CONFIRMED, low risk):
1. `AFMGR_DRIVEMODE` (0xC32065A0) + `AFMGR_MODE` (0xC32046A4) + `AF_STATE_ROUTE` (0xC32915B0) — live AF mode/state.
2. `AF_CONTRAST_HI/LO` + `AF_PEAK_STATE` — live CDAF numbers + peak search.
3. `DET_RESULT_MGR` (0xC37CCA9C) + `AAT_BOX` (0xC3033E00) — faces/eyes + tracking box (with mode +0x3D0).
4. `AF_MODEL` (0xC3404674) + `AF_DRIFT_MON` (0xC33D1958) — body-motion + re-focus triggers.
5. Accessors `focus_get_pos/min/max` (read-only, zero-arg, zero side-effect) — prove the call-op path
   before enabling any control op. Do not treat the historical `focus_drive_gated` label as authorization
   or a complete idle/recording guard. Establish a bounded completion/abort path before movement;
   `lens setfpos` bypasses this entry, and `ptp focus_comp` is only a notification, not abort.

**2026-09-16 gate correction:** `C04EF7D0` has no direct `+0x220` capture-state check; the 0x9032 caller
`C04F5AE8` checks `+0x220==0` and `+0x7C==0` only after MenuSet synchronization. The predicate
`C035F560` refers to lens-controller state, not proven camera LiveView; `C0362558` is a lens property/protocol
check, not proven AF busy. See [drive-gate audit](FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md).

**Cited prior notes:** `AF_AE_INTERNALS.md` (②/⑤/⑥/⑦/⑧/⑨/⑩), `FACE_EYE_AF.md` (①/②/④/⑤/⑧), 
`CAMERA_STATE_SOURCES.md` (general live map, §5/§6/§8/accessors), `TASK_PRIORITY_MAP.md` (§2b idx 26/32/33),
`SHELL_COMMANDS.md` (mem/menu/af), `PTP_FOCUS.md`, `DISPLAY_OSD_MAP.md`.
