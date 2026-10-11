# Internal compressed 3K CinemaDNG target

Updated 2026-09-09 following the user's revised ultimate goal. Internal means
the camera's SD card. Target lossless compression first, preserving the current
12-bit RAW sample values; true 24 fps first, then 25/30 if measured capacity permits.
Lossless encoding alone does not establish that every sensor photosite contributes.

## Preserve the working baseline

Current camera-tested package: prototype/fp3k-0.3.5-fullheight. Resident SHA256
8cf489ef8ad5e4c8723adac4dd421f6943a5d4f6338c030f70148764901b243e.
Settings, QS, HUD and full-height LCD have passed the user's latest tests.
Keep this resident as the rollback reference. No compression or SD-routing change
has been implemented or installed by this investigation.

## First milestone: harden the current SSD version

1. Trace physical CINE/STILL changes, preset recall and media-loss handling to
   the acquisition lifecycle. Existing settings wrappers cover resolution,
   format, quality, rate, crop and media setters, but do not prove coverage of
   these other paths. Restore stock geometry before incompatible acquisition
   begins; synchronize private mode and UI. Do not change tables during recording.
2. Identify native stop reason, writer completion/error and queue accounting
   paths. Add bounded event diagnostics only after ownership and hook timing
   are understood. Distinguish a manual stop from backpressure, media loss and
   native errors. Earlier 3–7 second stops also occurred without AutoRun; cause
   remains unknown. A retry capture had ten video frames against ~2.875 seconds
   of audio, so elapsed time alone is an inadequate check.
3. Validate longer 3K and stock recordings, repeated start/stop and supported
   transitions. Check full frame sequences, audio duration, RAW validity and
   native errors. Use adequately charged power and document test conditions.
   Do not deliberately unplug media during writes for routine validation.
4. Verify image quality and sensor reduction with suitable matched RAW captures
   and further scaler/readout analysis. Current framing success is insufficient
   to claim every-photosite processing.

## Compression feasibility evidence

- Sigma documents losslessly compressed 12/14-bit still DNG and UHS-II SD support:
  https://www.sigma-global.com/en/cameras/fp/
- Our archived SDIM0165 RAW is 6064×4042, 14-bit lossless JPEG compressed;
  see fullheight-reference-comparison.md. This establishes a working still-file
  compression path, not continuous video performance.
- fpSup identifies a hardware lossless JPEG engine at 0x300D0000 and candidate
  wrappers C05A6890/C05A6920:
  https://github.com/ijigen/fpSup/blob/main/projects/raw-sup.md
  Treat clock, throughput, contention and standalone-call claims as research
  leads pending independent verification on firmware 5.02. Its throughput
  estimate is not a measurement, and this is not necessarily a one-number problem.

Current stored raster is 3032×2020, including margins outside the 3000×2000 crop.
At 12 packed bits this is 9,186,960 bytes/frame before container overhead:

| fps | Input Mpixel/s | Uncompressed MB/s | MB/s if exactly 2:1 |
| --- | ---: | ---: | ---: |
| 24 | 146.99136 | 220.48704 | 110.24352 |
| 25 | 153.11600 | 229.67400 | 114.83700 |
| 30 | 183.73920 | 275.60880 | 137.80440 |

Decimal MB; excludes audio, metadata and filesystem overhead. The 2:1 column
is an illustration, not an achieved or guaranteed ratio. Noisy/detailed frames
can compress poorly. Card label or host benchmark does not establish sustained
camera write performance; buffering must cover measured latency variation.

## Staged implementation after baseline hardening

1. Audit the native still encoder's input layout, bit depth, tiling, alignment,
   buffer ownership, cache operations, clocks, interrupts and cleanup. Trace
   the existing CinemaDNG writer separately. Do not call the known hanging
   still_raw_dump command at C343A624.2.
2. Build a bounded, isolated single-frame encode experiment. Decode on the host
   and compare every sample against the source. Determine required output
   capacity and handle incompressible input without overrunning buffers.
3. Benchmark repeated 3K encoding, then concurrent capture/preview. Measure
   throughput, latency distribution and memory traffic at several noise/detail
   levels. At 24 fps the pipeline must sustain one frame every 41.67 ms on average,
   with sufficient buffering for latency excursions; test beyond brief bursts.
4. Produce valid compressed DNG files with correct tile/strip tables, byte counts,
   compression tags, crop/CFA/black/white metadata and CinemaDNG timing. A tag-only
   change is invalid. Verify sample equality and intended editing-app support.
5. Integrate compressed recording to SSD first to isolate encoder/packaging
   defects. Then route compressed output through the native SD writer, measure
   queue occupancy and sustained write latency, and handle clean finalization,
   full media and encoder/write failures. Only then expose internal 3K selection.
6. Qualify 24 fps first; investigate 25/30 separately using actual capture timing
   and worst-case encode/write headroom. Keep the tested uncompressed SSD path.

No immediate camera action is needed for static lifecycle/encoder investigation.
Before SD qualification, obtain the exact card model/capacity and intended editing
application. Hardware benchmark and long-recording evidence will be needed later.
