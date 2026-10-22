# Res Lab controls / native LCD validation — 2026-10-10

Final installed card: `../../cards/20261010-controls-v23/debug`.
Res Lab header **15**, res-custom header **6**. This is a development card,
not a published release. No commits or remote publication were performed.

## Changes

- Move the Mode selector into the diagram. UP from Bit reaches it; LEFT/RIGHT
  changes the mode. Focus arrows and mode name are inside that area.
- Five large single-line FILTER rows, 81-pixel sidebar separators. The right
  diagram moves from x390 to x420, with no menu grid behind or around it.
  Its 570×380 canvas and the ARM coordinate calculation use the same scale.
- OUTPUT has Crop with lock, binning with the six kernels/std/soft, common
  Desq presets, Output with auto/lock/free, and a per-FPS MB/s estimate.
  Native vector padlocks avoid missing emoji glyphs. The icons are inserted
  above the row background; the earlier v18 draw order hid them.
- User-requested labels: `Mode Corp`, `Output Corp`. Main sidebar font 40,
  diagram font 36, secondary kernel caption 28. Native popup positions and
  scrollbars stay screen-wide when the Mode row moves.
- Width filters start at 2850 / 3800 / 5700 pixels. Stable mode IDs survive
  filtering and Quality/FPS/RS sorting. Crop and output locks are independent;
  AUTO exists only for non-isotropic mode sampling. Lens presets remain
  independent of the output lock/free choice.
- MB/s: actual record matrix (including border/retained pixels) × bits × FPS
  / 8, decimal MB/s rounded to an integer. The row covers 23.98, 24, 25,
  29.97, 48, 50, 59.94, 100, 119.88, 239.76, 279.72. It is an uncompressed
  payload estimate, not storage measurement or a supported-FPS indicator.
  A separate callback updates only the estimate, not recording FPS or Apply.
- Generic optional RCD section 11 carries the two binning taps, two kernels
  and std/soft. Both virtual commit and SAVE use it. The consumer driver
  shims correct branch-C double reduction and apply the selected coefficients
  to transient driver arguments, leaving stock coefficient tables untouched.

## Offline evidence

Build commands from the project root, each in a fresh directory:

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --no-shell --out projects/res-lab/cards/20261010-controls-v23/plain
python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --out projects/res-lab/cards/20261010-controls-v23/debug
```

- [v22 focused suite](test-v22.log): **9 passed**. Real ARM filter, independent
  lock/policy, rate calculation, binning encoder/consumer, native driver shims,
  register/SP preservation, original-route pass-through, malformed-section
  rejection, automatic commit, SAVE, native page and return navigation.
  The binning test includes an isolated hook-bypass mutation that the assertion
  detects, and restores all declared consumer hooks at shutdown.
- [Rate depth extension](test-v22-rates-14bit.log): **1 passed**, four geometries
  (including a native 14-bit mode) × 11 rates, independently checked with
  integer arithmetic; viewing rates preserves the active consumer and generation.
- [Final v23 native UI](test-v23-native.log): **3 passed**. Native allocation,
  private references, SAVE action and return state machine checked on final UI.
- [Exact artifact proof](artifacts-v23.json): all source hashes and manifest
  hashes matched at build validation. Plain/debug product BINs are identical.
  The v23 producer executable bytes `[32:30824]` equal the v22 tested executable;
  only Mode popup/scrollbar placement differs. The complete consumer equals v18.
- Earlier failed logs are retained. Causes fixed: stale lens-preset expectations,
  unseeded private-pool fixture producing a false relocation collision, stale
  Unicorn translation cache after restoring the ROM selector, and an incorrectly
  ordered test section descriptor. Production guards were not weakened.

## Deployment and hardware

[v23 deployment](deployment-v23/deployment.json) backed up the installed files,
verified the v18 before-image, changed only `50RESLAB.BIN`, then read the entire
625,696-byte result back and compared it. Existing res-custom RCS1 settings and
Loader FSDS settings were preserved. AutoRun and Loader did not change.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| 50RESLAB.BIN | 625696 | `6970ceb926724ce1a83ee87c7e8f61f16248eeb0010eb154b26638526592f945` |
| 32RESCUS.BIN candidate, settings blank | 77120 | `ae82bcf8b8ab2b9f78319e24908805ca6020ac01a7def80d686c1735eada6556` |
| LOADER.BIN build, before persistent FSDS settings | 27668 | `07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f` |
| AutoRun.txt | 32768 | `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0` |

One reboot request returned USB IO as the device reset and was **not replayed**.
The exact owned daemon PID 4139 was released via QUIT; replacement PID 6423
started after the wait. ACCESS was traced to SIGMA interface 0's exact macOS
PTP claimant PID 4154, which was released once with the reviewed recovery
helper. Standby recovered. [Runtime headers](runtime-v23-boot.json) match both
expected product files. All live clients use the shared lease and no mutation
is blindly retried.

Actual camera checks:

- FILTER and OUTPUT render with large text; left separators stop at x358,
  right margin has no stray horizontal lines. Closed/open padlocks are visible.
- Mode focus shows both arrows; M123 → M124 changes the readout and applies.
- [11 native-key rate checks](rates-v23.json) pass. At M123 record matrix
  6048×3404/12-bit, displayed 279.72p is 8638 MB/s. Native FPS enum remains 3;
  consumer registry, generation and producer geometry stay identical.
- The 279.72 filter contains M9 and M12; it initially selected M9. A subsequent
  native Mode switch was explicitly verified as **M12 2016×672**, AUTO shown,
  output **992×662**, Crop locked. This is not a high-FPS recording test.
- SAVE produced `LAB001.RCD`, 48,064 bytes. Full readback decoded as M12,
  992×662, binning `(1,1,0,0,0)`. [Decoded evidence](LAB001-v23.json),
  [local file](LAB001-v23.RCD). Active consumer, rows and generation remained
  unchanged ([before](runtime-v23-before-save.json), [after](runtime-v23-after-save.json)).
  Only this newly created test file was removed from the card after verification;
  the five pre-existing RCDs and their sidecars remain.

Screenshots (1024×682, captured on the camera):

- [FILTER](../20261010-sidebar-v13/screenshots/1647-v23-filter-open.jpg)
- [OUTPUT and locks](../20261010-sidebar-v13/screenshots/1648-v23-output.jpg)
- [279.72p MB/s](../20261010-sidebar-v13/screenshots/1649-v23-rate-279.jpg)
- [Mode arrows](../20261010-sidebar-v13/screenshots/1650-v23-mode-focus.jpg)
- [M12 AUTO](../20261010-sidebar-v13/screenshots/1651-v23-m12-output.jpg)
- [SAVE](../20261010-sidebar-v13/screenshots/1652-v23-saved.jpg)

## Limits

No recording or SSD benchmark was performed in this UI revision. The user's
earlier confirmation of the v12 M12 first-second preview fix is preserved in
the recording-formula notes; this UI pass does not extend that acceptance.
The physical all-mode/kernel/recording matrix and approximately ten switch
power cycles remain incomplete. RAW14 remains calculation-only for the current
consumer. Existing 32 unique asset packs / 4 MiB per boot limits still apply.
Julien-style generation remains a future producer of the shared Virtual RCD API.
