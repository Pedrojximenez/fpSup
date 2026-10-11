# SIGMA fp Ver.5.02 — TELEMETRY HOOK design (per-frame fast-state → RAM ring → EP84 stream)

Read-only static RE + design. Firmware `out/MAIN_c0000000.bin`, base `0xC0000000`
(`file_off = addr − 0xC0000000`). **CONFIRMED** = read from disasm/decomp or proven on-camera in a
prior stage. **INFERRED** = deduced, not yet hardware-proven. **PROBE** = needs one live `mem`/shell
round to settle.

Goal: a tiny sampler injected into a per-frame firmware tick that snapshots the fast camera state into
a RAM ring each tick; a separate low-priority worker drains the ring out **EP84 IN** continuously. The
request/response shell tops out ~12 reads/s @85 ms — useless for fast data. This gets native temporal
resolution (50 Hz state + full 2500 Hz gyro) at trivial bandwidth (~20 KB/s).

---

## 1. HOOK POINT(s)

### 1A. PRIMARY — gyro-thread handler hook `0xC00D0794` — CONFIRMED, PROVEN ON-CAMERA
- **Site:** `0xC00D0794`, inside `FUN_c00d0738` (the GyroData handler).
- **Displaced instruction:** `blx #0xC01EC6F8` (ARM, **4 bytes**, encoding a BL-with-exchange to the
  gyro-ring accessor `FUN_c01ec6f8`). Verified by capstone:
  ```
  0xC00D0790: mov  r0, sp
  0xC00D0794: blx  #0xC01EC6F8     <-- replace with `bl <cave>`, cave re-issues the call then samples
  0xC00D0798: mov  r1, r0
  ```
  This is exactly the site Stage-4/5 patched (gyro archive). The cave stub must: preserve r0–r3/lr,
  re-issue the original `blx 0xC01EC6F8` (r0=sp already set by the displaced-instruction context — the
  hook trampoline should replicate `mov r0,sp` semantics or call with the same frame), take the return,
  run the sampler, then branch back to `0xC00D0798`.
- **Context / task:** runs in the **GyroData task, priority 20 (0x14)** (TASK_PRIORITY_MAP §4;
  master-table idx 38 "GyroData"). **Normal task context, NOT an ISR** — `tk_*` syscalls and the µs
  TickTimer are safe here (Stage-5 called `FUN_c002b6e0` from this exact path on hardware).
- **Rate:** **50.0 Hz measured** (Stage-5: 1170 drains / 23.378 s = 50.0 Hz; 20 ms period). That is
  ≥ video frame rate (30/24/60-ish) — a clean per-frame-or-better tick.
- **Gyro fidelity bonus:** at each fire the full 600-sample sub-ARM ring is available and ~50 new
  8-byte samples have accrued since the last fire (50 samples/drain measured = 2500 Hz). Copying the
  ring **delta** each tick preserves the entire 2500 Hz gyro stream — no need to hook at 2500 Hz.
- **Why this over a "cleaner per-Vd" site:** it is the ONE injection point proven to run safely on the
  user's camera (Stage-3/4/5 shipped it). It is task context (blocking-tolerant, syscall-safe), fires
  above frame rate, and already sits next to the gyro ring. Recommended as the default.

### 1B. ALTERNATIVE — sensor **Vd frame IRQ 0x79** handler `FUN_c0125478` — CONFIRMED site, INFERRED-safe
- **What it is:** the sensor Vd (vertical-sync) frame interrupt. AF_AE_INTERNALS §(3-tap register)
  states the AF thread's per-frame wake source = "**sensor Vd 幀中斷 IRQ 0x79** (`FUN_c0125478`, bound
  via `FUN_c0016a7c(0x79,…)`, pri 0x37), dispatched by the scheduler." `FUN_c0125478` is a **Thumb**
  function (verified: prologue `push.w {r4,r5,r8,lr}` at `0xC0125478`, entry `0xC0125479`). It calls a
  registered callback `[0xC31D89C4]` and `FUN_c0128e50`.
- **Rate:** exactly **per-Vd** (phase-locked to the frame: ~30/60 Hz per readout). Cleaner phase than
  the gyro tick if you need frame-aligned samples.
- **Context:** **IRQ / interrupt level.** Tighter budget, and `tk_*` blocking syscalls are prohibited
  here (standard µITRON rule). A hook must be *very* tiny: read raw fixed cells + snapshot only. The µs
  TickTimer read (`FUN_c002b6e0`, a monotonic counter read) is *probably* IRQ-safe but that is
  **INFERRED** — mark PROBE.
- **Recommendation:** use 1A first. Only move to 1B if strict per-Vd phase alignment matters, and then
  keep the IRQ hook to raw-cell copies (no syscalls, no `tick_us` until proven).

### 1C. NOT recommended for the hook: AF thread `FUN_c028c620`
The AF task (AfMgr, idx 26, prio 14) wakes each Vd on event flag `0xC33D51C8` bit0 and is the true
per-frame consumer of the AF state — but hooking inside the AF thread risks destabilizing autofocus
mid-drive. Read its outputs from the sampler; do not inject into it. (CONFIRMED wake mechanism,
AF_AE_INTERNALS.)

---

## 2. WHAT IS COHERENT AT THE 1A (gyro) TICK

The 1A hook fires asynchronously to the AF/tracking/Vd tasks (it is the GyroData 20 ms tick, phase-free
vs Vd). Each fast-state global is written by its OWN task per-Vd; the sampler just snapshots the current
value. Consequences:

| Source | Addr | Coherent at gyro tick? | Note |
|---|---|---|---|
| Gyro ring (delta) | ring via `0xC31E3FCC`→P→`*(P+0x60)`=`0x2E00644C`, head @ring_base | **YES, fully** | read head word once, copy samples since our last head; single-writer ring, race-free snapshot | 
| AAT box `{x,y,w,h}` | `0xC3033E00` (i16×4) + conf `0xC3033E26` | mostly — tiny tear risk | 8-byte struct written per-LV-frame by tracking task; a mid-write read could tear x/y vs w/h once in a while. Acceptable for telemetry; flag it | 
| AF contrast HI/LO | `0xC32985E8[idx]` / `0xC32986B4[idx]`, idx `_DAT_c3291534` (`0xC3291534`) | current-frame value | i32, updated per CAF eval frame (divisor 1–2 → ~17–33 ms). Read idx then the cell | 
| AF peak now/max/min | `0xC32915C4 / …C8 / …CC` | current | i32 | 
| AF drive/servo mode | `0xC32065A0` | current | i32 (4/8 = AF-C servo) | 
| AF route/strategy | `0xC32915B0` | current | i32 | 
| Body-motion flag | `0xC3404678 + 0x04` | current | nonzero = AF-C wants Rocking | 
| Focus position | getter `FUN_c035fd48()` | **stale mid-move** | getter samples at drive-END only (AF_LIVE_STATE §5). Sample every K ticks, treat as slow | 
| Exposure/gain `G` | `0xC343A6A0` fields (+0x0c mode, +0x18/ISO, +0x34 HCG) | slow | sample every K ticks (§3) | 

All the `0xC320xxxx / 0xC329xxxx / 0xC33Dxxxx / 0xC37Cxxxx` cells are live-BSS the firmware derefs every
frame → safe raw reads (AF_LIVE_STATE_MAP). **Never** read the unmapped hole `0xC31C0000–0xC31F0000`
(froze the camera — GYRO archive §六). The AAT color-model deref `*0xC37CDFA8` and `FD_WORK 0xC37CD754`
are NOT in the per-tick set (deref/size risk) — leave them to the slow request/response shell.

---

## 3. RING BUFFER + RECORD DESIGN

### 3.1 Placement — code cave in main-ARM RAM (CONFIRMED writable & executable on-camera)
The loaded main-ARM image at `0xC07xxxxx` is DRAM-resident, writable, and executable (Stage-4/5 wrote &
ran code in it). Zero-cave scan found:
- `0xC072DE64` len **0x4BDC (19420 B)** — the Stage-4/5 cave (only 0x368 B used).
- `0xC0732C81` len 0x2003, `0xC0728758` len 0x405 — spares.

**Proposed layout inside the big cave:**
```
0xC072DE64  ..  +0x0600   sampler stub + hook trampoline   (code)
0xC072E464  ..  +0x001C   CONTROL BLOCK (see 3.3)          (head/tail/seq/drop/gen)
0xC072E480  ..  0xC0732A40  RING BUFFER  (~0x45C0 ≈ 17.7 KB, byte ring)
```
17.7 KB / ~120 B avg frame ≈ 145 frames ≈ **~3 s of buffering @50 Hz** — ample slack for the worker.
(If more is wanted, allocate a memmgr buffer instead; the cave is simplest and proven.) All of it is
main-ARM cached DRAM; producer (GyroData task) and consumer (worker task) run on the same core so a
plain read/write + a `dmb` between payload-write and head-publish is coherent. **Do NOT** issue any
explicit cache-invalidate/clean calls — those are known to hard-lock (USB/gyro notes).

### 3.2 Per-tick TELEMETRY FRAME (little-endian; fixed 52 B + variable gyro tail)
```
off  size  field              source
+0   u32   magic = 'TLM1' (0x314D4C54)
+4   u16   frame_len          total bytes = 52 + 8*gyro_n
+6   u16   seq                tick counter (wraps 16-bit)
+8   u32   tick_us            FUN_c002b6e0()          (µs, wraps ~71.6 min)
+12  u16   gyro_n             raw samples in tail (0..~64; clamp)
+14  u16   gyro_head          ring head index at drain (for continuity check)
+16  i16   gyro_x  (+18 y, +20 z, +22 pad)   latest sample (convenience; full set in tail)
+24  i16   aat_x (+26 y, +28 w, +30 h)       0xC3033E00
+32  u8    aat_conf           0xC3033E26   (>19 = locked)
+33  u8    af_drivemode       (u8 of 0xC32065A0: 4/8 = AF-C servo)
+34  u8    af_route           (u8 of 0xC32915B0)
+35  u8    flags              bit0 body-motion(0xC3404678+4!=0), bit1 slow-block-present, bit2 wrap
+36  i32   af_contrast_hi     0xC32985E8[ _DAT_c3291534 ]
+40  i32   af_contrast_lo     0xC32986B4[ _DAT_c3291534 ]
+44  i32   af_peak_now        0xC32915C4
+48  i32   focus_pos          cached; refreshed every K ticks (slow)
--- variable tail ---
+52  gyro_n × { i16 x, i16 y, i16 pad, i16 z }   raw ring delta since last tick (2500 Hz)
```
Fixed state block = **52 B/tick** ("tens of bytes" as required); gyro tail ~50×8 = 400 B/tick optional.
At 50 Hz: state ≈ 2.6 KB/s, +gyro ≈ 20 KB/s — trivial for bulk EP84.

**SLOW fields** (exposure/gain, focus range) don't belong every tick. Emit a separate **`'TLMS'` slow
frame** every K≈50 ticks (~1 s) carrying `G` @`0xC343A6A0` (ISO/gain_state/HCG/analog), focus min/max,
AF area mode `0xC32046A4`. Keeps the hot record small and avoids calling getters every tick.

### 3.3 Control block (single-producer / single-consumer, lock-free)
```
+0x00 u32 head        producer-owned  (byte offset of next write)
+0x04 u32 tail        consumer-owned  (byte offset of next read)
+0x08 u32 seq         producer tick counter
+0x0C u32 drop_frames producer: bumped when a frame won't fit (ring full) — frame skipped, never blocks
+0x10 u32 gen/magic   = 'TLMR' once initialized (worker sanity gate)
+0x14 u32 ring_base   = 0xC072E480 (self-describing for the host)
+0x18 u32 ring_size   = 0x45C0
```
Producer writes payload into `[head..)`, `dmb`, then publishes new `head`. If `free < frame_len`,
bump `drop_frames` and skip (bounded, non-blocking). Consumer reads `tail..head`, copies out, advances
`tail`. Wrap handled with a frame that never straddles the end (if it won't fit before end, write a
1-byte `'P'` pad-to-wrap marker or store `frame_len` first so the reader can detect wrap). Simplest:
byte ring with `frame_len` at +4 lets the reader walk frames; on wrap the producer pads the tail gap
with zero and the reader skips zero (magic-resync).

---

## 4. PUSH PATH (worker task + framing)

### 4.1 Worker task (proven ABI)
Create one low-priority worker via the **main task path** (TASK_ABI_VERIFIED §6, proven on-camera as
probe A5 "WORK", id 119): `tk_cre_tsk 0xC0016A58` (service 0x80010100) + `tk_sta_tsk 0xC0016BC0`.
Descriptor: `tskatr=1 (TA_HLNG)`, `entry=<worker>`, **`itskpri=0x64 (100)`** (TASK_PRIORITY_MAP §6:
strictly below shell=25 and gyro=20, a proven in-use level), `stksz=0x2000`. Cleanup via main-path
`tk_ter_tsk 0xC0016E?`/`tk_del_tsk 0xC0016978` if needed (or self-loop with a stop flag).

### 4.2 Drain loop (event-driven EP84, mode 2 — CONFIRMED path)
Reuse the shell's proven EP84 IN arming (USB_COMPLETION_PATHS). This is small data → no giant-TRB:
```
loop:
  if (head == tail):            # nothing new
      dly_tsk(5)                # 0xC03705D8(r0=5ms); yield
      continue
  n = copy_frames(tail..head, out_buf, up_to ~8 KB)   # coalesce many frames per transfer
  FUN_c01e6b80(9)               # StartTransfer EP84 IN (param 9)
  r = FUN_c01e4e80(4, timeout)  # block on ctx4 completion flag (IRQ-posted); 0=done -5=timeout
  if r==0: advance tail by n; else handle timeout/disconnect (bounded)
```
`FUN_c01e4e80(4,…)` sleeps on the shared completion event flag `_DAT_c31e3210` set by DWC3 IRQ 0x34 —
genuine event-driven, no spin-poll. Coalesce multiple ring frames into one bulk transfer for
efficiency. **Coexistence:** the worker shares the EP84 mode-2 endpoint with the request/response shell
— they must not both arm EP84 concurrently. Either (a) run telemetry as a *mode* the shell enters (shell
hands EP84 to the streamer until a STOP command), or (b) gate on the shell being idle. See
SHELL_COEXIST.md (disarm/quiesce discipline). **This ordering is the main integration risk → PROBE.**

### 4.3 Host framing (continuous stream parser)
The host reads a byte stream of concatenated frames. Resync rule: scan for `'TLM1'`/`'TLMS'` magic,
read `frame_len`, validate `52 + 8*gyro_n == frame_len` (for TLM1), consume, repeat. `seq` gaps +
`drop_frames` (echoed in the periodic TLMS frame) tell the host how many ticks were lost. `tick_us`
gives absolute timing; per-gyro-sample time = interpolate 400 µs back from `tick_us` across the tail
(same scheme Stage-5 validated). No CRC needed for a live monitor; add a per-frame u16 checksum if
recording to disk.

---

## 5. SAFETY

Hook runs in the GyroData task (1A) — tiny, non-blocking, bounded. Rules:
- **No locks, no blocking syscalls in the hook.** Only allowed calls: the original `blx 0xC01EC6F8`
  (must re-issue) and `FUN_c002b6e0` (tick_us, proven safe from this task in Stage-5). Everything else
  is raw fixed-cell reads + one ring copy. Bound the gyro tail copy (clamp `gyro_n`, e.g. ≤64).
- **Ring full ⇒ skip + bump drop_frames.** Never spin or wait in the hook.
- **`dmb` before publishing `head`; no cache-invalidate/clean calls** (hard-lock risk — USB/gyro notes).
- **Restore hook on teardown:** rewrite `0xC00D0794` back to `blx 0xC01EC6F8` before removing the cave
  (AutoRun discipline: restore hook site first).
- **Addresses UNSAFE to touch from any context:** the unmapped hole `0xC31C0000–0xC31F0000` (freeze).
  Do **not** deref `*0xC37CDFA8` (AAT color model) or read `FD_WORK 0xC37CD754` (0x38400) in the hook.
  **Never** call any focus-DRIVE function (`FUN_c035ffc0`, `FUN_c04ef7d0`) or any setter from the hook —
  read-only sampling only.
- **focus_get_pos (`FUN_c035fd48`)**: zero-arg getter, low risk, but returns stale value mid-move and
  is a *call* — sample it only every K ticks in the slow block, or read a pinned cell once found. Do NOT
  call it every 20 ms.
- **AAT tear:** the 8-byte AAT box may occasionally tear across a tracking-task write — acceptable for a
  monitor; note it in the host tooling.
- **EP84 sharing** (§4.2) is the real hazard, not the hook: two arm-ers on ctx4 will collide. Enforce a
  single owner (shell-hands-off or idle-gate).

---

## Feasibility & recommendation (summary)

**Feasible and safe.** Recommended build:
- **Hook site: `0xC00D0794`** (gyro handler), displace `blx 0xC01EC6F8` (4 B, ARM), runs in GyroData
  task prio 20, **50 Hz** — proven-safe on the user's camera, syscall-safe, above frame rate, and copies
  the full 2500 Hz gyro delta each tick. (Use IRQ 0x79 `FUN_c0125478` only if strict per-Vd phase is
  required, with IRQ-only raw-read constraints.)
- **Record:** 52-byte fixed state frame (`'TLM1'`, tick_us, seq, gyro-latest, AAT box+conf, AF
  drive/route/body-motion, contrast hi/lo, peak, focus) + optional 8 B×N gyro tail; periodic `'TLMS'`
  slow frame for exposure/gain/focus-range.
- **Ring:** ~17.7 KB byte ring in the `0xC072DE64` cave (`0xC072E480`), SPSC lock-free head/tail/drop
  control block — ~3 s buffering @50 Hz.
- **Push:** proven `tk_cre_tsk`(main path, prio 100) worker draining coalesced frames out EP84 IN via
  `FUN_c01e6b80(9)` + event-driven `FUN_c01e4e80(4,…)`; host resyncs on magic+len.

**Bandwidth:** ~2.6 KB/s state, ~20 KB/s with full gyro — trivial. The win is temporal resolution.

**Live PROBES to settle before/at bring-up:**
1. **EP84 ownership** — confirm the telemetry worker can arm EP84 IN without colliding with the shell
   (SHELL_COEXIST): run worker while shell idle, watch for stalls. (Highest-risk item.)
2. **`FUN_c01e4e80(4, timeout)` returns 0** for our context on the streaming path (not just native PTP).
3. **AAT/contrast cell liveness** — a one-shot `mem read 0xC3033E00 0x30`, `0xC32985E8 0x08`,
   `0xC3291534 0x04` in LiveView to confirm nonzero/moving before wiring (cheap, over existing shell).
4. If using 1B: confirm `FUN_c002b6e0` is IRQ-safe (or drop tick_us from the IRQ hook and timestamp in
   the worker).
