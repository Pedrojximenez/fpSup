# SIGMA fp Ver5.02 — Hardware Lossless-JPEG codec (standalone-callable) — RE 2026-08-20

> **2026-10-15 correction:** The global absence claim for H.264/HEVC and the identification of all of `0x300C` as a non-compressing RAW front end are withdrawn. The MOV initialization chain reaches a hardware codec at `0x300Cxxxx`, with an additional HEVC candidate branch. Neither 10-bit support nor direct Bayer input follows from this. See [H.264 10bit hardware analysis](FP_H264_10BIT_FEASIBILITY_2026-10-15.md).

Goal that motivated this: compress raw CinemaDNG frames ON-CAMERA (before USB push) to cut link/storage
rate, losslessly. Confirmed feasible. EAs are ARM (base 0xC0000000); file-offset in MAIN = EA − 0xC0000000.
Confidence: [C] confirmed in disasm, [I] inferred, [P] needs live probe.

## TL;DR
Two separate lossless-JPEG paths exist:
- **Path B — `XC_HalLjpeg`, dedicated fixed-function engine at MMIO `0x300D0000`, IRQ 0x29.** Used by the
  **still-DNG** encoder. It is a CLEAN STANDALONE PRIMITIVE: raw {src,dst,w,h,bitdepth,tileW,tileH} in →
  lossless-JPEG bitstream + per-tile byte-count out. **This is the one to replay.** [C]
- Path A — `XC_SigproJpegComp`, the SIGPRO DSP task used by **UHD CinemaDNG video**. Replayable in principle
  but needs a live frame-graph + 0x4c plane descriptors + DSP session token. Different silicon. Skip. [C]

Lossless is fixed in hardware (no quantization/quality knob anywhere) → Path B *is* the `Compression=7`
engine; output is bit-exact. [C]

## Key corrected fact (fixes an earlier wrong assumption)
- **fp CinemaDNG VIDEO (FHD & UHD) is recorded UNCOMPRESSED (`Compression=1`, 12-bit).** Proven on real
  camera-original FHD frames (`/Users/dido/Movies/A001_001/*.DNG`: 1936×1090, 12-bit, Comp=1, crop 1920×1080).
  That is why slimRAW gets a big (~2:1) lossless reduction on fp UHD footage — the whole entropy-coding
  headroom is on the table because the camera never compressed it.
- **fp STILL photo DNG is `Compression=7` lossless-JPEG, 14-bit** (`_SDI0011.DNG` SubIFD: 6064×4042, 14-bit,
  tiled 256×256, WhiteLevel 16383). The camera runs the Ljpeg codec ONLY for stills, NOT for CinemaDNG video.
- A `3856×2170 Compression=7` file seen earlier was a **slimRAW OUTPUT**, not a camera original — the source
  of the earlier mistaken "UHD already compressed" claim.

## PATH B — replay sequence (recommended)
```
1. RAWCD()                    @c062f440  -- lazily creates event flag DAT_c2f2e60c (auto, from inside encode)
2. FUN_c05a6890(&initStruct)  @c05a6890  -- init: latch src/dst/geometry into globals (→FUN_c062f5a8 @c062f5a8)
3. FUN_c05a6920(&encStruct)   @c05a6920  -- ENCODE, BLOCKS to completion (→FUN_c062f6f8 @c062f6f8); ret success
4. FUN_c05a6990(resultPtr,1)  @c05a6990  -- copy result/size table out (→FUN_c062fa48 @c062fa48)
```
Power/clock/IRQ bring-up is automatic inside encode (`FUN_c062fee8` @c062fee8: FUN_c0708c60(1), FUN_c06304f0,
FUN_c07095a8(5,1), registers IRQ 0x29 handler c0630430, one-time-guarded by _DAT_c37cf878).
Decode counterpart: `FUN_c05a69e0` @c05a69e0 (use for round-trip verification).
Real call site to copy: **blk_c03.c:85623-85636** (still path); src = *(ctx+300) or *(ctx+0x68).

### initStruct (for FUN_c05a6890) — 9 words + 1 byte, consumed by FUN_c062f5a8
| word | meaning |
|---|---|
| [0] | width |
| [1] | height |
| [2] | bitdepth CODE (FUN_c062fe40: 0→12, 1→14, 2→16, 3→10) |
| [3] | tile width (still uses 0x100) |
| [4] | tile height (0x100) |
| [5] | **SRC DRAM ptr** → _DAT_c302cdd4 |
| [6] | secondary/work base → _DAT_c302cddc |
| [7] | **DST/compressed-out + size-table base** → _DAT_c302cde4 |
| [8] (byte) | mode flag (0=full-frame, nonzero=strip) |

### encStruct (for FUN_c05a6920) — 5 words, consumed by FUN_c062f6f8
`[0]=width [1]=height [2]=bitdepthCode [3]=tileW [4]=tileH` — geometry only; buffers come from the globals
that the init call latched.

### MMIO block base 0x300D0000 (programmed by FUN_c062fff8 @c062fff8)
`+0x00` control (**bit1=start compress**, bit0=decompress) · `+0x04` status/result · `+0x40` bitdepth/mode ·
`+0x44` width(&0x7FFF) · `+0x48` height · `+0x4C..0x54` tile params · `+0x6C/0x70` stride ·
`+0x74` IRQ-enable · `+0x78` src≫10 · `+0x7C/0x84` 2nd/3rd buf≫10 · `+0x8C/0x90` end addrs ·
**`+0xF8` produced-byte count** · `+0x3FC` busy/clear. Adjacent gates: 0x30000814 (clock),
0x30002218 (top IRQ en), 0x30100550. IRQ 0x29 handler `FUN_c0630430` @c0630430 reads 0x300D0004,
sets flag via FUN_c062fcb0→FUN_c0016b9c; error = flg&4.

### Output size
Per-tile byte count read from `0x300D00F8`, accumulated by FUN_c062f6f8 into size table at _DAT_c302cde4
(= initStruct[7] region); FUN_c05a6990 copies it out. Bitstream DMA'd to dst; EOI fixup FUN_c062f6c0
(patches FF D9).

### Blocking model
Synchronous. FUN_c062f6f8 kicks (0x300D0000|=2 via FUN_c0630208) then waits on event flag
FUN_c0016c08(DAT_c2f2e60c, mask=5, …) with size-derived timeout (min 100 ticks). A standalone caller outside
task context could instead POLL 0x300D0000/0x3FC/0x0004 — exact done-bit is [P].

### Buffer constraints
- **1 KB alignment**: addrs programmed as (virt+0xC0000000)≫10; validated &0x3FF==0. [C]
- Geometry: width 8..0x4000 mult-of-8; height 2..0x4000 even. [C]
- Physical/uncached DMA (FUN_c062f510 @c062f510 maps to 0x40000000/0xC0000000 window, cache-clean
  FUN_c000e91c). Caller buffers: place in uncached DRAM window or flush src / invalidate dst around call. [I]

## PATH A — SIGPRO DSP (video) — for reference, NOT recommended
Entry FUN_c04247b0 @c04247b0 → FUN_c04247e8 @c04247e8 loops planes 0..3, builds 0x2c XC_SigproJpegComp from
live 0x4c plane descriptors (FUN_c0699288 src +0x10/+0x14/+0x1c; FUN_c06992b8 params +0x38 dst/+0x40 cap/
+0x48 bitdepth/+0x3c result). Submit = FUN_c042e7e8 @c042e7e8 → FUN_c042ec90 → FUN_c01aa888 → FUN_c01af740:
snd_msg to queue DAT_c2f14d1c + infinite event-flag wait DAT_c2f14c88. Dispatcher FUN_c01af950. Manager
singleton global 0xC375BA2C (FUN_c0423c48). `XC_SigproJpegComp__v0` @c042e7c0 is a no-op destructor, NOT the
submit. Requires synthesizing a live frame object graph — high entanglement, skip.

## RISK — engine contention (the real hazard) [I/P]
The 0x300D0000 engine is a **single global resource with NO mutex** in the HAL — only init-once guards
(_DAT_c37cf878) and a mode byte (_DAT_c37cf87c). If the imaging pipeline is mid-still-write, a standalone
kick corrupts both and can wedge IRQ 0x29 / the event flag → likely reboot (cf. RAWGRAB/EP84 wedge history).
**Only invoke while idle** (not writing a still). During LV/video the stills engine 0x300D0000 is plausibly
idle (video uses the SigPro path), but confirm the two engines aren't bridged to the same silicon [P].

## Probe plan before any bake [P]
1. Read 0x300D0000 / 0x300D03FC / 0x300D0004 at idle to learn idle vs busy encoding (define done-bit).
2. Confirm whether FUN_c062fee8 power/clock bring-up is required for a bare kick or already-on when idle.
3. From-scratch init+encode on a SMALL 1KB-aligned synthetic buffer while camera idle; read 0x300D00F8 size;
   round-trip decode via FUN_c05a69e0 and compare bit-exact.
4. Cache-coherency behavior for caller-owned buffers.
Only after 1–4 pass: wire it into the worker's pre-USB-push path (grab 12-bit frame → Ljpeg → push compressed).

## Throughput / why video is left uncompressed (RE 2026-08-20) [C code / I units]
Encode wait `FUN_c062f6f8` (blk_c06.c:42680-42685) computes its timeout as
`timeout_ticks = tile_aligned_pixels / 32000` (via 64-bit divide `FUN_c00158a4` @c00158a4), floored at 100.
No large safety multiplier ⇒ the firmware's own time model ≈ pixels/32000 ticks. Tick≈1ms [I] ⇒ engine
throughput ≈ **32 Mpixel/s** (≈1 pixel/clock at a ~32 MHz engine clock; clock gate 0x30000814).
- Still 6064×4042 (24.5 Mpix) → ~0.77 s (one-shot, acceptable).
- UHD 3840×2160 (8.3 Mpix) → ~0.26 s → ~4 fps max ⇒ far below 24–30.
- FHD 1920×1080 (2.07 Mpix) → ~65 ms → ~15 fps max ⇒ below video rates.
⇒ This is a STILLS-class lossless engine; it cannot sustain UHD (nor comfortably FHD) at video frame rates.
That is why fp records CinemaDNG uncompressed and only invokes Ljpeg for single stills. [conclusion, I]

### Implication for our USB shell (non-realtime) — still a net win
Our USB grab is already far slower than realtime (bulk-bound). Compressing a grabbed UHD frame (~0.26 s)
before pushing HALVES the USB payload (12.5 MB → ~6 MB) → lower end-to-end time and link rate, even though
frame rate can't reach 30. Compression is worth it for the shell's per-frame transfer, just not for realtime.

### Still-open contradiction [P]
Agent reported SIGPRO `XC_SigproJpegComp` (Path A) in the "UHD CinemaDNG video frame writer" (imaging.c
~3690-3715: calls FUN_c04247b0, sums per-plane byte counts into *(param_1+0x10)), yet real camera-original
CinemaDNG video is Compression=1 (uncompressed). Need to confirm whether that SIGPRO comp produces the RAW
bitstream, an embedded preview, or a still-capture SubIFD (mislabeled path). Does NOT affect the speed
conclusion or Path B feasibility.

## VERDICT: compressed UHD RAW → SD at video rate (RE 2026-08-20, 2 agents + direct trace)
**Lossless compressed UHD 12-bit RAW to SD at video rate = NOT FEASIBLE on fp hardware.** [C]
- Only lossless Bayer codec = XC_HalLjpeg (0x300D, ~32 Mpix/s) = 8× too slow for UHD30 (~249 Mpix/s).
- Fast DSP codec XC_SigproJpegComp (0x301B) is **lossy DCT** (quality 0x55/0x5a/0x5f = Q85/90/95, rate-
  controlled via FUN_c042e920 @c042e920), stills/preview ONLY (callers XC_StillCreateJpeg @c037d8f0,
  XC_SensorAdjustmentCaptureConcrete @c0522428), NEVER on per-frame video path. Submit needs live 0x4c
  plane descriptors + DSP session (msg-queue DAT_c2f14d1c / event-flag DAT_c2f14c88, FUN_c01af740).
- The former global claim that no H.264/HEVC codec exists is **withdrawn (2026-10-15)**. The MOV SDK reaches the
  `0x300Cxxxx` video codec. This does not establish a Bayer compression path; see the analysis linked above.

### What IS ready (blocker is ONLY the compressor)
- Compressed-CinemaDNG WRITER already exists: single Compression-tag writer FUN_c06a5290 @c06a5290 (IFD0) +
  FUN_c06a56c8 @c06a56c8 (subIFD), class XC_StillFileFormatDngTh, builder c06a4bd0. Emits Compression=1 or
  =7 based on flag byte at (image-descriptor)+4; =7 branch writes 256×256 tiled lossless-JPEG (tags
  0x142/0x143=0x100, 0x144/0x145). Decode round-trip: XC_PlayFuncSeqDngDeveloping__v32 @c03c8350
  (if compression==7 → XC_HalLjpeg decode c05a6890/c05a69e0). Exposed for stills by config
  `cam_still_raw_compress` (0..1, backing 0xc3758bc4, rawbit.c:765). **No `cam_movie_raw_compress` exists.**
- SD/SSD gate is SOFT (menu-layer policy), relaxable in principle: EXCL_CinemaDNGQuality (c06cbbe0, model
  vtable +0x4fc), EXCL_StorageMedia (c06cbe68, +0x510); clamp MenuItemMovieCinemaDNGQuality__v8 @c00a7ee0
  forces quality index=4 when resolution-state==3 (UHD). Storage state cam_Current_Storage @0xc3758c30,
  external media type=5 (mediaobs.c c02de5b8). UHD geom 0xF00×0x870 table FUN_c0438338 @c0438338.

### Feasible fallbacks
- **Low-fps LOSSLESS UHD RAW to SD**: ~4fps (matches 0x300D engine) or ~15–20fps uncompressed (matches SD
  bandwidth). Needs only: relax the soft gate + hook the movie-DNG writer to set object+4 (compress) and/or
  allow UHD dest=SD. Real deliverable (timelapse / stop-motion / low-speed cine).
- **Lossy compressed raw to SD** at higher fps: MAYBE via 0x301B DSP DCT engine — needs on-camera probe of
  (a) standalone ≥166 Mpix/s, (b) CFA input acceptance, (c) spare DSP cycles during record. Lossy, not bit-exact.
- **24fps margin play**: engine(6.5%) + CPU sw(~4%) ≈ 10% bandwidth cut — only crosses SD if uncompressed
  24fps (298 MB/s) is JUST over the real SD ceiling. Pending SD-ceiling number (2nd agent).

## SD/SSD destination GATE (RE 2026-08-20, agent + verify) — SOFT, patchable
Gate fn **FUN_c04a19b0 @0xC04A19B0** (installed at obj+0x1FC4, blk_c04.c:119462). Blocks (returns 0) iff:
  recFormat==0 (DNG; FUN_c005be90 acc +0x194) && recSize==3 (UHD 3840x2160; FUN_c005c058 acc +0x1a0)
  && ( FUN_c0518410(5)==0  [ext USB media idx5 not ready]  ||  FUN_c005f288(this,1)!=1 [dest!=external] )
Pure 3-enum policy triad — NO speed/bitrate/DMA/bytes-per-frame term. Media idx: 1=internal SD, 5=external
USB/MassStorage (FUN_c0366a98 asserts slot∈{1,2,3,5}). RecSize enum table @0xC0742228: 2=FHD1080, 3=UHD2160.
Record routing XC_StorageMgrObserverRecordPathMgr__v1 @0xC06A1128 (*param==1 SD / ==5 USB). Sibling
FUN_c04a1120 @0xC04A1120 picks quality code from same triad. Menu clamp MenuItemMovieCinemaDNGQuality__v8
@0xC00A7EE0 forces quality idx=4 when UHD-DNG && no slot5. Storage selector obj cam_Current_Storage
(0xC3759DBC [0,1]) read by FUN_c005f288.

### No firmware SD ceiling
Firmware never compares a MB/s / speed-class limit. Reads card UHS grade (SSR, vtable+0x24: 0 inval/1 normal/
2 UHS-I/3 UHS-II) → boolean "is UHS-II" (FUN_c06b1ed0 @0xC06B1ED0, stored MovClass+0x154) → only tunes write
pacing (FUN_c06b2238 @0xC06B2238: UHS-II → 0x1806000=24MiB chunks w/ yield; else single write). Ceiling =
whatever the card physically sustains.

### Overflow handling = clean STOP, no corruption
Bounded frame-descriptor pool (FUN_c0374268 @0xC0374268, 0x111c-byte desc, slot idx <0x60=96, FUN_c03753c0).
Writer behind → -1/-2 → dbfull @0xC0397E60 → stop notify FUN_c0396E80. Reason map FUN_c04ade10 @0xC04ADE10:
event 0xD → reason2 "StopOverflow" (table FUN_c06b0038, logged mov_log.txt). Enums eMOVREC_STOP_OVERFLOW/
_FAT/_OVERTIME. Reactive not preventive; clip ends cleanly, no partial/corrupt frames.

### VERDICT — enabling UHD RAW to SD
Gate is patchable (force FUN_c04a19b0→1; bypass clamp @0xC00A7EE0; fix FUN_c04a1120). Record path
(MovRecFuncStateCinemaDng, cdngqual.c) does NOT re-check storage → patched gate + current-storage=SD →
UHD DNG writes to SD. Physics: UHD 12-bit = 12.44MB/frame → 24fps 298 / 30fps 373 MB/s → StopOverflow on
even top V90 UHS-II (~250-290). WORKS at reduced fps: ~12fps 149 / ~10fps 124 / ~8fps 100 MB/s. FHD 12-bit
24fps=74.6 (fp's own SD-allowed figure, validates math). No compressed-CinemaDNG path exists → compression
is NOT a firmware lever.

## FINAL: two goals
- Compressed UHD RAW to SD @24-30fps (lossless) = INFEASIBLE (no video-rate lossless Bayer codec).
- **UHD 12-bit RAW to SD @~10-12fps (uncompressed) = FEASIBLE via 3-address gate patch, no codec needed.**
  Low-speed RAW / cine-timelapse mode SIGMA locks out by menu policy only. Risk = StopOverflow (safe: no
  damage). Deliverable via AutoRun/shell patch. [P] live: verify NOP'd gate runs to StopOverflow, measure
  real sustained SD MB/s on target card.

## ⚠️ CORRECTION (2026-08-20): the 32 Mpix/s was a TIMEOUT FLOOR, not throughput
Earlier sections treated 32 Mpix/s (from timeout pixels/32000) as the engine's real throughput and concluded
"8× too slow / stills-class / lossless UHD-to-SD infeasible". THAT WAS WRONG — 32 Mpix/s is a watchdog timeout
(~9× safety margin), proving only real throughput ≥ 32. (Classic "self-consistent wrong values" trap.)
Corrected engine spec (agent RE):
- Clock ≈ **300 MHz** [I; supporting interpretation withdrawn 2026-10-15] — the 300000000 constant in
  `C070BE68` is a video-codec processing-budget constant, not a measured `0x300D` clock. The original inference
  used the shared domain via `FUN_c062fee8 → FUN_c07095a8(5,1)`.
- **~1 pixel/clock** [I] — timeout formula is bit-depth-independent (10-bit NOT faster than 14-bit); bitdepth
  only scales output-packing stride regs +0x6C/+0x70. Classic 1-sample/clock predictor+Huffman.
- ⇒ theoretical ceiling **~300 Mpix/s** [I]; best estimate **~150–300 Mpix/s**; firm floor 32 [C]; true
  sustained UNKNOWN [P] (Huffman VLC + DMA stalls + per-stripe power-cycle overhead pull it below ceiling).
- **Single engine** (register-pattern 40/44/48/4c/6c/70/78/7c set appears ONLY at 0x300D) — no parallel 2nd
  instance [C]. **Not safely overclockable** — clock shared with sensor readout, no software divider [C/P].
- Per-stripe power cycling: FUN_c062fe70 (on) / FUN_c062fe80 (off) each stripe; a ≤64MB frame = 1 stripe = 1
  power cycle (amortized); small frames pay full settle each call.

### REVISED VERDICT — lossless compressed UHD RAW to SD
UHD30 lossless needs 248.8 Mpix/s. If the engine sustains ≥~250 Mpix/s (within its ~300 ceiling), then:
compress UHD30 lossless ~2:1 → ~186 MB/s → fits top UHS-II SD; gate is soft/patchable; 0x300D is IDLE during
video (video uses DSP 0x301B + RFC 0x300C, not the lossless engine) → no ISP-engine contention. **⇒ lossless
compressed UHD RAW to SD @30fps is POTENTIALLY FEASIBLE — hinges entirely on the true sustained Mpix/s (32–300,
unmeasured).** No residual/lossy/frame-split tricks needed if the engine is fast enough.

### THE decisive live probe (low-risk, idle only)
Measure real throughput: while camera idle, drive 0x300D on a known 1KB-aligned buffer (init FUN_c05a6890 →
encode FUN_c05a6920), and TIME the IRQ-0x29 completion (or poll 0x300D0000/0x3FC done-bit) against the pixel
count. Repeat for a few sizes to separate fixed overhead from per-pixel rate → gives sustained Mpix/s → settles
whether lossless UHD video-rate is real. Contention-safe (engine idle when not shooting stills).

## ADVERSARIAL HARDENING (2026-08-20) — confirmed
- **The old two-engine inventory was incomplete (corrected 2026-10-15).** In addition to `0x300D` lossless-JPEG
  and `0x301B` lossy JPEG, the MOV SDK configures a video codec at `0x300Cxxxx`. `C070B7A0` configures its
  encoding parameters, and `300C0208` contains GOP and processing-budget fields; it was incorrectly described
  here as a sensor clock divisor. HEVC has a candidate driver branch. Direct Bayer input and 10-bit video
  capability remain unverified. The CPU-only Lz4/SRLE library is a separate, off-Bayer-path implementation.
- **0x300D cold-standalone-callable confirmed** — wrappers self-satisfy all prereqs: event flag DAT_c2f2e60c
  lazy-created by RAWCD(); power domain 5 + clock + IRQ0x29 brought up inside FUN_c062fee8 (FUN_c0708c60(1),
  FUN_c06304f0 0x30000814|=0x2008, FUN_c07095a8(5,1), one-time IRQ guard _DAT_c37cf878, FUN_c0630480(1)); mode
  byte _DAT_c37cf87c set by programmer. NO dependency on live capture / RFC-active / calibration — synthetic
  src buffer works. Power domain 5 is REFCOUNTED (FUN_c070dc18, table DAT_c38d6124+domain*4) → codec power-off
  won't gate the sensor if RFC holds it → safer than feared. Guards all caller-controlled (geom 8..0x4000/
  align 1KB). Residual: single engine no mutex → invoke ONLY while idle. [C]
- **Throughput bottleneck = VLC samples/clock, NOT DMA** — the +0x78/+0x7c/+0x84 regs are src/2nd/3rd DRAM
  base addresses (>>10, 1KB-aligned), NOT burst config; there is no burst-length register. Input read only
  450-600 MB/s < DDR. Every practical frame (UHD/FHD/full-still) = 1 stripe (64MiB band budget FUN_c062f478)
  = ONE kick / ONE IRQ0x29 / ONE domain-5 cycle. No perf counter anywhere → real Mpix/s unmeasured in
  firmware. Only risk to UHD30: VLC sub-1-px/clk on high-entropy tiles (unobservable statically). [C/I]
- **NO latent compressed-video path** — CinemaDNG hard-wired Compression=1. Only cam_still_raw_compress
  (0xc375955c, still-only). Compress flag byte at (image-desc)+4 set by ONE fn FUN_c06a3730 with ONE caller
  XC_StillCreateFile__v4 @c037e0f8 (still capture). CinemaDNG quality enum 0..4 = bit-depth, not compression.
  ⇒ movie compression must be BUILT by us (DNG writer exists, just not wired to MovRecFuncStateCinemaDng). [C]
⇒ Net: HW compression is real, standalone-callable, idle-safe, nothing better hidden. ONLY open question =
  true sustained Mpix/s (32–300), settleable ONLY by live IRQ-0x29 timing probe.

## ⚠️ LIVE TEST 2026-08-30 — the engine is NOT cold-standalone-callable

First time the engine was actually driven on hardware, over the USB shell with
`callfn`. The ABI is right and the throughput is still unmeasured, because the
call never reaches the engine.

**What works.** `FUN_c05a6890(&initStruct)` returns 1 (success) and latches our
buffers into the globals — read back live: `_DAT_c302cdd4`=src,
`_DAT_c302cddc`=work, `_DAT_c302cde4`=dst. initStruct layout as documented.

**What fails.** `FUN_c05a6920(&encStruct)` returns 0. Its convention, from
`C05A6974-C05A697C`: inner result 0 → return 1 = SUCCESS; non-zero → return 0 =
FAILURE. So 0 is a real failure, not a quiet no-op. Timing 5-6 ms (once 68 ms),
far under the ≥100-tick timeout, so it exits early.

Bisected by calling each step directly:

```
FUN_c062f440   event flag           OK   flag id 146 at 0xC2F2E60C, created
FUN_c062fee8   bring-up             ret 1  FAIL
  FUN_c0708c60(1)   power domain    ret -99 (0xFFFFFF9D)   FAIL  <- root
  FUN_c06304f0()                    ret 0   OK
  FUN_c07095a8(5,1) clock domain 5  ret 1   FAIL
  FUN_c0630480(1)                   ret 0   OK
FUN_c0630208   kick                 ret 1  FAIL
```

`FUN_c0708c60` takes one argument and is a thin wrapper: it calls
`FUN_c01222f8(3, 0, arg)` and returns 0 when that answers 0 or 1, otherwise
`mvn #0x62` = -99. So -99 means the power manager refused the request. **The
domain-5 request is refused too.** This contradicts the earlier
adversarially-hardened claim that 0x300D is "cold-standalone-callable and
idle-safe (refcounted domain 5)" — that was static reasoning, and live it is
wrong.

**Two other traps found the same session.**

- **MMIO 0x300Dxxxx reads back all zeros through the shell's `mem get`** —
  control, status, width, height and the produced-byte count at +0xF8 alike,
  including geometry we had just programmed. The byte count of 0 proves nothing.
  Same shape as the 0x3011xxxx registers that misled this project before: the
  probe's own output has to be validated before it is used as evidence.
- **The IMAGE region is not idle during live view.** Borrowed
  0x49801000/0x49C01000/0x4A001000 out of its 17.8 MB; the contents changed
  between reads on their own (`803F813F...` → `80098110...`), so nothing written
  there can be read back as proof either.

**What this means for compressed CinemaDNG.** The open question is unchanged --
real sustained Mpix/s, somewhere in 32..300 -- but the way in has to change. The
engine will not come up on request from an idle camera in STILL_REC; whatever
grants that power domain has to be understood first, or the encode has to be
driven from inside the still path that already owns it (hook the real call site,
blk_c03.c:85623-85636, rather than calling the API cold).

`memmgr bufmem get` is also unusable from the shell: 8 MB and 16 MB both wedged
the worker and cost a battery pull. Borrow from the `memmgr bufchk` map instead.

## LIVE 2026-08-30 (2) — hooked the real still path; power domain 3 is the wall

The engine fails inside a genuine still capture too, in exactly the way it fails
cold, so the earlier result was not an artefact of calling it from the shell.

**The hook.** One word: the `bl 0xC05A6920` at **0xC037E7AC** (still path;
0xC037E760 init, 0xC037E7AC encode, 0xC037E7C8 size, all one function) redirected
to `raw/ljtime.S` at 0xC072E100. It times the call and passes r0 and the return
value straight through, so the caller at 0xC037E7B0 cannot tell. Restore by
writing 0xEB08A05B back and calling FUN_c000e91c.

**The clock.** `FUN_c002b6e0` — what the gyro logger has always used as its batch
timestamp — is a **1 MHz microsecond counter**: 2,008,597 units across 2.01 s
measured host-side, 999,993/s. Free-running, callable from any context, and
already proven by every take the logger has written.

**What a real capture reported.** count=1, geometry **6064x4042 = 24.51 Mpix**
(full sensor, so the hook is on the real path), result **0 = FAILURE**, elapsed
**14 us** — and 11 us on a second shot. The same instant bail as the cold call.
The caller checks it (`cmp r2,#0; beq 0xC037E848`), so the firmware sees the
failure and takes its fallback.

**Root cause, one level deeper than last time.** `FUN_c0708c60(1)` wraps
`FUN_c01222f8(3, 0, 1)` — power domain **3**. That function returns 4 when
`[0xC31D7FC0]` is zero, 3 for a domain outside 0..0x1e, 2 for arg >= 7, else the
result of `FUN_c0122148`. Live:

```
[0xC31D7FC0]                = 1     the manager IS initialised
FUN_c01222f8(dom=3, 0, 1)   = 4     <- what bring-up asks for; refused
FUN_c01222f8(dom=5, 0, 1)   = 0     granted
```

Domain 3's 4 therefore comes from `FUN_c0122148`, not from the readiness check —
the manager is up and specifically declines domain 3. Granting domain 5 by hand
first does not help: bring-up still fails, and so does `FUN_c07095a8(5,1)`.

**Settings found while looking for an enable.**

- `setting get/set cam_still_raw_compress` works (name at 0xC0BC963C, in the
  `cam_*` settings-name table). It read 0; setting it to 1 and shooting changed
  nothing — the engine failed identically. Restored to 0.
- `menu SetStillDNGQuality` with no argument returns the current value: **1**.
- **`menu SetMovCinemaDNGQuality` exists and reads 0** — a per-movie CinemaDNG
  quality setting in the firmware's own menu API. Worth pursuing on its own.
- Both setters answer OK to 0..4 with no validation, so what they accept says
  nothing about what the values mean. Left as found (1 and 0).
- `menu dump` is a raw hexdump of the active settings block at **0xC31B32BC,
  2496 bytes** — no labels, so field offsets have to come from the setters.

**Where this leaves the open question.** Sustained Mpix/s is still unmeasured.
The instrument now exists and is proven (hook + microsecond clock, reporting real
geometry from a real capture); what is missing is a camera state in which power
domain 3 is granted. Next: read `FUN_c0122148` to see what makes a domain
available, or find which subsystem holds domain 3 and when.

## MEASURED 2026-08-30 — 169.7 Mpix/s

The number the whole compressed-CinemaDNG question hung on, from a real still
capture on a healthy camera, with the timing hook at 0xC037E7AC:

```
6064 x 4042 = 24,510,688 px    full sensor, so this is the real path
result 1 = success             the caller's own convention
144,431 us                     FUN_c002b6e0, a 1 MHz counter
                               -> 169.7 Mpix/s
```

The firmware's `pixels/32000` watchdog is therefore a **5.3x** margin, not a
throughput figure. The old "8x too slow, lossless UHD impossible" conclusion was
built on reading that deadline as a rate; it was wrong, and so is any claim that
the engine is stills-class.

| | needs | verdict |
|---|---|---|
| UHD 3840x2160 @30 | 249 Mpix/s | short — engine does 20.4 fps at UHD |
| UHD 3840x2160 @24 | 199 Mpix/s | short |
| FHD 1920x1080 @30 | 62 Mpix/s | **feasible, 2.7x headroom** |
| FHD 1920x1080 @24 | 50 Mpix/s | **feasible, 3.4x headroom** |

One sample, and a busy scene: the file came out 36.1 MB against ~51 MB
uncompressed, about 1.19:1, well under the 2.3:1 in these notes. Lossless JPEG is
entropy coding, so a flat frame should encode faster — the spread is unmeasured
and the numbers above may be the slow end.

**A stills camera compresses by default, and we broke it.** File sizes on the
card: 26-28 MB before today, 51.1-51.2 MB for three shots taken after our cold
probing, 36.0 MB on the first shot after a power cycle. The engine really was
dead for those three, and it stayed dead until the battery came out. Cause: the
cold sequence in the previous section -- `FUN_c05a6890` (which overwrote the
still path's own src/work/dst globals), four failed encodes, `FUN_c062fee8`,
`FUN_c0630208`. These notes already said the engine is a single global with no
mutex that must only be touched while idle. **Do not call it; hook it.**

**Opportunistic compression is legal.** CinemaDNG is one file per frame and each
carries its own Compression tag, so a sequence may mix 1 and 7 freely and any
decoder will read it. At UHD30 the engine keeps up with about two frames in
three, which is roughly a third off the write bandwidth -- the real gate for
UHD-to-SD -- and would move uncompressed UHD-to-SD from ~12 fps toward ~17-18.
FHD needs no such scheduling at all.

## Movie frames do NOT go through the shared file writer

`FUN_c06a4990` is where sixteen callers meet and everything below it -- including
the DNG writer `FUN_c06a5290` that emits the Compression tag -- is shared. A
trampoline on its prologue (`raw/whowrites.S`, logs lr into a ring) says:

```
one still            10 calls   0xC03A31B4 x6, 0xC03A0ED4 x2
one 2-3 s clip       13 calls   the same two, plus 0xC038A238 x1
```

A 2-3 s FHD clip is 60-90 frames, so **the per-frame DNG write is not on this
path** — it belongs to a separate, faster one, which is what a writer sustaining
149+ MB/s would need. The Compression-tag writer under `FUN_c06a4990` is the
stills writer; movie frames build their headers elsewhere, and that code is what
has to learn to emit Compression=7.

Where that is remains open. The per-frame filename comes from `'_%06d.%s'` at
0xC0B55C46, built by `FUN_c030aca0`, reached from `FUN_c030abe0` <- `FUN_c030b068`
— and `FUN_c030b068` has no direct callers, so the movie path dispatches through
a C++ vtable (`RecordFilePathInfoCinema`, name at 0xC0B55A90). Next step is to
hook `FUN_c030aca0` and count calls across a recording: if it fires once per
frame it is the anchor into the movie path, and the writer is a short walk from
there.

Also settled: **the CinemaDNG quality enum (`menu SetMovCinemaDNGQuality`, 0..4)
is bit depth, not compression** — and `cam_still_raw_compress` is 0 on a camera
that is compressing normally, so it is not the switch either. Both setters accept
0..4 without validation, so what they take says nothing about what they mean.

### The movie frame path, found by counting (2026-08-30)

`raw/tapcount.S` is a generic counting trampoline: the host fills in the
displaced instruction and the continuation address at install time, so it drops
onto any function with a position-independent prologue without writing a new
stub. Installed on `FUN_c030aca0`, the per-frame filename builder (`'_%06d.%s'`
at 0xC0B55C46), across one recording:

```
FUN_c030aca0 calls   164        caller 0xC0376CA0 dominates
frames in A001_020   157        the extra 7 are clip-level files
```

So `FUN_c030aca0` is per-frame, and the chain into the movie writer is:

```
0xC0376CA0   blx r2 -> FUN_c030aca0     path built, copied to (frame obj)+0x1030
0xC0376B20   the enclosing file-creation function; takes F_VOL 0xC0444658
0xC0372CE0   bl 0xC0376B20              per-frame driver
0xC0372D90   bl 0xC0372DE8 (r1 = frame obj)   <- the actual frame writer
```

`FUN_c0372de8` calls into 0xC0698FF8 / 0xC0699288 / 0xC0423xxx — the 0xC069xxxx
neighbourhood of the DNG writer at 0xC06A5290. That is where the movie DNG header
is built and where Compression=7 would have to come from.

Not yet done: reading a movie frame's actual DNG header. `getfile.py` is
unreliable at these sizes -- it wedged the worker once and froze the camera once,
both needing a battery pull. Read a frame from the card instead.

### What a movie frame actually is (read from the card, 2026-08-30)

`\CINEMA\A001_020\A001_020_20260830_000001.DNG`, FHD 30p, 3,244,544 bytes:

```
IFD0, 58 tags, no SubIFDs -- the image is IFD0 itself
ImageWidth      1936        ImageLength   1090
BitsPerSample   12          WhiteLevel    4095
Compression     1                      <- uncompressed
Photometric     32803 (CFA)
StripOffsets    78848       RowsPerStrip 1090
StripByteCounts 3,165,372
```

**One strip for the whole frame, and a fixed 78,848-byte header.** That is the
easiest shape this could have taken: making it compressed touches three fields
and nothing else.

```
Compression      1 -> 7
StripByteCounts  3,165,372 -> whatever the engine produced
StripOffsets     unchanged at 78848
file length      78848 + N
```

The other 55 tags stand. DNG allows Compression=7 with strips -- no tile table,
no TileOffsets/TileByteCounts, no structural change. At 1936x1090 = 2.11 Mpix and
the measured 169.7 Mpix/s that is 12.4 ms a frame against a 33 ms budget at 30p.

Still open: where between "frame in DRAM" and "bytes at offset 78848" to
intervene. `FUN_c0372de8` (r1 = frame object) is the writer; the pixel source and
the write call inside it are the next thing to find.

### The per-frame path, measured rather than guessed (2026-08-30)

Every step below was settled by counting calls on the camera, because two
attempts at picking the likely branch out of the disassembly both led to probes
that never fired.

```
FUN_c030aca0    per-frame filename          164 calls / 157 frames
  called from 0xC0376CA0, a `blx r2` inside
FUN_c0376b98    per-frame file creation      75 calls /  74 frames
  called from 0xC037A51C, and only from there
0xC037A574      `blx r1` -- the last act of the per-frame function
  r0 = 0xC3438400 (file object)   r1 = FUN_c030b2e8
```

`FUN_c030b2e8` turned out to be a commit, not a write: it bumps two counters at
+0x14 and +0x1c and calls `FUN_c030bc40(obj+8)`. **The frame bytes are written
asynchronously by a writer task** — which is what a path sustaining 149 MB/s has
to do, and it means there is no single call holding both the header and the
pixels to intercept.

Dead ends worth not repeating: `FUN_c0372de8`, reached by following
`FUN_c0376b20`'s other caller `0xC0372CE0`, is never called during recording (a
probe on it counted 0 across a whole clip). The literal 78848 and 3244544 appear
only in resource data, not in code. `0xC37CE210` = {1936, 1090, 3244544} is the
recording geometry, confirmed live, but the header size and StripByteCounts are
not near it.

**Still open: where the DNG header is assembled.** That is the interception
point — Compression and StripByteCounts live there, and the compressed bytes have
to reach the writer in place of the raw strip. Next probe: capture the queued
request at the commit (`FUN_c030bc40`) and follow it to the buffer the writer
task takes, rather than looking for the header in the frame-producing code.

### The power manager's tables (read live, 2026-08-30)

`FUN_c01222f8(domain, sub, on)` at 0xC31D7FC0:

```
0xC31D7FC0        readiness flag, 1
0xC31D7FC4        ownership table, entry = [sub + domain*7], -1 = free
0xC31D830C        group id per sub-index; sub 0 -> group 2
0xC31D8328        second readiness byte, 1
0xC31D832C        client table, 4 words per group
```

Live, with the camera idle:

```
domain 3 row   -1 -1 -1 -1 -1 -1 -1     free, not held by anyone
domain 5 row   -1 -1 -1 -1 -1 -1 -1
group 2        0  0  0xC0122BF1  0      a Thumb code pointer in slot 2
```

So the 4 that `FUN_c01222f8(3,0,1)` returns does **not** mean "in use" or
"unavailable": the entry is free, the function calls `FUN_c0122400` to claim it,
re-reads the entry, finds it still -1, and reports 4. **The claim does not
stick.** `FUN_c0122400` walks the group's client table and does its work through
whatever is registered there; why that leaves the entry unclaimed for us and not
for the still path is the open question.

What is certain: the still path claims it successfully, because the encode
measured 169.7 Mpix/s from inside a real capture. So the difference is context,
not capability.

Next experiment: log `FUN_c01222f8`'s arguments and result during a real still
capture and compare with ours. Both it and `FUN_c0708c60` are Thumb, so the
trampolines here (`raw/tapcount.S`, `raw/tapargs.S`, `raw/tapblx*.S`, all ARM)
need a Thumb variant first.

## THE BLOCKER IS GONE — the recording pipeline can power the engine

Two probes settle it. First, `raw/tappwr.S` -- a Thumb trampoline on the `bl`
inside `FUN_c0708c60` (0xC0708C6C; the BL encoder was proved by recomputing the
original instruction and matching the camera byte for byte) -- watching a real
still capture:

```
FUN_c01222f8(3, 0, 1)  ->  0    power domain 3 on, inside the still path
FUN_c01222f8(3, 0, 0)  ->  0    and off again when done
FUN_c01222f8(3, 0, 1)  ->  4    the same call from the shell's borrowed handler
```

**Identical arguments, opposite answers.** The gate is the calling context, not
the parameters, and the still path releases the domain after use.

Then `raw/pwrtest.S` on the per-frame function `FUN_c0376b98`, asking from
inside the movie pipeline on the first frame of a recording:

```
FUN_c0708c60(1)     power domain 3   ->  0    granted
FUN_c07095a8(5,1)   clock domain 5   ->  0    granted
FUN_c0708c60(0)     released          ->  0
```

So the engine is available to code running in the recording path. Everything
this project concluded about the engine being unreachable was about the USB
shell's context and nothing else.

What that leaves for compressed FHD CinemaDNG:

```
throughput      169.7 Mpix/s measured        FHD needs 62 -- 2.7x headroom
engine access   granted inside recording     just proved
frame format    one strip, header 78,848 B   two fields change: Compression,
                                             StripByteCounts
remaining       where the DNG header is assembled
```

The last line is engineering, not an unknown: the shape of the answer is known,
only its address is not.

## The writer already does compression — read from the decompilation

`out/decomp/full/blk_c0*.c` is a full decompilation covering every function this
project has been reading as disassembly, and `out/decomp/rtti_classes.txt`
resolves the C++ dispatch that cost several probes today. Use it first.

`FUN_c06a5290` — the writer these notes named all along — builds the IFD, and the
compression branch is already there:

```c
cVar1 = *(char *)(iVar2 + 4);            /* the compress flag */
local_34 = (cVar1 == '\0') ? 1 : 7;
FUN_c00ba378(param_2, 0, 0x103, 3, 1, &local_34);      /* Compression */

if (cVar1 == '\0') {                     /* 0x111 StripOffsets
                                            0x116 RowsPerStrip
                                            0x117 StripByteCounts */
} else {  local_4c = 0x100;  FUN_c00ba378(param_2,0,0x142,...);  /* TileWidth  */
          local_48 = 0x100;  FUN_c00ba378(param_2,0,0x143,...);  /* TileLength */
          FUN_c00ba378(param_2,0,0x144,4,*(int *)(iVar2+0x18),0); /* TileOffsets */
          FUN_c00ba378(param_2,0,0x145,4,*(int *)(iVar2+0x18),0); /* TileByteCounts */ }
```

So compressed DNG is **tiled at 256x256**, which is exactly the tileW/tileH the
still path hands the engine — the whole chain is consistent, and nothing about
the DNG structure has to be built by us. An earlier note here that movie frames
would need Compression=7 with a single strip is wrong; follow the firmware's tile
path instead.

`iVar2+4` is the same flag `FUN_c06a3730` sets (`strb #1, [r4,#4]`).

**The movie header is a per-clip template.** Comparing the 78,848-byte headers of
consecutive frames from one clip:

```
frame 1 vs 2    9 bytes differ
frame 1 vs 3   12 bytes differ
   +0x3E2/3EA/3F2/3FA (one value in four places), +0x50A,
   +0x410C, +0x43BE, +0x4463, +0x6F4B, +0x6F54
```

All metadata — timestamps, a counter, exposure fields. **No tag value changes**,
because every uncompressed frame has the same StripByteCounts. That is why the
per-frame probes never saw `FUN_c06a5290`: the header is built once per clip,
among the ~13 calls the shared writer sees at clip start.

Which is also the real difficulty. Compressed frames each have their own tile
sizes: 1936x1090 in 256x256 tiles is 8 x 5 = **40 tiles**, so TileOffsets and
TileByteCounts are 160 bytes each and both change every frame. The firmware
already patches nine bytes of header per frame, so a per-frame patch path exists
— extending it to carry the two tile tables is the work.

### Who owns what, from RTTI (out/decomp/rtti_classes.txt, 2461 classes)

```
XC_StillFileFormatDngTh              the DNG writer FUN_c06a5290 belongs to this
                                     -- Still, which is why per-frame probes on
                                     the movie path never reached it
MovRecFuncStateCinemaDng             : XC_RecFuncStateCommon
CinemaDngRawMemInterface             : XC_LiveViewRawMemInterface
CinemaDngFileReader / TagReader      : XC_ThreadEntryBase   (playback)
MenuItemMovieCinemaDNGQuality        : MenuItemCommon<eRawBitType>
```

That last line settles it by type name: **the CinemaDNG quality menu item is
`eRawBitType`** — bit depth, not compression. No more probing that setting.

And there is **no CinemaDng writer class** in the table: the readers exist
(FileReader, TagReader, PlayThread), the writer does not. So the movie frame's
DNG is not produced by a peer of `XC_StillFileFormatDngTh`; it is written by
something else, and `CinemaDngRawMemInterface` is the likeliest thread to pull
next — it is where the raw frame memory is handed over.

The header being 78,848 bytes is not a constant anywhere in code, so it is not a
memcpy'd template: it is what the tag writer lays out and pads to. Consistent
with the nine bytes that differ between consecutive frames being metadata values,
not structure.

## The whole recipe, in C (blk_c03.c:85604-85650, the still path)

`FUN_c06a3730` — the compress flag — has exactly one caller in the firmware, and
this is it. Everything the engine needs is here:

```c
local_1d4 = (**(code **)(*(int *)(iVar5 + 0x14) + 0x58))(iVar5);   /* image desc */

local_e4 = *(param_2 + 0x10);        /* width                */
local_e0 = *(param_2 + 0x14);        /* height               */
local_dc = *(param_2 + 0x30);        /* bitdepth code        */
local_d8 = 0x100;  local_d4 = 0x100; /* tile 256 x 256       */
local_d0 = *(int *)(param_2 + 300) ? *(param_2 + 300) : *(param_2 + 0x68);  /* SRC */
local_cc = *(undefined4 *)FUN_c0398b00();   /* work buffer   */
local_c8 = *(undefined4 *)(local_1d4 + 0xc);/* DST, from the descriptor */
local_c4 = local_c4 & 0xffffff00;    /* mode flag 0          */
FUN_c05a6890(&local_e4);             /* init                 */

/* encStruct: the same geometry again */
iVar7 = FUN_c05a6920(&local_f8);     /* encode, blocking     */
if (iVar7 != 0) {
    iVar7 = FUN_c05a6990(*(undefined4 *)(local_1d4 + 0x10), 1);  /* size table */
    if (iVar7 != 0) {
        FUN_c06a3730(local_1d4);     /* mark it compressed   */
    }
}
```

**The descriptor carries the buffers.** `+0xC` is where the compressed bitstream
goes, `+0x10` is where the per-tile size table goes, and `+0x18` (read by
`FUN_c06a5290`) is the tile count. So the forty TileOffsets and TileByteCounts a
compressed FHD frame needs are **not ours to build** -- `FUN_c05a6990` fills the
table and the existing writer emits both tags from it. That removes the one part
of this that looked like real work.

What a movie frame needs, then, is the same five steps against its own
descriptor. The open question narrows to: does the movie frame path have a
descriptor with this layout, and if so, who writes its DNG. The still writer
belongs to `XC_StillFileFormatDngTh`, and no CinemaDng writer class exists in the
RTTI table, so that is where to look next.

Also from the same source: `FUN_c0398b00` returns the work buffer the engine
needs, so we do not have to find or allocate one.

### Only the still writer can emit tiles — so do not use tiles

Every function in the firmware that writes TileWidth/TileLength/TileOffsets/
TileByteCounts (0x142/0x143/0x144/0x145) belongs to one class:

```
FUN_c06a5290  FUN_c06a56c8  OpNewCore<<unnamed>::XC_StillFileFormatDngTh>::v9
```

The movie frame writer has no compression branch at all, so "set the flag and let
the firmware emit a compressed DNG" does not transfer from stills to movies. The
`MovRecFuncStateCinemaDng` methods (all 24, decompiled with names in
`out/decomp/dng_named/dng_named.c`) touch neither the engine nor any TIFF tag —
they are the recording state machine, not a writer.

**The way around it is to never need tiles.** Compression=7 with strips is legal
DNG, and the engine's tile size is an argument we supply:

```
still path passes   tileW = tileH = 0x100   ->  8 x 5 = 40 tiles -> tile tags
we can pass         tileW = 1936, tileH = 1090 -> one tile -> one strip
```

Geometry allows it: width must be a multiple of 8 (1936 is) and height even
(1090 is). Then the movie header changes in exactly two fields:

```
Compression      1 -> 7
StripByteCounts  3,165,372 -> whatever the engine produced
StripOffsets     unchanged at 78848
```

No tags added, no IFD entries shifted, no 160-byte tile arrays to place in the
header's padding. The tile route would replace three entries with four and move
everything after them.

So the earlier "one strip" note was right after all, but for a different reason
than it gave: not because a movie frame must be a strip, but because we can ask
the engine for a single tile and sidestep a capability the movie writer lacks.

Unverified: that the engine accepts a tile as large as the whole frame. The
constraints in these notes cover the image geometry; whether tileW/tileH share
the 8/even rule and the 0x4000 ceiling is stated but not tested. That is the
first thing to check, and it can be checked from inside a still capture where the
engine is already powered.

### The engine's real limits (FUN_c062fff8, and one measurement)

Asking for a tile the size of the whole frame fails: `raw/tiletest.S` copied
width and height over tileW/tileH inside a real 6064x4042 still capture and the
encode returned 0 after 172 us -- a parameter refusal, not work attempted. The
reason is in `FUN_c062fff8`, which programs the MMIO block:

```
width   >= 8      <= 0x4000    multiple of 8
height  >= 2      <= 0x4000    even
tileW   >= 0x20   <= 0x200     multiple of 32      <- 512 maximum
tileH   >= 2      <= 0x200     even                <- 512 maximum
all five buffer addresses      1 KB aligned
```

`FUN_c062f478` -- the other size check -- is a 64 MB working-set cap and passes
for anything this camera shoots, so the tile ceiling is the only real limit.

**So a single-tile frame is impossible and the strip plan is dead.** FHD
1936x1090 at the largest legal tile, 512x512, is ceil(1936/512) x ceil(1090/512)
= 4 x 3 = **12 tiles**, minimum. TileOffsets and TileByteCounts are unavoidable,
and the movie writer cannot emit them.

The way through is not in-place surgery on the IFD. The header is 78,848 bytes of
which the IFD is 702, so there is room to **build a fresh IFD in the padding**
with Compression=7, TileWidth/TileLength, TileOffsets and TileByteCounts, and
repoint the first-IFD offset at file offset 4. Two arrays of twelve u32s is 96
bytes; the entry count goes from 58 to 59 as three strip tags become four tile
tags. Nothing existing has to move.

That is the design. Per frame: run the engine at 512x512, take the size table
from descriptor+0x10, lay out the new IFD, repoint offset 4.

### The descriptor, and four reusable pieces

`FUN_c06a3650`, from `src/library/FileMgr/src/XC_DngTileFormatter.cpp` —
a **library** module, not part of the still path — is the tile offset
accumulator, and it spells out the whole descriptor:

```c
*(desc+0x14)[0] = firstOffset;                     /* TileOffsets[0]        */
for (i = 1; i < *(uint *)(desc + 0x18); i++)       /* tile count            */
    TileOffsets[i] = TileByteCounts[i-1] + TileOffsets[i-1];
```

```
desc+0x04   compress flag        set by FUN_c06a3730
desc+0x0C   compressed bitstream buffer
desc+0x10   TileByteCounts[]     filled by FUN_c05a6990 from the engine
desc+0x14   TileOffsets[]        filled by FUN_c06a3650
desc+0x18   tile count           read by FUN_c06a5290
```

So compressed DNG is four ready-made pieces: encode, accumulate offsets, set the
flag, emit the tags. **All of them are library code.** What the movie path lacks
is not capability but wiring -- nothing calls them for a movie frame.

Module map, from the firmware's own `__FILE__` strings:

```
0xC0B9E5AC  src/framework/recMgr/src/CinemaDngFile.cpp   -> FUN_c03a4xxx
            (= out/decomp/dngwrite.c; FUN_c03a4d00 is the clip-level setup
             that also writes SPP_metadata.xmp)
0xC2E3A0CC  src/library/FileMgr/src/XC_DngTileFormatter.cpp -> FUN_c06a3650
0xC2DFD2F0  src/library/CinemaDngPlay/...                   playback only --
            CinemaDngRawMemInterface belongs here, not to recording
```

Listing these `src/...` strings and finding who references them is far faster
than following call graphs, and it is how both of the above were found. Do that
first next time.

### CinemaDngFile.cpp is not the frame writer either

All seventeen functions in the module (0xC03A4438..0xC03A5050, decompiled as
`out/decomp/dngwrite.c`) were read. **None touches the compression pieces** --
no call to FUN_c05a68/69xx, FUN_c06a3650 or FUN_c06a3730 anywhere in it. What it
actually does:

```
FUN_c03a48e8   remaining-capacity estimate: 64-bit free space / per-frame size
FUN_c03a4b00   feeds it
FUN_c03a4d00   clip-level setup, and writes SPP_metadata.xmp
FUN_c03a4c00   the one that reaches the shared file writer FUN_c06a4990
```

So the movie side of `recMgr` handles capacity, the clip folder and the sidecar,
and the per-frame DNG bytes are produced somewhere else again -- consistent with
a path that has to sustain 149 MB/s not going through the generic machinery.

Still unfound: where a movie frame's header and pixels are assembled. What is now
excluded, each by evidence rather than by reading: the shared file writer
(13 calls per clip against 157 frames), `FUN_c0372de8` (probe counted 0 across a
clip), the 24 `MovRecFuncStateCinemaDng` methods (touch no tag and no engine),
`CinemaDngRawMemInterface` (belongs to CinemaDngPlay, playback), and now this
module.

The header offsets that differ frame to frame -- 0x3E2/0x3EA/0x3F2/0x3FA, 0x50A,
0x410C, 0x43BE, 0x4463, 0x6F4B, 0x6F54 -- all sit past the 702-byte IFD, so they
are out-of-line tag values (timestamps and counters), not structure. Whoever
writes those is the per-frame path, and finding the code that touches those
offsets is the next thread to pull.

## Movie frames never touch the file API — that is why every probe missed

`FUN_c03660e8(file, buf, len)` is the MediaFile write, the vtable +0x14 dispatch
in `src/hal/MediaDriver`, through which the general file machinery puts bytes on
the card. `raw/tapwrite.S` on it, across a whole one-second clip:

```
buf 0xC3A42B74  len       298    the SPP_metadata.xmp
buf 0x45166700  len       940    a small file
buf 0x52B00580  len   475,136    audio -- 0x52Bxxxxx is MOVAUDIO in bufchk
                                 THREE calls, and not one frame
```

**The CinemaDNG frames do not go through it.** They are written by a dedicated
path straight to the SD controller, which is the only way to hold 149 MB/s, and
it explains every dead end today: the shared file writer saw 13 calls per clip,
`FUN_c0372de8` saw none, the state machine touches no tags, `CinemaDngFile.cpp`
does capacity and the sidecar. All of them are the general machinery, and the
frames are not in it.

The assumption underneath all of those probes -- that a frame must pass through
some file-write function -- was wrong from the start.

So the header and pixels are assembled in a buffer that a DMA path consumes.
Finding the code that fills that buffer is the remaining work, and the way in is
the buffer, not the call graph: the header is a template patched at fixed offsets
(BlackLevel 50714, RawDataUniqueID 50781, TimeCodes 51043 -- the only three tags
whose values differ between consecutive frames), so whoever patches those offsets
is holding its address.

## Where to intervene: frame+0x138, vtable +0x14

Following the buffer instead of the call graph found it. `FUN_c0374268` prepares
each frame's record, and `vbuf` repeats the same two lines:

```c
iVar7 = (**(code **)(*(int *)(*(int *)(frame + 0x138) + 8) + 0x14))(*(int *)(frame + 0x138));
*(int *)(frame + 0xffc) = *(int *)(frame + 0x128) + iVar7;
```

```
frame + 0x138   the image/format object
   vtable +0x14 returns this frame's byte count   <- the single source of size
frame + 0x128   base position
frame + 0xffc   running file position
frame + 0x1c0   this frame's size, accumulated into the clip total at +0x98
frame + 0x1060  copied metadata           frame + 0x1030  the path
```

Everything downstream -- file position, the clip's byte total, the
remaining-capacity estimate in `FUN_c03a48e8` -- derives from that one virtual
call. **Compression has to change what it returns, and because it is virtual,
replacing it is cleaner than chasing the arithmetic that consumes it.**

That gives the shape of the implementation:

```
1. per frame, before the size is asked for:
   run the engine on the frame (512x512 tiles, 12 for FHD)
   FUN_c05a6990 -> TileByteCounts at desc+0x10
   FUN_c06a3650 -> TileOffsets at desc+0x14
2. patch the header template: Compression 1 -> 7, strip tags -> tile tags
3. return the compressed size from frame+0x138's vtable +0x14
```

Still to find: which object sits at frame+0x138 and where its data buffer is.
But the anchor is no longer a guess -- it is the one call every byte of
accounting comes from.

## Yes, the frame passes through DRAM — IMAGE is the ring

`memmgr bufchk` with the camera in movie mode reports `mem mode =
MOVIE_REC_DNG (3)` and a different map from STILL_REC. Sampling the large
regions:

```
IMAGE  0x49800FC0  17,822,464 B   7F097F12 7F107F07 ...  16-bit pixel pairs
LVIEW  0x4A900340  12,515,520 B   1B211D1D 1A1E1C1D ...  8-bit, live-view YUV
OSD    0x467FEA00  47,185,984 B   code pointers, not pixels
```

Read twice two seconds apart, **every word of IMAGE and LVIEW had changed** --
live data, not residue. 17,822,464 / 3,165,372 = 5.6, so IMAGE holds about five
frame buffers.

**So the soft-hook premise holds: a frame's raw pixels sit in DRAM, at an address
we can read and write, before anything writes them to the card.** Every region
begins with a `DEADBEEF` allocator header (magic, size, prev, next) -- the
payload starts after it, which is why a naive read of the region start shows no
pixels.

No DNG header (`II*\0` = 0x002A4949) was found at the offsets sampled inside
those regions, so the header is assembled somewhere else and is not adjacent to
the pixels.

Still open: which of the five slots holds the frame being written, and where its
header lives. But the question that gates everything -- whether the data is in
memory at all -- is answered.

## FOUND IT — the whole DNG is assembled in DRAM before it is written

`raw/tapargs.S` on `FUN_c0376b98` (the one point verified per-frame: 75 calls
against 74 frames) captured the frame object at 0xC357F2A4, and scanning its
fields for pointers and known lengths gave:

```
frame + 0x004C   0x53B02C00     buffer for this frame
frame + 0x014C   0x00013400     78,848 -- the header size, matching the file
frame + 0x1030   "\CINEMA\..."  the path, confirming the object is the right one
frame + 0x1174   0x53E1D000     the next buffer, 0x31A400 further on
frame + 0x01C0                  the frame's byte count
```

Reading those two addresses:

```
0x53B02C00:  002A4949 00000008 ...   II*\0, IFD0 at offset 8, 58 tags
0x53E1D000:  002A4949 00000008 ...   the same
+0x13400:    10033110 F10F0121 ...   pixels, exactly where StripOffsets says
```

**Fifty-eight tags, the same as the file on the card.** The complete DNG --
header and pixel data -- is built in DRAM in a ring of buffers around
0x53Bxxxxx, and only then handed to the SD path. Nothing about it is streamed
past us.

So the implementation is fully specified, every address known:

```
1. hook FUN_c0376b98        already proven to fire once per frame
2. buf = *(frame + 0x4C)    the complete DNG for this frame
3. engine: src = buf + 78848, tiles 512x512 (12 for FHD), dst = scratch
   FUN_c05a6990 -> TileByteCounts,  FUN_c06a3650 -> TileOffsets
4. copy the compressed bitstream back to buf + 78848
5. patch the header in place: Compression 1 -> 7, strip tags -> tile tags
   (the IFD is 702 bytes of the 78,848, so the arrays go in the padding and
    nothing existing has to move)
6. correct the byte count at frame + 0x1C0 to 78848 + compressed size
```

Every unknown that has blocked this is now closed: throughput (169.7 Mpix/s),
engine power inside recording, the descriptor layout, the tile limits, the frame
format, and now the buffer.

## vbuf schedules; the imaging pipeline assembles and writes

Two marking tests, each verified by the DNG on the card rather than by reading
memory back:

```
hook inside FUN_c0376b98        42 frames, 0 marked
hook at 0xC037A384, the         79 frames, 0 marked
  `bl FUN_c030cff0` carrying
  r1 = *(frame + 0x4c)
```

Neither mark survived, and `FUN_c030cff0` explains why: it is
`Cont_Pause(ImagCtrl(), buffer)` -- a method on the imaging-control singleton at
0xC34393E8, reached through `FUN_c030c768`. **vbuf is the scheduler. It hands an
empty buffer to the imaging pipeline; the pipeline fills it with header and
pixels and writes it, in another task.** So `frame+0x4c` is a destination, not a
finished frame, and every hook placed in vbuf is necessarily too early.

That single fact explains all three misses today, including the two probes that
never fired at all -- they were on branches of a scheduler, not on the path that
touches data.

The buffers are real and the DNG in them is real: read after a recording,
0x53B02C00 and 0x53E1D000 both held `II*\0`, IFD0 with 58 tags, pixels at
+0x13400. That was the finished product sitting in the ring, not something vbuf
had built.

**Next, and statically:** the consumer side. `ImagCtrl` at 0xC34393E8 owns the
queue; find the task that takes buffers off it, and the assembly -- and the only
correct place to compress -- is there. Marking from vbuf cannot work no matter
which of its branches is chosen.

## THE HOOK POINT — a function pointer in RAM, not a patched instruction

Read out of the source rather than probed for. The chain from vbuf:

```
vbuf  ->  FUN_c030cff0(ImagCtrl(), buf)          = Cont_Pause(obj, buf)
      ->  FUN_c0631640(buf)   _DAT_30182180 = buf >> 2     the DMA destination
      ->  FUN_c06305a0(0, buf)  keeps it in _DAT_c37cf8c4/c8
```

So `frame+0x4c` is where the **hardware is told to write**, which is why two
marking tests placed in vbuf left nothing on the card: at that moment the frame
does not exist yet.

The completion side, `FUN_c0630620`:

```c
if ((_DAT_c37cf8cc != (code *)0x0) && ((_DAT_30182048 & 1) != 0)) {
    _DAT_30182048 = _DAT_30182048 & 0xfffffffe;      /* clear the interrupt */
    uVar1 = FUN_c06305c0();                          /* the buffer just filled */
    ...
    (*_DAT_c37cf8cc)(uVar1, _DAT_30182184 * 4 + 0x40000000);
}
```

**`_DAT_c37cf8cc` at 0xC37CF8CC is a function pointer in RAM**, called when the
DMA has finished a frame, with the buffer as its first argument and the DMA end
address as its second. A second pointer, `_DAT_c37cf8d0`, is called after it.

That makes the hook a pointer swap:

```
save   *(0xC37CF8CC)
write  our stub's address
stub   receives (buf, end) -- nothing to look up, nothing else read
       compress, patch the header, then jump to the saved original
restore by writing the saved value back
```

No instruction is modified, so there is no cache maintenance, no displaced
instruction to replicate, and no branch-range arithmetic -- and it satisfies the
rule that a hook in a recording path works only on what it is handed.

Unverified: that the DNG header is already in the buffer at that moment (the DMA
carries pixels; the header may be written before or after). The same cheap test
settles it -- mark from inside the stub, then look at the card.

### The imaging-controller callback is not the CinemaDNG path either

`FUN_c06305d8` writes `_DAT_c37cf8cc` (the frame-complete callback
`FUN_c0630620` dispatches through) and `FUN_c06305f0` clears it; both are Thumb
and both build 0xC37CF8CC with movw/movt. Instead of replacing either -- an ARM
branch over a Thumb prologue is a crash, caught before recording -- the two
constants were re-pointed at a word of ours, so the firmware would keep the real
callback there while 0xC37CF8CC held our stub. Encodings were proved by
recomputing the originals and matching the camera byte for byte.

After a 63-frame recording:

```
saved 0xC072EF00  = 0            FUN_c06305d8 was never called
slot  0xC37CF8CC  = our stub     still ours, never replaced
frames marked     = 0
```

**`saved` being zero is the answer**: the registrar does not run during
CinemaDNG recording, so neither does `FUN_c0630620`. That whole imaging-control
path -- ContSet Mem0/Mem1, the DMA-complete interrupt, the callback -- belongs
to another capture mode. All constants restored.

**Method note.** This is the fourth intervention point tried and the fourth miss
(FUN_c0376b98, the FUN_c030cff0 hand-off, 0xC037A46C, and now this), each
costing a recording. The failures were not wrong reading -- each path is real --
but wrong assumption about which path CinemaDNG uses. One-point-per-recording is
the wrong instrument for that question.

**Build a multi-point counter instead**: one stub installed at N candidate sites
at once, each bumping its own slot, so a single recording says which sites are on
the live path. `raw/tapcount.S` already generalises the trampoline; only the slot
indexing needs to differ per site. That should have replaced the guessing after
the second miss.

### Multi-point counting — one recording, eight answers

`raw/tapmulti.S` is `tapcount.S` with the slot index set at assembly time
(`-DIDX=n`), so N copies can watch N sites in one recording. Eight ARM
push-prologue candidates, across a 71-frame clip:

```
FUN_c037a990     71    per frame
FUN_c0374268     71    per frame
FUN_c03a4660     71    per frame
FUN_c03a4620    306    several times per frame -- a getter
FUN_c03a4700     21
dbfull            1    clip level, despite the name
FUN_c0397cd8      1
FUN_c0374ee8      1
```

Reading the three that run per frame: `FUN_c0374268` prepares the record and
writes +0xffc; `FUN_c03a4660` records the file position; and `FUN_c037a990`
checks capacity against `frame+0x1c0` and then **allocates** the frame's memory
(`FUN_c001cfd8(..., frame+0x68, ...)` -- the handle from which +0x4c is derived).

**All three are on the preparation side. None is a completion.** That is the null
result the method was built to deliver, and it is worth more than four separate
misses: the whole candidate set was the wrong side of the pipeline, and vbuf
never learns that a frame is done.

`dbfull` was the most promising name and fires once per clip, which is a useful
reminder that recovered names describe the function's origin, not its role.

So the frame is prepared and handed off in vbuf; the fill and the write happen
elsewhere and report back to nothing vbuf can see. Neither the MediaFile API
(3 calls a clip) nor the imaging-controller callback (registrar never runs)
carries it.

**What has not been tried**: the storage side. The frames reach the card at
~97 MB/s through some driver path, and that path must touch every frame. Counting
across candidate SD/storage driver entries the same way is the next move, and it
costs one recording rather than eight.

## The storage side is the path — FileSplitWriter takes (buffer, length, ordering kind)

Second multi-point sweep, seven storage-side candidates, one recording:

```
XC_MediaFileSdCard__v1    68   per frame
FUN_c069ac88              56   per frame
FUN_c069ade0              56   per frame
FUN_c069b0a8              55   per frame
FUN_c069b198             252   several times a frame
XC_MediaFileSdCard__v2    10
FUN_c069af88               0
```

Unlike the eight preparation-side candidates, these are on the live path. Both
belong to `src/library/FileMgr/src/FileSplitWriter.cpp`, found by listing the
firmware's own `__FILE__` strings.

`FUN_c069ac88(writer, seg, kind)` **registers a write segment**. The later live capture
showed the third argument is the ordering kind (always 2 on this DNG path), not a byte offset:

```c
iVar3 = param_1 + *(int *)(param_1 + 0x90) * 0x10;
*(undefined4 *)(iVar3 + 0x10) = *param_2;      /* buffer  */
*(undefined4 *)(iVar3 + 0x14) = param_2[1];    /* length  */
*(undefined4 *)(iVar3 + 0x18) = param_3;       /* ordering kind; list sort key */
```

kept in a list sorted by offset at `writer+0x8c`, counted at `writer+0x90`, with
an assert at eight. `FUN_c069ade0` then opens the file (`FUN_c0365fb0`, mode
0x406/0x806/0x1806) and walks that list to write it.

**So a DNG is written as segments, and the length of each is a value passed in.**
That is the shape compression needs: the same buffer, a smaller length. And it
satisfies the rule that a hook works only on what it is handed -- buffer and
length arrive as arguments, nothing has to be looked up.

Next: capture (seg, kind) at `FUN_c069ac88` for one frame to see how a DNG is
split -- one segment or two, and whether the pixels arrive as their own segment
with offset 78848. That determines whether compressing means editing one length
or two.

## THE INTERVENTION POINT — FUN_c069ac88, one segment per frame

Captured with `raw/tapseg.S` across a recording, the last eight of 70 segments:

```
buf=0x5C6A0000  len=3,244,544  arg3=2
buf=0x5C385C00  len=3,244,544  arg3=2
buf=0x5C06B800  len=3,244,544  arg3=2
buf=0x5BD51400  len=3,244,544  arg3=2
...              spacing 0x31A400 between buffers
```

**One segment per frame, carrying the whole DNG.** The buffers run from at least
0x56FC1000 to 0x5C6A0000 -- about 92 MB, roughly 28 frames deep. The third
argument is 2 for every frame, so it is a kind, not a byte offset.

So the hook is:

```c
FUN_c069ac88(writer, seg, kind)
    buf = *seg          /* the complete DNG, header at 0, pixels at 78848 */
    len = seg[1]        /* 3,244,544 */
```

and compression is:

```
1. engine on buf + 78848, 512x512 tiles (12 for FHD 1936x1090)
   FUN_c05a6990 -> TileByteCounts,  FUN_c06a3650 -> TileOffsets
2. compressed bitstream back to buf + 78848
3. header edited in place: Compression 1 -> 7, strip tags -> tile tags
   (the IFD is 702 bytes of the 78,848; the arrays fit in what follows)
4. seg[1] = 78848 + compressed size
```

Every value is an argument or reached through one, so the hook needs to look
nothing up -- which was the constraint from the start.

The search that got here: four single-point attempts all missed, then two
multi-point sweeps (`raw/tapmulti.S`, slot chosen with `-DIDX=n`) settled it in
two recordings -- eight preparation-side candidates, all wrong side; seven
storage-side, five live. Reading tells you what a path does; only the camera says
whether it runs, and asking about one site per recording wastes the question.

## CONFIRMED — the hook edits every frame on its way to the card

`raw/cdngcomp.S` at `FUN_c069ac88`, stage 1 (mark only), across a 74-frame clip:

```
74 frames, 74 marked
A001_036_..._000001.DNG   3,244,544 bytes   IFD0 58 tags   pixels intact
```

**Every frame carried the mark and every frame is valid.** So at
`FUN_c069ac88` the buffer is the finished DNG, our writes reach the card, and
touching it breaks nothing. Two earlier marks (inside `FUN_c0376b98`, and at the
`FUN_c030cff0` hand-off) left nothing, because both sit before the frame exists.

That closes the search. What remains is the build:

```
scratch     the engine reads src and writes dst, so it cannot work in place.
            The frame ring has 8,704 bytes of slack (3,244,544 used of 3,253,248
            spacing) and the pool is 1 MB against ~1.5 MB of compressed FHD, so
            neither will do. `memmgr bufmem get` wedged the worker twice from
            the shell -- but that says the shell's context cannot do it, not
            that nothing can. The hook runs in a camera task, and today's power
            domain result is exactly that distinction: refused from the shell's
            borrowed handler, granted from inside recording. The gyro logger
            likewise calls firmware file APIs from its own thread without
            trouble. **So allocate lazily from inside the hook, not from the
            AutoRun** -- it leaves the boot path alone, keeps this independent
            of the gyro build, and is one cheap test (call it once, note the
            address, see whether the camera survives). Untested either way.
engine      buf+78848 as src, 512x512 tiles -> 12 for FHD 1936x1090
            FUN_c05a6990 -> TileByteCounts,  FUN_c06a3650 -> TileOffsets
header      in place: Compression 1 -> 7, strip tags -> tile tags. The IFD is
            702 bytes of the 78,848, so the two 48-byte arrays fit after it --
            but the padding is not all zero (278 non-zero bytes were found in
            0x0F000..0x11000), so the space has to be chosen, not assumed.
length      seg[1] = 78848 + compressed size
```

`cdngcomp.S` carries a `mode` word so the stages can be exercised without
reassembling: 0 passes through, 1 marks, 2 compresses.

### The hook can allocate its own scratch — no AutoRun needed

`raw/scratchtest.S` asked for 4 MB once, on the first frame, from inside the
hook, using the firmware's own idiom (`FUN_c001cf78(0)` ->
`FUN_c001d038(alloc, size, 0, 0, 0)` -> `FUN_c001b668(handle)`):

```
allocator  0xC3073A5C
handle     0x45166B00
address    0xC5166B00      = handle | 0x80000000, the cached alias
contents   00080000 00050000 07800000 04380000   -- 2048/1280/1920/1080,
                                                    recycled from something else
```

**It works from a camera task**, which settles the question the shell's two
wedges could not: `memmgr bufmem get` failing there was the shell's context, not
the allocator -- the same distinction as the power domain, refused from the
borrowed handler and granted from inside recording. So the scratch is taken
lazily in the hook, and the boot path and the gyro build stay untouched.

Two details to carry into the implementation:

```
alignment   the handle came back at 0x45166B00, and 0xB00 & 0x3FF != 0.
            The engine validates buffers as & 0x3FF == 0, so round up to
            0x45167000 and lose the first 1,280 bytes of the allocation.
form        the engine programs addresses as (virt + 0xC0000000) >> 10, so use
            the 0x45xxxxxx handle, not the 0xC5xxxxxx alias `FUN_c001b668`
            returns.
```

Nothing is left unknown in the plan now: hook, buffer, length, engine, tiles,
size table, tile offsets, header fields, and scratch.
