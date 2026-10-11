# Res Lab Mode strip and named SAVE — 2026-10-10

Final build: [v25 debug](../../cards/20261010-save-v25/debug/) and
[plain](../../cards/20261010-save-v25/plain/), Res Lab header 16. The validation
directory retains its initial v24 name. This is an unpublished development card.

## Changes

- Mode occupies its own right-hand strip at (420,81), 570×48. The sensor
  diagram begins below it at (444,145), 510×340. UI and ARM use matching
  coordinates and retain a common pixel scale, center and corner connectors.
  The fixed Sensor 6064×4042 label is removed; the left 81-pixel grid remains.
  Information text remains transparent. A v26 trial added matching gray text
  plates, but the user observed that they obscured the diagrams. All plates were
  removed, restoring the exact previously tested v25 source and product bytes.
- SAVE has Name and Save RCD controls, plus a read-only Mode heading. There
  is no Mode selector or write action in that tab. Filename/save commands
  return before policy reconciliation, fitting or automatic commit.
- Seven character positions accept uppercase A–Z and digits; blank slots are
  omitted. LEFT/RIGHT selects a position, UP/DOWN changes the character,
  OK/MENU finishes. All blank retains automatic LAB001…LAB999 allocation.
- Existing filenames are checked case-insensitively and never overwritten.
  The internal VRC000 label is reserved. Names synchronize the RCD label,
  row, summary and QS/SET/FONT resource names; the atlas covers all 36 glyphs.
  Short and seven-character names are supported by the existing consumer.
- Filter expansion publishes the new native selector maximum before the
  retained Mode index, avoiding clamping against the previous, smaller list.
- No changes to recording geometry, preview formula, consumer, shared loader
  or AutoRun. The user-accepted M12 first-second correction remains unchanged.

## Build and offline evidence

Fresh output directories were built with `build_v3_reslab.py --virtual-rcd
--card`, with/without `--no-shell`. [Artifact proof](artifacts-v25.json)
verifies source hashes, complete manifests, identical plain/debug product
bytes, and byte identity of consumer/Loader/AutoRun against installed v23.
The final v25 ARM executable and owned-state layout equal tested v24; v25
aligns SAVE help text with sidebar rows. The rejected v26 trial also preserved
the same executable `[32:31920]`, as [its artifact proof](artifacts-v26.json)
records. After removing the plates, every final source hash and manifest entry
was again checked against the existing v25 candidate before installing it.

- [Initial tests](tests.log): eight completed cases passed: filename editing,
  save neutrality, case-insensitive collision refusal, short/seven-character
  assets and real ARM consumer loading, automatic names/invalid names,
  stable filter selection with a modeled native clamp, native page structure,
  ordinary SAVE and automatic edit commit. The subsequent slow single-Sup
  failure test was interrupted and rerun using the correct dual-Sup fixture.
- [Final native page](tests-v25-native.log): SAVE layout/allocation/reference
  checks passed. A second test was initially addressed under the wrong class;
  this was a test invocation error, retained in the log.
- [Correct native navigation tests](tests-v25-return.log): **2 passed**, SAVE
  command binding and return to SupManager through the native state machine.
- [Final failure and restore tests](tests-v25-failures-restore.log): **2 passed**,
  short write, corruption and trailing bytes rejected; both products' claimed
  words and tables restored on modeled shutdown. Firmware call alignment
  assertions also pass in filename/export/consumer integration cases.
- [Intermediate v26 native layout](tests-v26-native.log): **2 passed**, complete native
  allocation/relocation checks, SAVE controls and return state machine.

The first build stopped on an accidental private-string-offset collision in
the stock unaligned 0x11009 table. Useful initial labels replaced blank diagram
placeholders; the complete bytewise relocation guard remains enabled. A compile
error from the unity compiler's static-name prefix was corrected before any card
was produced. Neither issue reached the camera.

## Deployment

[First deployment](deployment-v25/deployment.json) backs up and checks v23;
[intermediate deployment](deployment-v26/deployment.json) verifies v25 then writes v26.
[Final transparent-text deployment](deployment-transparent/deployment.json)
restores the tested v25 after the user's correction. Each changes only
50RESLAB.BIN and verifies exact size and complete readback.
Existing RCS1 and FSDS settings are preserved. For the shorter v25 file,
the old producer was removed only after its verified backup to avoid a tail.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| 50RESLAB.BIN | 607608 | `3c216d4b36d74393c7ea8f7ea81ac54e54faa204d2c98d8ca452b68d4aebd060` |
| 32RESCUS.BIN candidate, blank settings | 77120 | `ae82bcf8b8ab2b9f78319e24908805ca6020ac01a7def80d686c1735eada6556` |
| LOADER.BIN before persistent FSDS settings | 27668 | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` |
| AutoRun.txt | 32768 | `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0` |

## Physical verification

v25 was loaded and both product headers verified in [runtime proof](runtime-boot.json).
Each reboot command was sent once; a USB reset IO response was never replayed.
After the first reboot, SIGMA interface 0's verified macOS PTP claimant PID 6431
was released and the owned daemon changed from 6423 to 8372. Standby recovered.
All camera clients use the same exclusive lease.

- [Native filter test](filter-camera.json): M12 remained selected while the FPS
  filter expanded from 279.72 to All fps. Native selection correctly changed
  from list index 1 to 61; readout, crop, output 992×662 and the active consumer
  registry/generation remained identical.
- [Native SAVE test](save-camera.json): enter the name editor from the SAVE tab,
  use native direction/OK keys to create **A9.RCD** then **B9.RCD**. Both files
  are 48,068 bytes and fully read back. The standard decoder confirms label,
  Mode 12 and output 992×662. Local evidence: [A9](A9.RCD), [B9](B9.RCD).
- A repeat save displays `Name exists`; a second complete readback of B9 is
  byte-identical. The Mode, all geometric state, active consumer rows and
  registry/generation remain unchanged throughout filename editing and saving.
  Only these two newly created test files were removed after validation; the
  five pre-existing RCDs and their sidecars remain.
- SAVE has a read-only Mode heading and the first DOWN selects the filename.
  [Name screenshot](../20261010-sidebar-v13/screenshots/1655-v24-name.jpg)
  and [saved screenshot](../20261010-sidebar-v13/screenshots/1656-v24-saved.jpg)
  were captured on v25; their historical capture tags are retained.
- The user's rejection of opaque text plates was applied and physically
  verified after the final reinstall: [transparent OUTPUT screenshot](../20261010-sidebar-v13/screenshots/1658-final-transparent-output.jpg).
  [Final runtime](runtime-final.json) confirms the 607,608-byte v25 producer
  and unchanged consumer. Final screen is M12 / 992×662 OUTPUT, AUTO output,
  279.72 FPS filter (two matching modes), standby. The owned daemon is PID 9055;
  the final reconnect released only the verified SIGMA PTP claimant PID 8905.

## Scope limits

This revision does not repeat recording/SSD benchmarks or the physical
all-mode/kernel matrix. Approximately ten power-switch cycles remain incomplete.
RAW14 calculation-only and existing asset-memory limits remain as documented.
No commits, pushes or publication were performed.
