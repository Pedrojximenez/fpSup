# RAW14 private 18p: audio singleton, WAV header and clock trace

2026-10-04. Read-only audit of the pinned fp Ver.5.02 image
`out/MAIN_c0000000.bin` (SHA-256
`92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4`)
and its `out/decomp/full` output. The isolated iXML candidate below was
assembled and run in Unicorn memory only. No camera operation or card change
was made by this audit.

## Answer to the clock question

The copy at `FUN_c01fa408 C01FA408` **does affect WAV metadata**. It has no
confirmed data-flow to the DSP sample clock, PCM sample count, or audio packet
cadence in the traced stock code. That distinction is stronger than the earlier
recorder/audio audit, which had stopped at the singleton write.

`FUN_c01fa408` writes the native movie-rate enum from settings `+0x14` to
audio singleton `C31F7D84+0x20`. `FUN_c01fa3f8` returns a pointer to that
singleton's `+0x10` field. Two audio device methods,
`DspAudioDevice__v3 C01FF120` and `AsicAudioDevice__v3 C0200760`, pass that
pointer to `FUN_c0200ec0()`'s virtual method `+0x10`. The stock virtual table
at `C2E3629C` resolves `+0x10` to **`WaveFileFormat__v2 C0685788`**, the
RIFF/WAV header formatter. The same table's `+0x0C` method returns `0x3AC`,
the formatter's header length. Thus these calls are WAV header construction,
not an audio hardware clock setup call.

Within `WaveFileFormat__v2`, `iXML C0685B78` reads its config `+0x10`, which
is singleton `+0x20`, twice. The results become `<MASTER_SPEED>` and
`<CURRENT_SPEED>`. Its separate config `+0x14` becomes `<TIMECODE_RATE>`.
`FUN_c0685b20 C0685B20` maps enum `1` to the ROM string `24000/1001`; the
table has no `18/1` entry. Therefore a private 18p image sequence carried as
native enum `1` would have **wrong WAV iXML image-speed labels**, even if the
PCM sample count and rate are correct. The `TIMECODE_RATE` field truthfully
describes the still-native timecode basis until that timecode path is changed.

The hardware start path does not establish an FPS-derived sample clock.
`DspAudioDevice__v11 C01FF8F0` configures the DSP/ASIC, calls
`FUN_c01fa408`, then invokes the device virtual method `+0x3C`; the DSP
table `C07E44A4` resolves that method to `DspAudioDevice__v13 C01FFE60`.
Its visible argument builder `FUN_c01fed68` uses audio/settings values and
does not read singleton `+0x20`. `DspAudioDevice__v1/v5` and the ASIC setup
use the independent audio format returned by `FUN_c0200f18` and conversions
such as `FUN_c0200290`, not the movie-rate enum. This does **not** prove that
the physical DSP clock is 48 kHz during a private 18p capture: firmware
decompilation cannot establish the clock programmed inside the DSP or the
relative timestamps of two live devices.

## PCM bytes and BWF time reference

The stock WAV formatter obtains PCM format from its `param_1` format object,
not the `param_4` singleton config. Its sample rate and bytes/second are
`param_1[2]` and `param_1[2] * blockAlign`; data length comes from total
file bytes minus the fixed header. `FUN_c0200ec0` initializes this object
with `DAT_c07e47a4 = 0x00020010` (two channels, 16 bits) and
`DAT_c07e47a8 = 0x0000BB80` (48,000 Hz). The actual stock ARM formatter,
executed with this object, wrote PCM type 1, two channels, 16 bits,
48,000 Hz, block alignment 4, and 192,000 bytes/s. `AudioFileWriter__v1
C01FBD40` writes incoming audio blocks by their byte offsets and lengths,
seeking when offsets have gaps; no movie-FPS division occurs in that writer.
The existing r83 card-read report independently found 48 kHz two-channel
16-bit WAV files, but those files are 12-bit / stock-rate clips.

`bext C06859E8` writes the BWF `TimeReference` at WAV header offset
`0x166`. Its helper `FUN_c06858e0 C06858E0` computes that value from the
singleton config's **separate** `+0x14` timecode-rate enum, `+0x1C` start
frame count, and the WAV format object's sample rate. For enum 1 it uses
24 nominal frames and a 1001/1000 factor. A concrete stock ARM run with
24 start frames and 48 kHz yielded 48,048 sample units. The recorder's start
frame count is itself produced by `FUN_c00d0180` using the same native movie
rate (`C0378A50` path), so this pair can remain internally consistent under
the 23.976 carrier. **Changing only the BWF divisor to 18 would be wrong**:
24 carrier-counted frames would then represent 1.333 seconds instead of
1.001 seconds. When private 18p timecode is implemented, the start-frame
source and BWF conversion must be designed together. No BWF patch is justified
from the present evidence.

The WAV PCM sample count comes from file data bytes / block alignment, and
the WAV playback duration is that count / 48,000. The copied native FPS
therefore does not directly shorten the WAV through the stock header code.
The sample *production* and A/V sync remain empirical questions.

## Isolated private 18p iXML candidate

Two stock `BL FUN_c0685b20` sites inside `iXML` are exact and narrow:

| Site | Source field | Candidate behavior |
| --- | --- | --- |
| `C0685BEC`, word `EBFFFFCB` | config `+0x14` → `TIMECODE_RATE` | Keep stock `24000/1001` until timecode is changed. |
| `C0685BF8`, word `EBFFFFC8` | config `+0x10` → `CURRENT_SPEED` | In validated private 18p, return `18/1`. |
| `C0685C04`, word `EBFFFFC5` | config `+0x10` → `MASTER_SPEED` | In validated private 18p, return `18/1`. |

The 200-byte source-only
[`wav18_speed_candidate.S`](wav18_speed_candidate.S) checks native carrier
enum 1, Sensor Lab enabled, private marker 1, RAW14, rate index 11, all nine
AXIS words against the published RECIPE snapshot, recipe validity, M0/M141,
and nominal rate 18. Other states tail-call stock `FUN_c0685b20`. It has
**not** been packed into USER or added to r86.

[`verify_wav18_audio_candidate.py`](verify_wav18_audio_candidate.py) executes
both iXML lookup sequence and the complete stock `WaveFileFormat__v2` in ARM
Unicorn against the pinned image. The report
[`wav18_audio_candidate_unicorn.json`](wav18_audio_candidate_unicorn.json)
shows native stock `24000/1001` in all three fields; validated private18
`18/1`, `18/1`, `24000/1001` for master/current/timecode; and stock behavior
for marker-off, RAW12, wrong rate, stale snapshot, and another native enum.
The candidate changed only the iXML region `0x274..0x38B` of the complete
WAV header. RIFF, `bext` including `TimeReference`, PCM `fmt `, 48 kHz and
data length bytes were identical to stock. This proves isolated ARM behavior
and header non-interference, not integrated card behavior or actual recording.

## Minimal finite-clip measurement once private 18p REC is integrated

1. Use M0 or M141 RAW14 18p with the exact published recipe and substantial
   free card space. Capture a short clip with audio on and manual stop; record
   the wall-clock time from REC press to stop. Confirm the first DNG arrives,
   frame numbers have no gaps, final DNG closes, and WAV has valid RIFF/data
   sizes. The current r86 card has no selectable private 18p path, so this
   is a future controlled trial.
2. Use two visible/audible claps or LED/beep edges near the start and end of
   a roughly 10-second take. Count video frames between edges and PCM samples
   between matching audio transients. True 18p with 48 kHz audio is about
   `48000/18 = 2666.67` samples per image frame; a 23.976-based contraction
   would be about `48000×1001/24000 = 2002` samples per frame. Over 180
   frames these hypotheses differ by about 119,640 samples (2.493 s), far
   larger than a fixed audio startup/tail offset.
3. Compare WAV `data` bytes / 4 / 48,000 with the measured wall duration and
   image-frame count / 18. A second take of a different finite length can
   separate fixed startup/tail from a duration-dependent slope. Inspect iXML
   speed fields, BWF `TimeReference`, DNG `FrameRate`, DNG timecode and any
   per-frame timestamp separately. The existing nine stock-rate WAVs show
   startup/tail differences, so a single short WAV-minus-video difference
   cannot by itself diagnose clock drift.

The first supported 18p release needs the separate picker/REC bridge, image
timecode/tag repair, recorder frame-cap/display policy, and this audio
measurement. The iXML candidate only solves one metadata mismatch.

Sources: [stock WAV and iXML decompile](../../../../out/decomp/full/blk_c06.c),
[audio singleton and writer](../../../../out/decomp/full/blk_c01.c),
[audio format dispatch](../../../../out/decomp/full/blk_c02.c),
[timecode conversion](../../../../out/decomp/full/blk_c00.c),
[recorder start](../../../../out/decomp/full/blk_c03.c),
[existing recorder/audio audit](RAW14_18P_RECORDER_AUDIO_AUDIT.md),
[r83 card read](card-read-20261004.json).
