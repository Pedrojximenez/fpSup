# Sensor Lab RAW14 full-height rate audit (2026-10-04)

Sensor Lab's RAW14 scope is all eight stock RAW14 sensor modes and all
physically solvable axis/rate combinations.  The public `sigma-fp-supmod`
M100/23.976 implementation is evidence for a recording path, not a whitelist
for this project.

**Status update, 2026-10-04:** The "unreachable" and "UI not connected"
statements below describe the earlier source and card.  The current 18p bridge
was verified offline.  It exposes a private Sensor rate choice for M0/M141,
uses legal native 23.976p as its carrier, and maps the picker to recipe rate
index 11.  Its default artifact vetoes 18p REC; a separate diagnostic artifact allows an
exactly matched manual short clip.  The diagnostic safety artifact has now
been written to fpSup2; independent readback hashes match its BIN
(`8d00088d1db0c4246279c140ca0865579b18930848accaf745fcd7151174884d`)
and MANIFEST
(`297b717f36572165f859a090be3ed71179ad5233aad186d8ab5338fb6b01a5b6`).
The camera has not rebooted or recorded with it; the default veto artifact
remains offline.  The diagnostic path has no automatic duration limit; its iXML
speed still says 23.976p, and audio/timecode behavior needs real clips.  See the
[18p bridge verification report](../../res-lab/validation/20261004-raw14/18p-bridge-report.md).

## Firmware and current-card result

The Ver.5.02 IMX410 metadata has eight modes with `+0x3C == 1` (RAW14).  The
recipe requires `72,000,000 / fps >= (raster_h + vblank) * hmax`, in addition to
its timing table and geometry checks.  The current rate table starts at
`24000/1001` (23.976).  An independent metadata scan gives:

| Mode | Raw raster | hmax | vblank | Maximum with blanking | Current fitting rates |
| --- | --- | ---: | ---: | ---: | --- |
| M0 | 6064 × 4042 | 911 | 30 | 19.409p | none |
| M141 | 6064 × 4042 | 911 | 50 | 19.314p | none |
| M95 | 5712 × 3216 | 911 | 14 | 24.469p | 23.976, 24 |
| M129/M144 | 3968 × 2640 | 911 | 50 | 29.381p | 23.976, 24, 25 |
| M6/M100/M122 | 4176 × 2174 | 911 | 50 | 35.537p | 23.976, 24, 25, 29.97 |

At **18.000p**, the timing budget is exactly 4,000,000 cycles.  With hmax
911, the existing solver produces `(vmax, tail) = (4391, 710)` and satisfies
the blanking requirement for both M0 and M141.  At 19p it also fits both, but
18p is near M141's factory timing and has more blanking headroom.  The
uncompressed packed-14 payload at 6064 × 4042 × 18p is about **772 MB/s**;
the recording buffer and medium can therefore end a take quickly even if the
sensor configuration itself works.  This is an observation target, not a
software reason to hide the mode.

| Candidate | Cycles/frame | hmax 911 `(vmax, tail)` | M0/M141 blanking check |
| --- | ---: | --- | --- |
| 15.000p | 4,800,000 | `(5269, 852)` | both pass |
| 18.000p | 4,000,000 | `(4391, 710)` | both pass |
| 19.000p | 3,789,474 (rounded) | `(4160, 625)` | both pass |

## Why the hidden 15p value cannot be used directly

The native rank table contains `(internal 0, export 0, rank 1500)` and the
private native input-pair table deliberately leaves the hidden 15p value at
row 10 (`imx410_rate_native.py`).  But the original picker suffix builder
`XC_LiveViewConfiguratorW71c1__v2` at `0xC043CAF0` has no case for export 0;
its default calls the native assertion and loops forever
(`out/decomp/full/blk_c04.c`, around line 40893).  The SD-card setter probe
accepted only internal values `{1,2,3,4,5,12,13}`
(`HSW_240FPS_MODE12.md`, section 32).  Also, a newly persisted native enum
could be read during boot before the card loader runs.  A direct internal-0
menu row is therefore not a safe route to full-height RAW14.

## Contained private-rate design

Add an **18p** selection to a Sensor Lab owned, volatile control.  Keep a
known native rate, such as internal 1 / export 1 (23.976), as the app's carrier
and record the 18p choice only in Sensor Lab RAM, using the existing RATE240
pattern.  The picker must override its `CUST23_98` rate index only while that
private choice is active, and clear the choice when leaving CUSTOM.  The REC
preflight must require a freshly valid 18p RAW14 recipe before dispatch.  The
CinemaDNG `FrameRate` hook and nominal shutter-rate hook must both report 18p.
The UI must show the actual 18p selection and data-rate estimate; borrowing a
23.976 label would conceal an important mismatch.

The 12th logical rate fits most existing fixed table slots without changing
their base addresses: `RATETAB` grows from 132 to 144 bytes and ends exactly
at `TMGTAB` (`0xC0730490`); `RATNUM` grows from 88 to 96 bytes and ends
exactly at `RATE_CODE` (`0xC0730B00`).  `TMGTAB` grows from 264 to 288 bytes
and would overlap the current `CTMPL` at `0xC07305A0`; move `CTMPL` to
`0xC07305C0` (88 bytes, ending `0xC0730618`, before `ASPTAB` at
`0xC0730620`) after rechecking the relocated USER pack.  The native-key
`RATESTR` table must retain its eleven existing entries: appending a 12th
would collide with `INPUT_PAIR` at `0xC07301C0`, and the private 18p choice
has no native key suffix.  Consequently the picker needs separate native-key
count 11 and recipe-rate count 12.  The recipe's hmax row stride, host model,
MODE scan, filter, output text, and rate-list masks all need the twelfth index.

The smallest staged implementation is:

1. Add rate index 11 = 18p to the host model and recipe tables, after moving
   `CTMPL` as above.  Set the recipe's `N_RATE` to 12.  Keep
   `imx410_fmt.S`'s native suffix scan at 11 and override its chosen rate from
   a dedicated RAM flag only when the private 18p control is active.  Prove
   M0/M141 at 15/18/19p with `test_imx410_recipe.py`'s ARM harness, and
   reject invalid combinations in the REC guard.
2. Add a Sensor Lab owned 18p recording control and its volatile flag in the
   private page; `SL_RATE` and its native setting remain the current ten-row
   list.  The existing `MV_FrameRate` callbacks at `0xC057A6F8` and
   `0xC05821B8` can clear the flag on ordinary selection.  The picker site is
   `0xC043CCF8`; the native suffix builder is `0xC043CAF0`.  The DNG tag
   hook is `0xC00C9BD0`, shutter nominal-rate callers are the four
   `FPS_HOOKS` in `imx410_plan.py`, and the planned REC preflight site is
   `0xC03A33C8`.  These are exact sites for offline hook/ABI tests, not a
   proposal to write a native setting value of zero.
3. Trace and validate the recorder's clock, timecode and audio consumers of
   `FUN_c005c0f0` (getter uses internal 1 on the 18p carrier), then test
   successful start/stop with a finite clip.  Only after this is measured
   should the control be offered on a card for camera testing.

This is **not ready to publish as a supported recording rate**.  The stock
recorder, timecode, and audio path still sees the 23.976 carrier.  Existing
`imx410_rate.S` only fixes the DNG tag; its own comment and
`IMX410_FULL_DESIGN.md` section 5.3 identify those other consumers as
unverified.  A producer slower than its container may also expose a different
buffer-completion path from the previously tested fast-sensor slow-motion
case.  The MODE page now offers an 18p sensor choice with a legal native
23.976 carrier, but the default card visibly labels it **18p REC off** and
vetoes recording.  The separately labeled **18p test** card may pass an exact
REC preflight for a manually controlled short clip; its timing and audio still
require actual clip measurement before being called supported.

### Native-rate consumer trace (2026-10-04, static)

The private 18p sensor choice now reaches the picker through a volatile marker.
A carrier of native internal 1 is still interpreted as 23.976 in several
independent recording paths:

| Path | Verified firmware/source behavior | Required before a selectable 18p take |
| --- | --- | --- |
| Picker `C043CCF8` | `imx410_fmt.S` maps `CUST23_98` to rate 11 only while the private RAM marker is 1. | Verify a full camera selection and readout. |
| REC preflight `C03A33C8` | `imx410_rec_guard.S` checks the native carrier, bit depth, published picker tuple and timing; the default build refuses rate 11, while an explicit diagnostic build may pass it. | Verify first-frame, recurring completion and clean stop on a short clip. |
| DNG FrameRate `C00C9BD0` | `imx410_rate.S` now includes rate index 11 = `18000/1000`. | Verify the tag on actual recorded DNG frames. |
| Shutter nominal rate | Four `FPS_HOOKS` call `imx410_fps.S` using recipe nominal FPS. | Verify 18p only after donor timing is applied and REC can start/stop. |
| Timecode | `FUN_c037ff70` and `FUN_c03a7be0` read native movie rate from the config copy at `FUN_c0021c40()+0x14`; `FUN_c00d0010` classifies native enum 1 as 23.976. | Trace and adapt timecode generation; check each DNG timestamp and BCD tag across a finite clip. |
| Audio | `FUN_c01fa408` copies native rate into the audio singleton `C31F7D84+0x20`; the DSP/ASIC start path uses the singleton. | Establish synchronization semantics and check sample count versus wall duration and DNG frames. |
| Recorder frame events | `XC_StillCreateImgObs__v1` (`C037F778`) dispatches image event 0 through `C0379E08` and event 1 through `C037A590`; the buffer dispatch itself uses completed descriptor counts rather than native FPS. The upstream image-event cadence has not been established by this trace. | Instrument first-frame, recurring completion and clean stop; expect approximately 55.56 ms between frames and 18 × elapsed seconds frames. |
| Recorder count/time display | `FUN_c03a48e8` derives a 7200-second frame cap from native rate; `FUN_c038c7b8` divides completed frames by native rate for displayed duration. | Adapt cap and display time to private 18p; at 18 real frames with a 23.976 carrier, the stock display advances only about 0.751 seconds. |

The timecode evidence is from `out/decomp/full/blk_c03.c` around 86360 and
115460–115854, and `blk_c00.c` around 156299.  The audio evidence is from
`blk_c01.c` around 155942 and 160338 and `blk_c02.c` around line 393.  The
tag callback invokes the rate-dependent timecode function, but this static
trace does not establish a per-frame callback cadence or audio sync behavior.
R120's M100/23.976 path does not exercise the private 18p route.
The frame event/count evidence is in `blk_c03.c` around `C037F778`,
`C0379E08`, `C037A590`, `C0378A50`, `C03A48E8`, `C038C7B8`, and
`C03A4B00`.  It does not prove the upstream event cadence or finite-clip
stop behavior at 18p.

The REC guard rejects a null or unaligned imager descriptor, timing-table base,
or published ENTRY timing pointer before dereferencing it.  It also refuses a
nonzero private 18p marker if CUSTOM/CinemaDNG is no longer active.  These
checks do **not** prove that every nonzero, aligned pointer names valid mapped
memory; offline emulation cannot establish that for arbitrary camera runtime
states.  A real camera trial remains necessary.

Sources in this repository: `imx410_full.py` (`RATES`, `Registry`),
`imx410_block.py` (timing formula), `og3krecipe.S`, `imx410_fmt.S`,
`imx410_rate.S`, `imx410_fps.S`, `imx410_rate_native.py`,
`sl_menu/sl_modes.c`, `imx410_plan.py`, `out/decomp/full/blk_c04.c`, and
`projects/open-gate/notes/HSW_240FPS_MODE12.md`.
