# RES-Lab M12 virtual-rate audit — 2026-10-11

## Status

The original 240/280p early termination and preview mosaic remain unresolved.
Do not describe this candidate as a sustained-recording fix. The separate
same-carrier notification and DNG metadata defects have concrete code fixes;
hardware samples now confirm correct240/280 rationals. Sustained recording is
still failing; see the current live report.

The authorized private history starts at commit
`13890262b461a637195cbd211959b3c0947aa5bf` and records the notification change at
`4822a94d64c04c7d15f432c7659107bee4d14378`. These are project snapshots in the
private git:3000 repository, not commits in the user's dirty nested fpSup checkout.

## Propagation through the system

| Consumer | Verified behavior | Remaining limitation |
|---|---|---|
| Native menu / virtual rank | Rows 8/9/10 select native119.88 / virtual239.76 / virtual279.72. Internal carrier stays7. | An internal enum7 read alone does not identify actual cadence. |
| Native notification | Original C0074D78 only notifies an enum change. v10 adds the missing post-commit reload to both callbacks C057A6F8/C05821B8. | Reloading alone did not fix the picture or stop. |
| Sensor timing | M12 hmax/tail330; vmax1820/910/780 gives120000/1001,240000/1001,280000/1001. Exact picked timing words verified on camera. | This is register/entry readback, not an independent physical exposure-frequency measurement. |
| Engine publication | Canvas+30 reaches C31DF574; current values60/239.76024/279.72028.279.72 was also observed in REC. | Native >99 branch differs from normal120. Previous engine60/30 experiments failed and remain withdrawn. |
| Shutter | Four native call sites consume picked nominal240/280; virtual angle/range logic tested offline. | Not a proof of every physical shutter duration. |
| Preview/RAW geometry | M12 output992x662, RAW1008x672, bin1x1, no extra crop/desqueeze; same established r78 geometry. | HDMI280 shows a vertical scale mismatch. Preview motion is not continuous even in several120 controls. No geometry workaround accepted. |
| DNG FrameRate | Native C00C9BD0 exports the carrier rational120000/1001. v10 hardware samples confirmed this on240/280. v12 adjusts the native result only for a matching picked virtual entry; all six240/280 hardware samples have the correct rational. | Metadata correction is not a recording-cadence fix. |
| Recorder elapsed/capacity | C038C7B8, C03A0DF0, C03A48E8, C03A4B00 consume C02DB1D8 using the original carrier enum. | These remain uncorrected: elapsed time, remaining-time estimate,7200s frame cap and per-frame audio estimate can be wrong. The ~87k frame cap does not explain stopping at94. |
| WAV / timecode | Audio metadata still derives from the original rate domain; PCM uses a separate48kHz source. | No claim that virtual rates are fully propagated into iXML/timecode. Must audit paired timecode domains before changing them. |
| Lens control | Donor nominal META+40 belongs to a native control domain accepting selected rates including240, but not arbitrary280. | Globally replacing all120/240 fields with280 would enter native assertion paths. |

Conclusion: 240/280 are real sensor timing choices, but they were not completely
propagated through the whole system. A menu label is insufficient evidence.

## Early-stop evidence

See `../20261011-m12-rate-reload-live/RESULTS.md` and the individual trial JSONs.
Quiet recordings have no camera queries after MOV release until the4s target.

- 120p:388/388 and400/400 frames, normal button stop and positive green STBY.
- 240p and280p:94/94, `vbuf/94`, `raw1`, automatic stop. All requested frames
  eventually finishing does not mean recording lasted the requested duration.
- 280p8-bit also stops at94. Native quality enum is4, not2.
- The96-descriptor native pool stops when free_count reaches1. One bounded
  observation saw captured94, poolfree1, writer requests3/finished3; independent
  reads are not an atomic snapshot. Dense polling also disturbed120p, so those
  observations are diagnostic only.
- A temporary real FS batch limit64→16MiB changed later batch sizes, but240p
  still stopped at94. The original literal was fully restored and this
  experiment is not in the candidate or production source.
- 12-bit files are1,095,168 bytes: nominal file payload is about262.6MB/s at240
  and306.3MB/s at280 before filesystem overhead. Later native SD batches report
  roughly250–265MB/s. Sustained SD throughput is a separate constraint; it
  does not explain the8-bit and initial-buffer results by itself.
- This run uses UHS-II SD. A preserved earlier runtime log identifies SSD at
  5000Mbps with the same94/94 vbuf stop; this is historical evidence, not a
  current controlled SSD comparison.
- The user subsequently confirmed that SSD reproduces the same fault and has
  now connected the SSD. Storage speed alone is therefore not an adequate
  explanation. Continue investigating the recording/preview pipeline; a new
  instrumented SSD run is supporting evidence, not a prerequisite for accepting
  the user's report or for continuing the fix.

Nine v10 DNG samples (first/middle/last of120/240/280) decoded successfully and
did not show the same preview mosaic. This does not validate every RAW frame.
Full HDMI captures are preserved as FFV1 with verified decoded-RGB SHA256 and
byte count. Equality checks on all frames distinguish scene freeze from UI
changes; screenshots or req=fin alone are not sufficient acceptance.

## Metadata candidate v11 was rejected on hardware

v11 passed nine offline notification/metadata tests, but its getter called
`vr_live`, which entered interactive settings through C0057AE8/C005C0F0.
The latter makes virtual menu calls and normalization, so it is inappropriate
to assume it is a leaf recorder read. Those calls were stubbed in the initial
tests; successful emulation did not establish recorder-task safety.

On camera, v11's120p control wrote397/397 and returned to STBY. Its240p trial
A001_056 froze with REC shown; the first post-start status query timed out.
No stop key was sent. A subsequent rate-selection preflight also timed out
before any key. The full300-frame HDMI freezes at frame55 through299. No
file tools ran after the fault. User manually restarted the camera; new code
identity and native REC0 were verified before any update.

This proves v11 is not an accepted candidate. It does not independently prove
the exact point of the hardware hang. v11 bytes/evidence remain preserved.

## v12 change and offline results

- Run the original C00C9BD0 first; only adjust its rational afterward.
- Require active flag, picked entry, bounded/aligned entry offset, matching
  row/rank, enabled virtual UI and matching native carrier rational.
- No interactive settings getter, allocation, file operation or notification in
  the override. Preserve the native r0 return, callee-saved registers and stack.
- Keep the hook in the common loader's shutdown journal. Consumer header12;
  no loader, AutoRun, producer, geometry, pool or sensor-rate changes.

`test_reslab_record_rate`:4 tests passed in132.464s. The new call-context test
fails against frozen v11 by observing both forbidden settings calls. The suite
also executes the native ROM fallback,120/240/280/17.98 rational handling,
pending/inactive/changed-carrier guards, stack/register checks, journal restore
and a missing-hook mutation. The initial baseline command had a wrong relative
path and ran zero tests; the corrected absolute-path run is the baseline proof.

`test_reslab_rate_commit.RateCommitTests.test_same_carrier_round_trip_reloads_after_both_native_callbacks`: passed in64.897s against the v12 card.

Candidate identity is in `candidate.json`; plain/debug consumer bytes are
identical:183488 bytes, SHA256
`c63f197f389afc596f8853407216386fb8f0440876843f3bd7659e792ef03be9`.
AutoRun, loader and producer compare byte-for-byte with v11/v10 for both cards.
Live deployment/readback and subsequent trial evidence live in
`../20261011-virtual-rate-context-live/`.

## Acceptance still required

Sustained240/280 recording with continuous correctly scaled preview, full RAW
sequence integrity, independent cadence measurement, remaining recorder/audio
rate consumers, and approximately ten warm shutdown
cycles have not passed. No production release is claimed.
