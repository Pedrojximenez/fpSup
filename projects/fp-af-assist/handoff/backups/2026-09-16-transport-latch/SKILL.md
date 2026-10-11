---
name: sigma-fp-af-research
description: "Collect or replay SIGMA fp Ver.5.02 autofocus telemetry with the local USB-shell AF-fusion tools, run authorized original half-press AF trials, and validate native H/L–position sweep histories. Use for fp AF/DFD measurements and these tools' operation; not generic camera advice or Sony firmware analysis."
---

# SIGMA fp AF research

Use the maintained tools in the research tree, not copied implementations inside this skill.
Default repository: `/Users/dido/Developer.localized/SIGMAfp_re`; respect an explicitly supplied alternative.
The supported live target is **SIGMA fp Ver.5.02 with the already-working fp USB shell**, not fp L or another firmware.
For low-level USB transport, ARM probe changes, scratch ownership or worker recovery, read the installed
[fp-usb-shell skill](/Users/dido/.codex/skills/fp-usb-shell/SKILL.md). Ordinary offline AF replay does not need it.

## Route by intent

- Documentation, replay, or analysis: stay offline. Do not connect to or move the camera merely to validate instructions.
- Live telemetry without AF: `af_fusion_collector.py collect` without half-press options. This leaves lens/exposure controls alone but **temporarily writes camera RAM and borrows echo**; it is not zero-write observation.
- Original AF experiment: only when the user's current scope authorizes lens movement. Before dispatch, verify that authorization covers the planned bounded trial. Automatic skill selection itself grants no permission to focus, capture, record, flash, or change settings.
- Completed history: `af_fusion_history_probe.py` reads RAM without installing a handler; it does not itself establish AF completion or semantic validity.
- History analysis: `af_fusion_history_analyze.py native-history.json --output NEW.json` is offline-only and validates the narrow completed Near / area-0 protocol. Read the usage note's analysis section; an accepted structural candidate still does not establish freshness or DFD eligibility.
- Direction diagnostics: `af_fusion_direction_replay.py HISTORY... --output NEW.json` is offline-only. Its H-derived reference and same-side pair counts are internal consistency checks, not independent optical accuracy or a DFD controller.
- Native lens readout: `af_fusion_lens_readout.py --output NEW.json` is a live, non-moving cached getter/conversion check. Read the usage note and its linked drive-gate audit first; it is not a calibration sweep or a movement capability.
- Bounded contrast prototype: read `projects/fp-af-assist/README.md` and its validation note first.
  `fp_af_assist.py --demo` is offline; `--probe` temporarily leases RAM for getters, not zero-write.
  `sample_probe.py --output NEWDIR` validates scheduler-progress H without movement.
  `validate_motion.py` / `validate_assist.py` are explicitly authorized lab entrypoints, not permission
  to run them merely because a camera is attached. Fixed-copy sampling and cancellation before movement
  passed; a later four-step run was manually cancelled after recurring transport errors and fully restored
  RAM/settings, leaving the lens at 10807 rather than its 10707 start. This is historical evidence, not a
  current-position oracle. The complete AF loop is not yet hardware-validated; do not resume motion merely
  because that partial run's native completion checks passed.

For a live run or unfamiliar CLI use, read the repository's
[AF_FUSION_TOOL_USAGE.md](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/notes/AF_FUSION_TOOL_USAGE.md)
in full first. For a changed repository root, resolve that same relative path there.
For pairing, state, or exposure interpretation, also read
[FP_ORIGINAL_AF_TRIAL_2026-09-16.md](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/notes/FP_ORIGINAL_AF_TRIAL_2026-09-16.md).

## Reuse the tools

Tools live in `research/autofocus/`:

```sh
af_root=/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus
python3 "$af_root/af_fusion_collector.py" inspect
python3 "$af_root/af_fusion_collector.py" collect --duration 3 --hz 100 --retries 0
```

`inspect` assembles locally without touching the camera. Bare `collect` has no half-press action.
The current default shell directory is derived from the script location; keep the script with its sibling
`af_fusion_snapshot.S`. Use `--usb-shell` / `--socket` only when the actual installation differs.

An explicitly authorized, bounded original AF trial is:

```sh
python3 "$af_root/af_fusion_collector.py" collect \
  --duration 6 --hz 100 --retries 0 \
  --half-press-after 1.5 --half-press-hold 2
```

The program prints the new capture directory. Use that exact path for the history probe's
`--output .../native-history.json`; do not invent a directory or overwrite an earlier run.
`collect --output` must name a nonexistent directory; otherwise omit it for a timestamped default.
For replay use `decode PATH/samples.bin`; host wall-clock timestamps remain only in the original JSONL/events.

## Live invariants

- Confirm the supported camera/firmware and existing USB-shell session. A host ping alone does not verify firmware identity. Missing socket or unknown firmware is not permission to flash/install a card payload.
- Preserve baseline focus rectangle/mode/area/size. Do not run exposure diagnostics as getters: `imager high_gain_off` with no arguments changes state; `check_convert_abs_gain` with arguments drives actual gain.
- Keep exclusive `/tmp/fp-af-fusion.lock` ownership. Do not interleave callfn, raw dumps, another echo borrower, or another shell client during a run. An unknown echo owner must be investigated, not overwritten.
- Use the collector's paired S1ON/S1OFF path. Never retry uncertain S1ON, send S2, use `af msr`, or bypass gated lens controls to obtain a curve. The trial refuses movie recording, but it is not a universal idle/firmware validator.
- Require binary v3 / JSON v6 for live capture guards. Actual MovieRecording is byte `C30338D0`; four
  other busy bytes occupy `C30338C8..CB`, and the full u32 shutter-sequence gate is `C3033A6C`.
  Historical v1/v2 fields used incorrect/unsupported addresses; decode their recording state as unknown,
  preserve their raw bytes, and never use them to authorize S1. New records are 212 bytes with nonce seed
  `C072F7D4`; the handler still fits 1000 bytes. Read the usage guide's capture correction before live use.
- Normal cleanup sends S1OFF before restoring echo. Logging failure must not block release. Inspect manifest/events, then verify echo and baseline settings; ACK is not an optical focus-completion or physical key-state measurement.
- Cleanup failure, unknown ownership, unsupported state, or repeated transport failure ends further motion tests. Preserve evidence and diagnose; do not keep triggering AF to rescue a run. Disconnection/SIGKILL can defeat cleanup; do not promise a hardware watchdog.
- Use the verified DMA-copy handler. The old 952-byte direct-code-cave-DMA handler had cache-line mixing; stable header/trailer alone cannot rehabilitate its dynamic payloads. `inspect` currently reports 1000 bytes; compare source/hash against the research note when diagnosing versions.

## Do not promote transport integrity into scientific validity

- Check manifest invalid/stale/duplicate/out-of-order/gap counters and camera ticks. Contiguous sequence numbers do not mean every requested sampling time occurred.
- `snapshot_coherent=true` means stable indices, not exposure-aligned H/L and position. Leave `usable_for_dfd` unapproved until separately established.
- C329153C is strategy-dependent: Fast can publish the completed index, Near can publish the next unfilled index. Idle mposm histories are stale; position zero alone is not an invalid marker.
- Prefer completed native histories. The current probe dumps **area 0 only**, at most 128 entries, with raw u32 words. It does not select another area, prove completion, convert signed values, or enforce `two_passes_equal` as an exit condition.
- For the verified completed Near path, verify object/vtable, completion, descriptor pointers, stable metadata, delay `d`, sample `n`, and count. State 4 plus completion 1 can be valid; do not require state 6 universally. Then pair the supported prefix `H[k]/L[k]` with `mposm[k]`; do not shift contrast by `d` again. Stop short of pairing if the selected area or strategy is unverified.
- The offline analyzer distinguishes full-dump equality from history stability. Its only permitted varying word is `C32914FC`, a current area-0 L-derived statistic; do not generalize this exception to other globals or history words. It requires both chosen and reference areas to be 0 as a conservative supported protocol, not a universal firmware rule. It preserves `freshness_confirmed=null` and `usable_for_dfd=null`.
- Native peak reconstruction is an index/algorithm cross-check, not independent optical timing ground truth or proof that DFD works. H/L are CDAF frequency bands, not PDAF halves. UI ISO can remain fixed while AF changes actual sensor gain.
- H/L are processed accumulations, with separate scaling, conditional correction, saturation, and a mode-dependent +256/0 offset. Do not treat them as scan-min-subtracted values or assume their ratio cancels gain. Legacy JSON `peak_now/max/min` fields are aggregate small-H/main-H/small-L values, not extrema; see the direction-diagnostics note linked by the usage guide.
- Do not trust the historical `focus_drive_gated` label as a complete LiveView/AF-idle/recording guard. `C04EF7D0` success is submission, `C035FD48` is cached position, and `ptp focus_comp` is notification, not abort. Before a new movement route, read the drive-gate audit and establish bounded completion/abort; do not bypass a range rejection or replace it with `lens setfpos`.
- For new direct control read `FP_NATIVE_FOCUS_CONTROL_2026-09-16.md`: initialized native-L identity,
  successful event-reference result and pattern 3 matter; abort acceptance is not stopped. For settled H,
  read `FP_AF_STATS_FRESHNESS_2026-09-16.md`: route 14 or changed H alone is insufficient. The narrowly
  supported mode-1/3 scheduler witness is not a frame ID, seqlock or optical-settling calibration.
- The prototype leases only echo `C0BAC2F8` and `C072F700..F9FF`, saves/compares all 192 scratch words,
  and uses single-use nonce-checked native operations. Never retry uncertain move/abort/echo calls.
  Its optional 152-byte fixed H/L copy uses `F740..F7D7`, within the same approved lease; opcode 9 writes
  only nonce/results in `F700..F73B`. It is installed/read-back/cache-published/restored with the lease,
  not a worker change. With it installed, all host exchanges keep >=5 ms pacing; the old four-read
  burst is retained for fixed read-only diagnostics, not the active camera sampler. Snapshot timestamps
  cover the whole host RPC, not the duration of the camera copy. It is not interrupt-atomic or exposure-aligned.
  Two diagnostic short replies are confirmed PTP SessionNotOpen; this does not prove nonexecution or
  permit retrying echo/move/abort. See the USB skill's shared-path note; pacing is not a proven fix.
  A failed read can invalidate the observation; do not bypass its guards to force a completed run.
  Default observation deadline is 8 s for this slow prototype, not a camera exposure deadline.
- For publication-triggered/high-rate sampling, first read
  `research/autofocus/notes/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md` and the project's hook plan.
  Prefer an audited producer-completion point over raising USB polling frequency; it still does not prove
  new sensor exposure or position alignment. AF-task hook removal needs AF-task quiescence, not merely
  a fresh shell reply. Existing echo/scratch consent does not authorize a new code hook or buffer range.

## Persist reusable evidence

Follow repository `INDEX.md`: tools are loose files under `research/autofocus/`, notes under `notes/`,
captures under `captures/af-fusion/`. Keep original samples.bin, JSONL, manifest, events, history and handler
source/hash. Store interpretations separately; do not rewrite raw evidence to look validated.
Record changes in [AF_FUSION_TOOL_USAGE.md](/Users/dido/Developer.localized/SIGMAfp_re/research/autofocus/notes/AF_FUSION_TOOL_USAGE.md)
when CLI or safety behavior changes. Do not maintain a fork of the tools inside the skill.
