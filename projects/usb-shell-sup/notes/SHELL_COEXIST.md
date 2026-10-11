# SIGMA fp Ver.5.02 — USB Shell Worker ↔ Normal-Operation Coexistence

<!-- index-stamp -->
> **這份的結論已被推翻。**
> 這份寫的是 EP 0x05 OUT / EP 0x84 IN。現行 build 用 EP 0x01 / 0x82 / 0x83(`host/fpshd.c:31-32`、`patches.py:15-20`),EP84 在現行描述元下不存在。
> 先看 [`USB_SHELL_INDEX.md`](USB_SHELL_INDEX.md)。


Why the persistent VENDOR-USB "shell worker" (prio 28, EP05 OUT / EP84 IN) can freeze the
camera on a half-press when the host daemon has released the interface, and how to make the
worker **idle-transparent**.

Firmware `out/MAIN_c0000000.bin`, base `0xC0000000` (file_off = addr − 0xC0000000).
Decomp `out/decomp/full/blk_c0*.c`. Builds on `USB_COMPOSITE_MAP.md`,
`USB_COMPLETION_PATHS.md`, `USB_COMPOSITE_RECIPE.md`, `TASK_PRIORITY_MAP.md`,
`CAMERA_STATE_SOURCES.md`. **[C]** = confirmed from code/bytes, **[I]** = inferred,
**[P]** = needs a live probe.

---

## 0. TL;DR

- **Most likely freeze cause [I]:** the worker **re-arms EP05/EP84 (StartTransfer → DEPCMD)
  while the DWC3 link is NOT in U0-configured state.** When the daemon releases interface 1,
  the device stays *configured* (releasing a libusb interface sends **no** SET_CONFIG(0) and
  **no** bus reset), so the link idles and drifts to **U1/U2/U3 suspend**, or the host stack
  issues a **bus reset**, exactly around the moment you half-press (the half-press flips
  camera power/enumeration state). The firmware's reset/suspend handlers **tear down all data
  endpoints (ep1..6) and zero the DALEPENA shadow**; the worker's *un-gated* re-arm then fires
  DEPCMDs at a disabled/suspended endpoint. That desyncs `DALEPENA(HW) 0x2100C720` vs shadow
  `0xC31E398C` and stalls the DEPCMD busy-spin, wedging the controller. The whole-camera hang
  (UI + image) is consistent with a **DWC3 IRQ-0x34 livelock** on the wedged controller (IRQ
  runs above every task, so it starves imaging/UI regardless of the worker's low priority).
- **The builder hook `0xC04DC618` is almost certainly NOT the half-press trigger [C-path]:**
  it lives inside `FUN_c04dc4c0` (the `func_id==5` *connect/enumerate* handler), which is
  reached **only** by an explicit "start USB gadget mode" call (`FUN_c0031910/…c10`), i.e. a
  **USB MODE CHANGE** (menu usb ptp/msc/uvc). A suspend/resume/bus-reset does **not** re-enter
  it — those go through the device-event path (`FUN_c01e7498`/`FUN_c01e3d68`) which re-arms
  *existing* endpoints, never rebuilds descriptors. **But** the hook *will* break a genuine
  menu-driven USB mode change while installed → the worker/AutoRun should be able to uninstall
  it when idle (§4).
- **Idle-transparency is FEASIBLE with a named, readable gate [C]:** call
  **`FUN_c01e40d0()` @ `0xC01E40D0`** (zero-arg, side-effect-free) → returns the
  bConfigurationValue when *configured AND running*, `-1` otherwise. Combine with a
  not-suspended check (`_DAT_c31e3748 (0xC31E3748) == 3`, i.e. NOT 4=suspend) and "no pending
  device event" (`_DAT_c31e3900 (0xC31E3900) == 0`). When the gate is false: **disarm EP05/EP84
  and do NOT re-arm** — sleep-poll the gate instead of arming TRBs.

---

## 1. USB device-controller state machine & the disconnect/reset/suspend handlers [C]

### 1.1 Layers
- **Session/enumerate layer** (mode selection, descriptor build): `FUN_c0031910(func_id)` →
  `FUN_c0031a40` → `FUN_c0031c10` → per-mode builder. `func_id==5` → **`FUN_c04dc4c0(5)`**
  (contains the project hook `0xC04DC618`) → `FUN_c04e9148` (PTP builder). Entered only on an
  explicit mode start, **never** from a link event.
- **Link/device-event layer** (reset/suspend/resume/disconnect): DWC3 event ring ISR
  **`FUN_c01e3660`** (IRQ `0x34`) decodes DEVT events and OR-s a type bit into
  **`_DAT_c31e3900` (0xC31E3900)** (`blk_c01.c:134678`), then posts the shared completion flag
  `_DAT_c31e3210` bit `0x10000000`. A task drains `_DAT_c31e3900` via
  **`FUN_c01e7498` (`@0xC01E7498`)**.

### 1.2 `FUN_c01e7498` — device-event dispatcher (the reset/suspend/resume handler map) [C]
Decodes `_DAT_c31e3900` bits (`blk_c01.c:138020`):

| `_DAT_c31e3900` bit | DEVT meaning | Action | Return code to session task |
|---|---|---|---|
| `0x001` | **Disconnect** | `local_40 = -4` | **-4 = DISCONNECT** |
| `0x002` | **USB Reset (USBRst)** | sets `_DAT_c31e3748 = 2`; if `DSTS(0x2100C700) & 0x3f8`: **EndTransfer ep1..6** (`FUN_c01e6d48`), clear DEPENA bits `0x3f8`, `FUN_c01e5e20`, re-init ep0 `FUN_c01e62a8(0)` | (drops to reset cleanup) |
| `0x010` | **ConnectDone / re-config** | if `_DAT_c31e3a2c`: **re-arm all active eps** (`FUN_c01e69e8(0xc,…)`); if state==4 → state=3, code `0x31` | reconfigure |
| `0x040` | **ULStChng (link-state change → SUSPEND/RESUME)** | read `DSTS 0x2100C70C`; if link field `&0x3c0000==0xc0000` (U3) and state∈{2,3} and `DAT_c31e396c!=0` → **`_DAT_c31e3748 = 4` (suspend)**, code `0x30`; set/clear `_DAT_c31e3a2c` from `DSTS&7==4` | suspend/resume |
| `0x200` / `0x800` | other/err | `local_40 = -1` | error |

- **Full bus-reset cleanup** = `FUN_c01e67f8` (`blk_c01.c:137380`): zeros **`DAT_c31e396c`
  (config byte)**, **`_DAT_c31e398c` (DALEPENA shadow)**, `DAT_c3032a92` (link-state cache),
  `_DAT_c31e3884`, the per-ctx tables (`0xC31E3970` +0x10, `0xC31E39A4` +0x54), etc. **After a
  reset the device is UNCONFIGURED and every data endpoint is torn down.** [C]

### 1.3 The state variable `_DAT_c31e3748` (0xC31E3748) [C]
| value | meaning | set at |
|---|---|---|
| 0 | off / deinit | `FUN_c01e3318(3)`, teardown |
| 1 | powered / ep0 up (attached) | `FUN_c01e3170`, re-init paths |
| 2 | default / just-reset | reset event (`:138106`) |
| 3 | **configured / running** | resume ConnectDone (`:138099`) |
| 4 | **suspended (U3)** | ULStChng (`:138063`) |

### 1.4 What a re-arm while host-absent does to the controller [C mechanism / I for the freeze]
- StartTransfer `FUN_c01e6b80` → issues DEPCMD via **`FUN_c01e6a48`** (`blk_c01.c` ~137519 /
  the DEPCMD writer). `FUN_c01e6a48` writes `DEPCMD(0x2100C80C) |= 0x400 (CMDACT)` then
  **busy-spins** `while (DEPCMD & 0x400)`, bounded by `FUN_c01e4cb8(…,60000)` (elapsed-time
  timeout) and `FUN_c01e3318(2)` (controller-alive bit `uRam300b0000 & 0x10`). Bracketed by
  `FUN_c01e6758`/`FUN_c01e67b0`, which only toggle GCTL suspend bits `0x2100C200 & 0x140` — **not
  a global lock**. [C]
- If the link is in **U3/suspend** (PHY low-power) when the DEPCMD is issued, CMDACT does not
  clear and the spin runs to its timeout; DALEPENA shadow (`0xC31E398C`) vs HW (`0x2100C720`)
  desyncs because the config-gated resync at `blk_c01.c:138229` runs **only when
  `DAT_c31e396c != 0`**. A half-torn-down/half-suspended controller that keeps signalling
  `GEVNTCOUNT (0x2100C40C)` → **IRQ-0x34 livelock** in `FUN_c01e3660`, which runs above all
  tasks → **whole-camera freeze, battery-pull recovery.** [I — the exact stall point is [P]]

**Note (from `CAMERA_STATE_SOURCES.md`):** blind reads inside `0xC31C0000–0xC31F0000` froze
the camera before (unmapped holes). The USB state cells below are all **live BSS the USB stack
derefs**, so reading them is safe; do not widen the window.

---

## 2. What a half-press (S1) touches vs. the shell worker [I, with [C] negatives]

**Direct USB-connect call?** No. `UsbDoConnect1 (@0xC04BBB60)` — the class-transition entry —
is called only from USB **session state handlers** (`CommonEventHandler_w71c1`,
`StandbyEventHandler_w71c1`, `UsbEventHandler_w71c1`, `blk_c04.c:57195/98328/101221`), which
are driven by the device-event codes (0x30 resume / 0x31 reset / 0x10 idle) produced by
`FUN_c01e3d68`. The half-press (AfMgr, prio 26) does **not** call `FUN_c0031910/…c10` or
`FUN_c04dc4c0`. So the half-press does **not** re-enter our builder hook. [C-path]

**Shared lock / priority inversion?** Priorities (`TASK_PRIORITY_MAP.md`): AfMgr=26,
usbctrl=20, usb_ds=21 — **all outrank the worker (28)**. The worker cannot starve them by CPU.
The DEPCMD path takes **no task mutex** the AF path needs (§1.4). So a plain busy-spin in the
worker cannot by itself hang the UI — **which is why the freeze needs the controller-wedge /
IRQ-livelock pathway, not a lock.** [C for "no shared task-lock on the DEPCMD path"]

**Shared endpoint contexts / DALEPENA?** YES — this is the real shared resource. The worker's
EP05(ctx5)/EP84(ctx4) live in the same DWC3 endpoint set (ctx table `0xC31E3888`, DALEPENA
`0x2100C720`, shadow `0xC31E398C`, completion flag `0xC31E3210`) that the native stack
reset/suspend handlers tear down. The conflict is **worker-rearm vs. link-event-teardown of the
same endpoints**, not an AF data structure. [C]

**Shared DMA buffer `0xC3757A7C`?** Not an imaging buffer — it's a `get_type/rel_type …Byte`
typed allocation (`blk_c03.c:171247`, debug-logged). No evidence the half-press/AF path touches
it. Not the conflict. [C-negative]

**So the concrete shared resource a half-press exercises indirectly = the DWC3 endpoint
hardware (DALEPENA/ctx4/ctx5/event-ring).** The half-press is the *trigger* that flips the USB
link state (idle→suspend, or host-side re-probe→reset); the worker's un-gated re-arm is what
turns that transition into a wedge. [I]

---

## 3. Idle-transparent worker design [C for the gate, I for the policy]

### 3.1 The gate — "vendor interface up AND host actively configured AND link active"
Prefer the firmware accessor over raw cells:

| Signal | How to read | True means |
|---|---|---|
| **`FUN_c01e40d0()`** `@0xC01E40D0` | **CALL** (0-arg, no side-effect) | returns bConfigurationValue (>0) iff `_DAT_c31e3748 ≥ 2` **AND** `DAT_c31e396c != 0`; else `-1`. **Primary "configured" gate.** [C] |
| `_DAT_c31e3748` | raw `mem read 0xC31E3748 4` | must be **`== 3`** to arm (3=running; 4=suspend, 2=just-reset). Excludes the suspend case `FUN_c01e40d0` alone misses. [C] |
| `_DAT_c31e3900` | raw `mem read 0xC31E3900 4` | must be **`== 0`** (no unhandled reset/disconnect/suspend event pending). [C] |
| `DAT_c3032a92` | raw `mem read 0xC3032A92 1` | link-state cache; `0` = U0/active. Optional belt-and-suspenders. [C] |
| DALEPENA HW vs shadow | `mem read 0x2100C720 4` vs `0xC31E398C 4` | if they differ, a teardown happened — do NOT arm until re-synced. [C] |

**Arm-permit predicate:** `FUN_c01e40d0() > 0  &&  _DAT_c31e3748 == 3  &&  _DAT_c31e3900 == 0`.

> Honest limit [C]: **no firmware flag distinguishes "daemon closed its handle" from "daemon
> attached but idle."** Releasing an interface leaves the device configured
> (`DAT_c31e396c` stays nonzero, state stays 3). The only device-side signal of "no host
> traffic" is the **EP05 OUT command timeout the worker already sees**. So idle-transparency
> gates on *link health* (safe to arm?), not on *daemon presence*. That is sufficient: the
> freeze is a link-health problem, not a daemon-presence problem.

### 3.2 Worker policy
```
loop:
  if arm_permit():                      # FUN_c01e40d0()>0 && state==3 && events==0
        EndTransfer(EP05); arm TRB; StartTransfer(10)     # as today
        r = FUN_c01e4e80(5, T)          # blocks on 0xC31E3210 until IRQ
        if r == -4 (disconnect) or r == -5 (timeout): fall through to re-check gate
        else: process host cmd; reply on EP84; continue
  else:                                 # host absent / link suspended / reset in flight
        EndTransfer(EP05); EndTransfer(EP84)   # QUIESCE — leave endpoints DISARMED
        release/hold the TRB+DMA buffer (do NOT keep a TRB armed)
        sleep ~200 ms (plain tk_dly — NOT FUN_c01e4e80, which would arm nothing/spin)
        # optional: block on the session event-queue so the IRQ wakes us on real activity:
        #   XC_UsbCtrlCore queue FUN_c001a048(id, 0x100000, …) — connect/resume events
  goto loop
```
Key change vs. today: **never call StartTransfer while `arm_permit()` is false.** That removes
the "re-arm into a suspended/reset controller" that wedges the DWC3. On resume, `FUN_c01e40d0`
flips back to >0 and state→3, and the worker re-arms cleanly.

### 3.3 The builder hook `0xC04DC618` — uninstall when idle? [C reasoning]
- It does **not** re-fire on suspend/resume/reset, so it is **not** the half-press freeze and
  does **not** need removing to fix that.
- It **does** permanently redirect `func_id==5` (`FUN_c04dc4c0`). If the user ever triggers a
  real USB **mode change** (menu → PTP/MSC/UVC, or a host that forces re-enumeration to class
  0x06) while the patch is live, the connect path runs our vendor-build code in the wrong
  context → broken enumeration / possible hang. **Recommendation:** make AutoRun/the worker
  able to **restore the original instruction at `0xC04DC618`** (revert the patch) whenever it
  goes idle or detects a pending mode change, and **re-install** it when standing the shell
  back up. This is a code patch we own, so it is straightforward. Treat it as a *separate*
  hardening item from §3.2, not the primary freeze fix. [I that it's separate; C that the hook
  is off the suspend/resume path]

---

## 4. CONFIRMED vs INFERRED summary

**CONFIRMED [C]:**
- Reset/suspend/disconnect handler map (§1.2), state var values (§1.3), the reset cleanup that
  zeros `DAT_c31e396c` + DALEPENA shadow + tears down ep1..6 (`FUN_c01e67f8`).
- DEPCMD issue is a busy-spin with a 60000-unit timeout and only GCTL-suspend-bit bracketing,
  **no task mutex** (§1.4).
- The builder hook is on the *mode-start* path only, not the link-event path (§0, §3.3).
- The gate accessor `FUN_c01e40d0()` and the raw state/event cells (§3.1) exist and are safe to
  read; the config-gated DALEPENA resync at `:138229`.
- Priorities: worker(28) < AfMgr(26) < usb_ds(21) < usbctrl(20) → no CPU starvation of AF/UI.

**INFERRED [I]:**
- The precise freeze chain (half-press → link suspend/host re-probe → endpoint teardown →
  worker un-gated re-arm → DALEPENA desync / DEPCMD stall → IRQ-0x34 livelock → whole-camera
  freeze). The individual links are confirmed; that this *specific* sequence produced the
  observed freeze is inferred (releasing an interface does not itself reset/suspend — the
  half-press-coincident timing is circumstantial).
- That the whole-system hang is an IRQ livelock specifically (vs a 60 s DEPCMD spin the user
  didn't wait out) — both fit "recovered by battery pull."

**NEEDS A LIVE PROBE [P] (over the shell, read-only):**
- P1 — At the moment of freeze/half-press, `mem read 0xC31E3748 4` (state), `0xC31E396C 1`
  (config), `0xC31E3900 4` (pending events), `0x2100C70C 4` (DSTS link state), `0x2100C720 4`
  vs `0xC31E398C 4` (DALEPENA HW vs shadow). If state==4 or events!=0 or DALEPENA≠shadow at the
  hang → confirms the suspend/reset-vs-rearm wedge.
- P2 — `mem read 0x2100C40C 4` (GEVNTCOUNT) repeatedly while hung: a stuck-nonzero / churning
  count confirms the IRQ-0x34 livelock.
- P3 — Repro with the worker **gated** per §3.2 (arm only when `FUN_c01e40d0()>0 && state==3`):
  if the half-press no longer freezes, the design is validated.

---

## 5. Address index

| item | addr | note |
|---|---|---|
| Mode connect handler (contains hook) | `FUN_c04dc4c0` `0xC04DC4C0`; hook `0xC04DC618` | func_id==5 only |
| Mode dispatch | `FUN_c0031910/…a40/…c10` `0xC0031910/…` | explicit mode start |
| DWC3 event ISR (IRQ 0x34) | `FUN_c01e3660` `0xC01E3660` | posts `0xC31E3210` |
| Device-event dispatcher | `FUN_c01e7498` `0xC01E7498` | reset/suspend/resume/disc |
| Session event fetch | `FUN_c01e3d68` `0xC01E3D68` | emits 0x10/0x30/0x31/0x1f |
| Reset cleanup (zeros config+DALEPENA) | `FUN_c01e67f8` `0xC01E67F8` | |
| DEPCMD issue (busy-spin) | `FUN_c01e6a48` `0xC01E6A48` | 60000 timeout, no lock |
| StartTransfer / EndTransfer | `FUN_c01e6b80` `0xC01E6B80` / `FUN_c01e6d48` `0xC01E6D48` | |
| Completion wait | `FUN_c01e4e80` `0xC01E4E80` | 0 done / -5 timeout / -4 disc |
| **Configured? accessor (GATE)** | **`FUN_c01e40d0` `0xC01E40D0`** | >0 iff state≥2 && config!=0 |
| USB device state | `_DAT_c31e3748` `0xC31E3748` | 0/1/2/3=cfg/4=suspend |
| **Config byte (SET_CONFIG value)** | `DAT_c31e396c` `0xC31E396C` | 0=unconfigured |
| Pending device-event bitmap | `_DAT_c31e3900` `0xC31E3900` | 0=none |
| Link-state cache | `DAT_c3032a92` `0xC3032A92` | 0=U0 |
| Suspend-transition flag | `_DAT_c31e3a2c` `0xC31E3A2C` | |
| DALEPENA HW / shadow | `0x2100C720` / `_DAT_c31e398c` `0xC31E398C` | resync only when configured |
| DSTS / GEVNTCOUNT / DEPCMD / GCTL | `0x2100C70C` / `0x2100C40C` / `0x2100C80C` / `0x2100C200` | |
| Completion event flag id | `_DAT_c31e3210` `0xC31E3210` | shared ctx1..6 |
| ctx/mode table base | `0xC31E3888` stride 0x10 | ctx4=EP84, ctx5=EP05 |
| USB session class transition | `UsbDoConnect1` `0xC04BBB60` | from session handlers only |

## ================= WORKER HANG DIAGNOSIS (5-agent fan-out, 2026-08-20) =================
ROOT CAUSE (Item4 + Item5 converge): **EP84 IN is re-armed (StartTransfer 9) with NO EndTransfer(4) first.**
- arm_out (EP05 OUT) is correct/self-healing: EndTransfer(5) → TRB → StartTransfer(10) → wait(5).
- arm_in / do_rawpush (EP84 IN): TRB → StartTransfer(9) → wait(4), NO EndTransfer(4).
- v27 tolerated it via host-paced `ctrl sleep` serialization + stage7 EndTransfer(4) cleanup. Free-running
  persistent worker has neither → when wait(4) times out or host doesn't drain (back-to-back RAWGRAB), next
  StartTransfer(9) hits an already-active EP84 → DEPCMD busy-spin (60s, no mutex) → DWC3 IRQ-0x34 livelock →
  whole-camera hang → reboot. (Matches "RAWGRAB stalls shared EP84 if not serialized".)

RULED OUT [C]:
- Wrong-flag / bit mapping: Item2+3 confirm wait mask (FUN_c01e71e0) == ISR set bits (FUN_c01e3660).
  EP84 logical4 → complete bit21 (1<<(4+0x11)); EP05 logical5 → bit22. Flag obj = _DAT_c31e3210 @0xC31E3210.
- Stale callback / stale rsc-index: Item4 — completion is a STATELESS shared ISR; rsc-idx re-bound every arm
  at 0xC31E3A30+phys*4 (EP84→0xC31E3A54, EP05→0xC31E3A58); StartTransfer reads DEPCMD[22:16], EndTransfer
  consumes same slot. No per-transfer callback to go stale.
- Worker DALEPENA desync: Item4 — worker never writes DALEPENA (0x2100C720) / never disables an ep; enables
  happen inside SET_CONFIG control transfer whose status stage flushes shadow (0xC31E398C)→reg (FUN_c01e7780).
  NOTE Item2: the command-0x2a enable path (FUN_c01e62a8) only sets the shadow + auto-STARTXFERs OUT eps →
  latent hang IF an ep is enabled via 0x2a with no following control transfer (reg never flushed). Not hit by
  the current SET_CONFIG path, but a footgun if the enable path changes.

FIX (mirror arm_out): insert EndTransfer(4) at head of arm_in (~L457) and do_rawpush (~L386):
    mov r0,#4 ; blx FN_ENDX(0xC01E6D49)   @ retire prior EP84 xfer before re-arm
Minimal-risk variant: only on the IN-wait-timeout fault_retry branch (happy path untouched).

SECONDARY HARDENING (Item5):
- Re-assert ctx4 mode=2 at head of arm_in: `mov r1,#2; str r1,[=0xC31E38C8]`. v27 stage3 did this every IN
  arm; if ctx4 reverts to mode 3 (record-start/re-enum), completion routes to mode-3 callback 0xC30257B0 NOT
  the shared flag 0xC31E3210 → wait(4) blocks forever.
- Gate should also check arm-gate FUN_c01e40d0 / DALEPENA 0x2100C720 == shadow 0xC31E398C before arming
  (current gate L143-158 only checks USB_STATE>=2 / LINK!=0 / EPMASK==0).

SEPARATE [P] (not this hang): TRB bufptr window — worker uses buf+0xC0000000, firmware elsewhere buf-0x40000000
(cached vs uncached alias; 0xC31E3264[ep]=0xC31E3238[ep]+0x40000000). Verify the DMA-visible window is right.

Key EAs: StartXfer FUN_c01e6b80(9=EP84,10=EP05); wait FUN_c01e4e80(4=EP84,5=EP05); EndXfer FUN_c01e6d48
(thumb 0xC01E6D49); ISR FUN_c01e3660 (IRQ0x34); flag 0xC31E3210; rsc-idx tbl 0xC31E3A30; ctx4 mode 0xC31E38C8;
armed-state 0xC31E3910; DALEPENA 0x2100C720/shadow 0xC31E398C; event ring 0x431E3780.

## ===== CORRECTION (2026-08-20, user firmware analysis, EAs verified) =====
The record-start hang is NOT the EndTransfer(4) gap and NOT a ctx4-mode rewrite (no evidence record-start
writes ctx4 mode — retract Item5 hardening #2). TWO DISTINCT failure modes:
- **Idle streaming EP84 wedge** = missing EndTransfer(4) before EP84 re-arm (Item4/5). Still worth fixing for
  RAWGRAB serialization. Secondary.
- **Record-time hang (PRIMARY)** = v27 BYPASSES the firmware's native USB-connect ADMISSION gate.

### The admission mechanism (verified in decomp)
- Shell recording == physical record button: both drive the SAME RecMgr state machine.
  movrec dispatcher 0xC0403558, start FUN_c0403298, stop 0xC0403400 (rec 0xC04074E8 = MOV log only).
  movrec start: build SHLLREC observer → RecMgr FUN_c0370fa0(...,0,1) → wait rec-state event (≤600s) →
  RECSTART→REC → ChangeMovieRecording @0xC035C9A0 sets recording flag object+0x157, notifies observers.
- **DelayableUsbConnectingObserver__v1 @0xC0498F40** (bool "can-connect"):
    busy = (*(obj+4).vtable[+0x14])();   // is an exclusive op (recording) in progress?
    if (busy) { vtable[+0x10](); vtable[+0x18](); }   // DEFER: queue connect until state clears
    return busy == 0;                    // permitted iff not busy
  Sibling SystemStatusOperatableObserver__v1 @0xC0498E38 same query. Status masks 0x101080/0x100080/0x80 via
  SysNoRemain (system-status-remain subsystem). So the factory design DEFERS USB connect while recording and
  finalizes it only when the state permits.

### Why v27 hangs on record but not idle
v27 AutoRun: install USB descriptor hook (fixed) → wait FIXED 30s → force-write ctx4/ctx5 → call low-level
endpoint initializer → start EP05/EP84. It NEVER consults the admission gate. If RecMgr is still RECSTART/REC
when v27 forces the USB session, the two state machines deadlock / operate an un-permitted USB session →
top LED red, buttons dead, live view still alive. Idle boot works because no recording state conflicts.
Fixed 30s is not a legal firmware state boundary → apparent time-drift.

### CORRECT FIX = change the BOOTSTRAP (not more endpoint patching)
- Boot: load program + install only the non-USB entry.
- Do NOT force-init USB after a fixed delay.
- Gate v27 init on the firmware's admission: poll/hook the "connect permitted" point — i.e. the
  DelayableUsbConnectingObserver__v1 @0xC0498F40 busy-query returning 0 (RecMgr out of RECSTART/REC, USB
  connect admitted) — THEN run the proven v27 OUT→IN init sequence unchanged.
- Keep v27's verified transfer order.

### OPEN (concrete piece for the fix) [P]
Resolve the vtable +0x14 busy-query to a directly-callable EA + the singleton the worker can reach (or a
simpler RecMgr-recording getter via object+0x157), so the worker bootstrap can poll it instead of the 30s.

### POLLABLE GATE — the concrete worker fix (2026-08-20)
Replace the fixed-30s USB init with a poll of the movie-recording flag:
- **Poll byte `0xC347E08F`** = FUN_c035b2d0()+0x157 (Camera3/RecMgr obj 0xC347DF38 + 0x157). Written by
  ChangeMovieRecording @0xC035C9A0 at RECSTART→REC. **==0 ⇒ USB connect PERMITTED; !=0 ⇒ recording, defer.**
  Absolute address, no live object needed. This is the exact state DelayableUsbConnectingObserver defers on.
- Require ~3 consecutive clear reads (≈200ms apart) to skip the sub-second RECSTART→REC window where the flag
  is transiently still 0.
```c
FUN_c035b2d0();                 // 0xC035B2D0: force Camera3 recMgr lazy-init (optional)
int stable=0;
while (stable<3){ if(*(volatile uint8_t*)0xC347E08F==0) stable++; else stable=0; delay_ms(200);}
run_v27_usb_init();             // proven OUT->IN sequence unchanged
```
Reachable singletons: FUN_c035b2d0 @0xC035B2D0→0xC347DF38 (rec flag +0x157); FUN_c00178d8→0xC3033834
(system-status pub/sub); movie-rec state machine 0xC351FE88 (via FUN_c0370cf8→FUN_c0371730). SysNoRemain
@0xC0017920 = pub/sub register (NOT a peekable status word). vtable+0x14 concrete EA unresolved (observer
ctor not in decomp) but semantics = "recording in progress?" ⇒ the flag peek is the equivalent.
SCOPE: this covers the RECORDING exclusive state (the diagnosed hang). If still/cine switch (masks
0x1000/0x100000) or the 0x80 common lock also block connect, add those checks too.

## ===== RETRACTION (2026-08-20, live trace + Codex) =====
The earlier "WORKER HANG DIAGNOSIS" block ranked **adding EndTransfer(4) before arm_in** as the #1 fix.
**THIS IS RETRACTED — live trace disproves it.** Two SEPARATE failure modes were conflated:

1. **IN-path HWO-never-clears** (live trace 17:57): with EndTransfer(4)-before-arm_in (and background endpoint
   management), EP84 StartTransfer(9) returns success + a resource index, but the TRB's HWO bit never clears,
   DWC3 never executes the IN, NO EP84 completion event fires, wait returns -5. Root: **v27's verified success
   path does NOT EndTransfer before the IN — it cleans up only AFTER a complete round.** Adding EndTransfer(4)
   (and generally turning v27's host-paced controlled transaction into a persistent background USB driver)
   BREAKS the IN path. → DO NOT add EndTransfer(4)/mode patches/self-heal. Stay v27-faithful: init → EP05 OUT
   → wait → EP84 IN → wait → EndTransfer cleanup, host-paced.

2. **Record-then-USB hang at double-blink** (the REAL structural bug): the AutoRun bootstrap force-inits USB
   after a fixed 30s, bypassing the firmware's native USB-connect admission (DelayableUsbConnectingObserver
   @0xC0498F40 → recording flag 0xC347E08F). If RecMgr is in RECSTART/REC, the two state machines conflict.
   Confirmed: even pure v27 (c32a754) hangs when a (shell) recording ran first. Fix = **defer the bootstrap
   USB init until admission granted (recording flag 0xC347E08F clear)**, keeping v27 transfer order UNCHANGED.
   NOT solvable by mode=2 re-assert or EndTransfer.

STRUCTURAL note (Codex): the persistent worker "permanently owns" native ctx4/ctx5 with no lock / ownership
handoff, while the firmware USB state machine also drives reset/resume/record-mode teardown on the same
context/TRB/rsc-idx/event-flag. Long-term: don't permanently own native context — either join the native
dispatcher or establish explicit ownership handoff. Near-term: v27 baseline + bootstrap admission deferral only.

DEPLOYED BASELINE = v27/c32a754 (dist/AutoRun.txt, worker code 0xC072Exxx, GO/state 0xC072E07C). The
admission-gate poll I added earlier went into shell_rw_worker.S (PARALLEL lineage, STATE 0xC072F000) — so it
must be re-targeted onto the v27/c32 bootstrap, not shell_rw_worker.S.

## ===== RECORD-SAFE BOOTSTRAP — firmware attach points (2026-08-20 agent) =====
- 0xC072723C is NOT the builder hook — it's zeroed rodata (SysNoRemain default observer-table template,
  copied to 0xC3033834+0x704 by FUN_c0017868), repurposed as AutoRun code cave.
- REAL descriptor-builder hook = **0xC04DC618** inside FUN_c04dc4c0 @0xC04DC4C0 (func==5 → FUN_c04e9148 PTP
  builder). Reached only via FUN_c0031c10(5) = operator USB-mode-start/replug → DOWNSTREAM of admission.
  ⇒ any gate AFTER enumeration/echo/30s cannot un-admit an in-flight connect (why idlepoll/enum-gated failed).
- Native connect proceed/defer branch: w71c1 __v36 (0xC04510C0 / 0xC0483D38 / 0xC0486E10), gate
  param_2[0x14]!=0 && *param_2==0 → PROCEED UsbDoConnect1 @0xC04BBB60 (→ builder + endpoint-enable
  FUN_c01e62a8); else DEFER (Standby). DelayableUsbConnectingObserver registered mask **0x100080** via
  FUN_c0487468 @0xC0487468 (unreg FUN_c0487490); defers connect while recording.
- **Admission RELEASE = FUN_c00180a0 @0xC00180A0** (publish/notify): walks obj+0x704..+0x7c4, calls each
  observer vtable+0xc(obs, changed_mask, obj+0x18). ChangeMovieRecording @0xC035C9A0 (flag 0xC347E08F) drives
  the status change; on record-end, FUN_c00180a0 re-notifies → deferred connect proceeds. Status obj handle
  FUN_c00178d8 @0xC00178D8 → 0xC3033834.
- FIX RANKED: (b) register OUR observer via SysNoRemain(FUN_c00178d8(),0x100080,&obs), vtable+0xc = our init
  trigger — invoked by firmware at native release, race-free. (a) trampoline-hook FUN_c00180a0, latch+signal
  if (changed&0x100080)&&*0xC347E08F==0. (c) poll 0xC347E08F BEFORE our forced init (echo/FUN_c01e62a9), 3×
  consecutive clear — immediate fix, misses still/cine 0x100000 & common 0x80.
- KEY: the gate must WITHHOLD our forced init until native admission granted; place it BEFORE the endpoint
  init, NOT after enumeration / after GO. v27 OUT→IN order unchanged.

## ===== RECORD-SAFE FIX BUILT (option A, poll_gate detour) 2026-08-20 =====
Deployable minimal fix for the record-then-USB hang, WITHOUT rebuilding the card worker (whose build
pipeline is not in-repo). Gates ONLY the forced endpoint-enable on recording-clear.
- The card echo handler @0xC072DF00 = the forced init: push{r4,lr}; FUN_c01e62a9(4); FUN_c01e62a9(5);
  DALEPENA(0x2100C720)|=0x600; r0=1; pop{r4,pc}. Called ONCE at `echo` (not a per-txn callback).
- FIX: detour 0xC072DF00 (E92D4010 → **0xEA0007BE** = B 0xC072FE00). poll_gate @0xC072FE00 (camera/poll_gate.S,
  clang-assembled, 20 words) replicates the displaced push{r4,lr}, polls REC_FLAG 0xC347E08F for 3 consecutive
  clears (200ms/FN_DLY 0xC01F89C4 apart), then `bx 0xC072DF04` to resume the original endpoint-enable.
  push/pop balanced, lr via stack. Position-independent (all absolute addrs).
- Variant: dist/AutoRun.recsafe-pollgate.txt (= card AutoRun.txt + detour + poll_gate block). SHA
  6bda429c057d471e2ca15ed5b684d6693c94d00c8fcde7602f4b6fd5984ca0f1. Card baseline AutoRun.txt (SHA
  d9c5c9db, c32) UNTOUCHED = fallback.
- NOT YET TESTED on hardware. Deploy = backup AutoRun.txt then rename recsafe variant to AutoRun.txt.
- Scope: gates RECORDING only (REC_FLAG). Native re-enum on operator replug is deferred by firmware admission
  anyway; this gates OUR forced endpoint-enable. Full observer (option b) needs the worker rebuild (blocked).

## ===== ROOT CAUSE of the time-based freeze (2026-08-20, agent, 5 clues) =====
SINGLE mechanism explains all 5 clues: **un-gated persistent ownership of native DWC3 endpoints
ctx5(EP05 OUT)+ctx4(EP84 IN) that ignores the USB link/device state machine.** NOT the gyro hook,
NOT a watchdog, NOT priority.

Freeze fires on the FIRST DWC3 link transition under that ownership (host selective-suspend when idle,
bus reset/re-enum, or record-mode USB reconfig):
- reset/suspend cleanup FUN_c01e67f8 tears down eps + zeroes DALEPENA shadow 0xC31E398C + config byte
  DAT_c31e396c.
- worker's un-gated re-arm keeps issuing DEPCMDs (FUN_c01e6a48 @137475, busy-spins CMDACT|0x400, 60000
  timeout) at a disabled/suspended endpoint.
- DALEPENA HW 0x2100C720 vs shadow 0xC31E398C resync is CONFIG-GATED (blk_c01.c:138229:
  if(DAT_c31e396c!=0 && 0x2100C720!=0xC31E398C) 0x2100C720=0xC31E398C) — can't run while unconfigured →
  permanent divergence.
- wedged controller keeps asserting GEVNTCOUNT 0x2100C40C → DWC3 IRQ 0x34 handler FUN_c01e3660 (above
  every task) can't progress → whole-camera freeze; LV DMA paints one more frame ("live view may stay").
  Battery-pull only recovery. "Time" = latency to first link transition, not an internal accumulator.

RULED OUT [C]:
- Gyro hook 0xC00D0794: inside GyroData task FUN_c00d0738 @156614 (pri 20, 50Hz not 2500). Injection hook
  is ONE-SHOT self-restoring (writes HOOK_ORIG 0xFA046FD7 back, preserves r0) → zero steady-state overhead.
- Watchdog: ZERO watchdog/wdt/heartbeat symbols. FUN_c000ea54 = cache-invalidate (not a timer). Symptom
  (frozen+LV up+battery-pull) disproves a watchdog (would reboot, not freeze). No watchdog exists.
- Priority: worker pri 28 < all critical (Gyro20/usbctrl12/usb_ds14/AF14) — can't starve; freeze is
  IRQ-0x34 livelock, bypasses task priority.

5-CLUE RECONCILIATION:
1 no-daemon→freeze: OS still SET_CONFIGs; host selective-suspend after idle → teardown under un-gated worker.
5 daemon→stable: active daemon keeps link ALIVE (no selective-suspend) → no transition → no wedge. (v27's
  "stability" = the daemon masking the bug.)
2 daemon+rec→freeze: record-mode USB reconfig = a link transition → teardown-vs-rearm collision (also v27
  bypasses admission DelayableUsbConnectingObserver 0xC0498F40 / rec flag 0xC347E08F / release FUN_c00180a0).
3/4 rec transient then freeze: wedge trips on the next transition, correlates with injection completing the
  persistent endpoint ownership, not with recording per se.

FIX (carry onto the deployable v27/c32 lineage — the UN-GATED one; the gated shell_rw_worker.S STATE
0xC072F000 already has most of this but is a parallel build):
- Gate EVERY arm on link health before StartTransfer: FUN_c01e40d0()>0 AND [0xC31E3748]==3 (running not
  4=suspend) AND [0xC31E3900]==0 (no pending event) AND 0x2100C720==0xC31E398C (DALEPENA in sync). If false:
  EndTransfer(EP05)+EndTransfer(EP84), disarm, tk_dly-poll the gate. NEVER StartTransfer into suspended/reset.
- Handle ALL transitions (suspend/reset/record), not just recording. Gyro hook needs no change.
- arm_in also needs EndTransfer(4) before re-arm (EP84 not self-healing like EP05's arm_out EndTransfer(5)).

## ===== ROOT CAUSE — REFINED/code-confirmed (2026-08-20, clue-5 pass) =====
Precise mechanism: LINK POWER-STATE / DALEPENA-ownership wedge. Camera stays alive iff the HOST holds the
DWC3 link in U0 AND the native stack doesn't re-init config. TWO exact triggers:
- TRIGGER 1 (no daemon → host selective-suspend, link U3): worker re-arm StartXfer sets DCTL 0x2100C704|=0x100
  (ULSTCHNGREQ device wakeup) + clears GCTL 0x2100C200 power-down (FUN_c01e6f98/FUN_c01e6758). Host suspended
  an UNCLAIMED iface (no remote-wakeup feature) → ignores device wakeup → PHY stuck U3 → DEPCMD CMDACT(0x400)
  never clears → FUN_c01e6a48 60000-unit busy-spin → GCTL power-bit toggling + ULStChng event stream →
  continuous IRQ 0x34 → device-wakeup-vs-host-suspend LIVELOCK → freeze. Time = host suspend idle timeout.
- TRIGGER 2 (record → native USB reconfig): ChangeMovieRecording @0xC035C9A0 → rec flag 0xC347E08F →
  SysNoRemain 0x100080 → DelayableUsbConnectingObserver reconfig → re-runs FUN_c01e62a8(0) @0xC01E62A8 whose
  tail HARD-SETS DALEPENA 0x2100C720=0x3 and shadow 0xC31E398C=0x3, CLEARING the worker's hand-set 0x600 →
  EP05/EP84 DISABLED in HW. Un-gated worker keeps arming disabled eps → CMDACT never clears → same 60s spin →
  same livelock. Daemon can't save it (eps disabled regardless of host traffic). Config-gated resync
  (blk_c01.c:138229) re-syncs HW←shadow=0x3, confirming the disable, never restoring 0x600.
Clue-5: daemon holds link U0 → DEPCMDs complete, no suspend to fight, FUN_c01e62a8(0) never re-runs →
DALEPENA keeps 0x600 → stable forever.
Confirmed NON-accumulators: rsc-idx balanced (EndTransfer frees, StartTransfer re-allocs 0xC31E3A30+phys*4);
event ring drained per IRQ; wait-timeout FUN_c01e4e80 triggers nothing; the USB semaphore 0xC31E3A88 task
waits TMO_FEVR (no watchdog action). Single-shot wedge, NOT slow accumulation.
FIX: gate every arm on FUN_c01e40d0()>0 (configured) && 0xC31E3748==3 (running≠4 suspend) && 0xC31E3900==0
(no pending event) && (0x2100C720 & 0x600)==0x600 (our eps still enabled) && 0x2100C720==0xC31E398C (synced);
fail→EndTransfer both + disarm + tk_dly-poll, NEVER re-arm into suspended/disabled controller. Re-sync
(re-enable 0x600 only when configured, via admission observer) after any suspend/resume/record transition.

## ===== CLUE 6 (shutdown freeze) CONFIRMED — same wedge (2026-08-20) =====
Power-off USB teardown is another link-down transition the un-gated worker collides with. Two blocking
surfaces: (1) session dispatch FUN_c0031910 @0xC0031910 falls through to a BLOCKING usbTask() (blk_c00:41206)
— shutdown waits on the USB task; (2) teardown's own EndTransfer FUN_c01e6d48 @0xC01E6D48 → FUN_c01e6a48
@0xC01E6A48 BUSY-SPINS a DEPCMD (60000). The worker's StartXfer runs FUN_c01e6f98 @0xC01E6F98 (DCTL
0x2100C704 |= 0x100 = ULSTCHNGREQ device-wakeup) which FIGHTS the shutdown soft-disconnect (DCTL &= 0x7fffffff
RUN=0, blk_c01:134409/134453) on the same unlocked reg → link never settles → usbTask blocks → shutdown hangs.
Device-event dispatcher FUN_c01e7498 @0xC01E7498 (disconnect 0x001→-4; reset 0x002→EndTransfer ep1..6 +
cleanup FUN_c01e67f8 @0xC01E67F8 zeros config 0xC31E396C/shadow 0xC31E398C/rsc-idx 0xC31E3A30→0x80/flag
0xC31E3210). USB deinit FUN_c01e3318(3) @0xC01E3318: state 0xC31E3748=0, wakes waiters (flag bit 0x80000000).
Why daemon-connected hangs shutdown but no-daemon is clean: (timing) daemon → worker in tight active DEPCMD
cycle, teardown window coincides with in-flight DEPCMD; no-daemon → worker parked in 50s wait 99.9% → teardown
completes in the gap. (persistent state) arm_in StartXfer(9) with NO EndTransfer(4) leaves ctx4/EP84
armed-but-never-ended once a daemon drives a reply; worker advanced into active re-arm loop; both survive
cable-pull → collide with power-off. No-daemon never reaches arm_in → ctx4 clean → clean shutdown.
⇒ ALL 6 CLUES = one code-confirmed mechanism (un-gated ctx4/ctx5 ownership vs link teardown). Same fix
(gate/disarm on link-down: state!=3 / pending event / DALEPENA lost 0x600 → EndTransfer both + stop arming,
no StartXfer/no recovery-request) makes suspend, record, AND shutdown clean. [P] hang-time reads: DCTL
0x2100C704, DSTS 0x2100C70C, GEVNTCOUNT 0x2100C40C, worker STATE markers.
