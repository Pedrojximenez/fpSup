---
name: fp-camera-control
description: Drive a USB-connected SIGMA fp (Ver.5.02) entirely from the host — change any menu setting, inject any button press, switch GUI screens, take and retrieve screenshots, log which .xci icons the UI loads, read/write camera memory, and move bulk data over the shell’s two IN endpoints — the finished EP82 reply path (MEM1: 382 MB/s read / 398 MB/s write — skill fp-usb-transfer) and what a camera-side EP83 streaming sender still needs. Use this whenever work needs the camera's screen observed or its state changed, instead of asking the user to press buttons. Also covers getting the USB shell working on macOS (ptpcamerad steals the interface).
---

> **設定區風險（2026-10-04 更新）**：原廠在 loader 前讀取持久設定；
> 不支援的值可能使開機或選單失效，拔卡本身不會清除該值。使用者已指出現在有還原手段，
> 因此不再把這類故障描述成不可恢復。上機前確認會保存的值、可能症狀及適用的還原流程；
> 未確認還原條件時，優先把自訂狀態留在 RAM。240 fps 與 14-bit 的處理不同，
> 詳見 `research/SETTINGS_AREA_FIRST_RULE.md`。
> *(Stock firmware reads persistent settings before the loader. A recovery
> method now exists; check its applicability before a live trial.)*

# SIGMA fp — driving the camera from the host

The camera's debug shell exposes near-total control of the UI. **Before asking the
user to touch the camera, check whether one of these commands does it.** The user
having to press a button is a last resort, not the default.

Requires a card carrying the USB shell (`fpSup.BIN` + AutoRun). **Shipping OG3K
cards do not include the shell** — if `ver` times out with `moved=0/64`, that is
almost certainly the reason, not a fault.

## 0. Getting the shell up on macOS

Two host-side problems, both of which look like a dead camera:

**`LIBUSB_ERROR_ACCESS` on claim.** The fp enumerates as PTP (interface class 6)
and macOS's `ptpcamerad` grabs interface 0. It is SIP-protected:

- `launchctl bootout` → `Operation not permitted`
- `SIGTERM` / `killall` → ignored, process survives
- **`kill -9` works**, but launchd restarts it within seconds

First inspect `lsdesc`, existing daemon processes and interface ownership.
Only if the active interface is still PTP-class and a competing PTP claimant
is confirmed should a scoped host recovery be considered for that session.
Do not install a persistent process-killing watchdog as a default startup step.

**Multiple `fpshd` daemons fighting over the interface.** Inspect the exact
processes first. Use the daemon's socket-level `QUIT` for a clean shutdown when
authorized; `host/fpsh quit` is a firmware command, not that control request.
If needed, act on a verified owned PID, then start one daemon. Do not use a
blanket `pkill` as a normal recovery step.

`ioreg -r -c IOUSBHostDevice -n "SIGMA fp" -l -w 0 | grep '+-o '` lists who holds
the device. A re-plug changes the node id, which is how you confirm the user
actually replugged.

The daemon needs `libusb-1.0.dylib` on its rpath (`.../SIGMAfp_re/codex/lib/`);
the repo restructure broke this once.

## 1. Talking to the shell

```python
import sys; sys.path.insert(0, '<repo>/fpSup/fp_usb_shell')
from putfile import sh, mem_get, mem_set
sh('version')        # model = w71c1, rel version = 5.02.0.V91
sh('help')           # full command list
sh('<cmd>')          # inspect command semantics first; no-arg may mutate state
```

Some commands (notably `key QSON`) make the camera busy enough to time out the
USB transfer. The shell recovers — wrap calls in try/except and carry on rather
than treating a timeout as failure.

## 2. Changing settings — `menu Set*`

```
menu SetMovRecSize          → prints current value
menu SetMovRecSize 4        → sets it
```

No argument reads, an argument writes. Everything in the menu is here
(`SetRecMode`, `SetShutterSpeed`, `SetFnum`, `SetIsoSensitivity`, …); run `menu`
for the list. For OG3K, movie resolution enums are **3 = UHD, 2 = FHD, 4 = OG3K**.

Avoid `menu save` / `setting save` / `setting write` — those write FlashValue and
break the "pull the battery and everything is stock" guarantee.

## 3. Pressing buttons — `key`

```
key QSON / QSOFF / MENUON / OKON / UPON / DOWNON / LEFTON / RIGHTON
key S1ON / S2ON / CAPTUREON / MOVON / PLAYON / DISPON / FnON / AELON
key CINESWON / STILLON / MODEDIAL / CMDDIAL1 / CMDDIAL2 / CMDDIAL3
key check       # camera reports the key events it receives; any shell input exits
```

**`QSON` and `QSOFF` are two separate events and the app toggles on both** —
sending the pair opens QS and immediately closes it again. Send `QSON` alone.

**`S2ON` is not "take a photo" — it is the shutter button, and what the shutter
button does depends on the mode.** In CINE mode a complete S2 pulse **starts a
recording**, and the next one stops it. A host script that assumes S2 means
"still capture" will silently record clips instead. Check first, every time:

```python
sh('status get app_current')     # 2 = CINE on the camera this was found on
sh('status get is_recording')    # and check it again afterwards
```

`is_recording` read immediately after a pulse can still report the previous
state — poll it a second time about 3 s later before concluding anything, or a
"stop" pulse will start a new clip instead of confirming the old one ended.

**CINE / STILL is a physical switch and the key events do not override it.**
`key STILLON`, `key STILLON` + `STILLOFF`, and `key CINESWON` all leave
`app_current` unchanged (they do move `menu SetRecMode`, which is misleading —
the setting moves, the app does not). Nothing in the shell switches it. This is
one of the few things that genuinely needs the user's hand on the camera, so ask
for it rather than burning shots looking for a command.

The movie button is different.  `MOVON` is key-down and `MOVOFF` is key-up;
`MOVOFF` is **not** a dedicated stop-recording command.  One complete press
toggles recording, so remote start and stop each require their own pulse:

```python
sh('key MOVON', retries=0); time.sleep(0.12); sh('key MOVOFF', retries=0)  # start
time.sleep(duration)
sh('key MOVON', retries=0); time.sleep(0.12); sh('key MOVOFF', retries=0)  # stop
```

Check `status get is_recording` before the first pulse and after the second.
Never retry `MOVON` merely because its USB reply timed out: it may already have
toggled recording.  If a post-check explicitly reports `is_recording -> 1`, a
further complete pulse is the safe stop action.  Measure short high-bandwidth
tests from the first `MOVON`, not from the later USB reply.

## 4. Screenshots — the whole loop, no user needed

`CAPTUREON`/`CAPTUREOFF` is the screenshot key. The camera writes
`SS__nnnn.JPG` into `\DCIM\100SIGMA`:

```python
sh('key CAPTUREON'); sh('key CAPTUREOFF')          # ~2 s to land
r = sh(r'dir \DCIM\100SIGMA')                      # newest file is last
# getfile.py needs --size when the file is not in its cached dir listing
```
```sh
python3 getfile.py '\DCIM\100SIGMA\SS__0458.JPG' out.jpg --size 308467
```

Screenshots are 1024×682. **Caveat: pressing the capture key dismisses the QS
overlay**, so this cannot photograph QS — use the image-load log (§5) to see what
QS draws instead.

## 5. Seeing what the UI draws — `gui image log`

This is the single most useful diagnostic for UI work. It logs every `.xci` icon
the GUI loads, with its pixel dimensions:

```python
sh('gui image log 1')      # → "load image name log on (attr=00000004)"
sh('log act GUI')
sh('log clear')
# ... trigger the screen ...
r = sh('log out GUI')
```

Two interleaved lines per image: call site `0xc055fdf4` carries the filename,
`0xc055fe14` carries `w,h,0,0`. Pair them in order.

**The GUI channel is flooded** by `ERR` spam from `0xc055fa14` / `0xc055fa30`
(LV_VolumeCh1). Filter those lines out client-side or the real entries are buried
— this made the log look empty and cost a whole round of investigation.

Reading the result: each QS tile loads a **label plate plus a value icon**
(`menu_cine_fps.xci` + `qs_fps_3_S.xci`). A tile that loads only its plate is
drawing stale framebuffer content — that is what "garbled tile" actually means.
Icon filename indices track the display state, so a missing state shows up as a
missing `qs_<thing>_<n>_S.xci`.

Other channels: `log` lists 37 flags (`GUI`, `MENU`, `DRAW`, `UI`, `PLAY`, …),
`log act <FLAG>` / `log out <FLAG>` / `log clear`.

## 6. Other GUI introspection

```
gui geti/getf/gets <name>     read a UI variable
gui seti/setf/sets <name> <v> write one
gui scr set <name>            switch screen directly
gui lang <0-16>               ja en de fr es it zh_CN zh_TW ko ru nl pl pt da sv nn fi
gui gc                        Lua GC — the GUI layer is Lua
gui ver / gui mem
gui trace|req|area|time log <0/1>
```

Screen names live in the resource string pool: `1_01_CINE`, `1_02_CINE`,
`1_03_CINE`, `1_04_SLike`, `1_01_STILL`, …

**`gui seti` is overwritten almost immediately by whatever publishes that
variable** (e.g. `LV_Resolution` is republished by
`XC_GuiStandbyCineMenuNotifier_w71c1__v59` on every LV update). It cannot be used
to force a display state.

**`gui geti` can read a different instance than the one the screen uses.**
`LV_Resolution` has separate Cine and StillLike publishers with independent key
tables (`0xC2DF3448` / `0xC2DF3D0C`). A value from `gui geti` that contradicts
other evidence is not proof — cross-check against the image-load log, which
reflects what was actually drawn.

## 7. Memory

```
mem get [start,,] | [start,end,] | [start,,size]
mem set [address] [data]
mem save [path] [start,end,]        → dumps to a file on the card, then getfile it
```

`mem save` is far better than word-by-word reads for dumping a region.

Standing rule in this project: **every memory read needs the user's explicit
consent, naming the addresses, each time.** The same goes for ad-hoc writes to
stock data. Running vetted tooling (`og3k_load.py`) is not the same thing.

## 8. Measuring what the UI drew — cross-frame pollution

`gui image log` captures a window spanning more than one frame, and **the first
draw after a state change still carries the previous state's assets**. A naive
probe — change setting, clear log, open the screen, read — reports the old
state's icons as if they were the new state's.

This produced two wrong conclusions in a row: a memory patch was declared
"working" twice on the strength of an icon that was actually left over from the
preceding setting.

**The discipline that works:**

```
close the screen → change the setting → wait ~3 s
→ open  (first draw — DISCARD)
→ close → log clear
→ open  (second draw — this is the measurement)
```

Cross-check by probing two different states in sequence (e.g. UHD then the state
under test). If the state under test reports the *other* state's icon, you are
looking at pollution, not a result. `build/qsprobe.py` implements this.

A patch that changes nothing is a real result — but only once measured this way.

## 8b. Heavy QS toggling wedges the USB worker

Repeated `key QSON` reliably kills the shell: `LIBUSB_ERROR_TIMEOUT moved=0/64`,
while the camera stays enumerated (unchanged ioreg node id, so it has not
rebooted) and the screen keeps working. Recovery is a USB unplug/replug.

Each rigorous probe toggles QS five times, so **do not chain many probes in one
run** — two states per run is about the limit. A wedge mid-write leaves a patch
half-applied; keep an originals file and re-run the revert after replugging.

## 8c. After a wedge, verify the affected payload before trusting it

A wedge interrupts writes mid-flight and leaves the installed payload
half-applied. `og3k_load.py --check` reports "N words differ" but does not
distinguish harmless runtime log slots from a broken lookup table — 9 differing
words were once dismissed as log slots when they included the menu-row-to-enum
mapping, which made selecting the custom resolution write an out-of-range enum
and silently fall back to the default display state.

After a wedge, identify the interrupted operation and verify the affected
memory or file against its saved before-image or intended bytes. Re-apply only
the payload whose state is proven incomplete and whose recovery is within the
current authorization. A disconnected shell alone does not show that an
unrelated payload was damaged.

## 9. Status and other useful commands

```
status get app_current | app_lv_attribute | is_recording
memmgr memtbl | poolchk | heapmem
display osdfile <path> <layer> <monitor> <h> <v> <offset>   draw a TIF onto the OSD
ui rdump / ppmgr list / imager mode_now / imager mode_list
```

`display osdfile` can composite arbitrary graphics onto the screen from a file on
the card — a route to on-screen content that needs no resource-pack work.

## 10. Camera-side cautions

- Never `dir` a clip folder (`\CINEMA\A001_nnn`). `dir \CINEMA` is fine.
- Never `delCinemaDng`, `deloneimg`, `delall`.
- **Deleting one file you put there: `fl del \fpSup\NAME.BIN`** (answers `OK`, or
  `<path> can't delete` when it is not there; its help text "currently not working"
  is stale, measured working 2026-10-06). Use `putfile.delete_file()`, which refuses
  anything but a plain `\DIR\...\NAME.EXT` path and anything under DCIM/CINEMA.
  **Mode 7 does not truncate**: writing a smaller file over a larger one keeps the old
  tail, so delete first -- `fp_usb_shell/v3/deploy_v3.py` does delete -> write -> full
  readback -> size check per file.
- An armed USB worker can deadlock against card I/O IRQs. If the camera wedges
  during card activity, unplug USB, operate the camera, replug.
- **Do not pick a cave address. Ask for one.** `fp_usb_shell/cave.py`:

  ```python
  import cave
  at = cave.claim('mytool.code', 512)   # same address all boot; new one after a reboot
  ```

  It takes the space off the camera's own bump pointer — the one stage2 resets
  every boot and the gyro's hook veneers come out of — so a claim cannot land on
  anything the camera placed, or on another tool's. The register of who has what
  is a file on the host; the camera holds one number. `python3 cave.py` prints
  the map. The arena is `0xC072E064..0xC072EFB4`, 3,920 bytes.

  Two tests in `gyro/test_safety.py` hold this up, and both are mutation-tested:
  `ArenaTests` fails the build if any source names an address inside the arena,
  and `CaveTemplateTests` fails it if an assembly source takes its block from the caller
  and some `assemble()` of it does not pass one.

- **A new `.S` probe requires its caller's allocated block address.** Pass
  `P=0x...` (or the source's `SCRATCH`/`SLOT` name) from the host tool and
  require a missing value to fail compilation. Do not silently fall back to an
  old fixed scratch address. `inject.py` passes guarded names; the corresponding
  host address and assembly value must match. A mismatch in `getfile.S` once
  hung the shell and cost a power cycle.

- **The worker's own words are the exception**, and they are not allocatable:
  the resident worker was built with them in it, so both sides must agree.
  `cave.ABI` lists all eight (`pool_ptr`, `code_ptr`, `abort`, `pool_desc`, the
  two load stamps, `park_stub`). `store_boot.S`'s bootstrap word is fixed too —
  it runs before stage2, so there is no arena yet.

- Before placing anything by hand anyway, read the target range and confirm it
  is zero. Thirteen probes in `raw/` still default their slot to `0xC072E080`,
  which is the gyro's fourth hook veneer; they are guarded now, so they are only
  dangerous if you inject one without passing `SLOT`.

## 11. The two bulk IN channels — EP82 replies, EP83 streaming

Shell v3 has the firmware build and own all three endpoints (that is the whole
point of v3: v1 bolted on endpoints the firmware did not know about, so recording
tore the channel down).

```
EP 0x01 OUT  bulk 1024, burst 3    commands
EP 0x82 IN   bulk 1024, burst 3    replies
EP 0x83 IN   bulk 1024, burst 3    streaming, for a hook to arm directly
```

EP 0x83 is PTP's unused interrupt endpoint turned into a second bulk IN, so a
stream and the command channel do not block each other. **EP 0x84 does not
exist** — `DALEPENA` is `0xA7`, physical 9 is not enabled, and `StartTransfer` on
it is refused instantly, 100 times out of 100. "EP84 halts, pull the cable" was
always that. EP83 *is* enabled, *is* bulk, and accepted Start 100 out of 100 —
**but Start acceptance is not bytes delivered, and no EP83 payload has ever
reached the host.**

> **2026-10-06:** both directions now run at the link's ceiling through MEM1
> (write 398 MB/s, read 382 MB/s, window-protected, no echo borrowing) — see
> skill **fp-usb-transfer**. The 73 MB/s figures below are the older
> `dumpdirect` path and are kept as history.

### Want a bounded batch out of the camera? Use EP82. It is already fast.

Do not wait for EP83 to move a few KB or a few MB. The reply path is finished and
measured on the camera: the worker takes a source address in `CAP_PTR` and points
its TRB at it instead of copying through the 16 KiB capture buffer, so a reply
comes from wherever the answer already is.

| | |
|---|---|
| camera memory → host | **73 MB/s** (0.42 s) |
| card → camera memory | 183 MB/s (0.17 s) |
| `getfile.py` end to end | 1.17 s (was 76 s) |

Replies carry up to 16 MB. **One megabyte per transfer measured fastest** — 4 MB
drops to 9.5 MB/s, 16 MB to 2.1, and the camera does *less* work at those sizes,
so that ceiling is on the host. Buffers come from the firmware's own allocator
(`FUN_c001d740` / `FUN_c001d7f0` / `FUN_c001d7a0`), measured good 64 KiB–32 MiB;
do not carve up a megabyte grabbed at boot.

`projects/fp-af-assist/highrate/af_hook_trial.py` is the worked example — it
exports its whole 8,256-byte capture over this path (`transport='EP82-raw-bulk'`,
`ep83_delivery=False`) and refuses to run if the resident worker body differs from
the reviewed `CAP_PTR` implementation.

### Host side of EP83 — written and tested, not deployed

`fpSup/fp_usb_shell/host/fpshd.c` has the consumer. One socket line:

```
EP83 <bytes> <shellline>   -> OK83 <bytes> <seq>\n  then exactly <bytes> binary
                           -> ERR ep83 ... quarantine=<0|1>
```

It reuses the existing libusb handle and interface — **it does not open a second
owner.** Sequence: read both MPS from the descriptors, dispatch the trigger line
on EP01, read the EP83 byte prefix, then verify one original 64-byte FPSH
terminal on EP82 with matching sequence, CRC and status. Limits: 1..65,536 bytes,
16 KiB chunks, a 2,000 ms deadline for the whole exchange, MPS-aligned reads with
the short read only at the end.

Rules baked in, keep them: any failure **quarantines the daemon** for all later
camera exchanges; no drain, no clear-halt, no retry, no recovery on this path.
Once the OUT is dispatched and the outcome is unknown, the camera may still own
its DMA — restarting the daemon does not prove otherwise.

`host/tests/test_ep83_host.py`: 11 tests against the real `fpshd.c` with a fake
libusb (lengths and MPS combinations, old-handle reuse, timeout, OUT/data/terminal
faults, sequence and CRC, error locking). Run it before touching the daemon.

**The running daemon almost certainly does not have this.** Check before assuming:

```sh
strings -a fpSup/fp_usb_shell/fpshd | grep -c EP83     # 0 = old binary
```

The 9/25 binary reports `transport=EP01-EP82` in `STATUS` and has zero `EP83`
strings, while the source (9/27) has the consumer and is still uncommitted.
If this candidate is authorized for live use, rebuild it with the reviewed
flags (`cc -std=c11 -O2 -Wall -Wextra -Werror`, `-lusb-1.0`, rpath and `-L` at
`projects/usb-shell-sup/lib`). Inspect the exact running daemon first; use
socket `QUIT` or a verified owned PID to release it before starting one
replacement. Do not use a blanket process kill.

Do **not** reach for `projects/fp-af-assist/highrate/ep83_libusb_owner.py` as a
second claimant: it refuses to run while `/tmp/fpshd.sock` exists (correctly — two
owners cannot claim interface 0), and its default libusb path resolves to a
nonexistent `projects/lib/libusb-1.0.dylib`.

### Camera side of EP83 — this is the unfinished work

Nothing on the camera sends on EP83 yet. `highrate/af_ep83_camera.c:638` still
calls `af_ep83_camera_make_synthetic`, the host session hard-requires
`camera_state=SYNT`, and `build_ep83_camera.py` reports `deployment_ready`,
`loader_integration_complete` and `single_usb_owner_verified` all false. What has
to be settled, in this order:

1. **Pick one camera owner.** The resident `worker.S` is the text shell
   dispatcher; the highrate native mode-5 CMD4 adapter is a different one. Do not
   arm both — they compete for EP01/EP82.
2. **Get the TRB away from the stock PTP event sender.** It writes the *same*
   EP83 TRB (`C01E91D0` → `C01E5880`). Patching a descriptor does not make the
   controller bulk and does not exclude that sender. The boot-plan candidates are
   `C01E5880` success-noop and `C07E2800` ctx3 default mode 2→1 — **candidates**,
   they change stock event delivery, and they must be shown to coexist with the
   shell, the native USB task, enumeration, reset and power-off. Live-read ctx3 is
   `{2,1,3,0}`. Never set mode=1 alone (the stock event selector then cannot find
   its mode-2 IN), and do not hot-patch ctx3 in a running session.
3. **Wait for completion without re-arming anything.** `highrate/af_ep83_wait.c`
   is a direct one-shot RTOS event wait that deliberately avoids
   `C01E56F1 → C01E7780`, which may rewrite the completion and re-Start bulk OUT
   EP01.
4. **Own your memory.** Allocate your own (`af_probe_helper.S`, 1100 bytes: one
   64 KiB USER allocation, CP15/MMU noncache mapping verified, D-cache
   publication before export). The current worker publishes its own pool at
   `pool_ptr 0xC072F050` / `pool_size 0xC072F054` / `code_ptr 0xC072F058`
   (`cave.ABI`); the legacy `C3757A7C` 1 MiB pool descriptor is **not** yours.
   For small blocks use `cave.claim()` as in §10.
5. **Never send USB from the hook.** The hook does a bounded copy plus commit and
   returns; a separate task sends. No allocation, no wait, no retry, no lens
   command in a hook.

One trial is: one trigger → one EP83 batch → one EP82 terminal, a single batch in
flight. A host `while` loop around a one-shot is not a stream — the sender result,
camera private state, control entry, host session and libusb owner are all
single-use, and a continuous session needs a per-batch ownership handoff that
releases a buffer only after **both** the EP83 completion and the EP82 terminal.

Files: `highrate/af_ep83_camera.c`, `af_ep83_control.c`, `af_ep83_wait.c`,
`af_ep83_memory.c`, `af_sender.c`, `ep83_receiver.py`, `ep83_host_session.py`,
`ep83_boot_plan.py`, `build_ep83_camera.py`.

**Current gate:** `af_hook_trial.py` no longer blocks unconditionally, and it
registers nothing. Before its first write it finds the shared loader's journal
through both power-off lists and requires it to hold the AF callsite's stock
word — which means the card declared that site as a four-byte section — and it
reads it again immediately before arming. No flag skips any of it. See §12.
Still open: a battery pull or crash runs no callback at all.

## 12. Putting a borrowed firmware word back at power-off

**The shared loader owns this. Do not register a callback of your own.** Since
2026-09-25 stage2 registers one power-off object in both of `XC_PowerOffMgr`'s
lists before it places anything, copies every firmware word a card changes
(at or above `0x40000000`, outside the cave `0xC072D000..0xC0735000`) into a
journal, and its callback writes the journal back. `fpSup/HOOKS_AT_POWER_OFF.md`
is the reference.

**A word you patch at run time gets in by being declared on the card**: a
four-byte section holding the *firmware's own* word, which stage2 journals before
the entry runs. Writing a site's own word back is a no-op on a stock image and a
repair on one a missed power-off left patched. gyro's `hook_sites()` in
`gyro/build_base_card.py` is the pattern; `--also-bin 0xADDR:file` is the CLI
equivalent (`--also` assembles a source file, `--also-bin` takes raw bytes).
`projects/fp-af-assist/highrate/hook_site_section.py` emits such a section with
the word read from the checked ROM, and verifies a built card declares it.

Why not your own object, even though the ABI is simple: the ordinary list has ten
slots and **the firmware already fills eight**; the forced list has ten and the
firmware fills one. stage2 takes one more of each on every load. Spending the
last ordinary slot to duplicate a mechanism the loader already provides is how
you get a card that cannot load next to anything else.

To verify rather than register, read it back:

```
C0023A98  () -> the manager, a lazily constructed singleton at 0xC30756C4
C0024118  (mgr, obj, forced) -> 1 registered, 0 list full
          forced == 0 -> ordinary list at mgr+0x0C (0xC30756D0), ten slots
          forced != 0 -> forced   list at mgr+0x34 (0xC30756F8), ten slots
at power-off: obj->vtbl[+0xC](obj, reason), from C0023C50 / C0023F38 (reason 4)
```

The loader's block, from `fpSup/fp_usb_shell/asm/stage2.S` `lh_setup`, is identifiable
without any marker — `LH_MARK+8` publishes the address *before* registration, so
it is not proof of anything:

```
X+0  X-8        the "vtable" pointer, so [vtbl+0xC] is X+4
X+4  X+12       the routine, copied there
X+8  journal    { address, bytes, original words }..., terminated by address 0
```

`shutdown_restore.py` in the same project walks both lists, finds the block that
fits that layout **and is registered in both**, walks the journal bounded, and
reports the recorded word for an address. Refuse when the recorded word is not
the stock one: a power-off callback that never ran (a frozen camera, a battery
pull) leaves a patched word, and the next load journals it as if it were stock.
That case is known and open.

What none of this covers: a battery pull or a crash runs no callback at all, and
a power-switch restart keeps the firmware image and the cave while clearing BSS
(so every registration and the pool pointer go) and rebuilding the heap. Code in
the cave survives and runs again; anything pointing into the pool must not be
left behind. Measured, three restarts in a row, in `HOOKS_AT_POWER_OFF.md`.
