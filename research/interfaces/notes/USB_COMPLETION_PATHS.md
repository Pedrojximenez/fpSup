# USB bulk-transfer completion delivery — EP05 OUT / EP84 IN (fp Ver.5.02)

<!-- index-stamp -->
> 這份寫的是 EP 0x05 OUT / EP 0x84 IN。現行 build 用 EP 0x01 / 0x82 / 0x83(`host/fpshd.c:31-32`、`patches.py:15-20`),EP84 在現行描述元下不存在。
> 先看 [`USB_SHELL_INDEX.md`](../../../projects/usb-shell-sup/notes/USB_SHELL_INDEX.md)。


Question: when an EP05 (Bulk OUT) or EP84 (Bulk IN) TRB completes, how does software
learn of it, and is there a hookable callback/event enabling a self-sustaining
(event-driven) USB worker — or must completion be polled?

Firmware: `out/MAIN_c0000000.bin`, base 0xC0000000. Decomp: `out/decomp/full/blk_c01.c`.
All line numbers below are in `blk_c01.c` unless noted.

---

## TL;DR verdict

| endpoint | mode | completion delivery | hookable? | context | status |
|---|---|---|---|---|---|
| EP05 Bulk OUT (ctx5) | 1 (normal bulk) | IRQ 0x34 → ISR posts **event flag** `_DAT_c31e3210` bit-per-endpoint | yes, via a **task that blocks on the flag** (`FUN_c01e4e80`) — no software callback pointer | wait runs in **task**; the set runs in **IRQ** | CONFIRMED |
| EP84 Bulk IN (ctx4) | 2 (shell) | same event-flag path as above | same | same | CONFIRMED |
| EP84 Bulk IN (ctx4) | 3 (native UVC/isoc) | IRQ → ISR calls **callback pointer `0xC30257B0`** on XferInProgress | yes, a real function pointer — but **shell does not use mode 3** | callback runs in **IRQ** | CONFIRMED (mechanism); N/A to shell |

Completion is **IRQ-driven at the firmware level, independent of AutoRun**. The staged
AutoRun echo polls the HWO bit only because a single `log` handler invocation cannot block;
the firmware's own path is a blocking event-flag wait woken by the DWC3 interrupt.

---

## 1. The DWC3 interrupt handler (completion source) — CONFIRMED

`FUN_c01e3660` (Thumb entry `0xC01E3661`) is the DWC3 event-ring ISR. It has **no textual
caller and no static pointer** in the image because it is registered dynamically at USB init:

```
blk_c01.c:134242  local_cc = 0xc01e3661;            // handler = FUN_c01e3660 (Thumb)
blk_c01.c:134243  FUN_c0016a7c(0x34, &local_d0);     // tk_def_int: define IRQ 0x34 handler
blk_c01.c:134244  FUN_c000fe08(0x34, 1);             // configure
blk_c01.c:134245  FUN_c000fad8(0x34, DAT_c2f165c0);  // priority
blk_c01.c:134246  FUN_c000fca0(0x34, 1);             // enable IRQ 0x34
```

Inside `FUN_c01e3660` (134567+):
- `_DAT_2100c40c & 0xffff` = DWC3 **GEVNTCOUNT** (bytes pending). If 0 → return (134589).
- Dequeues one 4-byte event `uVar7` from the software event ring
  `_DAT_c31e3744 + _DAT_c31e374c*4`, advances index mod 0x40 (134593-134602).
- Writes `_DAT_2100c40c = 4` to **ACK** 4 consumed bytes (134603).
- Decodes DEPEVT: `uVar7 & 1 == 0` → endpoint event; physical EP = `(uVar7&0x3f)>>1`;
  `iVar6` = ep number, direction = low bit. Event type field `uVar3 = uVar7 & 0x3c0`
  (= DWC3 event-type<<6):
  - **`0x40` (type 1 = XferComplete)**: for non-control ep, clears the software
    active flag and sets completion flag bit `1 << (iVar6+0x11)` (134623-134625).
  - **`0x80` (type 2 = XferInProgress)**: only if `_DAT_c31e3964 & 4` (mode-3 streaming
    active) → `FUN_c01e61a0()` (the `0xC30257B0` callback) or `FUN_c01e6d48()` on error
    (134628-134637).
  - **`0xc0` (type 3 = XferNotReady / progress)**: sets completion flag bit
    `1 << (iVar6+5)` (134666, 134672).
- Posts the accumulated mask to the endpoint-completion event flag:
  ```
  blk_c01.c:134685  FUN_c0016b9c(_DAT_c31e3210, uVar5);   // tk_set_flg
  ```

## 2. The endpoint-completion event flag `_DAT_c31e3210` — CONFIRMED

Created once at USB init (tk_cre_flg):
```
blk_c01.c:134177  _DAT_c31e3210 = FUN_c00169ec(auStack_2c);   // flag id (0xC31E3210 holds id)
```
Shared across all endpoints/contexts 1-6. The ISR sets per-endpoint bits into it; waiters
block on it.

## 3. The native completion WAIT (how firmware itself detects completion) — CONFIRMED

Blocking wait used by the echo (`FUN_c01e4e80(5,60000)`):
```
FUN_c01e4e80(ctx, timeout)          135922  -> loops FUN_c01e4b30 while ret==-5
  FUN_c01e4b30(ctx,0,timeout)       (poll+wait wrapper)
    FUN_c01e71e0(ctx|0x10000000|..)  -> the real flag wait
```
`FUN_c01e71e0` builds the endpoint mask and calls **tk_wai_flg on the SAME object**:
```
uVar4 = (1<<(ep+0x11)) | 0x90000000 | (1<<(ep+5));   // matches ISR's 0x40 & 0xc0 bits
FUN_c0016c08(_DAT_c31e3210, uVar4, 0x21, &local_44, timeout);   // tk_wai_flg
```
So the waiter blocks on exactly the bits the ISR sets. **Completion = IRQ → set_flg →
task wakes.** No polling in the native path.

## 4. StartTransfer registers NO completion callback — CONFIRMED

`FUN_c01e6b80` (137519, StartTransfer, EP05 OUT param=10, EP84 IN param=9):
- Loads DEPCMD parameter block from the context's TRB pointer.
- Sets the software **active** flag `*(ep*4 - 0x3ce1c6f0) = 1` (137556).
- `DataMemoryBarrier(0x1f)` then `FUN_c01e6a48(param,6,&local_30)` = issue **DEPCMD 6
  (StartXfer)** (137577).
- **No semaphore, no callback pointer is stored.** Completion is detected only via the
  shared event flag set by the ISR (section 1-3). The active flag is cleared by the ISR
  on XferComplete.

## 5. What "mode 1/2/3" means for completion — CONFIRMED

`FUN_c01e4d88(ctx)` returns the context's **transfer mode** byte:
```
FUN_c01e4d88:  return *(ctx*0x10 - 0x3ce1c778);   // mode table base 0xC31E3888, stride 0x10
```
ctx4 mode field = `0xC31E3888 + 4*0x10 = 0xC31E38C8` (matches known anchor). This is a
**USB-transfer mode**, NOT a sensor readout/gain mode.
- **mode 1** = normal Bulk (EP05 OUT ctx5). Completion → event flag. Re-arm at 138166:
  `iVar1==1` → rebuild TRB + `FUN_c01e6b80` (no callback).
- **mode 2** = the shell EP84 IN variant (ctx4 restored to 2 after registration). Same
  event-flag completion path as mode 1.
- **mode 3** = native UVC/isoc ring. Uses streaming flags `_DAT_c31e3964` (bits 1/2/4) and
  the `0xC30257B0` callback for auto-refill.

## 6. The `0xC30257B0` callback — mode-3 ONLY, IRQ context — CONFIRMED

Two dispatchers read+call the pointer:
```
FUN_c01e61a0  137137:  if cb==0 -> resend ZLP(FUN_c01e5998); elif !(3964&4) -> EndTransfer,-1;
                        else -> (*_DAT_c30257b0)()
FUN_c01e6208  137162:  cb==0 -> ZLP; else kick (*cb)() + up to 100x retry w/ FUN_c01f89c4(1) sleep
```
Callers, all gated on mode 3 / streaming flag:
- `FUN_c01e61a0` called from the **ISR** `FUN_c01e3660` at 134632, under event type 0x80,
  only when `_DAT_c31e3964 & 4`. → callback fires in **interrupt context**.
- `FUN_c01e6208` from `FUN_c01e4168` (137158, gated `_DAT_c31e3964 & 2`) and from 138169
  (`FUN_c01e4d88(ep)==3` && IN).

Therefore `0xC30257B0` fires for **EP84 IN in mode 3 only**. It does **NOT** fire for
EP05 OUT (mode 1) or for the shell's EP84 IN (mode 2). The v29 "proven one-time callback"
was a mode-3 experiment, not the stable mode-2 shell.

## 7. XC_UsbCtrlCore is a different object — CONFIRMED

`XC_UsbCtrlCore__v1 @0xC002CF80` and helpers wait via `FUN_c001a048(id, 0x100000, ...)`
(blk_c00.c:36933/36951, args `0xe`/`0x17`) — a **message/event queue** for high-level USB
session events (connect/disconnect/setup), NOT the per-TRB completion flag. Per-TRB
completion lives entirely in `_DAT_c31e3210` consumed by `FUN_c01e4e80`. The 0x100000
mask is unrelated to bulk completion.

---

## Feasibility verdict

**Event-driven completion is available and firmware-confirmed for both EP05 OUT and EP84 IN**
(modes 1 and 2): the DWC3 IRQ (0x34) → `FUN_c01e3660` → `tk_set_flg(_DAT_c31e3210, ep-bits)`
runs autonomously on hardware completion. A self-sustaining worker is feasible.

Caveat: for mode 1/2 there is **no per-endpoint software callback pointer to hook** — the
only exposed primitive is the shared **event flag**. To consume it event-drivenly you must
run a **task that blocks on the flag** via `FUN_c01e4e80(ctx, timeout)` (internally
tk_wai_flg). That is a true sleeping wait woken by the IRQ, not a spin poll.

A hookable IRQ **callback pointer** (`0xC30257B0`) exists only for **mode 3**; using it
would run your handler at interrupt level and switch EP84 to UVC auto-refill semantics.

### Recommended architecture: HYBRID (event-driven blocking task + bounded validate/re-arm)

Own a dedicated low-priority worker TASK that:
1. Arms EP05 OUT (`FUN_c01e6b80(10)`), then **blocks** on `FUN_c01e4e80(5, timeout)`
   (sleeps until IRQ posts the ctx5 completion bit).
2. On wake: validate frame (magic/version/len/CRC/seq).
3. Arm EP84 IN reply (`FUN_c01e6b80(9)`), block on `FUN_c01e4e80(4, timeout)`.
4. Loop. A watchdog/finite deadline on every wait; on timeout/CLOSE run bounded cleanup.

This is genuinely event-driven (the task sleeps; the IRQ wakes it) yet keeps
validation/dispatch/re-arm in task context where blocking is safe. It avoids: the mode-3
callback's IRQ constraints, the HWO spin-poll the staged handler was forced into, and the
cache-invalidate calls known to hard-lock.

Pure IRQ-callback (hook `0xC30257B0`) is viable only if EP84 is switched to mode 3; not
recommended for a shell because it changes transfer semantics and forces interrupt-level code.
Pure polling is unnecessary — the event flag exists.

### Exact anchors to use
- Completion event flag id: `[0xC31E3210]` (`_DAT_c31e3210`).
- Blocking completion wait: `FUN_c01e4e80(ctx, timeout_ms)` @ `0xC01E4E80`
  (Thumb call `0xC01E4E81`); returns 0 = completed, -5 = timeout, -4 = disconnect.
- StartTransfer: `0xC01E6B80` (Thumb `0xC01E6B81`); EP05 OUT param 10, EP84 IN param 9.
- EndTransfer: `0xC01E6D48` (`0xC01E6D49`).
- Mode getter: `FUN_c01e4d88(ctx)` @ `0xC01E4D88`; ctx-mode table base `0xC31E3888`
  stride 0x10; ctx4 mode `0xC31E38C8`.
- Mode-3 callback pointer (if ever needed): `0xC30257B0` — IRQ context.
- DWC3 regs: GEVNTCOUNT `0x2100C40C`; DALEPENA `0x2100C720` (shadow `_DAT_c31e398c`).
- USB completion IRQ number: `0x34`.

---

## Still needs a LIVE single-round probe to settle

1. **Does `FUN_c01e4e80(5|4, timeout)` return 0 (not -5) for our injected shell contexts?**
   v29 proved the TRB is consumed (control 0x813→0x812, len→0) and 4 host rounds succeed,
   which implies the ISR posted the flag — but the working echo used HWO snapshots, never
   captured the WAIT's return value in the mode-1/2 shell config. Probe: after StartTransfer,
   call `FUN_c01e4e80(ctx, short_timeout)` once and record return value + elapsed ms into a
   cave. Confirms the flag is actually delivered for our late-added contexts (not just the
   native PTP endpoints).

2. **Can a newly-created worker task safely share `_DAT_c31e3210` with the native stack?**
   The flag is shared across contexts 1-6 (PTP included). A second waiter could consume bits
   the native code expects. Probe: run the blocking-wait worker while PTP is idle, then while
   PTP is active; watch for PTP stalls and for cross-consumed flag bits.

3. **(Only if going mode 3) IRQ-context latency/safety of a `0xC30257B0` hook** — measure
   handler duration and whether re-arm from IRQ starves other USB events. Not needed for the
   recommended mode-1/2 task design.

## 2026-08-19 — Verdict: keep the blocking-worker receive (hooking EP05-OUT completion NOT worth it)

Verified against blk_c01.c. The current shell RECEIVE is already event-driven, not a poll:
FUN_c01e4e80(5,to) -> FUN_c01e71e0 -> FUN_c0016c08([0xC31E3210], mask,0x21,..,to) = a real tk_wai_flg SLEEP,
woken by the DWC3 event-ring ISR FUN_c01e3660 @0xC01E3661 (IRQ 0x34). Zero CPU while idle.
- EP05-OUT XferComplete arm is INLINE in the ISR (blk_c01.c:134611-134626): sets completion bit
  uVar5=1<<(ep+0x11), then iset_flg FUN_c0016b9c([0xC31E3210],uVar5) @134685 + isig_sem FUN_c01f8cdc([0xC31E3A88],1)
  @134691. There is NO per-endpoint completion-callback pointer for bulk mode 1/2 (unlike the frame path's
  FUN_c01d6690 vector @[0xC31E1BAC]). The only fn-ptr is _DAT_c30257b0 (dispatch FUN_c01e61a0 @0xC01E61A0) which
  fires ONLY for mode-3 UVC/isoc IN under _DAT_c31e3964&4 — not EP05-OUT.
- Context is HARD-IRQ. A receive hook cannot arm the EP84 reply there (StartTransfer FUN_c01e6b80 @0xC01E6B81 is
  a blocking-capable DEPCMD, not IRQ-safe). Only a latch-and-wake split is legal, and the native tk_set_flg
  already wakes our worker — so a hook buys ~µs and adds shared-DWC3-ISR risk (could stall PTP too). NET NEGATIVE.
VERDICT: the blocking worker IS the event-driven optimum for a low-rate request-response control channel. Only
revisit if sub-ms latency or catching commands while the worker is busy is ever needed; then latch-and-wake only
(patch bl into the ISR ctx5 arm, snapshot [0xC3757A7C], set cmd_ready, no reply in IRQ; never FUN_c000ea54, no
cache ops). Anchors: ISR FUN_c01e3660@0xC01E3661 IRQ0x34; flag [0xC31E3210]; driver sem [0xC31E3A88] (wait
FUN_c01f8e8c@0xC01E9380 / signal FUN_c01e93d8@0xC01E93D8); GEVNTCOUNT [0x2100C40C]; DMA buf [0xC3757A7C].
