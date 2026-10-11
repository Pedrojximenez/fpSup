# Res Lab sidebar / automatic Virtual RCD / SAVE — 2026-10-10

This is the historical v13 offline report. The later hardware findings, fixes,
installed v16 artifacts and camera validation are in [ON_CAMERA.md](ON_CAMERA.md).
The original "current source" comparisons below describe the v13 validation time.

## Result and scope

The native Res Lab SUP now has FILTER / OUTPUT / SAVE tabs, with sidebar controls
and a shared centered geometry diagram. There is no Apply button. Mode and option
changes apply automatically; numeric edits update the diagram while editing and
commit when OK or MENU finishes the field. Unchanged geometry does not apply again.
Recording/busy rejection preserves the previous active recipe and reports status.

SAVE writes a fresh `fpSup/RESCUS/LABnnn.RCD`, verifies its complete bytes by reopening
the file, and leaves the active virtual recipe unchanged. A second save uses the next
unused number. The file uses the existing res-custom RCD1 v3 format and loads at the
next boot, with LABnnn tiles rather than the temporary CUSTOM tile.

All validation below is offline. No camera, USB transport or physical card was changed.
The native LCD renderer, actual focus behavior of conditionally hidden controls,
SD storage, automatic live-view transitions and recording require camera validation.
The prior M12 first-second preview fix remains covered by the frozen r78 regression.
The separate 240/280 sustained-recording and SSD checks remain pending.

## Exact artifacts

- [Plain card](../../cards/20261010-sidebar-v13/verified/plain/)
- [Debug card](../../cards/20261010-sidebar-v13/verified/debug/)
- [Res Lab SUP](../../cards/20261010-sidebar-v13/verified/plain/fpSup/50RESLAB.BIN)
- [Exact-byte and source verification](final-artifacts.json)

Both cards contain the same product SUPs, loader and AutoRun. `50RESLAB.BIN` is
636,000 bytes, version 10, with a 907,136-byte resident block. Final `verified`
artifacts match the tested `ready` bytes exactly; their source manifests also match
the current source files. The final rebuild includes the updated offline page-probe
allocation helpers in its source manifest.

| File | SHA-256 | Compared with v12 |
| --- | --- | --- |
| 50RESLAB.BIN | `58b6664069555be79e1053325f1dad66590c6a2e026de42c76b8c377a86eb482` | Updated |
| 32RESCUS.BIN | `5d0699f05aac9679765b953cc79a2e2b0ebfcf48f22dfa020df27b0466d5547a` | Identical |
| LOADER.BIN | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` | Identical |
| AutoRun.txt | `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0` | Identical |

## Validation

- [Host C geometry audit](formulas.json): **70 modes, 142,800 cases passed**.
  This found and fixed height-led rounding that could shrink a very wide crop on a
  second fit. Width alignment is canonical after height clamping.
- [Real product ARM sweep](arm-all-modes.json): **70 modes, 1,750 cases passed**,
  including the complete 29-word canvas and data-rate string comparison against
  the host calculator. All 62 supported modes encode; all 8 RAW14 modes reject
  encoding as required by the existing consumer. No unaligned ABI calls observed.
- **15 distinct integration tests passed across the logs below**: 9 sidebar tests,
  2 preview-route regressions, 3 native UI tests and 1 debug boot/shutdown test.
  The results are combined across runs, not a claim that every intermediate run passed.

| Evidence | Verified behavior |
| --- | --- |
| [Integration and preview run](final-integration.log) | Numeric commit on edit completion; no duplicate commit; crop shape; independent lens correction; busy rejection; sequential SAVE without changing the active virtual recipe; actual native page parser and references; both preview regressions including M12 vs frozen r78 |
| [Native UI and mutation rerun](final-native-and-mutation.log) | SAVE uses its command variable; unchanged recording page/rate variants; native settings return to SupManager; disabling automatic commit in emulator memory makes its assertion fail |
| [SAVE compatibility and failure rerun](final-save.log) | res-custom loads saved geometry; short write, corrupted readback and trailing bytes all report failure |
| [Final debug card shutdown](final-debug-shutdown.log) | Product boot and shutdown restore claimed words |

Intermediate failures retained in `final-integration.log` were resolved as follows:

- The first mutation wrote a Thumb instruction at an odd function pointer. The
  corrected test clears the Thumb bit and passes; it never modifies the card file.
- SAVE compatibility/failure tests initially omitted the RESCUS directory in the
  combined emulator fixture. Delivered cards create that directory. The sidebar
  fixture now mirrors the delivered card; both tests pass in `final-save.log`.
- The combined storage model now delegates write/open handling to the producer
  model, preserving directory updates and failure injection. Sequential SAVE passes.
- Larger native pages exceeded the old test-only 256 KiB probe buffer. Page and
  state-machine probes now reserve memory from the measured page/pack size; native
  parser and return-to-manager tests pass. These are emulator allocation changes,
  not new firmware hooks.

## Reproduction

Build from the repository root into fresh directories; the builder refuses to
overwrite nonempty output directories:

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --no-shell --out /tmp/reslab-sidebar-plain-new
python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --out /tmp/reslab-sidebar-debug-new
```

From `projects/open-gate/build`, point `VIRTUAL_RCD_CARD` at the desired built card:

```sh
VIRTUAL_RCD_CARD=/tmp/reslab-sidebar-plain-new python3 -B -m unittest -v test_reslab_sidebar test_reslab_preview_route test_virtual_rcd.NativeUI
VIRTUAL_RCD_CARD=/tmp/reslab-sidebar-plain-new python3 -B test_reslab_formula_arm.py --report /tmp/reslab-sidebar-arm.json
VIRTUAL_RCD_CARD=/tmp/reslab-sidebar-debug-new python3 -B -m unittest -v test_virtual_rcd.VirtualTests.test_shutdown_restores_claimed_words
```

The existing consumer limits still apply: 32 distinct cached icon packs / 4 MiB
per boot. A rejected automatic update reports its reason and retains the prior
active recipe. Res Lab and res-custom remain separate SUPs.
