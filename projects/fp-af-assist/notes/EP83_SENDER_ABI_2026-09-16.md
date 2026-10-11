# EP83 task-context sender ABI / ownership contract (fp 5.02)

Date: 2026-09-16  
Original scope: **offline source/ROM audit only**. No camera or USB operation was run for that audit. This note is
limited to the fixed-address binding needed by `highrate/af_sender.c`; it is not a deployment
procedure and does not establish a usable EP83 bulk path.

Later authorized read-only follow-up on the same date: `../highrate/runtime-read-20260916-a.jsonl`
confirms fp w71c1 / 5.02.0.V91 / full expected build hash, live ctx3 `{2,1,3,0}`, and pool pointer
`0x44F6FE00`. Only native `version` and the two approved memory reads were sent, without retries or
camera writes. This confirms the runtime tuple, not actual controller registers, idle state,
exclusive ownership, DMA mapping, or successful EP83 delivery.

## Result first: the fixed-address adapter is still blocked

Two source facts prevent a truthful `firmware_adapter_complete=true` today:

1. **The correct IN wait is `0xC01E56F1`, not the `0xC01E4E81` used by
   `pushprobe.S` (then in `templates/`, now `fpSup/fp_usb_shell/asm/`).**  `C01E4E80` calls the common wait with direction 0;
   `C01E56F0` calls it with direction 1.  The native mode-2 IN sender uses
   `StartTransfer(7)` followed by `C01E56F0(ctx=3, timeout)`
   (`blk_c01.c:136367-136388,136482-136529`).
2. **The current EP83 patch changes USB descriptors, not the controller-side context mode.**
   ROM default ctx3 is `{mode=2, direction=1, endpoint=3}` (words at `C07E2800`), and reset
   restores that tuple (`blk_c01.c:137440-137445`).  `C01E62A8` emits the mode-1 config word
   ending in `...04`, but modes 2/3 use `...06` (`137243-137281`).  The six current EP83
   patches modify descriptor/companion bytes only (`fpSup/fp_usb_shell/patches.py:26-32`).
   Thus the host advertises bulk while the source-confirmed controller path remains the native
   mode-2/interrupt path.  The 100/100 probe proves only that Start accepted its DEPCMD; it
   does not prove one large bulk TRB can move bytes.

There is also an existing native ctx3 producer.  PTP event delivery follows
`C04DF5B0 -> C04E9048 -> C01E91D0 -> C01E5880`; `C01E5880` selects mode-2 IN ctx3, rewrites
the same TRB, calls Start(7), then WaitIn(3) (`blk_c04.c:167876-167904,174225-174240`;
`blk_c01.c:136482-136540,139876-139912`).  Changing ctx3 to mode 1 without first rerouting or
excluding that producer is not valid: `C01E5880` finds its endpoint by searching for the
mode-2 IN context.

`C31E3AC4` is **not a reusable lock**.  `C01E91D0` performs an ordinary load, a plain store of
1, the blocking send, then a plain store of 0.  There is no mutex, interrupt mask, compare-and-
swap, or participation by a direct Start caller; these are the only references in the full
decompilation (`blk_c01.c:139886-139907`).  Merely observing zero, or writing one from the new
sender, cannot close the race.  A binding therefore remains disallowed until one owner also
serializes/suppresses native PTP event transmission and owns the controller-mode transition.

## Exact callable ABI

All three USB calls below are Thumb entries.  Call them only from a schedulable task, with
AAPCS 8-byte stack alignment and normal preservation of `r4-r11`/`lr`; the wait blocks on an
RTOS event flag and is not hook/IRQ-safe.

| Operation | Entry and arguments | Return contract from source |
|---|---|---|
| Start | `int32_t C01E6B81(uint32_t physical_ep)`; EP83 uses `r0=7` | `0` means the Start DEPCMD did not report an error; it is **not** delivery. Nonzero means do not call Wait. For current mode-2 ctx3, the mode-1-only `-2` gate does not apply. |
| Wait IN | `int32_t C01E56F1(uint32_t logical_ep, uint32_t timeout)`; `r0=3`, `r1=finite timeout` | `0` is a completion-path result, subject to the postconditions below. Seen error classes are `-1`, `-4`, `-5`; none authorizes retry or buffer reuse. |
| End | `void C01E6D49(uint32_t logical_ep)`; `r0=3` | No meaningful return. It discards the lower DEPCMD result/status and therefore cannot prove DMA stopped. |

The project policy `wait_ms=1..2000` is a reasonable finite Wait parameter, but it is **not an
end-to-end two-second bound**.  Both Start and End reach `C01E6A48`, whose DEPCMD poll has its
own hard-coded `60000` timeout (`blk_c01.c:137473-137515`).  Scheduling latency and recovery
also sit outside the caller's Wait value.

The ctx3 TRB pointer cell is `C31E3270`.  Dereference the cell; do not replace it with a guessed
storage address.  For a single normal TRB write exactly:

```
word0 = independently verified DMA/bus address
word1 = 0
word2 = requested_len                 // 1..0x00ffffff
word3 = 0x00000813                    // HWO | LST | IOC, normal, not chained
```

Then order the TRB writes before Start.  A barrier is not payload cache publication.

## Source-backed success test

`C01E3660` decodes physical 7 as logical 3 / IN.  A real XferComplete clears ctx3 active
`[C31E391C]` from 1 to 0 and posts completion bit `0x00100000` to the event-flag object whose
ID is stored at `C31E3210` (`blk_c01.c:134603-134626`).  Wait observes that bit and dispatches
`C01E7780` (`137923-137979`).

Wait returning zero is not sufficient by itself.  `C01E6D48` can synthetically post the same
bit to an existing waiter after setting active to 2 (`137667-137697`), and mode-2 completion
decoding still returns zero.  With exclusive ownership, accept success only when all of these
hold after `C01E56F1` returns:

1. Wait return is `0`.
2. `[C31E391C] == 0` (real IRQ completion, not End's state 2 and not a new active transfer).
3. The owned TRB still describes this request, and `(trb.word3 & 1) == 0` (HWO cleared).
4. `residue = trb.word2 & 0x00ffffff` is no greater than the saved requested length.
5. `residue == 0` for this exact send (therefore actual length equals the saved requested length).

The firmware's cached count at `[C31E3A70]` is **not** an arbitrary-batch actual length.
`C01E7780` computes `MPS - residue` when `(word3 & 5)==0`, otherwise it stores MPS
(`blk_c01.c:138193-138212`).  That is valid for the native mode-2 sender because it arms at
most one MPS per TRB; it cannot validate the proposed 1,024-to-32,896-byte single TRB.  The
adapter must retain `requested_len` and inspect its own TRB as above.  Host-reported actual
length plus AFB1 length/nonce/CRC remains the independent end-to-end check.

On this confirmed success path, active=0 plus the completion event and cleared HWO establish
that this single TRB is no longer hardware-owned; do **not** issue a routine End after success.
The resource-index slot may still be below `0x80` after normal completion, and the native paths
re-arm without End.

## Failure and buffer-lifetime matrix

| Observation | What source proves | Required owner action |
|---|---|---|
| Preflight rejects before TRB/endpoint mutation | This attempt did not arm EP83 | DMA lease may be released by its owner. |
| Start returns nonzero | `C01E6B80` clears software active, but the DEPCMD was generally issued; lower errors can be command status, disconnect, or timeout. | Do not Wait, retry, overwrite, or free. Latch fault and retain/quarantine TRB plus DMA lease. |
| Start returns 0 | Only command acceptance/no reported error. `C01E6A48` can also leave with its initialized zero if the USB core-alive check fails while CMDACT is set. | Proceed once to WaitIn; never call this delivery. |
| Wait returns `-5` | Timeout; no End is performed, so active/TRB may remain owned. | Latch fault; retain. No retry. |
| Wait returns `-1` | Some inner event-error paths attempted End, but precheck/global-gate `-1` paths did not. Return value does not distinguish them. | Latch fault; retain. |
| Wait returns `-4` | Wrapper invokes global USB recovery, including endpoint End attempts. | Treat session/ownership as lost; retain until a separate lifecycle owner proves controller teardown/reinitialization. |
| Wait returns 0 but any success postcondition fails | Could be synthetic End wake, stale/shared event, partial transfer, or still-owned TRB. | Latch fault; retain. |
| `End(3)` returns | Function pre-sets resource index to `0x80`, ignores DEPCMD result, writes active=2, and manipulates the wait bit (`blk_c01.c:137633-137700`). | Never use return as a DMA-stop proof. A one-time recovery End may be chosen only by the sole lifecycle owner; quarantine remains afterward. |

The conservative behavior already used by `af_sender.c`—quarantine on every Start/Wait/
completion failure and never auto-End or retry—is therefore correct.  It is stricter than the
special mode-1 pre-command `-2` case, but ctx3 is presently mode 2, and the stricter rule avoids
depending on an unclosed ownership race.

## Preconditions the eventual binding must prove atomically enough

One task must hold a real higher-level lease covering the full operation, not a sampled boolean.
At minimum that lease covers:

- native PTP event sender admission (`C04DF5B0/C04E9048/C01E91D0/C01E5880`);
- ctx3 config tuple at `C31E38B8..C31E38C4` and any mode transition;
- TRB pointer cell `C31E3270` and its pointed 16 bytes;
- active state `C31E391C`, physical-7 resource slot `C31E3A4C`, and completion/not-ready
  event bits `0x00100000`/`0x00000100` in the shared event-flag object;
- `DALEPENA` physical bit 7 in both shadow `C31E398C` and hardware `2100C720`;
- the DMA staging lease and its CPU/bus mapping; and
- absence of concurrent Start, Wait, End, endpoint reconfiguration, suspend/reset, or a second
  batch until the preceding outcome is acknowledged.

Checking `C31E3AC4==0`, active==0, or an enabled DALEPENA bit individually is not exclusion.
The current sources expose no ctx3 mutex that a direct adapter can simply acquire.  Until the
PTP producer and mode transition are brought under one owner, `preflight()` must fail and no raw
MMIO/fixed-address adapter should be emitted.

## Cache and publication contract

The AFB1 image must live in an explicitly leased DMA buffer, not the cacheable C-region code
cave and not an assumed-free tail of the shell pool.  For a CPU-written cacheable mapping, use
the firmware's range clean `C000EB90(start, end_inclusive)` before arming.  The native IN paths
call it for C-region buffers (`blk_c01.c:136252-136263`); ROM disassembly confirms it performs
Clean Data Cache by MVA over the inclusive, cache-line-rounded interval, followed by DSB/ISB.
For a separately proven uncached/coherent mapping, follow that mapping's verified publication
rule instead.  In both cases, issue a final DSB after payload publication and TRB writes and
before Start.

The CPU-to-bus conversion is region-specific.  The eventual adapter must consume an independently
verified `dma_bus`; it must not infer one by copying the `+0xC0000000` arithmetic from a different
allocation class.  Keep payload, TRB, callback context, request/result, and sender code alive and
unchanged through success or through the entire quarantine/recovery lifetime.

## Consequence for the current offline sender core

`highrate/af_sender.c/.h` has the right conservative phase order and fault latch.  Its firmware
binding must specifically:

- bind `ops->wait` to **`C01E56F1`**;
- make `ops->completion` implement the five postconditions above, not merely return true after
  Wait 0 or read `[C31E3A70]`;
- preserve the statement that `wait_ms` is not the whole-operation deadline; and
- leave `firmware_adapter_complete=false` until controller-side bulk mode and native PTP-event
  exclusion have concrete ownership.

No source-backed change is required to the portable core's current rule of retaining DMA on all
post-Start uncertainty.

## Follow-up: bulk mode introduces an OUT re-arm side effect

The cold-boot isolation candidate (stub `C01E5880`, change default ctx3 mode) is **not yet a
complete adapter**. In `C01E7780`'s mode-1 completion branch, including an IN completion, if
`C31E3974 != 1 && C31E3A08 == 0`, the firmware selects the mode-1 OUT context through
`C01E60E0`, rewrites its TRB and calls Start OUT (`blk_c01.c:138238-138258`). Thus switching ctx3
to mode 1 and using WaitIn3 can also affect the existing EP01 command path. This is a concrete
remaining integration obligation, not something the pure receipt checker can exclude afterward.
The single worker must either establish the exact native OUT-owner state across that call or use
a separately audited completion wait that has no such re-arm path. Neither has been implemented.
Do not claim that two boot patches alone establish end-to-end exclusive ownership.
