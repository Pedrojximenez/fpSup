# OG3K shutter-angle exposure fix — 2026-09-15

## Status

The previous single-callsite candidate **fails** the verified idle-live-view
hardware test. The earlier apparent FHD/OG3K pass is withdrawn: the camera had
not actually switched to FHD or UHD in that sequence. The first
resolution-confirmed pair reproduces the defect at about `-1.38 EV` in OG3K.

Source tracing found four local angle-getter callsites, including a resolution
reconfiguration path that can overwrite the primary result. A separate VSHL
stage-2 defect omitted full I-cache invalidation after placing patched code.
The revised four-callsite, D-cache + I-cache candidate is pending a battery-out
cold-boot hardware test; offline verification must pass before it is installed.
Nothing from either candidate has been promoted into `fpSup`.

Warm restart and hot reinstall are not tested or supported; a battery-out cold
boot is the only accepted starting state.

The camera-freeze message immediately preceding this work was explicitly
clarified by the user as unrelated and misdirected. It is excluded from all
OpenGate, USB, media-throughput, and frame-rate conclusions here.

## Root cause

OG3K 23.976 through 59.94 reuse sensor mode 98 with timing copied from the
corresponding movie mode. Mode 98 nevertheless retains its stock integer
nominal-FPS metadata value 78. The firmware's shutter-angle branch reads that
field and computes nominal-fps × 3600 / angle, so 29.97/180° becomes about
1/156 rather than 1/60. The predicted -1.380 EV matches the reported
-1.3 to -2 EV range; 23.976/24 predicts about -1.70 EV.

The original patch assumed the primary exposure-property call at `0xC02092CC`
was the only relevant reader. Static tracing instead finds exactly four local
chains of `FUN_c0437078(2, 0, ..., 3)` followed by
`FUN_c032c750(mode)`:

| Callsite | Stock word | Role |
| --- | --- | --- |
| `0xC02092CC` | `0xEB048D1F` | primary exposure property |
| `0xC0218AEC` | `0xEB044F17` | angle metadata path A |
| `0xC0219260` | `0xEB044D3A` | angle metadata path B |
| `0xC03AA568` | `0xEBFE0878` | resolution reconfiguration sync |

All four stock branches resolve to `0xC032C750`. The last path is decisive:
`FUN_c03aa470` reads the stock nominal value, performs the angle conversion at
`0xC03AA5A0`, then writes the central settings fields at `+0x158/+0x15C` and
`+0x170/+0x174`. It can therefore restore the mode-98 result after the primary
callsite has produced a corrected value. The measured OG3K shutter of
`6411 us` is `1/156 s`, exactly the signature expected from `78 fps / 180°`.

Independently, `fp_usb_shell/asm/stage2.S` previously called only
`0xC000E91C` after copying all VSHL sections. Disassembly identifies that
routine as D-cache set/way clean/invalidate; full I-cache invalidation is
`0xC000EABC`. AutoRun runs after early live-view paths may already have executed,
so a correct branch word in RAM does not prove that the CPU stopped executing
the cached stock instruction. Both faults must be fixed and tested together.

Shared call/data-flow details are in
`../../../research/imx410/SHUTTER_ANGLE_NOMINAL_FPS.md`.

## Fix

- `build/fmttable.S` is now restricted to the CinemaDNG picker table and updates
  the two timing words inside one interrupt-masked transaction.
- `build/og3kfps.S` is reached from four local `BL` replacements at
  `0xC02092CC`, `0xC0218AEC`, `0xC0219260`, and `0xC03AA568`.
- It calls the stock getter first, then overrides only for mode 98, `FLAG == 1`,
  and one of the seven exact, whitelisted mode-98 timing tuples. Mixed or
  unknown tuples retain the stock result.
- `build/og3ksel.S` clears `FLAG` before leaving OG3K, restores mode 98's stock
  timing tuple, and publishes `FLAG == 1` only after the selected groups are
  ready.
- The wrapper is read-only, keeps 8-byte stack alignment, and preserves every
  callee-saved register it uses.
- The shared mode-98 metadata at `0xC0B59EC8` and the photo-shared p83 field at
  `0xC0BD47AC` remain untouched.
- The shutter-speed branch never executes the patched callsites.
- VSHL stage 2 performs D-cache clean/invalidate and then full I-cache
  invalidation after placing all sections and before transferring control.

The plan grew from 590 to 710 words. The native UI code and NBR pack remain
byte-identical to v0.2.0test.

## USB development loader boundary

`build/og3k_load.py` is now deliberately a first-install loader, not a hot
upgrader. It takes a complete read-only snapshot and accepts only a battery-out
stock baseline or the exact current resident. Old/partial/foreign hooks, stale
cave words, old shared-field edits, an occupied shell handler, or any read
failure cause zero writes and a cold-boot request.

For a clean first install it writes and verifies body data before any hook,
performs D-cache clean/invalidate followed by full I-cache invalidation, arms
the picker last, repeats the cache barrier, then verifies every hook. Any body,
hook, or cache fault keeps or rolls all executable entry points back to stock;
if rollback cannot be proved, the only recovery claim is a battery pull.
`build/test_og3k_load.py` fault-injects body writes, every hook commit, both
cache phases, foreign/inactive/legacy entry points, partial installs, and the
idempotent exact-install case. These loader hardenings are preventive and are
not evidence about the unrelated freeze the user corrected above.

## Existing exposure evidence

### Verified shutter-angle failure

The initial three screenshots in
`build/angle_fps_camera_20260915/` are invalid: despite their filenames, no
FHD or UHD transition was successfully completed. They cannot support an
exposure comparison.

The replacement idle-live-view pair in
`build/angle_fps_camera_20260915_verified_modes/` was confirmed using the
second QS draw and native resolution assets:

```text
FHD, enum 2:  font_menu_MB_resolution_2.xci / qs_resolution_2_S.xci
              SS__0485.JPG, 16663 us, gain 936, +2.3 EV
OG3K, enum 4: OG3K_FONT.xci / OG3K_QS.xci
              SS__0486.JPG, 6411 us, gain 936, +1.0 EV
```

No recording was started. With ISO800, 29.97 fps, 180°, and gain 936 held
constant, `log2(6411 / 16663) = -1.378 EV`. This is a valid reproduction of
the bug and a hardware failure of the single-callsite candidate.

### Existing shutter-speed control

The valid ISO800 shutter-speed pair A001_083 (FHD) / A001_084 (OG3K), compared
at frames 1, 7, and 13 after black subtraction, CFA-preserving common-FOV
mapping, and clipping/noise rejection, measures OG3K over FHD at:

```text
+0.01593 EV
+0.01306 EV
+0.01282 EV
correlation about 0.99725
```

This rules out the same 1.3-2 EV mechanism in the tested speed-mode condition.
The later A001_095/A001_097 files named as OG probes are actually 1936×1090
FHD and are excluded.

The old HCG/LCG defect is also a different signature: at ISO800 it made OG3K
about +2.675 EV brighter with BaselineExposure +0.322. The valid current pair
has matching ISO800 RAW levels and BaselineExposure +3, so the gain-state fix
is active. ISO100 cannot distinguish state 3 from state 7 because both remain
LCG.

## Offline acceptance

`build/verify_og3k_angle_fps.py` verifies:

- all four stock callsite targets and candidate branch destinations;
- exact per-format timing tuples, all synthetic cross-pair timing-tuple
  combinations, and the fail-open selection matrix; this does not validate a
  live CINE/STILL transition;
- no static plan writes to shared mode/photo/timing fields;
- code-cave zero baseline and payload size;
- fixed 710-word core, section order, and byte-for-byte presence in the
  generated VSHL.

The prior single-callsite debug and release artifacts are superseded and must
not be installed as the revised candidate. New package hashes should be
recorded only after the four-callsite plan and stage-2 cache sequence pass the
offline verifier. The rebuilt packages have not yet completed cold-boot
hardware acceptance.

The resolution setter restores mode 98 timing whenever it leaves OG3K, but a
CINE/STILL mode transition while OG3K remains selected has not yet been proven
to re-enter that setter. Until that transition has its own hardware test,
select FHD or UHD before leaving CINE. This is a pending boundary, not evidence
about the unrelated freeze excluded above.

## Pending cold-boot matrix

Use a static scene and identical aperture/ISO/WB. Keep every UHD/OG3K take to
about one second on the current SD card.

1. ISO800, 29.97, 180°: FHD then true OG3K; verify requested/actual shutter is
   about 16666 µs and compare RAW medians.
2. Repeat once to catch selection-order/timing-transition regressions.
3. Shutter-speed 1/60 FHD/OG3K control; it should remain unchanged.
4. ISO100 angle pair as an LCG control, not as proof of gain-hook correctness.
5. Optional 24/180° high-signal case and 100/180° zero-correction control.
6. Only after the exposure cases pass, test CINE → STILL → CINE both after
   first selecting FHD/UHD and, separately, with OG3K selected. Verify the
   stock mode-98 timing/flag state before treating warm or mode transitions as
   supported.

Do not query the camera while recording. Start and stop are separate complete
`MOVON` → short delay → `MOVOFF` pulses; never retry a timed-out `MOVON`
blindly.
