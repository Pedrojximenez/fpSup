# OG3K UI candidate — recording freeze follow-up

Date: 2026-09-14 (Asia/Taipei)  
Camera: SIGMA fp, firmware `5.02.0.V91`

This directory is project-coupled experiment evidence.  General USB key
semantics belong in `research/`; candidate hashes, clip container numbers, UI
captures, and the A/B decision remain here.

## Incident and reinstall check

The user's first full-UI OG3K recording attempt created the outer CinemaDNG
container `CINEMA/A001_082` and then froze.  The user recovered the camera by
removing the battery.

Both card files were read back in full after recovery:

```text
AutoRun.card.txt  32772 bytes
  3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53
VSHL.card.BIN     32768 bytes
  583190c93bc56aa5b1429d9a61a22d72d5dd6715314c5d26005c7fd32f22ab06
```

The hashes equal the local UI candidate exactly, so rewriting the same files
would not change the installation.  After the battery-out boot, the three hook
words were the expected candidate branches and the payload began with the
expected instructions:

```text
0xC05E5B58  B904F14D
0xC05E6400  BCE6F14C
0xC05E84D8  BBD4F14A
0xC0732C84  BF004778 E92D41F0 E1A04000 E1A05001
```

The initially zeroed 72-byte state only meant no target UI records had yet been
parsed.  A controlled Quick Set draw changed it to pack ready, 24,411 stock NBU
records, 164 exact copies, and the expected 164-bit active Quick Set set.

## Controlled recording results

The first remote FHD control revealed that `MOVOFF` is key-up, not a dedicated
stop command.  Recording remained active until a second complete
`MOVON` → `MOVOFF` press; it then stopped normally without a freeze.  Its exact
duration was not extracted and it must not be treated as a timed one-second
case.

With the corrected control, every high-bandwidth take was capped at about one
second as requested for this SD card:

| Outer container | Mode | Start-to-stop pulse gap | Result |
|---|---|---:|---|
| `A001_083` | FHD | longer than intended | stopped, no freeze |
| `A001_084` | OG3K | 1.004 s | pass |
| `A001_085` | OG3K | 1.004 s | pass |
| `A001_086` | OG3K | 1.002 s | pass |
| `A001_087` | UHD | 1.005 s | pass |
| `A001_088` | UHD | 1.005 s | pass |
| `A001_089` | UHD | 1.005 s | pass |

Each controlled post-check returned `is_recording -> 0`; firmware and USB shell
continued to respond.  Only the CINEMA outer directory was listed.  No clip
directory was traversed and no content-integrity claim is made.

After all seven transitions, a fresh second-draw Quick Set measurement again
loaded:

```text
OG3K_FONT.xci  150,38,0,0
OG3K_QS.xci     86,49,0,0
```

The final authorized `0xC0732700..0xC0732747` state read was:

```text
C68FF318 00000001 00000000 000086E9 000000A4 C1EAA1E5
FFFFFFFE FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF 0000001F
00000000 00000000 00000000 00000000 00000000 00000000
```

That decodes to the same resource context, pack ready, native result 0, 34,537
stock records, 164 exact copies, and the unchanged active bitmap.  Normal short
record transitions neither destroyed the private pack nor produced a visible
context-reload loop.

## UI clarification

The user initially reported seeing only two Quick Set choices, then confirmed
it was a misread.  The focus had been on `FORMAT`, whose two stock choices are
expected.  After moving one tile right to `RES.`, the same-frame GUI log loaded
all three resolution assets:

```text
set_resolution_1.xci
set_resolution_2.xci
OG3K_SET.xci
```

`QSREC2.XCI`/PNG and `QSRES5.XCI`/PNG are retained as capture traces.  The latter
decoded black because the wrong composition layer/timing was captured, so it is
not acceptance evidence; the earlier successful `camera_postboot/OG3KQS4.png`
and the three-name loader log remain the valid evidence.

## Decision

The immediate recording freeze is not reproducible on the installed full-UI
candidate: FHD 1/1, OG3K 3/3, and UHD 3/3 completed.  This is evidence against
an unconditional UI/REC startup bug, not proof of sustained stability.  The SD
card is too slow for a long UHD/OG3K run, and the original `A001_082` freeze
remains unexplained.

An exact core-only control is preserved at `../../ui_recording_ab/core_only/`.
It keeps the identical AutoRun, USB worker, and all 590 current OpenGate words,
while omitting only UI code/state/NBR and the three UI hooks.  It was not
installed because A no longer reproduced the failure.  Use it for a strict
ABBA run if the fault returns or when faster media is available.  The camera is
left on the full-UI candidate with `SetMovRecSize = 4`; nothing was promoted to
`fpSup`.
