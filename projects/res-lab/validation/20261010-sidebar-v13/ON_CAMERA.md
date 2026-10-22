# Res Lab sidebar hardware audit — 2026-10-10

The user authorized deployment, on-camera testing and bug repair. This report
supersedes the v13 offline-only status in [RESULTS.md](RESULTS.md). The final card
is v16: producer header version 13 and consumer header version 5. These are still
two separate SUPs. Only the affected SUP files were updated on the existing camera
card; shared Loader, AutoRun, disabled-SUP state and consumer settings were preserved.

## Hardware findings and fixes

| Failure found | Cause and repair | Evidence |
| --- | --- | --- |
| Sidebar values intruded into diagram; diagram and last row reached footer | Native Menu adds a 99-pixel vertical origin; static summaries also have an IconText parent. Use local diagram Y=81, 49-pixel rows and resize the summary parent. | [Before](screenshots/1626-v13-output-before-fix.jpg), [after](screenshots/1628-v14-m12-output.jpg) |
| Status text invisible | Above-tab placement was clipped; in-frame placement was covered by the later draw ordering of the sensor fill. Move the status to the front of the native sibling list. | [Visible rejection](screenshots/1636-v16-save-rejection.jpg), [visible success](screenshots/1637-v16-saved-lab002.jpg) |
| SAVE showed only `Saved ` | UI publication preceded filename concatenation. Publish once after building the complete message. | Native getter returned `Saved LAB002.RCD`; screenshot above |
| First SAVE on a five-file card made the next boot lose the Virtual RCD service | Six file rows exhausted the consumer's row capacity before it reserved its virtual row. Reserve one row before file selection when virtual support is present. | [Six-file boot](runtime-v15-saved-file-boot.json), [saved file selected](runtime-v15-lab001-selected.json) |

The last fix changes file selection capacity only: virtual-enabled builds select
five file rows plus one virtual row; standalone res-custom retains six file rows.
All valid files remain in the available-file catalogue. No new loader contract,
recording engine or second producer interface was introduced.

## Physical checks

- FILTER and mode selection: all ten FPS filter steps, RAW12 filtering and native
  mode popup exercised. 239.76+ leaves M9/M12; M12 applies without an Apply button.
- OUTPUT: shape lock, pixel crop, output dimensions, binning, intrinsic correction,
  anamorphic lens and lens-factor controls exercised. Numeric edits update the UI
  without repeated live-view initialization; OK or MENU commits once. Focus/tab
  changes alone do not consume another geometry pack.
- Conditional controls: with lens correction off, the hidden factor row is skipped
  by native navigation. An empty mode filter preserves the active consumer recipe.
- SAVE rejection: RAW14 reports `14-bit unsupported`, visibly, without writing a file.
- SAVE success: LAB001 (960×642) and LAB002 (992×662), both M12, were created on SD,
  fully read back and decoded as RCD1 v3. SAVE left the active consumer rows,
  generation and geometry unchanged. LAB002's full filename appeared on the LCD.
- Saved recipe independence: after reboot, LAB001 was visible in the original
  recording-resolution picker and selected through native keys; consumer row 1
  became active while the virtual generation remained zero.
- Both test RCDs were backed up, reread byte-for-byte and removed from the card.
  The five original RCD files were retained. The cleanup reboot restored the five
  original rows plus VRC000. See [cleanup proof](test-rcd-cleanup.json) and
  [clean boot](runtime-v16-clean-boot.json).

Detailed editing evidence: [sidebar trial](v14-edit-trial.json),
[empty filter and binning](v14-filter-bin-trial.json),
[before final SAVE](runtime-v16-before-save.json),
[after final SAVE](runtime-v16-after-save.json).
Every transport response is preserved in [commands.jsonl](commands.jsonl).

Final OUTPUT LCD: [M12 auto-applied, sidebar and nested diagram](screenshots/1638-v16-final-output.jpg).

## Final v16 recording check

M12 AUTO restore, 992×662 output, CinemaDNG 12-bit, native 29.97p: clip A001_026
completed **88 requested / 88 written frames** and stopped on the controlled native
button pulse. The native log reports `rec factor: Nothing`, `ui factor: Button`;
the camera returned to responsive standby. Sensor timing readback is
29.970029970 fps. First, middle (44) and last (88) DNGs have valid TIFF headers and
decode as 1008×672 padded RAW rasters.

This proves bounded recording and complete writes, but **does not verify the
first-second image seam**: the actual REC preview is black and the three RAW
samples are near black level (roughly 256; sampled 99.5th percentile 258). The
diagnostic PNGs stretch that noise; they do not show a usable scene. The user was
asked to provide a lit, detailed view before another visual regression trial.
No image-quality pass is inferred from a dark frame or from the offline r78 test.

- [Summary](v16-recording-summary.json)
- [Full recording, FPS, native log and DNG evidence](../20261009-recording-formula/v16-m12-2997-start-record.json)
- [Actual REC screenshot](../20261009-recording-formula/v16-m12-2997-start-rec-preview.jpg)
- [Trial transcript](v16-m12-recording.log)

RCD backups: [LAB001](LAB001-camera.RCD) / [decoded fields](LAB001-camera.json),
[LAB002](LAB002-camera.RCD) / [decoded fields](LAB002-camera.json).

## Offline regression evidence

- [36 integration tests](v15-integration.log): all passed (948.541 seconds), including
  automatic commit, SAVE failures, six-file boot, shared Virtual RCD contract,
  native UI, shutdown restoration and both preview regressions. M12's 29 formula
  fields, standby, geometry/profile words and sensor timing match frozen r78.
- [Final v16 native tests](v16-native-regression.log): all five passed, covering the
  final page bytes, SAVE command, original recording page, return navigation and
  shutdown restoration.
- [Standalone consumer](v15-standalone-six-formats.log): six-file capacity passed.
- [Old v14 reproduction](v14-reproduction.log): both new regression assertions
  fail against old exact bytes, then [pass on v15](v15-fix-focused.log).
- [v15/v16 code equivalence](v16-code-equivalence.json): ARM code and constants
  from offset 32 through 29703 are byte-identical; consumer BIN is identical.
  v16 only changes producer header version and the UI area's status draw order.
  Thus the v15 functional suite applies to the unchanged v16 executable paths;
  the final UI bytes have their own five-test run and LCD captures.
- The original 70-mode / 142,800-case host sweep and 1,750 ARM cases remain in
  [RESULTS.md](RESULTS.md). They are offline coverage, not physical testing of
  every mode, bit depth or frame rate.

## Artifacts and deployment

- [Plain v16 card](../../cards/20261010-sidebar-v16/plain/)
- [Debug v16 card](../../cards/20261010-sidebar-v16/debug/)
- [Source and artifact verification](v16-artifacts.json)
- [Consumer upgrade proof](deployment-v15/deployment.json)
- [Final producer deployment proof](deployment-v16/deployment.json)

| Built file | Bytes | SHA-256 |
| --- | ---: | --- |
| 50RESLAB.BIN | 636000 | `7f7ddf6ab3c2a2cd570f344aee97c0bdd4371f04b376ec6076e3c111823790e0` |
| 32RESCUS.BIN | 76352 | `bdbbe99d2ddba2a2dab8542fa042b130a66d5f9dd7d2661a34a949bc224e4fc2` |
| LOADER.BIN | 27668 | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` |
| AutoRun.txt | 32768 | `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0` |

Plain/debug product bytes match. Producer residency is 907136 bytes; consumer is
746752 bytes. The camera consumer includes its existing 96-byte RCS1 settings
area, and the camera Loader retains its existing FSDS trailer. These legitimate
persistent areas differ from blank candidates; deployment validates their format
and all code bytes rather than overwriting user state to match a hash.

Warm reboot disconnects were handled without replaying the reboot. macOS PTP
reclaimed interface 0; each recovery inspected the exact SIGMA interface owner
and released only that ptpcamerad PID. No blanket kill loop or second daemon was
used. All completed camera trials returned to responsive standby.

## Remaining scope

The lit-scene first-second preview recheck, 240/280 sustained-recording and high-rate DNG metadata issues, SSD throughput
validation, every-mode physical image-quality validation and extended warm-cycle
soak are separate unfinished checks. No claim of completion is made for them.
