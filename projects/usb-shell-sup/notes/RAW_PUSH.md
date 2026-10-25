# SIGMA fp Ver.5.02 — RAW FRAME PUSH channel (camera-push raw over EP84 IN, SuperSpeed bulk)

<!-- index-stamp -->
> ⚠ 2026-10-24 更正(projectFP 交接 F6,Ruari/Arktri,讀韌體 [C],未上機):UVC 視訊是 **bulk 上的 MJPEG(EP 0x81)**;唯一的等時端點 **EP 0x84 是麥克風**(44.1 kHz 16-bit 立體聲)。本文中「UVC isochronous on EP 0x84 / YUY2」的說法是錯的。另有隱藏指令 `usb uvcTest`:把卡上 `\UVC0..2.JPG` 原樣串流(僅限開機後第一次 webcam 連線前;缺檔會 assert)。
> 這份寫的是 EP 0x05 OUT / EP 0x84 IN。現行 build 用 EP 0x01 / 0x82 / 0x83(`host/fpshd.c:31-32`、`patches.py:15-20`),EP84 在現行描述元下不存在。
> 先看 [`USB_SHELL_INDEX.md`](USB_SHELL_INDEX.md)。


Design for streaming the raw/liveview sensor frame out USB **EP84 IN** as a camera-initiated
high-bandwidth push, triggered by a frame-ready event. Firmware `out/MAIN_c0000000.bin`, base
`0xC0000000` (file_off = addr − 0xC0000000). Decomp `out/decomp/full/blk_c0*.c` +
`out/decomp/{rawxfer,rawpath,lvraw}.c`. Builds on `RAW_GRAB.md`, `USB_COMPLETION_PATHS.md`,
`SHELL_COEXIST.md`, `USB_COMPOSITE_MAP.md`, `CAMERA_STATE_SOURCES.md`.
**[C]** = confirmed from decomp/bytes, **[I]** = inferred, **[P]** = needs a live shell probe.

---

## 0. TL;DR verdict

- **High-bandwidth raw push is FEASIBLE on this controller.** [C for mechanism, [P] for sustained MB/s]
- **Frame-ready hook site (still/rec raw): the `FrameExpos_s` call at `0xC0315C10`, invoked from
  the ImageController thread loop `FUN_c030d0c0` (`blk_c03.c:10830`) with a FIXED global frame
  descriptor `&DAT_c3439404`.** When the ImgCtrl message queue delivers opcode `0`
  (`_DAT_c3439404 == 0`), a frame has just been exposed and its raw buffer address is live in
  `*(0xC3439404 + 0x38)`. This is both hookable (patch the call/BL) and **raw-readable**
  (poll the fixed descriptor). [C]
- **Frame-ready (LV preview raw): the LV small-raw ring**, addr =
  `0x50000000 + idx*0x100000` (1 MB stride), managed by `XC_LiveViewRawMemInterfaceSample`
  (getter v1 `@0xC040F250`, advance v3 `@0xC040F528`). **11 buffers, idx 0..10** (v3 wraps at
  `>10`). Hook the advance (v3) or read the ring index cell to know the just-filled buffer. [C]
- **DWC3 TRB: single-TRB max transfer = 24-bit BUFSIZ = `0xFFFFFF` = 16 MB − 1** [C]. Firmware
  uses **exactly ONE 16-byte TRB per endpoint context** (no ring, no chaining) — control word is
  always `0x813` (HWO|LST|IOC, TRBCTL=Normal, **CHN=0**). Hardware *supports* chained TRBs; the
  stock firmware never uses them. [C]
- **Recommended mechanism: a copy-free chunk-loop.** Point the ctx4 TRB `bufptr` **directly at
  the `0x50000000` raw buffer** (its bus alias), size = `min(remaining, 0xFF0000)`, `StartTransfer(9)`,
  wait completion, advance offset, re-arm. No CPU copy. A self-built chained TRB list is an option
  but buys almost nothing over the chunk-loop (re-arm latency ≪ per-chunk transfer time). [C mech / I perf]
- **Expected throughput ballpark: ~100–300 MB/s sustained** (SuperSpeed bulk on this DWC3),
  so a 1 MB LV frame in ~3–10 ms (easily video-rate) and a 48 MB still raw in ~0.15–0.5 s. [I — [P] to measure]
- **Endpoint: reuse EP84 IN (ctx4) with a frame header for muxing** vs the shell/telemetry; a
  dedicated spare bulk-IN context is possible but needs a descriptor patch. UVC (mode 3) is the
  large-buffer template but is a mutually-exclusive gadget. [C]

---

## 1. Frame-ready hook (Task 1)

### 1.1 Still / record raw — ImageController exposure path [C]

`XC_ThreadHandlerImageController::v1 (@0xC030D0A8)` → `FUN_c030d0c0 (@0xC030D0C0)` is the ImgCtrl
thread main loop (`blk_c03.c:10806`). Each iteration blocks on a message-queue receive that fills
a **fixed global descriptor** and dispatches on its opcode:

```
blk_c03.c:10824  do {
                   iVar2 = FUN_c030d230(param_1, &DAT_c3439404, 0xffffffff);   // recv frame msg → 0xC3439404
                 } while (iVar2 == 0);
     10828      if (_DAT_c3439404 == 0) {                 // opcode 0 = FRAME EXPOSED
     10829        uVar1 = FUN_c0315bd0();
     10830        FrameExpos_s(uVar1, &DAT_c3439404);      // <-- HOOK SITE (BL @ ~0xC0315C10 call)
     10831        FUN_c036d758(param_1 + 0x10, 2);
                 } else if (_DAT_c3439404 == 1) { SetImgMode_s(...); }   // mode change
                 ... opcode 2/3 = eval/continuous
```

`FrameExpos_s (@0xC0315C10)` (`rawxfer.c:125`) receives `param_2 = 0xC3439404`, the frame
descriptor. **Raw-frame descriptor field map** (offsets confirmed from the UART-print code
`rawxfer.c:334-460`, per-pic stride `0x10` starting at `+0x30`):

| Offset (abs) | Field | Meaning |
|---|---|---|
| `0xC3439404 +0x00` | opcode | 0=FrameExpos, 1=SetImgMode, 2/3=eval/cont |
| `+0x12` | byte flag | 0 = still (relative_gain), else movie_raw (abs_gain) |
| `+0x1c` | sensor mode | acquisition/sens_mode enum |
| `+0x20` | **bit-depth enum** | 0:12, 1:14, 3:10, 4:8 bit |
| `+0x24` | OB flag | optical-black present |
| `+0x28` | **endian** | 0:Little, 1:Big, 2:Middle |
| `+0x2c` | pic count | #pics this exposure (bracket/burst); 0→treat as 1 |
| `+0x30 + n*0x10` | shutter[n] | per-pic shutter |
| `+0x34 + n*0x10` | gain[n] | relative/abs gain |
| **`+0x38 + n*0x10`** | **raw_addr[n]** | **full-frame raw buffer address (in 0x50000000 region)** |
| `+0x3c + n*0x10` | small_raw_addr[n] | downsampled small-raw buffer address |

So for a single-pic frame, **`raw_addr = *(uint*)0xC343943C`** and
**`small_raw_addr = *(uint*)0xC3439440`**. These update every exposed frame. `0xC3439404` is live
BSS the ImgCtrl thread derefs → safe to `mem read` (do **not** widen the window).

**Buffer geometry (still):** allocated in **16 MB blocks** (`FUN_c001a048(id, 0x1000000, 0, 4,
0x40000000, table_num, …)`, `blk_c03.c:120222-120583`) — multiple `table_num` slots (a **small
ring of 16 MB buffers**, not a single latch). Full still raw = 6000×4000×16b ≈ **48 MB spanning
~3 of these 16 MB slots** (matches `RAW_GRAB.md` dumping `0x50000000,,0x03000000`). fp L =
9520×6328. Format: **Bayer RGGB**, bit depth per `+0x20`, endian per `+0x28`, packing
`2 px→3 bytes` for 12-bit (see `RECORDER_SPEC §3.2`).

### 1.2 Live-view preview raw — the small-raw ring [C]

Managed by `XC_LiveViewRawMemInterfaceSample` (vtable slots in `lvraw.c`):
- **v1 `@0xC040F250` — current-buffer getter:** `return *(int*)(this+4) * 0x100000 + 0x50000000;`
  → **addr = 0x50000000 + idx·1 MB**.
- **v3 `@0xC040F528` — advance:** `idx = *(this+4); idx++; if (idx>10) idx=0;` → **11-buffer ring**,
  idx 0..10, i.e. `0x50000000 .. 0x50A00000`, **1 MB/frame** (downsampled small-raw).
- The ring index lives at `this+4` of the interface object (heap; not yet pinned to a fixed DAT →
  **[P]**: find the object base, or hook v3, or read `small_raw_addr` at `0xC3439440` which the
  ImgCtrl path also latches).

**Live ring vs single latch:** LV preview = an 11-slot **ring** (multiple buffers, producer wraps).
Still/rec = a small ring of 16 MB slots named per-frame by `raw_addr` in the `0xC3439404`
descriptor (a **latch that names the current buffer**, buffers themselves rotate).

### 1.3 Chosen hook

Hook **the `FrameExpos_s` call in `FUN_c030d0c0`** (patch the `BL` at the `0xC0315C10` call site, or
a thread-safe trampoline that reads `0xC3439404` then chains to the original). It fires **once per
exposed frame** for both still and movie_raw, and hands you `{raw_addr, small_raw_addr, W×H (via
sens_mode), bit-depth, endian}` in the fixed descriptor. For pure LV preview (no rec), hook the
LV-ring advance v3 `@0xC040F528` or read `small_raw_addr`.

---

## 2. DWC3 large-transfer / TRB capability (Task 2)

### 2.1 TRB descriptor format [C]

Per-context TRB pointer table **`DAT_c31e3264` @ `0xC31E3264`** (7 entries, ctx0..6, stride 4).
ctx4 (EP84 IN) pointer cell = **`0xC31E3274`**; ctx5 (EP05 OUT) = `0xC31E3278`. Each entry holds
the **bus/DMA address** of that context's TRB. Init (`blk_c01.c:134259-134271`):

```
TRB storage (CPU view) = 0xC31E32C0 + ctx*0x10       // ctx4 TRB @ 0xC31E3300
DAT_c31e3264[ctx]      = (that) + 0x40000000          // DWC3-visible (bus) TRB pointer
```

**Stride between adjacent context TRBs is 0x10 = exactly ONE 16-byte DWC3 TRB.** There is **no
multi-TRB ring** per endpoint in the stock layout — one TRB slot each. 16-byte TRB layout
(standard DWC3), as written by the re-arm code (`blk_c01.c:138161-138164`, `:138247-138250`):

| Word | Off | Field | Notes |
|---|---|---|---|
| 0 | `+0x0` | **BPTRL** buffer ptr low | `= cpu_ptr − 0x40000000` (cached→bus alias) |
| 1 | `+0x4` | BPTRH buffer ptr high | `= 0` (32-bit DRAM) |
| 2 | `+0x8` | **BUFSIZ / STATUS** | **size = bits[23:0]**; residue computed as `req − (word2 & 0xffffff)` (`:138201/138204`) → **24-bit size field** |
| 3 | `+0xc` | **CONTROL** | always **`0x813`** |

### 2.2 Size limit and control bits [C]

- **Max single-TRB transfer = `0xFFFFFF` = 16,777,215 bytes ≈ 16 MB.** (BUFSIZ is 24-bit; the
  firmware masks `& 0xffffff` when computing transferred length.) A 40–48 MB frame **cannot** fit
  one TRB — it needs ≥3 TRBs (chained or sequential).
- **Control `0x813`** decodes: `HWO(bit0)=1`, `LST(bit1)=1`, `CHN(bit2)=0`, `CSP(bit3)=0`,
  `TRBCTL(bits9:4)=1 (Normal)`, `IOC(bit11)=1`. i.e. **single, last, interrupt-on-complete,
  chain OFF.** (ep0 status TRBs use `0x823`.)
- **Chaining:** every TRB control the firmware writes is `0x813` — **the firmware never sets CHN
  (bit2) and never queues >1 TRB.** The **DWC3 IP itself supports CHN/LST chained TRB lists**
  (this is standard DWC3), but to use it you must supply **your own multi-entry TRB ring** and
  point `DAT_c31e3264[4]` at it (the stock 1-slot layout has no room — adjacent 16-byte slots
  belong to other contexts).

### 2.3 How the firmware moves big buffers today [C/I]

- **No mass-storage / UVC "giant TRB" template exists** — MSC and UVC also ride the same 1-TRB-per-
  context DWC3 driver. **UVC (mode 3)** moves large video frames via the **auto-refill callback**
  `0xC30257B0` (dispatchers `FUN_c01e61a0` / `FUN_c01e6208`, `USB_COMPLETION_PATHS §6`): on each
  XferComplete/InProgress the ISR calls the callback which **re-arms the next chunk** — i.e. UVC is
  itself a **single-TRB chunk-loop driven from IRQ**, not a chained list. That is the exact template
  for our push (just in task context instead of IRQ). [C mechanism]

---

## 3. Streaming design & no-copy feasibility (Task 3)

### 3.1 No-copy direct DMA from 0x50000000 — FEASIBLE [I, [P] to confirm alias]

The DWC3 reads whatever **bus address** sits in the TRB `BPTRL/BPTRH`. `0x50000000` is already the
**DMA/bus-physical** view of the sensor Bayer buffer (the sensor writes it via DMA; the shell reads
it directly via `mem save 0x50000000`). Therefore **write `bufptr = raw_addr` (0x50000000+off)
straight into the ctx4 TRB and the DWC3 DMAs the frame out with NO CPU copy.** The stock re-arm
converts a *cached* CPU pointer with `−0x40000000`; the `0x50000000` region is the uncached/bus
window, so it likely needs **no conversion** (use `raw_addr` as-is) — **[P] confirm the exact alias
with a 1-round probe** (§6). Copy-free is essential: a memcpy of 48 MB through the CPU would dominate
and defeat the point. **Avoid cache-invalidate calls** (known to hard-lock, `USB_COMPLETION_PATHS`);
DMA-ing the uncached `0x50000000` view sidesteps cache ops entirely.

### 3.2 Three options and throughput

Assume SuperSpeed bulk effective **~100–300 MB/s** on this DWC3 (5 Gbps line, 8b/10b, controller/
host overhead) — **[P]** to measure.

| Option | How | 1 MB LV frame | 48 MB still | Verdict |
|---|---|---|---|---|
| (a) one giant TRB | impossible >16 MB | n/a | n/a | **rejected** (24-bit size cap) |
| (b) self-built chained TRB list | own N-entry ring in a DMA cave, CHN on all but last (LST) | 1 TRB | 3 TRBs, 1 StartTransfer | works; saves 2 re-arms (~<1 ms) — **marginal** |
| **(c) copy-free chunk-loop** ★ | ctx4 TRB `bufptr=0x50000000+off`, size=`min(rem,0xFF0000)`, `StartTransfer(9)`, block on completion, advance | 1 chunk ≈ 3–10 ms | 3 chunks ≈ 0.15–0.5 s | **recommended** |

Per-chunk transfer (16 MB @ 200 MB/s ≈ 80 ms) ≫ re-arm latency (DEPCMD busy-spin + event-flag wake,
sub-ms). So the chunk-loop's re-arm overhead is <2%; **chaining (b) is not worth the extra TRB-ring
machinery.** LV 1 MB frames are one TRB each → trivially video-rate.

### 3.3 Worker loop (task context, event-driven completion) [C primitives]

```
per frame-ready (from §1 hook, delivering raw_addr,len,fmt):
  if !arm_permit(): drop frame (see §4)             # FUN_c01e40d0()>0 && state==3 && events==0
  off = 0
  push_header(raw_addr, len, fmt, seq)              # small EP84 IN telemetry-framed record
  while off < len:
      n = min(len-off, 0xFF0000)                    # ≤ 16 MB − 64 KB, keep 64B-aligned
      ctx4_TRB.bufptr = bus_alias(raw_addr + off)   # §3.1 — NO copy
      ctx4_TRB.size   = n
      ctx4_TRB.ctrl   = 0x813
      FUN_c01e6b80(9)                                # StartTransfer EP84 IN (ctx4)
      r = FUN_c01e4e80(4, timeout)                   # block on 0xC31E3210 until IRQ; 0=done -5=to -4=disc
      if r != 0: abort frame, re-check gate
      off += n
```

Completion is **IRQ-driven** (DWC3 IRQ 0x34 → `FUN_c01e3660` → `tk_set_flg(0xC31E3210)`), consumed
by the blocking wait `FUN_c01e4e80(ctx=4, timeout)` — a true sleep, not a poll
(`USB_COMPLETION_PATHS §3`). Anchors: StartTransfer `0xC01E6B80` (EP84 IN param **9**), completion
wait `0xC01E4E80`, EndTransfer `0xC01E6D48`, ctx4 TRB pointer cell `0xC31E3274`, completion flag id
`[0xC31E3210]`.

---

## 4. Coexistence / back-pressure (Task 4)

- **Frame rate vs drain rate — DROP, don't block.** The producer (sensor→ImgCtrl) runs at frame
  rate; the USB push must never stall the ImgCtrl thread. In the §1 hook, **snapshot `raw_addr`
  and hand it to a decoupled push worker**; if the worker is still draining the previous frame (or
  the host is slow), **drop the new frame** (skip). Never block inside `FrameExpos_s` — that would
  back up the imaging pipeline and can freeze the camera. [I — matches the freeze mechanics in
  `SHELL_COEXIST`]
- **Reading 0x50000000 while the sensor writes the next frame — use the ring, not the live slot.**
  Still: buffers rotate across the 16 MB `table_num` slots, so `raw_addr` for frame N names a slot
  the sensor is **done** with (safe to DMA) while the sensor fills a different slot for N+1. LV: the
  11-slot ring — read the **previous** index (`idx−1`), i.e. the just-completed buffer, never the one
  v1 currently points at (being filled). Latch the address at frame-ready and push that; if the ring
  laps you before you finish (slow host), you dropped frames anyway. [C ring structure / I safety]
- **Arm-gate every StartTransfer** with `FUN_c01e40d0()>0 && _DAT_c31e3748==3 && _DAT_c31e3900==0`
  (`SHELL_COEXIST §3`) so a suspend/reset mid-push can't wedge the DWC3.

---

## 5. Endpoint choice (Task 5)

- **Vendor gadget has exactly 2 bulk EPs** (OUT 0x01/ctx5, IN 0x82/ctx4; `USB_COMPOSITE_MAP §2A`).
  The shell already owns EP84 IN. **First cut: reuse EP84 IN (ctx4), mux raw with the shell** using
  a small frame header (magic/seq/kind/len) so the host demuxes telemetry vs raw payload. The push
  is bursty and large; keep shell command/response records small and interleave between raw chunks
  (raw chunk boundaries are natural yield points). [C]
- **Dedicated bulk-IN on a spare context** — ctx1/2/3/6 are free (7 contexts total, ctx0=ep0). A
  cleaner design adds a **3rd endpoint descriptor (bulk IN)** to the vendor config and enables its
  DALEPENA bit, giving raw its own pipe (no muxing, no head-of-line blocking of the shell). Costs a
  descriptor patch + re-enumerate. [C feasible / I effort]
- **UVC (mode 3) is the closest native video-streaming model** (its own class-0x0E gadget, isoc/bulk
  IN, auto-refill callback `0xC30257B0`). But **all USB modes are mutually exclusive single-function
  gadgets** (`USB_COMPOSITE_MAP` verdict) — you cannot run UVC-video + vendor-shell together. So raw
  push must live **inside the vendor gadget** (reuse EP84 or add a bulk IN), not as a parallel UVC
  stream. If a pure raw video appliance were the goal (no shell), the UVC path with its refill
  callback is the ready-made template. [C]

---

## 6. Live probes to confirm the two soft spots (over the shell, read-only unless noted)

1. **[P] Frame-ready descriptor.** In LiveView/record, `mem read 0xC3439404 0x50` repeatedly:
   confirm `+0x00` opcode toggles to 0 on exposure and `+0x38` (raw_addr) points into `0x50000000..`
   and **changes** frame-to-frame (proves the rotating-buffer latch). Cross-check `+0x3c`
   (small_raw_addr) vs the LV ring `0x50000000+idx·0x100000`.
2. **[P] No-copy alias.** Confirm the DWC3-visible bus address for `0x50000000`: read a known-good
   USB reply buffer CPU pointer and its ctx TRB `bufptr` (`mem read 0xC31E3300 0x10` after a shell
   round) to see the `−0x40000000` (or no) conversion, then decide whether `raw_addr` goes into the
   TRB as-is. A one-shot **mem-set** experiment (write `bufptr=0x50000000`, `size=0x1000`,
   `ctrl=0x813` into ctx4 TRB, `StartTransfer(9)`, read back 4 KB on the host) proves direct DMA.
3. **[P] Max-TRB size.** Arm a single 16 MB−64 KB TRB (`size=0xFF0000`) from a 0x50000000 slot and
   time the completion + host byte count → confirms the 24-bit cap and gives the real MB/s to plug
   into §3.2.
4. **[P] Sustained MB/s & re-arm latency.** Loop the chunk-push for a 48 MB still and record elapsed
   ms per chunk (via `tick_us` `0xC002B6E0`) → validates the throughput ballpark and the drop policy.

---

## 7. Address index

| item | addr | note |
|---|---|---|
| **Frame-ready hook (BL to FrameExpos_s)** | call in `FUN_c030d0c0`, target `FrameExpos_s @0xC0315C10` | ImgCtrl loop `blk_c03.c:10830` |
| **Still/rec frame descriptor (fixed)** | `DAT_c3439404 @0xC3439404` | opcode+0, raw_addr+0x38, small+0x3c, bit+0x20, endian+0x28, sens+0x1c, pics+0x2c |
| ImageController thread loop | `FUN_c030d0c0 @0xC030D0C0` (v1 `@0xC030D0A8`) | blocks on `FUN_c030d230(...,&DAT_c3439404,-1)` |
| LV small-raw current-buffer getter | `XC_LiveViewRawMemInterfaceSample::v1 @0xC040F250` | `0x50000000 + idx*0x100000` |
| LV small-raw ring advance | `::v3 @0xC040F528` | 11 buffers, wraps at idx>10 |
| Still-raw 16 MB alloc | `FUN_c001a048(id,0x1000000,0,4,0x40000000,table_num,…)` | `blk_c03.c:120222+` |
| Raw buffer base | `0x50000000` region | Bayer RGGB; LV 1MB/frame ring; still ~48MB / 3×16MB |
| **ctx4 (EP84 IN) TRB pointer cell** | `DAT_c31e3264[4] @0xC31E3274` | holds bus ptr to ctx4 TRB |
| ctx4 TRB storage (CPU view) | `0xC31E3300` (=0xC31E32C0+4*0x10) | 16 bytes: BPTRL/BPTRH/BUFSIZ/CTRL |
| TRB size field | word2 `+0x8`, **24-bit** `& 0xffffff` | max `0xFFFFFF`≈16MB |
| TRB control (normal single) | word3 `+0xc` = **`0x813`** | HWO|LST|IOC, TRBCTL=Normal, CHN=0 |
| StartTransfer | `FUN_c01e6b80 @0xC01E6B80` | EP84 IN param **9**, EP05 OUT param 10 |
| Completion wait (blocking) | `FUN_c01e4e80 @0xC01E4E80` | ctx=4; 0 done / -5 timeout / -4 disc |
| EndTransfer | `FUN_c01e6d48 @0xC01E6D48` | |
| Completion event flag id | `[0xC31E3210]` | shared ctx1..6; set by DWC3 IRQ 0x34 ISR `FUN_c01e3660` |
| Arm-permit gate | `FUN_c01e40d0 @0xC01E40D0` + `0xC31E3748==3` + `0xC31E3900==0` | quiesce/re-arm safety |
| UVC mode-3 auto-refill callback (template) | `0xC30257B0` (dispatch `FUN_c01e61a0/…6208`) | large-buffer chunk-loop, IRQ ctx |
| µs tick (timing probes) | `FUN_c002b6e0 @0xC002B6E0` | u32 µs |

---

## 8. CONFIRMED vs INFERRED summary

**CONFIRMED [C]:** the frame-ready hook site and fixed descriptor `0xC3439404` + field map; LV
11-buffer 1 MB ring formula `0x50000000+idx*0x100000`; still 16 MB-block allocation; TRB format,
**24-bit 16 MB size cap**, control `0x813` with **CHN never set / one TRB per context**; DWC3
completion is IRQ-driven via `0xC31E3210` consumed by `FUN_c01e4e80`; StartTransfer/EndTransfer
anchors and EP84-IN=ctx4=param 9; all USB modes mutually exclusive (raw must live in the vendor
gadget); UVC mode-3 refill-callback template.

**INFERRED [I]:** copy-free direct DMA from `0x50000000` (the alias/conversion needs a probe);
sustained MB/s (~100–300); that the chunk-loop beats chaining in practice; the drop-frame
back-pressure policy; effort of adding a dedicated bulk-IN endpoint.

**NEEDS LIVE PROBE [P]:** §6 items — descriptor liveness, the no-copy bus alias, the 16 MB TRB in
practice, and real throughput/re-arm latency.

## ================= TRANSPORT SOLVED (RE 2026-08-20, agent) =================
The RAWGRAB slowness is a METHODOLOGY error, not a bandwidth/wire limit. Confirmed:
- Link is USB3 SuperSpeed (bcdUSB 0x0320 @0xC072B334); our vendor bulk IN template @0xC072B000
  (07 05 82 02 00 04 = bulk mps1024) + SS companion bMaxBurst 3 → genuine SS pipe → measured ~300 MB/s real.
- The fp's own 49fps stream = **UVC isochronous** on EP 0x84 (desc @0xC072B428, YUY2 1920x1080, 6-slot ring
  UvcImgBf @0xC04D8538). YUY2 1080p×49 = 203 MB/s ⇒ mandates SuperSpeed. PTP "LiveView" (op 0x902B, handler
  FUN_c04f00c8) is PULL-only lossy JPEG on bulk 0x82 — NOT the 49p carrier, do not emulate.

### Why RAWGRAB wedges EP84 [C root cause]
1. ctx4 has ONE 16-byte TRB slot (0xC31E3300, ptr 0xC31E3274) — single outstanding transfer, no ring.
2. host-PULL command-per-frame (raw a n on EP05 OUT → arm 1 TRB → bulk-IN) + daemon clear_halt+drain+usleep120ms per grab.
3. back-to-back grabs / arming while prior HWO set → device-side DEPCMD stall (host clear_halt can't clear) → dead → cold reboot.
   Un-gated re-arm across USB state transition desyncs DALEPENA (0x2100C720 vs shadow 0xC31E398C) → DWC3 IRQ-0x34 livelock.

### Raw CAN ride our own bulk EP (NOT UVC's isoc) [C mechanism / I rates]
- Bulk has no wMaxVideoFrameSize cap; only cap = 24-bit TRB size = 16 MB. UHD 12-bit raw = 12.4 MB → fits ONE TRB.
- @~300 MB/s: uncompressed UHD 12-bit = **~24 fps continuous** (no codec needed!); 2:1 compressed (~6MB) = **~50 fps**.
- Full-res still raw 48 MB (fp L) = 3-TRB chunk loop (~0.15-0.5s, stills only).
- DON'T ride UVC isoc EP: mutually-exclusive gadget (kills shell), no retransmit (corrupts raw), format-capped. Bulk is better.

### The "right way" recipe (replaces RAWGRAB) — mirror UVC producer/consumer/continuous
Producer (hook, snapshot only, never blocks imaging): hook FrameExpos_s @0xC0315C10 (raw_addr *(0xC3439404+0x38))
  or LV ring advance XC_LiveViewRawMemInterfaceSample::v3 @0xC040F528 (11-slot 1MB ring 0x50000000+idx*0x100000).
  Snapshot {raw_addr,len,fmt,seq} → N-deep ring (UVC uses 6). Ring full → DROP frame, never block producer.
Consumer (dedicated task, continuously armed):
  pop oldest → push_header{magic,seq,kind,len} → loop chunks n=min(len-off,0xFF0000):
    ctx4 TRB.bufptr = raw_addr+off (NO copy, DMA from 0x50000000 [P alias]); TRB.size=n; ctrl=0x813;
    arm_gate: FUN_c01e40d0()>0 && [0xC31E3748]==3 && [0xC31E3900]==0;  StartXfer FUN_c01e6b80(9);
    wait FUN_c01e4e80(4,timeout) (IRQ flag 0xC31E3210, ISR FUN_c01e3660 IRQ0x34); off+=n.
  Host: continuous bulk-IN, demux by header. NO per-frame command, NO clear_halt, NO drain/usleep. Keep ctx4 armed frame-to-frame.
Key EAs: TRB 0xC31E3300/ptr 0xC31E3274; StartXfer 0xC01E6B80(9); wait 0xC01E4E80(4); EndXfer 0xC01E6D48;
  flag 0xC31E3210; ISR 0xC01E3660(IRQ0x34); arm gate 0xC01E40D0+0xC31E3748+0xC31E3900; DALEPENA 0x2100C720/
  shadow 0xC31E398C; frame desc 0xC3439404(+0x38 raw_addr); LV ring adv 0xC040F528; UVC-style IRQ auto-refill API 0xC01E8658.
Open [P]: no-copy bus alias for 0x50000000 into TRB bufptr; real sustained MB/s + re-arm latency under continuous loop.

### CONSEQUENCE for the whole project
USB REALTIME raw streaming needs NO compressor: fixing transport alone → ~24fps UHD raw uncompressed. Compression
(0x300D, ratio ~2.3:1 measured on real frame) is a MULTIPLIER: ~50fps over USB, or enables SD recording. The
throughput probe gates only the compression bonus, NOT the base realtime-raw-streaming win.
