# fp 5.02 native-L focus control audit

Offline source/binary audit, 2026-09-16. This note does not authorize deployment,
RAM execution, or lens movement. Motion and abort require a separately authorized,
reviewed protocol. The later project validation recorded a 20-pulse move, native
abort acceptance, completion flags and exact RAM restoration; see
[project evidence](../VALIDATION_2026-09-16.md).
That narrow trial is not proof of optical motion interruption, all-lens support,
or unconditional emergency stop. This audit itself was performed offline.

Source references below are repository-relative and give one-based line numbers in
the current decompilation. `C03` means `out/decomp/full/blk_c03.c`, `C04` means
`out/decomp/full/blk_c04.c`, and likewise for other blocks. Register/virtual-table
details were cross-checked against `out/seg0_c0000000.bin` (base `0xC0000000`).
Decompiler `void` signatures are not reliable evidence that R0 is unavailable.

## Critical system-status base correction

`C00178D8()` returns singleton **B = 0xC3033834** (C00:21475–21488).
`C0017AC8(r0=B)` returns **S = B + 0x18 = 0xC303384C** (C00:21558–21564).
The latter is also explicit in ARM instructions at `C0017AC8–C0017AD4`.

The stock PTP focus caller `C04F5AE8` tests **S+0x220 == 0** and **S+0x7C == 0**
before calling `C04EF7D0` (C04:181133–181145). Therefore:

| Field | Correct absolute address | Width | Interpretation supported by source |
| --- | --- | --- | --- |
| S+0x220 | `0xC3033A6C` | u32 | Inactive shutter-sequence gate when zero; not the movie-recording flag |
| S+0x7C | `0xC30338C8` | byte | StillExposing |
| S+0x7D | `0xC30338C9` | byte | StillSaving |
| S+0x7E | `0xC30338CA` | byte | MovieSaving |
| S+0x7F | `0xC30338CB` | byte | StillImageProcessing |
| S+0x84 | `0xC30338D0` | byte | MovieRecording |

**`0xC3033A54` is not S+0x220.** Any prior collector/documentation treating it as
that gate has a base-offset error; a value previously observed there does not
establish the shutter/capture state.

The capture names are firmware-derived, not inferred from an old research label:

- `GimbalStateNotifier::v1` calls `C04873D8` and passes its result to
  `StillImageProcessing`/`C04EF710` (C04:101453–101503).
- `C04873D8(S)` maps nonzero S+0x84 to enum 2, +0x7E to 3, +0x7C to 4,
  +0x7F to 5, +0x7D to 6; all five zero yields enum 1.
- `C04EF710` names these enum values `MovieRecording`, `MovieSaving`,
  `StillExposing`, `StillImageProcessing`, `StillSaving`; enum 1 is `Idle`
  (C04:177298–177331; the `Idle` literal at `0xC0CF4794` was checked in the binary).
- Observer registration is `C0487468` (C04:101506–101519). The generic observer
  dispatcher `C00180A0` passes B+0x18 as the status argument
  (C00:21941–21957). A separate direct query uses
  `C00178D8 -> C0017AC8 -> C04873D8` (C04:101615–101619), confirming the base.
- S+0x220 is set to 1 after successful `C0370D08`, to 0 after cancellation
  `C0370D40`, and to 2 after full-press paths including `C0370D70`
  (C04:95363–95466). The diagnostic path `C03DCD50` calls those operations with
  `S1WaitErr`, `CancelWaitErr`, and `S2WaitErr` labels (C03:155141–155158).
  The precise complete enum/state machine was not exhaustively audited.

A conservative non-capture precondition is **all five capture bytes zero and
S+0x220 zero**, freshly checked on the camera immediately before motion. A host
snapshot cannot make this atomic with future recording/shutter activity.

## Lens movie-speed flag is a different field

`0xC347E08F` is the lens synchronization singleton `0xC347DF38` +0x157.
`ChangeMovieRecording`/`C035C9A0` writes it and sends a lens protocol setting
(C03:60742–60769). Native focus drive `C033EC80` uses it to select one of two
default-speed getters when the requested speed is zero (C03:41352–41383).
Call sites set it to 0 in `C039D9A0` and `C039E280`, and to 1 in `C039DDE8`
(C03:108357,108522,108721). Their enclosing state transition is `C039BFA8`
(C03:107194–107267).

This audit did **not** prove that the lens flag alone exactly tracks active file
recording throughout all movie/live-view transitions. Do not use it as the sole
non-recording guard or call its setter. The independent system-status capture
flags above have direct firmware capture-state labels.

## Native-L identity and read-only state

Require supported firmware/strict device identity before interpreting addresses.
The native-L selector is `*(u32*)0xC3476408 == 1`: `C033D8E8` returns that selector
address and `C033D868` dispatches 0 to no lens, 1 to native-L, 2 to MC
(C03:40467–40508). Unsupported selectors must not be passed through a getter that
could assert/loop.

The native-L focus singleton is **F = 0xC3476414** (`C033DB20`,
C03:40666–40679). Its first word must equal **0xC0B8EEEC**, installed by the
constructor (C03:40597–40599). Binary vtable entries relative to that pointer:

| Offset | Function | Role |
| --- | --- | --- |
| +0x14 | `C033DBC8` | Return pointer F+4 to cached position |
| +0x18 | `C033EC80` | Absolute native drive |
| +0x20 | `C033F638` | Queue abort request |
| +0x2C | `C033F7D0` | Busy test |
| +0x30 | `C033F810` | Wait for completion, not stop |
| +0x3C | `C033DC10` | Set cached position |

Controller vtable `0xC0B8DA14` contains +0xB4 `C0332308`, +0xB8 `C03324D8`,
+0xC4 `C03325C0`, +0xCC `C0332628`, +0xD0 `C0332658`, and +0x28 `C03318C8`.

| Entry | Verified register ABI / meaning |
| --- | --- |
| `C035FD48()` | R0 = signed cached focus position; wrapper dereferences the native F+4 pointer |
| `C02DFFB0()` | R0 = signed native minimum, including native allowance |
| `C02DFFD0()` | R0 = signed native maximum, including native allowance |
| `C035FF18()` | R0 = done, inverse of native busy |
| `C035FF28()` | R0 = busy, XOR of done with 1 |
| `C036D888(r0=event_wrapper*, r1=out[3])` | R0 = 1 success / 0 failure; on success writes 3 u32 words, with flag pattern in out[2] |

Getter sources: C03:63425–63432,63946–63954,33496–33507,40701–40708;
C02:142765–142791; C03:63665–63684,64218–64226,33674–33685,74895–74911.

`C036D888` does not overwrite the caller's output on failure. Initialize all
three words, record R0, and accept **only R0==1**. Its wrapper argument is not the
flag pattern itself: the wrapper holds an RTOS object ID.

- Focus event wrapper **F+0x44 = 0xC3476458**; done means **out[2] exactly 3**.
- Lens synchronization ready wrapper **0xC347E02C**; readiness needed by the
  native call is **(out[2] & 1) != 0**, with successful reference call.
- Abort-pending byte **F+0x28 = 0xC347643C**; zero means no native abort pending
  (`C033F7C0`, adjacent to C03:41767).

The native busy getter ignores the event-reference return and compares an
uninitialized local if that call fails (C03:41767–41779). Prefer an explicit
validated `C036D888` snapshot over the done/busy convenience getter.

Cached position is not continuous motor telemetry. The drive-end message updates
it via `C033DC10` (C03:40725–40733,42186).

## Direct restricted move: ABI and limitations

The direct three-register API is:

```text
C035FFC0(r0 = signed absolute target, r1 = direction mode, r2 = speed request)
```

For the limited route considered here use **r1=0, r2=0**. The native PTP helper
`C04EEBF8` uses exactly this combination (C04:177037–177048; ARM checked because
the decompiler omits the third zero argument). Mode 0 selects automatic direction
and does not request the mode-1/2 backlash correction in `driveImpl`.

Call chain: `C035FFC0 -> C0360430 -> C03324D8 -> C033EC80 -> C033F050/driveImpl`.
Sources: C03:63769–63778,64130–64136,33600–33610,41352–41383,41507–41688.
R0 from native drive is preserved through the wrappers: 1 for its queued-drive
path, 0 for no-op/disconnected paths. A queue failure invokes an assertion before
the source can still reach return 1 if assertion returns; **R0==1 is not physical
completion or an unconditional delivery guarantee**.

The API does not enforce the proposed ±100 pulse policy. A future camera-side
wrapper needs all of the following before invoking it:

1. Strict identity/native-L/vtable validation; lens initialized and connected;
   verified capture-idle checks above; no other AF/PTP/manual interaction.
2. Successful focus event snapshot with pattern exactly 3; abort pending zero;
   successful ready snapshot with bit 1 set.
3. Fresh cached position equal to the host's expected position. Signed target
   must be within fresh native minimum/maximum. Check arithmetic overflow and
   require a nonzero delta with `abs(target-current) <= 100`.
4. A single-use request nonce, consume-before-call semantics, fixed operation
   dispatch (no arbitrary function/address input), and result/nonce validation.

Read-only identity/state checks are safeguards, not an atomic ownership lock.
No global ownership protocol excluding concurrent firmware AF/recording actions
has been proven. Host exclusive transport does not itself grant lens ownership.

This is asynchronous with respect to **focus completion**, but not guaranteed
instant or entirely time-bounded:

- `C035B780` waits ready bit 1 with literal timeout **5000**, then asserts on
  any nonzero result (C03:59979–59992). Both move and abort call this.
- Move's `PreCommunicationSequence` waits on communication semaphore
  `0xC347D098` with literal **3000** (`C036DBA0`). Failure invokes the lens fault
  path `C03508B8(...,1)`, not a clean ordinary rejection
  (C03:55986–56038,41663–41672,75073–75081).
- These numbers are **firmware timeout units**. Millisecond units and a complete
  worst-case call duration have not been established. Logging, assertions,
  callbacks and deeper fault handling are not proven bounded by these literals.

## Completion and abort

Normal event sequence, subject to completion occurring between host polls:

```text
3 done -> 1 command queued -> 0 task begins -> 2 command sent -> 3 drive-end
```

Drive clears bit 2 before queueing (C03:41663). Task message 0 clears bit 1,
sends focus command, sets bit 2 (42143–42154). Message 3 updates cached position,
clears abort pending, runs the native completion callback, then sets bit 1
(42186–42201). A host need not observe every intermediate pattern, but should
validate final pattern 3 and the final cached position. Pattern 3 follows the
normal callback return, not merely command acceptance.

`C035FEE8()` takes no arguments and preserves native R0 through
`C0360540 -> C03325C0 -> C033F638`
(C03:63632–63639,64186–64192,33646–33656,41692–41732).

- Returns 0 if already done or already aborting.
- Otherwise performs the same ready wait (5000 firmware units), queues a
  20-byte message of type 1, sets abort pending, returns 1.
- Task message 1 clears backlash and sends native focus mode 3 with existing
  target/speed. It does **not** set the done event (C03:42156–42165).
- Only a later validated done snapshot and drive-end cached position establish
  completion of the abort path. Return 1 means requested, not stopped.

A future abort dispatcher should reject calls for unknown/non-native identity,
use initialized successful event snapshots, avoid duplicate abort when pending,
and require ready bit 1. Even this does not eliminate the readiness race between
the snapshot and the native wait. One bounded host attempt plus bounded polling
can limit host retry activity, **not prove physical stop**. If status/transport
is lost, report an unknown outcome and do not submit another move.

**`C035FF08()` is not abort.** It reaches `C033F810` and waits mask 3 with literal
15000; timeout enters assertion/fault handling. It can also return success on a
disconnected-lens branch (C03:41809 and surrounding function). Do not substitute
it for a stop operation or use it as proof of an emergency stop.

## Why bypass the PTP worker for the proposed direct route

`C04EF7D0` checks the PTP worker's ready state, sets W+8 callback, and submits a
move, but does not itself start the worker. `C04EF1F8` subsequently calls
`C036E1B8(W+4,W)` after acceptance (C04:177141–177145; ARM verified at
`C04EF278–C04EF284`). W is the object pointed to by `0xC3774A44`.

`PtpFocusWait::v1` waits for focus, sends `C04E50E8` notification, calls W+8 if
non-null, then clears W+8 (C04:177052–177067). Notification `C04E50E8` contains a
semaphore wait with **0xFFFFFFFF** (C04:171691), so this worker's lifetime is not
bounded by the focus wait. The pool worker clears its active entry and sets ready
bit 1 only after the entry returns (C03:76107–76134). Do not forcibly reset ready,
clear busy, kill/free the worker, or claim abort makes it immediately reusable.

PTP observer busy byte `0xC3774A90` is set by `C04EEBF8`, whose observer registration
is at `0xC3774A8C` (C04:177037–177048); observer callback `C04EEAA0` clears it and
returns 0 (C04:176957–176965). Generic native completion notification removes
observers returning 0 (C03:8184–8197).

`C04EE890(kind,param)` calls `C04EE980(0xD,request,0,5000)`
(C04:176870–176885). Kinds 2 and 3 are the new-move and completion handshake paths.
`C04EE980` accepts any event-wait result other than 1, including 2
(C04:176926–176954). Event wait maps native 0 to 0, native -0x32 to 2, others to 1
(C03:74875–74891). The precise native -0x32 meaning and timeout unit were not
established here; the literal alone does not prove successful handshake.

Direct `C035FFC0(target,0,0)` does not itself create a PTP waiter, callback, or PTP
observer obligation. It still relies on the native task and its normal generic
completion callback. This avoids adding PTP lifetime dependencies but does not
make an existing PTP/AF operation safe to overlap.

## Instruction-cache publication

Native `mem set` **does not publish instruction code**. `C03FA010` performs a
plain store, output, and data readback comparison (C03:171056–171084;
`out/decomp/memmod.c:120–150`). Its dispatcher has no cache-maintenance tail
(C03:171163–171192). A successful readback proves data visibility, not instruction
cache freshness.

Binary-verified ROM helpers:

- **`C000E91C()`**: no argument; data-cache clean/invalidate by set/way,
  `MCR p15,0,r7,c7,c14,2` at `C000E970`, DSB at `C000E998`, ISB at `C000E99C`.
  It temporarily masks interrupts and restores the original mask before return.
  This routine is **not** whole-I-cache invalidation.
- **`C000EABC()`**: no argument; `MCR p15,0,r0,c7,c5,0` at `C000EAC0`, then
  DSB/ISB and return. This is whole instruction-cache invalidation.

The existing loader calls data maintenance then instruction maintenance before
branching to uploaded entry (`fpSup/fp_usb_shell/asm/stage2.S:72–88`,
definitions at lines 7–8). A separately authorized bridge installation must
publish both caches **before its first RAM instruction executes**. A RAM bootstrap
that performs its own first publication does not solve the first-execution
problem. Calling the verified ROM helpers in that order before arming the RAM
callback is consistent with the existing loader; this audit did not execute or
validate that installation procedure on a camera.

## Outstanding gates before any motion support

- Keep current move/abort operations hard-disabled; source review is not live
  authorization or hardware validation.
- Correct the system-status base in downstream collector names, schemas and
  documentation; preserve old raw evidence and explain reinterpretation rather
  than silently altering recorded data.
- Implement and review camera-side idle/identity/range/expected-position checks,
  request single-use behavior and initialized event result handling.
- Demonstrate exclusive safe operating conditions and decide how to handle
  capture/AF state races. There is no proven atomic global lens-ownership lock.
- Validate instruction publication before any new RAM execution.
- Establish timeout units and failure-path behavior if a real-time duration
  guarantee is required. Existing source supports finite literal waits on some
  paths, not a proven total execution/physical-stop bound.
- Define disconnected/ambiguous-response behavior as unknown outcome, no retry
  movement, no repeated abort loop, no forced flag resets, and no automatic power
  or recording/settings intervention.
