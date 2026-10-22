---
name: fp-usb-shell
description: "Use the existing SIGMA fp Ver.5.02 USB shell: inspect host transport, build or review ARM probes, choose safe execution context, manage shared scratch/DMA buffers, and plan authorized deployment or recovery. Based on the project's existing USB-shell knowledge; not authorization to operate the camera, change cards, stop processes, or publish code."
---

# SIGMA fp USB shell — current Codex entrypoint

Imported 2026-09-16 from the existing local skill:
`/Users/dido/Developer.localized/SIGMAfp_re/fpSup/.claude/skills/fp-usb-shell/SKILL.md`.
The original is preserved byte-for-byte in [references/upstream-fp-usb-shell.md](references/upstream-fp-usb-shell.md).
Source SHA-256: `5a9b9e8b9cd1085fd18f6b4976f5a4bbceb54a5053deb1048621075cf9759d3e`.
The source file is not changed by this installation. **The corrections below supersede conflicting historical instructions.**

## Scope and maintained sources

Default root: `/Users/dido/Developer.localized/SIGMAfp_re`; respect an explicit alternate root.
Current code is `fpSup/fp_usb_shell/`, not `codex/usbshell/` or an old worktree.
Do not copy the host tools into this skill. Use their maintained implementation and verified version.

- For ARM probe design, pool threads, callbacks, or hot replacement, read the full upstream reference first,
  then the actual template/host script being used. Its relative paths refer to the repository, not this skill folder.
- Before relying on another shell note, read
  [USB_SHELL_INDEX.md](/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/notes/USB_SHELL_INDEX.md).
  The index is a chronology, not an infallible version oracle: check current source and git tags for version claims.
- For AF collection or native sweep interpretation, use the installed
  [sigma-fp-af-research skill](/Users/dido/.codex/skills/sigma-fp-af-research/SKILL.md)
  and its research tools. Do not improvise another AF handler here.

Documentation, installation, and offline diagnosis stay offline. Loading this skill grants no authority to
focus, start recording, inject code, modify an SD card, restart daemons, or commit/push. Check the user's scope
before mutations. Name exact addresses and obtain consent for ad-hoc RAM operations; an already-authorized,
reviewed tool must remain within its documented ranges and ownership checks. Do not inherit the archived
instruction to commit/push every build; publish only when requested. The historical companion `fp-camera`
is not automatically installed or made authoritative by this import.

## Execution context and ARM invariants

- Prefer an existing native command or a reviewed tool. There is no native firmware `call` command;
  `callfn.py` works by borrowing a command handler, not a privileged independent channel.
- A shell handler runs in the dispatcher task; a gyro callback is interrupt-like and must not block or take
  mutexes. Pool threads are a third, distinct resident-code route; use the reference's ABI and actual source.
- Keep the stack 8-byte aligned at calls, preserve LR when calling out, and preserve the borrowed site's
  call/return semantics. A function-pointer table entry and an instruction hook are not interchangeable.
- Write code/data, read it back, repair only verified holes with a bounded retry policy, and verify before
  arming. Native `mem set` and `putfile.put_slow` do **not** publish instruction caches. The verified loader
  sequence is no-arg ROM `C000E91C()` (D-cache maintenance), then `C000EABC()` (I-cache invalidation), before
  any new RAM instruction. Use a reviewed installer with this sequence; a fresh RAM helper that cleans its
  own cache cannot bootstrap its first execution. See the maintained native-focus control audit.
- Save the exact expected original hook, refuse unknown ownership, and restore in `finally` with readback.
  For the verified echo handler: slot `C0BAC2F8`, original `C03D99A0`. Do not overwrite an unknown borrower.
- A rotating multi-hop pointer chain must be captured inside one reviewed camera-side snapshot, not stitched
  from several host reads at different times. Snapshot integrity still does not establish semantic alignment.

## Shared memory is not free space

The archived claim that `C072FA00..C0730000` is free is obsolete. Current `putfile.py` uses:

| Region | Existing use |
|---|---|
| C072F700..C072F7FF | shared parameters/results; AF record and nonce also occupy this area |
| C072F800..C072F9FF | working template |
| C072FA00..C072FAFF | bulk loader |
| C072FB00..C072FBFF | copying raw reader |
| C072FC00..C072FFFF | direct-dump code slot; AF collector borrows the same slot |

These are mutually exclusive borrowed resources, not guaranteed idle or a permanent allocation for a new
probe. A zero-filled region alone does not prove ownership. Check active payloads, code size, hook ownership,
and the current build layout. During AF collection honor `/tmp/fp-af-fusion.lock`; tools that ignore this
lock can still collide, so do not interleave callfn/getfile/putfile/dumps with an AF lease.

Read the existing DMA-pool pointer from `C3757A7C` only in authorized operations. Current pool layout includes
`+0x2000` capture buffer, `+0x6000` gyro, and `+0x10000` template staging. Do not reuse a historical fixed pool
address or assume a formerly spare pool tail is still free. Bounds and reservations come from the running build.

Do not run live `memmgr bufmem get` or `memmgr bufchk` as harmless queries; both have caused endpoint freezes.
Boot-time allocation and the reviewed firmware heap-allocation/file-transfer path are different workflows;
do not turn this warning into a ban on all allocation.

**DSB is not D-cache cleaning.** Do not point USB DMA directly at a record in the cacheable C-region cave.
Follow `templates/dumpraw.S` or the current AF snapshot: CPU-copy to the existing DMA capture buffer, then
publish its length. `dumpdirect.S` documents its pool/allocator address assumptions. Changing an address to
a guessed uncached alias or flushing all cache on each sample is not a substitute for a verified buffer path.

## Host transport and recovery boundaries

- Current interface 0 uses EP01 OUT / EP82 IN; EP83 is the additional IN endpoint. Old EP05/EP84 examples
  must not be used as current addresses. Do not issue endpoint MMIO/StartTransfer while enumeration owns them.
- Reuse one verified daemon/socket; check existing processes before starting another. Native client
  `host/fpsh --status` asks the host daemon for STATUS without camera exchange. `host/fpsh ping` sends PING
  through the daemon to the camera, but does not identify firmware. `putfile.sh('ping')` is a different,
  native-shell request, not that host operation.
  The daemon unlinks its socket path at startup and has no singleton lock; socket existence alone is not
  sufficient evidence that starting another daemon is safe.
- A reply timeout is an uncertain outcome for non-idempotent commands. Do not blindly retry key presses,
  record toggles, or writes merely because no reply arrived; verify the resulting state within scope.
- The worker dispatches a shell handler synchronously and the daemon checks request sequence. A fresh
  successful same-worker command can prove that an earlier handler returned; it does not prove physical
  lens completion. If quiescence/ownership cannot be established, retain in-flight code/parameters and
  stop further operations. An upload that never armed echo is a different, narrower recovery case: restore
  only an exact saved before-image after checking every current word is original or from that upload.
- If stopping the daemon is authorized, its socket-level `QUIT` is the clean path (`OK bye`, release
  interface, close device/socket). **`fpsh quit` is not that path**: the client forwards it to firmware as SHL.
  Inspect the client/daemon implementation before issuing host control. Only fall back to a verified exact
  owned PID when needed; no blanket `pkill`, kill loops, or ptpcamerad watchdog as a default prerequisite.
- Interface ACCESS errors can be another daemon or a PTP claimant. Inspect descriptors/ownership; installing
  a skill does not authorize killing macOS import services or modifying the card's interface-class patch.
- Connected recording has been demonstrated with the current firmware-owned endpoints. Do not reinstate
  the old rule that any attached daemon or any command during recording always freezes the camera. This also
  does not prove arbitrary shell commands are safe during record-start; use the operation's tested workflow.
- After a wedge, preserve evidence, identify the interrupted operation and current ownership, then choose a
  scoped recovery. Do not automatically reload an unrelated payload or assume all RAM was reset by replugging.
- Authorized host-only diagnostics captured two 12-byte IN responses as PTP `SessionNotOpen` (0x2003),
  with transaction IDs matching FPSH sequences. Native PTP and the worker share endpoint/TRB state;
  neither the precise live race nor every historical timeout is established. A PTP error does not prove
  the shell was not executed: never retry uncertain move/abort/echo. One existing 20 ms drain window
  contained no further response; this is not permission to ignore PTP or infer exactly-once execution.
  See `research/interfaces/notes/FP_USB_PTP_SHARED_PATH_2026-09-16.md` and the prototype transport audit.
  Pacing passed bounded trials but is not a root-cause fix. Do not replace host/worker without scope;
  the diagnostic daemon only logs received bytes and preserves normal error handling.

## Reusable operations, not surprise deployment

`putfile.py` writes card files; `getfile.py` reads them but uses borrowed RAM/code; `memprobe.py` writes test
patterns. They are not interchangeable read-only utilities. `swapworker.py` and some deploy scripts act on
the camera with no arguments: inspect source/help handling offline, never run bare scripts to discover usage.
Do not create or deploy AutoRun/VSHL, switch worker implementations, or release/push a build merely because
the upstream reference shows that recipe. Follow the explicit task and current source constraints.

Do not generalize "no arguments prints usage" into a safety rule. The AF research verified that
`imager high_gain_off` without arguments changes state and `check_convert_abs_gain` with arguments changes
actual gain. S2/MOV events depend on camera mode and can toggle recording; screenshot keys write files.

This is a local adaptation, not proof that every historical experiment still works. Distinguish source facts,
measured results, and conjecture, preserve hashes/build identity, and update conclusions when new evidence
contradicts them. Keep camera-independent knowledge under `research/` and project-coupled incidents under
`projects/`, following the repository index.

Native focus/capture/cache facts: before new lens-control work read
[FP_NATIVE_FOCUS_CONTROL_2026-09-16.md](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/notes/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md).
The `projects/fp-af-assist/` prototype and its incident/recovery evidence are not a generic shell installer
or permission to enable motion. Its source contains guarded motion operations even when its host probe
API exposes getters only.
