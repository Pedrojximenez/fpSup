# RAW14 18p recorder, timecode and audio audit (fp Ver.5.02)

2026-10-04. Read-only trace of `out/decomp/full/blk_c00.c`, `blk_c01.c`,
`blk_c02.c`, and `blk_c03.c`; no camera operation, SD write, or payload change.
Addresses below are stock virtual addresses. Decompiler output establishes the
listed data flow, but it does not prove the camera's actual event cadence or DSP
clock. A private 18p recipe currently has to retain the legal native 23.976
movie-rate enum `1`; the Sensor Lab engine's rate index `11` represents 18p.

## Which native rate consumers can block a short take?

| Consumer | Confirmed stock behavior | Consequence with native enum 1 and actual 18p |
| --- | --- | --- |
| REC prepare `C03A33C8 → C03A2438` | The Sensor Lab guard checks the published picker tuple before the native prepare side effects. Current code maps native enum 1 to index 0 unless its private 18p marker is valid. | This **does block** 18p with the current guard until an exact-card 18p branch is added and tested. It is a mod guard, not a native recorder limit. |
| Clip capacity at `C0378AE8` in `FUN_c0378a50` | Calls `FUN_c03a48e8(ctx, descriptor, 1)`, saves result to recorder `+0x9C` (frame cap), sets `+0x98` (completed frame count) to zero. `vbuf C0379E08` compares `+0x98 >= +0x9C`; if true it follows its stop/error path. Accepted frame batches add their descriptor count (`+0x1C0`) or one to `+0x98`. | `FUN_c03a48e8` estimates bytes per frame with `FUN_c03a4b00`; the latter divides an audio-per-second term by **native** FPS. The clip-mode cap also multiplies its 7200-second limit by native FPS. Thus the cap and free-space estimate may be optimistic for 18p. This is not a demonstrated immediate-start gate when the card has ample free space and the trial is short, but it is unsafe near card exhaustion or for long takes. |
| Metadata creation after cap | `FUN_c0378a50` passes its cap to `FUN_c03a4d00`, which creates/writes `metadata.xmp` and returns success/failure. This path can fail on media/file errors. | A different frame-cap value is passed into metadata, but the trace does not show that merely using native 23.976 causes a file failure. |
| Completed duration display `C038C7B8` | Reads completed count at recorder `+0x98`, divides by `FUN_c02db1d8(native movie rate)`, and rounds. `MovRecFuncStateCinemaDng__v30` uses it for the displayed duration. | At 18 frames the UI would advance about 0.751 s rather than 1.000 s. This is a display defect; no observed control path from it to frame writer start/stop. |
| Manual stop / completion | `FUN_c0377620` sets the stop flag `+0x78`, drains the recorder, then calls `FUN_c0377118`. `XC_StillCreateImgObs__v1 C037F778` dispatches image event 0 to `vbuf C0379E08` and event 1 to `FUN_c037a590` for completed buffers. | No native-FPS division appears in this event dispatcher or the shown manual-stop path. The upstream cadence, buffer completion, tail drain and correct file close at 18p remain unmeasured. |

The stock recorder therefore gives a plausible **bounded diagnostic clip** path
after picker/guard integration: keep native enum 1, start with substantial free
space, record only a few seconds, stop manually, and inspect every written file.
That does **not** prove a production-ready 18p option. An 18p producer may have
different buffer timing; RAW14 6064×4042 at 18p also has a much higher data rate
than the existing 12-bit card samples. A real clip must establish that image
events recur at about 55.56 ms, completed frame counts advance, and the final
buffer drains on stop.

## Timecode and DNG tags

`FUN_c037ff70 C037FF70` reads the native movie rate at
`FUN_c0021c40(FUN_c0021c00())+0x14`, converts internal frame/timecode state
through `FUN_c00d00f0`, then returns the timecode structure. Both the clip
setup in `FUN_c0378a50` and the per-frame
`XC_RecMgrTagCinema__v1 C03A8490` invoke it. `FUN_c03a7be0 C03A7BE0`
reads the same native rate and packs four BCD timecode bytes through
`FUN_c00d0248`, placing them in the DNG tag object. The stock rate classifier
`FUN_c00d0010 C00D0010` maps native enum 1 to its 23.976 timecode family;
there is no native 18p enum in its switch. The per-frame tag function calls
`FUN_c037ff70` and `FUN_c03a7be0` before emitting its tag set, so a private
18p clip would carry incorrect timecode unless adapted. This is metadata
corruption, but no traced branch here vetoes DNG image writing.

`imx410_rate.S` is a separate guarded override of the CinemaDNG `FrameRate`
rational at `C00C9BD0`; its present table bound includes engine index 11 and
can return `18000/1000` in isolated ARM tests. This repairs only the DNG
`FrameRate` tag. It does not repair BCD timecode, frame timestamps, WAV sync,
or the recorder clock. The `FUN_c03a7f30` date string is built from the tag
object's timestamp fields, but this trace does not establish how those fields
are advanced for each frame. Do not infer correct per-frame timestamps from a
correct `FrameRate` rational.

For production, derive 18p timecode from the actual completed-frame sequence
and any preserved start time, then add a **private-mode-only** wrapper at the
timecode/tag path. Hooking the global native enum classifier to invent an 18p
value would affect unrelated stock modes and is not a narrow solution. The
candidate site must be tested with exact ARM call semantics and first/middle/
last DNG tags before card release. During a diagnostic clip, incorrect timecode
may be measured and corrected afterward; it must not be reported as valid 18p
metadata.

## Audio and WAV duration

`FUN_c01fa408 C01FA408` copies native movie rate `config+0x14` to the audio
singleton `C31F7D84+0x20`. `DspAudioDevice__v11 C01FF8F0` calls it during
the audio DSP/ASIC start sequence. A deeper [audio singleton and WAV header
trace](RAW14_18P_AUDIO_SINGLETON_TRACE.md) resolves the consumer: the
singleton's `+0x10` pointer is passed by the DSP/ASIC audio-device methods to
`WaveFileFormat__v2 C0685788`, where `iXML C0685B78` reads the copied enum
and writes `<MASTER_SPEED>` and `<CURRENT_SPEED>`. Native enum 1 produces
`24000/1001`, so those two WAV metadata values would be wrong for actual
18p images. Its separate `<TIMECODE_RATE>` remains on the carrier until the
timecode path is repaired. An isolated candidate changes only the two image
speed lookups, with stock behavior for non-private states; it is not in r86.

The WAV PCM format follows a different source: the stock format object holds
two channels, 16 bits and 48,000 Hz, and `WaveFileFormat__v2` derives 192,000
bytes/second from that object. Executing the complete stock ARM formatter
with and without the isolated iXML candidate leaves PCM fields, WAV data
length, and BWF `TimeReference` unchanged. `bext C06859E8` computes its
TimeReference from the carrier-based start-frame count and the same carrier
timecode rate. Changing only its divisor to 18 would break this pair. The
traced code does **not** establish the physical DSP sample clock, generated
sample count or A/V sync under a private 18p sensor cadence; these still need
a finite live clip.

The WAV file path is visibly sample-offset based:
`AudioFileRecordingObserver__v1 C01FBB90` queues start/stop-like events, and
`AudioFileWriter__v1 C01FBD40` writes sample blocks using their source offsets
and byte lengths, seeking to recover gaps. `FUN_c0378a50` starts the audio
recorder with `FUN_c01fb640` after opening the image recording context; other
recorder states call `FUN_c01fb918` on stop. Whether their event timestamps
track wall time or native frame rate is still open. The nine existing r83
12-bit card clips have 48 kHz WAV durations 0.042–0.220 s longer than
`DNG_count / DNG_FrameRate`, which gives an empirical startup/tail baseline,
not a proof of the 18p path.

For a bounded diagnostic 18p clip, keep audio enabled and measure its actual
sample count and duration against wall time and the DNG frame sequence. Two
visible/audible sync events about ten seconds apart avoid confusing fixed
startup/tail with drift: 48 kHz audio at 18p implies about 2666.67 samples
per image frame, while a 23.976-based contraction implies 2002. Do not alter
the audio hardware path solely because the WAV iXML field copies enum 1. If
skew is observed, trace the first rate-dependent audio producer and adapt
only the private 18p session; test start, steady state, stop and WAV header
finalization.

## Smallest controlled path forward

1. Wire the volatile private 18p selection to the picker and REC guard only
   when RAW14 mode M0/M141 has a freshly published rate-index-11 recipe. Keep
   native enum 1; reject stale tuple, bit mismatch or private-marker mismatch
   before native PREPARE. Verify the exact built card through relocated USER
   code and mutation cases. The current 18p engine table alone is unreachable.
2. For the first short recording trial, use the existing `C00C9BD0` rational
   hook for `18000/1000`, keep the original recorder cap with a conservative
   free-space margin, and instrument first frame, recurring completion, manual
   stop, last completion, and audio start/stop. If the card is nearly full,
   refuse the trial rather than trusting the 23.976-based capacity estimate.
3. Audit *every* DNG for 14-bit uncompressed main IFD, expected dimensions,
   packed strip bounds, contiguous sequence, `FrameRate=18000/1000`, and
   timecode/timestamp progression; compare WAV sample duration to measured
   wall time and `DNG_count/18`. The read-only `raw14_dng_audit.py` covers
   structure but does not by itself validate clip sync or BCD timecode.
4. Before exposing 18p as a supported selectable rate, normalize the clip cap
   at the specific start call `C0378AE8` (or its returned `ctx+0x9C`) using
   actual 18p and audio bytes per actual frame; adapt the duration display and
   timecode in private mode. Add an audio change only if the bounded clip
   demonstrates skew or a confirmed rate-dependent audio consumer. Repeat a
   finite start/stop clip after these changes.

Evidence: [stock recorder decompile](../../../../out/decomp/full/blk_c03.c),
[timecode helpers](../../../../out/decomp/full/blk_c00.c),
[stock audio decompile](../../../../out/decomp/full/blk_c01.c),
[audio ASIC dispatch](../../../../out/decomp/full/blk_c02.c),
[private low-rate design](../../../open-gate/notes/IMX410_RAW14_LOWRATE.md),
[r83 card read](card-read-20261004.json).
