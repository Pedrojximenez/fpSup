---
name: fp-camera-control
description: "Operate and inspect a SIGMA fp Ver.5.02 through its existing USB shell: menu getters, authorized UI changes and keys, screenshots, GUI logs, and current CINE AF observation tools. Use for live camera UI or state diagnosis; use fp-usb-shell for ARM probes and transport internals."
---

# SIGMA fp camera control

Adapted from this project's Claude Code `fp-camera-control` and `fp-camera` skills on 2026-09-27. Default repository: `/Users/dido/Developer.localized/SIGMAfp_re`; honor an explicit alternate checkout. Paths below are repository-relative. Use maintained tools in `fpSup/fp_usb_shell/`, not copied implementations.

## Choose the operation

Documentation, skill installation and offline analysis do not require a camera connection. For live work, continue within the user's existing authorization; do not ask again for the same approved action. A prior trial's authorization does not imply permission to record, change cards, stop another process or publish code.

- Reuse the existing daemon after identifying its executable and owner. A socket alone does not prove ownership; starting a second `fpshd` can unlink the first socket and compete for interface 0.
- Diagnose ACCESS or TIMEOUT from the actual claimant, daemon and running build. Do not start a `ptpcamerad` kill loop or blanket-kill daemons. Preserve a user's already-running services.
- Honor `/tmp/fp-af-fusion.lock` during AF sessions and do not interleave other camera clients. File tools can borrow code/RAM even when reading a file.
- Before ARM injection, memory placement or transport recovery, read [fp-usb-shell](/Users/dido/.codex/skills/fp-usb-shell/SKILL.md) and the actual tool source. Historical fixed scratch/pool addresses are not a free allocation.

The native `putfile.sh()` helper defaults to retries. For non-idempotent actions use a reviewed runner or `retries=0`, inspect the response, and treat timeout as an uncertain outcome. Never replay a toggle to discover whether the previous toggle ran. Do not generalize “no arguments prints help” to arbitrary firmware commands.

## CINE autofocus work

The current AF project targets continuous focus while recording; preserve CINE when that is the user's scope. Maintained notes and captures are indexed by [fp-af-assist/PLAN.md](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/PLAN.md).

| Intent | Maintained entrypoint |
|---|---|
| Native fixed-address subject preflight | `research/autofocus/af_native_preflight.py --run-live-read --subject-path --subject-samples 8 --output NEW.jsonl` |
| CINE standby observation without a key | `research/autofocus/af_cine_baseline.py --run-live-read --samples 4 --output NEW.jsonl` |
| Previously authorized paired half-press trial in CINE standby | `research/autofocus/af_cine_acquisition_trial.py --run-live-half-press --output NEW.jsonl` |

These recipes are for non-recording standby; verify that state and review the runner's current guards before use. They do not start recording. The acquisition runner owns one S1ON/S1OFF pair and releases in cleanup; do not substitute raw S1 commands or the STILL-only tracking runner. The legacy `af_fusion_collector.py collect` live route is disabled pending memory ownership work; do not bypass its guard.

Face/AAT snapshots and S1 success do not establish tracking activation, a focus anchor, or video CAF quality. Menu focus-area values and the AF-copy field are different domains. Zero/inactive subject data stays unknown. Use [the CINE baseline evidence](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/FP_CINE_BASELINE_2026-09-27.md) and current AF tools for interpretation.

EP83 continuous telemetry is under development. Read `projects/fp-af-assist/notes/AF_STREAM_TRANSPORT_GAP_2026-09-27.md` before proposing a recording stream: current highrate adapters are synthetic/single-use, not a deployable continuous recorder. Generic shell polling during recording is not a substitute.

## Menu and UI commands

Import `putfile` from `fpSup/fp_usb_shell`. `menu SetMovRecSize` reads; `menu SetMovRecSize VALUE` changes state. Verify the specific setter and enum in the running product rather than copying an OG3K example into a stock camera.

`setting set` can change only a mirror; readback of that mirror is not proof the camera adopted the value. Verify the actual setting owner or observed behavior. `menu save`, `setting save` and `setting write` persist settings and are separate from temporary UI changes.

Useful reads include `status get app_current`, `status get is_recording`, reviewed `menu` getters, `imager mode_now` and `imager mode_list`. Camera build and source determine their interpretation; do not assume an old daemon version identifies the payload.

## Keys and physical mode

- `S2ON` is the shutter, not an unconditional still-photo command. In CINE it can toggle recording. `MOVON` is down and `MOVOFF` is up, not a stop command. Use a verified paired runner for authorized recording, with state checks and no blind retry; immediate state readback can lag.
- `QSON` and `QSOFF` have historically both toggled QS. Do not assume they form an ordinary press/release pair. Repeated QS experiments have wedged the USB worker; keep a diagnostic bounded and stop on a transport fault.
- Physical CINE/STILL selection has not been overridden by shell key events. Those events can move `SetRecMode` while leaving the active application unchanged. Cross-check active mode; keep CINE for the current AF project.

## Screenshots and GUI diagnostics

An authorized `CAPTUREON`/`CAPTUREOFF` pair writes `SS__nnnn.JPG` under `\DCIM\100SIGMA`. This is a card write. Screenshots observed on this firmware are 1024×682; capture dismisses QS, so use GUI image logs for QS instead.

`getfile.py REMOTE LOCAL --size N` needs the verified byte count, especially for subdirectories; it is not a native zero-write RAM reader. Never enumerate a clip's contents with `dir \CINEMA\A001_nnn`, or use clip deletion commands. `dir \CINEMA` lists folders.

For an authorized UI diagnostic, `gui image log 1`, `log act GUI`, `log clear`, and `log out GUI` expose loaded `.xci` assets. Filenames at `C055FDF4` pair with dimensions at `C055FE14`; filter `C055FA14/C055FA30` LV-volume spam. Log activation/clearing changes diagnostic state and can discard prior evidence.

Each QS tile normally loads a label plate plus a value icon. A window spans multiple frames: the first draw after a setting change can contain old assets. Discard that draw, clear only your diagnostic window, and measure the next draw; compare two states to detect stale content. Bound toggles and preserve fault evidence.

`gui geti/getf/gets NAME` reads UI variables; different publishers can expose different instances. `gui seti` is often overwritten by the publisher and does not force underlying camera state. Cross-check contradictory values against drawn assets. `gui scr set`, `gui lang` and other setters are mutations, not diagnostic getters.

## Memory and recovery

Use fixed ranges in reviewed tools within the current authorization. Scope any new ad-hoc access before running it; do not impose the imported historical rule of asking anew for every already-authorized read. `mem_get` may combine retries and is unsuitable for claiming an atomic multiword snapshot. Large reads can fail; use the operation's bounded transport.

Use the maintained `cave.py` allocator and actual running-build ABI for new scratch, not hand-picked addresses or a zero-fill test. A live `cave.claim()` reads/writes camera allocation state; it is not offline inspection. The worker publishes its pool at `C072F050` with size `C072F054`, distinct from the legacy logger descriptor `C3757A7C`; neither pointer grants an AF lease.

After a wedge, retain the transcript and identify the interrupted action and ownership. Do not automatically reapply an OG payload, free uncertain DMA, assume USB replug erased RAM, or overwrite unknown hooks. An in-flight upload must not be killed casually. Use the transport-specific recovery path and distinguish saved evidence, emulator results and measured camera behavior.
