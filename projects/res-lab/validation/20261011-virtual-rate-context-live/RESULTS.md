# v12 on-camera metadata validation, 2026-10-11

The DNG FrameRate defect is fixed in the sampled hardware files. The original
240/280p early termination and preview mosaic are not fixed. This remains a
development candidate, not a production release.

## Installation and boot

`deployment/deployment.json` records a verified183488-byte replacement of only
32RESCUS.BIN, with the existing96-byte CFG retained. Full readback matches the
prepared file, installed SHA256
`0c91b2a3ae45868503c1b78a0b558ce8e36336fe66311e0b27d2b411acbd3726`.
AutoRun, LOADER.BIN and50RESLAB.BIN were read before/after and are unchanged.

One reboot returned USB IO; it was not replayed. Task-owned daemon68745 was
cleanly replaced with69340. Within the user's explicit authorization, the
maintained reclaim path verified and released SIGMA interface0's exact
ptpcamerad claimant68755. `boot-v12.json` verifies the entire50710-byte immutable
core and both116-byte notification shims plus the80-byte recorder shim.
Header consumer12/producer17, fresh native REC0. Normal menus restored M12.

## Quiet recordings

M12, output992x662, RAW1008x672,12-bit, bin1x1, crop0, desqueezeOFF, UHS-II SD.
300 HDMI frames per trial,4s target. No camera query after start-key release
until the target; stop key only after a fresh positive recording read.

| Trial | Clip | Result |
|---|---|---|
| tagged-240-quiet | A001_056 |94/94, automatic vbuf stop, positive final STBY. No stop key. |
| tagged-280-quiet | A001_057 |94/94, automatic vbuf stop, positive final STBY. No stop key. |
| tagged-280-audiooff | A001_058 |94/94, automatic vbuf stop, positive final STBY. Audio getter0. |
| tagged-120-quiet | A001_059 |94/94, automatic vbuf stop despite no in-capture polling. First bulk write455ms. This negative control must not be omitted. |
| tagged-120-repeat | A001_060 |418/418, requested button stop, positive final STBY. Same rate/geometry/bit/audio settings, first bulk write246ms. |

The two120 trials verify sensor119.88011988/engine60/native carrier7 in their
preflight snapshots. Their difference is unexplained variability, not proof
that every120 trial is stable or that v12 caused a deterministic regression.
The earlier v11 control wrote397/397; v10 quiet control wrote388/388.

The audio contrast uses the original native menu setter. `audio-comparison.json`
and a fresh green STBY image prove audio restored to1 afterward. The initial
runner import collision occurred on the host before any camera command; the
corrected run and restoration are separate evidence. Audio-off changes the
initial write batch but does not avoid the descriptor exhaustion. No audio
code, pool size, batch limit or preview geometry was patched in this run.

The previous failed v11 recording showed A001-056 on HDMI, but did not leave
that clip folder in the next root listing. v12 subsequently created A001_056;
these are separate trials despite the reused counter. Do not assign v12 DNGs
to the failed v11 recording.

## Actual DNG files

Known filenames only, no clip-subfolder enumeration. Exact1095168-byte files
read through maintained getfile with source-address-tagged read_bulk, native
REC0 and fresh green HDMI STBY before file access. First/middle/last frames:

| Clip | Frames | FrameRate |
|---|---|---|
| A001_056 |1/47/94 |240000/1001 |
| A001_057 |1/47/94 |280000/1001 |
| A001_059 |1/47/94 |120000/1001 |

`raw-frames.json` retains parsed IFDs and SHA256; `raw-decode.json` records actual
LibRaw decoding. This proves the metadata propagation for these samples, not
complete sequence integrity, actual exposure cadence or A/V/timecode sync.

All HDMI archives retain full decoded-RGB byte/hash equivalence before removing
task-owned RGB temporaries. `scene-motion.json` checks every captured frame;
unique-transition contact sheets support visual review. Still images and
req=fin alone do not establish continuous preview quality.

The280p frame55 (`tagged-280-quiet/mosaic-frame-055.png`) has a clear displaced
rectangular region at upper left. Its scene ROI stays identical through85.
The decoded middle DNG47 does not show that patch; the defocused scene and
three-frame sample are not sufficient to rule out other RAW faults.

The whole-system audit and offline results are in
`../20261011-virtual-rate-context/RESULTS.md`. The user subsequently confirmed
that SSD reproduces the same failure and connected the SSD. Continue tracing
the recording/preview pipeline without attributing the defect to SD speed.
The last USB-verified state was M12/120p/12-bit with audio enabled; SSD attachment
is a new connection state and must be checked before another live operation.

## SSD attachment and next diagnostic

The user reported that SSD has the same failure, then connected the SSD.
`ssd-connected.png` shows green STBY,239.76p and counter A001-062. Host daemon
69340 still existed with the verified executable, but its cached `camera=open`
status did not mean the device was connected: the first native REC getter
returned `LIBUSB_ERROR_NO_DEVICE`, moved0/64. No key or subsequent native command
was sent. This is USB disconnection after the SSD swap, not another camera hang.

`ssd-240-manual/hdmi.mkv` preserves one60s HDMI window. All1798 decoded frames
show STBY; no manual recording occurred within this window. Therefore it is
connection/standby evidence only and must not be counted as an SSD recording
test. The user's SSD failure report remains valid reported evidence.

The prepared `planes` option in `record_trial.py` reads four bounded native BSS
ranges once in the recording transition (after a fresh REC1), with before/after
standby references. The ranges cover engine/geometry publication, routing,
both plane descriptors including buffer lists, and both consumer descriptors.
It uses native text `mem get`, one attempt per range, no pointer dereference,
scratch allocation, injected code or MEM1 transfer. The reads are independent,
not an atomic snapshot and not proof of buffer ownership. This is a diagnostic,
not a quiet performance acceptance run; only syntax has been checked so far.
It has not run on hardware because the USB port is occupied by the SSD.

Private checkpoint `7c265cd4ec453de2a4d10f845f76ab5811997909` was pushed and
verified on branch `fix/reslab-m12-rate-reload-20261011` in the private git:3000
repository. It contains the v12 fix and preceding evidence; this new SSD window
and the prepared diagnostic are subsequent work.


## Native completion trace and the lossless comparison

After USB reconnection, early native plane reads captured M12/120,240,280.
A001_063 wrote393 frames with button stop; A001_064 and065 each stopped at94.
The120 HDMI scene also froze112 frames. These independent plane reads are
transition snapshots, not proof of buffer ownership or atomic publication.

Existing native Logger rings were temporarily expanded to4096 RECMGR and
RECMGR2 records and enabled at DEBUG. All settings, ring ownership and static
256-entry rings were restored with exact original8-word header readback.
No native rings overwrote records. Logging affects scheduling.

A001_066 baseline: vbuf at1193.775 ms relative to the native log origin.
Only2 writer submissions and0 completions/releases preceded the94-frame limit.
First3 completions arrived1631.499 ms; releases began1856.413 ms.
The header interval includes an installed chain layer and must not be called
DMA-only time.

A001_067 quiet and068 native-trace trials temporarily changed the real FS
batch-limit word C0B9E5D8 from64 MiB to1 MiB, leaving the256 KiB buffer and
callback intact. Native ARM setup was emulated for64/16/1 MiB first. Each
1095168-byte DNG exceeds1 MiB and the native log shows single-file commits.
Both takes still stopped94/94. In068, the first completion was1054.658 ms,
vbuf1209.046 ms and its actual descriptor release1293.700 ms:239.042 ms after
completion. At vbuf:2 submissions,1 completion,0 releases. Thus byte-threshold
flush alone is insufficient; native RAW task/FIFO processing also falls behind.
Both temporary words were restored after native REC0 and positive HDMI STBY.
HDMI archives have complete decoded-RGB byte/SHA equivalence.

The maintained lossless notes EARLY_STOP_94.md document the same descriptor
pool and64 MiB deferred-completion mechanism. That earlier case had timely
submissions/acceptance and late completion callbacks; our current trace also
has delayed submission and delayed processing of an already-fired completion.
Samples A001_057 frames1/47/94 are Compression=1 (uncompressed).
Fresh full module readbacks and LOAD.LOG in optional-modules-inspection show
10LOSS.BIN is DISABLED (code13, sup_id LOSS); it is not loaded for this boot.
Gyro2 is loaded and owns C038C77C, the bracketed DNG-header call. Its maintained
source edits the per-frame MakerNote before forwarding to native DMA.

The initial CPU-header v13 experiment was withdrawn before emulation/deployment:
it would bypass Gyro2 when handled, and its timing attribution was incomplete.
Copied exploratory source/test/diffs are retained under withdrawn-header-copy;
its stale compiled debug artifact is preserved only as unverified history.
Production source is restored to v12. No claim of a recording/mosaic fix.


## Gyro2-off contrast and prior successful240 clip

Original FSDS disabled only LOSS. Existing module data was temporarily changed
to LOSS+GYR2, preserving the entire loader program/envelope. Full29276-byte
readbacks verified; after one reboot native C038C77C was stock FAF5BD03.
Reboot reclaimed only exact observed SIGMA PTP claimants69365 and71612. Daemon
71600 now owns USB. The first attempted recording stopped in preflight because
the selected native rate was still120, despite the280 recipe filter; no key
was sent. Normal UI then committed native row10 and verified all runtime fields.

- A001_069 (`tagged-280-gyro2off-quiet-selected`):94/94, vbuf automatic stop, positive HDMI STBY.
- A001_070 (`tagged-280-bulk1-gyro2off-quiet`):102/102, vbuf automatic stop. Actual1MiB literal made individual3–11ms commits; exact64MiB original restored in standby. Eight more descriptors recycled, but no complete recording fix.
- A001_071 (`tagged-280-gyro2off-native-trace`):94/94, vbuf at999.017ms relative to trace origin; before it5submitted,0completed,0released. Header bracket median2.101ms, maximum8.987ms. First three completion-to-release gaps221.156/221.382/221.612ms. Native logger settings and static256 rings fully restored.

All three full300-frame HDMI archives passed decoded RGB SHA equivalence.
Identical scene spans were29/25/30frames; equality does not by itself diagnose
mosaic. Gyro2 next-boot settings restored exactly to original loader SHA
7b78041d80ddf9a74f751c4d38366a5ae8fa4184ff5d41494f2f345d7d25d95b
before preparing the next candidate. Current boot remains gyro-disabled until reboot.

User supplied `/Users/dido/Movies/fpsup/hightspeed/A001_193` as a prior successful
240p recording.4809 DNG files numbered1–4809, no missing names, all1095168bytes.
First/middle/last parse and LibRaw decode:1008x672,12-bit, Compression1,
DefaultCrop992x662, header78848bytes, identical current file geometry. Legacy
DNG FrameRate is30000/1001. WAV duration20.069771s at48kHz, stereo; count/audio
duration239.614fps supports the user's successful240p report; user confirms SSD media. It does not prove
the old card identity, preview quality or exact exposure cadence. Metadata and
three decoded samples retained under `prior-240-success`; user originals untouched.

## v13 inner-header/local-bulk development candidate (not deployed yet)

New inner Thumb entry C00FBB90 leaves Gyro2's C038C77C outer chain intact.
CPU copy applies only to the native DNG caller, matching active992x662/12-bit
240/280 entry, exact native header-owner pointer/length and frame destination.
Only uncached MEM1 destination accepted; original cached/uncached source used
without changing aliases, physical alias overlap rejected. Other calls replay
stock prologue. C03A5144 changes only the native local FS setup descriptor's
64MiB batch to4MiB, preserving its work buffer, length and completion callback.
Global ROM literal, RAW pool, writer callbacks and pixels untouched.

Final card `20261011-virtual-header-inner/debug-final` consumer184448bytes SHA
6e8c2ec51471527fca2d82d6e713c2d2b298825b871efb4f4e8007a083952bf2.
Resident shim span moved from0x1280 to0x1300 after the builder correctly refused
a56-byte overflow. State initializers and all PIC coordinates rebuilt. Plain
and debug builds completed; AutoRun, loader and producer exact equal to v12.
Six Unicorn tests passed198.332s, including native callsite, real ROM CPU copy,
local FS descriptor, ABI, guarded fallback, alias overlap, journal and missing
hook mutation checks. These prove modeled software behavior, not real hardware
scheduling/cache/DMA/preview. Entry chain regression14builds/3AutoRun comparisons/
8catalogue refs passed. DNG rational regression passed32.887s; complete native
commit-callback regression passed all6 tests in360.566s. No v13 code deployed yet.

## v13 deployed contrast and descriptor-ownership correction

v13 full card backups/readbacks verified; CFG preserved, loader/AutoRun/producer
unchanged. One reboot; exact SIGMA PTP claimants71662/76135 released; daemon76118.
Core51414bytes, both rate shims, recorder and two new hook bodies read back exact.
Host verifier corrected its ARM BL decoding for kind1; camera code unchanged.
Native UI restored M12 and committed280p. A001_072:94/94 vbuf stop, nativeREC0
and positive HDMI STBY, no stop key. Bulk hook hit once at4MiB, actual log commits
3/4files per batch; global bulk log still64MiB because its literal is untouched.
Header94calls but0CPU hits, WHY3: r5=C3585994 is a native static-BSS object,
not a MEM1 image buffer. Source53800880, destination59CEA400, n78848. Full
HDMI archive/decode equivalence verified; visual contact shows left magenta
rectangle at frame55 then31identical scene frames. No recording/mosaic fix.

Native C038BD98 calls C0374220 then C03753C0(id) for r5; C03753C0 indexes
C351FF48..C35200C7 (96pointers). The table is cleared in standby, so post-stop
zero slots do not prove membership during capture. v14 adds exact native-table
membership before frame-field access and admits static BSS descriptors, while
retaining source/destination owner/length/alias guards. Tests now use actual
static descriptor address and native table slot93, including nonmember fallback.
Debug/plain builds exact consumer184448bytes SHA
f0c2eff7db5a3b982750028b1c597aae15732ddf86ac97724d9f4eec78084fb4.
This revised candidate is not deployed; all6 ARM tests passed in190.571s,
including the actual static-BSS/native-table fixture, nonmember fallback and
both new hook shutdown restoration. AutoRun/loader/producer match v13 exactly.

A001_072 known-size first/middle/last DNGs fetched in native+HDMI standby,
all1095168bytes and LibRaw672x1008 decode. First/last decoded images visually
show continuous scene with no matching left purple rectangle; this is only
three-frame sampling, not a whole-take RAW integrity verdict.

## v14 on-camera, SD contrast (fix not achieved)

Only consumer replaced; same CFG, AutoRun/loader/producer read back unchanged.
Installed CFG-bearing SHA2841b91637a70c0d0a5104b685f8cdf8c5b3a1c4823a018408ca00527e71ce7a.
One reboot, daemon76927. Exact observed SIGMA claimants76173/76962/77006
released individually; the first two immediate acquisitions returned ACCESS.
After waiting for exact process termination after asynchronous SIGKILL,
getterREC0 succeeded. Complete51454B core and all5hook bodies read exact.
Native UI selected M12/280p; no raw FPS/entry overrides.

- A001_073 quiet280p:94/94 vbuf stop;94/94CPU copy hits and4MiB local batch hit. First4-file request1040ms/finish1055ms. NativeREC0+HDMI STBY; no stop key.
- A001_074 diagnostic280p:94/94, CPU hits+94, local batch+1. vbuf971.591ms from native log origin,3submitted/0completed/0released before it. First completion1151.681ms; release1376.574ms (224.893ms gap). Header bracket includes Gyro2 and CPU now: min.986/median2.325/max35.137ms. Logger fully restored exact8words/static256rings.
- A001_075 quiet240p:136/136 vbuf stop;CPU hits+136, local batch+1. First4-file request865ms/finish879ms.42descriptors recycled, still not sustained recording. NativeREC0+HDMI STBY, no stop key.

These SD findings do not replace required SSD acceptance. Prior user report
that SSD also failed refers to an earlier candidate. Both v14 changes genuinely
execute, but neither complete recording nor no-mosaic is established.

A001_076 quiet120p control completed392/392 with requested button stop,
nativeREC0+positive HDMI STBY; no CPU or batch-clamp hits (native fallback).
Native UI returned to240p and complete state saved v14-ssd240-prepared.json.
User manual SSD swap requested; no further USB camera operation until reconnect.
SSDs occupy the camera USB port, so continuous HDMI captures the manual trial.

## v14 manual SSD/SD failure and leak check

User reports both media stop rapidly and still show mosaic. Full180-second HDMI
FFV1 capture5389frames saved/hash frozen; full decode succeeded. Observed SSD
REC/STBY takes268/269/270, followed by two SD takes076/077. Contact visibly shows
central vertical mismatch during SSD REC. This is still a failed candidate.
USB mode was storage after manual swap; no SIGMA device was enumerated. User
switched to camera control; same daemon76927 acquired nativeREC0 without PTP kill.
Retained native log is slot5/exFAT/5000Mbps, timestamp18:35:33,128requests/128finished,
vbuf128/raw1. Several takes occurred, so exact association to HDMI clip is not
asserted. No SSD filesystem readback. Full v14core/all5shims still read exact;
headerCPU hits1235,localbatch10hits/4MiB,engine239.7602386/sensor239.7602398.

After recording, native pool pointer/vptr verified and free count96/96 three
times across6seconds. Original stop flush stillE92D4030 atC0377118. Therefore
this observed standby has no stranded descriptor leak; it does not exclude
other memory domains, another stop path, or transient exhaustion during REC.

User supplied Downloads/fp-stop-leak-fix and fp-phase-detect. Copies/hashes
retained in reference-stop-leak.316-byte05STOPFX matches suppliedSHAf9f26a09…;
stockROMprologues and EA000160→C03776A0 verified independently. It proposes
flushing pending requests through existing ref-counted native release. Not
loaded or executed here. Current96/96 recovery means it is not a demonstrated
remedy for this trial. PDAF material is AF analysis, with no tested high-rate
recording correction; no AF/sensor modification made.

To isolate remaining per-frame work, data-only next-boot FSDS changed from
LOSS-only toLOSS+GYR2 for a new same-v14 CPU-header contrast. Entire loader
29276B readbacks exact; program/envelope unchanged. Persistent settings must
be restored after contrast.

## Same-v14 CPU-header / Gyro2-disabled contrast (still failed)

One normal reboot loaded the same verified v14 core and five shims, with stock
outer header word FAF5BD03. Owned daemon77641; exact observed SIGMA claimant77073
released before acquisition. Native UI verified M12/280/12-bit, original geometry.

- A001_081 quiet:140/140, automatic vbuf stop. CPU140hits, local4MiB batch hit.
- A001_082 real1MiB FS literal contrast:107/107, automatic vbuf stop. Literal restored to exact original64MiB four-word descriptor after nativeREC0/positiveHDMI STBY.
- A001_083 native DEBUG trace:101/101, automatic vbuf stop. Before vbuf17submitted/14completed/7release-entry notifications. First completion-to-release gaps14.139/15.027/16.102ms; header bracket median2.149ms, max5.955ms. DEBUG affects scheduling; release-entry events alone are not free-pool or durable-file proof.

All three full300-frame HDMI captures passed complete FFV1 decode/RGB SHA
equivalence. A001_081 contact still visibly contains a displaced left region;
none is a picture/recording acceptance. Logger restored exact original8words
and static256-entry rings. Next-boot Gyro2 FSDS restored fully to original
29276B loader SHA7b78041d80ddf9a74f751c4d38366a5ae8fa4184ff5d41494f2f345d7d25d95b.
Current diagnostic boot remains Gyro2-disabled until the next normal reboot.
No cached-alias optimization or global cache maintenance was installed.

`summarize_native_trace.py` now joins repeated slot ids by submission cycle
and actual RAW buffer. Exact101-header expectation and verified CPU/GyroOFF
context are explicit; prior94-header reports remain unchanged.

## User identifies the successful predecessor as Sensor Lab

The archived r10 notes record the user's2026-10-01 report that240 recording
completed well. Frozen r10 card61440B SHA918c9b515ea45c0403e1b22e19497cdcfb948ecf72e019f56c5f11089af57f34
is preserved; it is not proven to be A001_193's exact card. Its obsolete fixed
cave loader is not deployed. `extract_sensorlab_reference.py` executes only
its actual archived picker/recipe/canvas offline with original ROM tables.
It does not rebuild old code from current source, or emulate DMA/storage.

The actual r10 virtual240 path selects mode12,330/330/910/x6,1008x672 RAW,
992x662 crop, and engine239.7602386. Thus the suggestion that old successful
Sensor Lab generally kept the engine at30fps is disproven for this r10 card.
A001_193's30fps tag alone cannot identify its engine configuration.
Old native120 instead selects mode140 (445/740/1349), unlike today's fixedM12.

After matching the engine field,11 full-canvas words differ between archived
r10 high-rate and the r78 geometry retained by the current calculator.
The prior withdrawn4-word matching-tap/engine30/carrier30 trial leaves7 of
these geometry/class/window differences and is not a complete r10 replay.
Full old/current field evidence is `sensorlab-r10-r78-differences.json`.
Current high-rate full-canvas execution and actual candidate effects still
require verification; no root cause or successful fix is asserted.


## v15 complete archived Sensor Lab profile candidate

Frozen v14 actual high-rate ARM execution differs from the exact archived r10
canvas on11 words. Unlike the preliminary30p r78 comparison, high-rate B0 is
already1, while D4 is1023 rather than1024. The full negative test independently
fails as expected in31.769s; it detects the prior version rather than copying
candidate constants into an expected result.

The candidate restores the complete old65-word recording canvas only under
active M12/12-bit/23976 or27972 entries with exact PID, engine,330/330 timing,
910 or780 VMAX and original1008x672 RAW/992x662 crop. It changes processing
class, recording window and scale fields; the current virtual-rate picker,
producer, CPU-header and local4MiB batch stay as the same comparison baseline.
No old fixed-cave loader, pool expansion, cached alias guess or stop-release
patch is installed. This is a development comparison, not a validated release.

Debug/plain consumer184832bytes SHA51cd29c8f7eea3e6ff78f6398b82d5b0bffa2033f6afc875047c2217606a297f;
text51794bytes. AutoRun, loader and producer match v14 exactly. The actual240
canvas matches all65 archived words;280 matches the geometry with its own
rate/timing. Native ROM translator and predicate select class2/field58=4/
flag14=1 and enabled[0,1,0],mux[1,4]. This proves the modeled configuration,
not hardware DMA/media behavior.

Initial two-case run passed the old-profile case, but failed the low120
fixture because it used frozen30p B0=0. The fixture was corrected using the
independently archived native120 B0=1; candidate unchanged. Only the affected
low-rate/guard case was rerun and passed31.812s. All six header/descriptor/ABI/
fallback/journal regression cases passed190.373s. Raw initial, correction,
negative and regression logs are retained.

Card update completed with all-file backups, complete readback and unchanged
AutoRun/29276-byte loader/producer. Valid saved CFG retained; installed consumer
SHA5932f1aad4b871161e33a30716cf143bb99f2a0f8277a0f3a9f788fd9e9dc83a.
One reboot requested; USB IO response treated as uncertain and not replayed.
Replacement owned daemon79046 initially saw ACCESS; exact freshly observed
SIGMA claimant77679 released, nativeREC0 succeeded. Complete loaded bytes,
hardware trial and picture acceptance still pending.


## v15 real SD contrasts: preview improvement, sustained recording unproven

Full51794-byte loaded core SHAcb8b3d543525d61d627615e420b9725ddbddd84721c6d889d69270c98d4fe111
and all five exact hook bodies verified. Native menus restored M12 and240p;
legacy-profile hit counter changed before recording. No direct entry/FPS writes.

- A001_084 quiet240p:101requested/101finished, automatic vbuf stop; no stop key.
- A001_085 quiet280p:94requested/94finished, automatic vbuf stop; no stop key.

Both nativeREC0 and positive HDMI STBY confirmed. Both full300-frame FFV1
archives passed complete decoded RGB SHA equivalence; first/middle/last DNG
files1095168bytes fetched using exact known names and decoded by LibRaw.
Reviewed transition contacts show no obvious displaced patch seen in v14's
comparison. The blurred scene and short take do not establish no-mosaic under
all conditions. Longest ROI-identical spans are3frames at240 and4at280,
compared with prior multi-dozen-frame stalls. This is a preview improvement,
not a successful sustained-recording acceptance.

Full native engine/sensor rates, profile/CPU-header/local-bulk hits and all
readback identities retained in sensorlab-v15-sd-results.json. SD writes still
show long request or completion gaps before drainage. SSD behavior remains
unmeasured for this candidate. Normal menu returned to240; complete prepared
snapshot is v15-ssd240-prepared.json. User originals and old working card remain
preserved. No warm-cycle acceptance or release has been claimed.


## v15 SSD failure and unified-model counterexample

User acknowledges SSD swap and reports automatic early stop for the requested
20-second trial. Continuous300-second HDMI FFV1 capture8958frames/3072393421bytes
SHA847b9c29bac34a6e5b43b3a569ac06880d292349c3ee7cef4fe35172903716f0.
Full decode completed. Several earlier REC spans occurred before the requested
SSD trial; they must not be merged into its timing. A001_276 is visibly SSD/REC
at frame6838, through6906 (~2.3seconds host overlay), followed by STBY.
No USB camera commands were sent while the camera occupied the SSD port.

After reconnect, the computer mounted SSD at /Volumes/Untitled. Exact A001_276
contains134 DNGs numbered1–134 with no filename gaps, all1095168bytes. Every
file hashed; first/middle/last RAW plus WAV/XMP copied into task evidence,
originals untouched. All three LibRaw decodes1008x672,12-bit,Compression1,
crop992x662,FrameRate240000/1001. Audio0.741771s; count/audio180.6487fps is
not physical240-cadence proof because this is a short prematurely stopped
clip with uncalibrated audio start/stop offsets. Previous successful4809-frame
sequence's long duration gave a much stronger240 report. User additionally
reports recording image shrinks; fov-01..04 preserve STBY/REC frames, no
calibrated registration or FOV acceptance claimed.

Fresh USB request first returned NO_DEVICE; the actual daemon closes that
stale handle on this error. Owned daemon79046 still exact maintained executable.
Fresh USB enumeration shows RTL9210CN SSD but no SIGMA camera; fresh HDMI is
still in native menu. No blanket claimant kill, reboot or record toggle issued.
User asked to set camera USB mode to camera control; native retained log is
pending recovery. Do not infer a new native SSD vbuf count without that log.

The formula issue is concrete: sl_modes.c declare_post fixes PARAM+1C class1
and+88 zero. rl_v3.c rl_canvas_safe requires that class and rejects all no-bin
unequal preview H/V products. RATECANVAS only changes B0 for240/280; class,
window and reduction remain common. The complete archived r10 path uses
class2,+88=4 and preview2048/1024. Actual current ARM encoder accepts its own
calculated M12 profile and rejects this independent archived profile; new
counterexample test passed46.586s. These guards protect the current narrow
model; weakening them globally is not justified. Full generic native-path
calibration and sustained-recording repair remain incomplete. v15 consumer
restoration is a bounded contrast, not a generic producer formula correction.

## Successful clip dates narrow the actual predecessor to September29 H2

First/middle/last original A001_193 DNG EXIF and original WAV RIFF agree on
2026-09-29 09:14:25+08:00; last-frame filesystem time09:14:46. The standard
Software tag names stock5.02.0.V91 and does not identify a custom build. Originals
are untouched. Selected historical Open Gate records show a verified H2 RAM
installation at08:55local, actual M12 geometry and27-word recipe agreement. The
first new rate-hook install at09:16 failed in preflight, zero writes; the prior
H2 was reported retained. Two recovered nearby screenshots match the original
DNG camera serial and bound clock lead to about56–60seconds. Conditional on an
unchanged clock/timezone, clip start maps to host09:13:25–09:13:30. Its legacy
30000/1001tag agrees with this predecessor.

No located historical record explicitly names this exact dated take, so the
version family is strongly supported but an exact installed BIN/commit remains
unidentified. October1 r10 remains a separate later success reference.

New concrete difference: the contemporaneous H2 donor was nativep13, while the
frozen r10 replay usesp83. Applying the actual archived25-pair live canvas
readback to independent native defaults leaves PARAM+88=0 versus4. The live
list does not overwrite88. FPSLATCH+30 is excluded because no recorded full65-word
snapshot is available. Currentv15 restores the laterp83 value4. This is a new
native-path comparison target, not established early-stop root cause. No new
hardware/card/production changes made. Full reproducible audit in
`success-version-audit/REPORT.md` and associated JSON/excerpts/screenshots.

## H2S240 RCD reconstruction and capture/native rate separation

A001_193 date audit targets the September29 p13 H2 family, not October1 r10.
H2S240.RCD (7060B, SHA835d214c...) contains all25 archived live pairs, p13
defaults, M12,1008x672 RAW,992x662 crop,2048/1024 recording and preview zoom.
Required RCDv3 section12 stores per-carrier rank/crop/timing/engine/nominal.
Only the native30 entry requests330/330/910x6, sensor239.76, engine239.76 and
nominal240; UI/container retains native29.97. Engine reconstruction follows
the predecessor recipe/FPS-latch path, not a saved A001_193 full-latch readback.
Other carrier entries retain the current generated timing.

Consumer productv16 recognizes this required section; frozenv15 rejects it
with UNKNOWN before publishing the file. Existing RCD bytes and RES-Lab
producer, loader and AutoRun remain unchanged. Actual ARM loader/parser,
cloned sensor timing, full65 canvas, native ISP translation class2/field58=0
and selector tap4, native30 header rational, native header-copy fallback,
64MiB local writer,25p cached retiming and ABI/table canaries pass. Frozenv15
negative passes. Existing virtual240/280 and dynamic apply regressions pass.
Initial fixture used the fourth positional call argument as LR; it was fixed
by explicitly setting emulated R3, without changing the production artifact.

The saved v15 SSD A001_276 native log confirms req134/fin134 and vbuf stop.
Its saved summary bulk64MiB is the original descriptor, while repeated
request groups and earlier live BULK_HITS show actual4MiB local transactions.
It reaches sdb1 with low FS outstanding count; durable file finish is not
proof that all RAW descriptor consumers released their reference on time.
Hardware acceptance of the new H2 RCD remains pending.

## H2 v16 hardware comparison failed

Exact consumer core and five shims, installed RCD, normal-menu enable and
post-reboot H2 state verified. Full p13 canvas and timing remain sensor239.76,
engine239.76, native30 and S.VRATE0. Old r10 restoration, CPU-header and
local4MiB guard counters remain0, as intended for this historical comparison.

SD A001_086: req94/fin94, native vbuf/94/raw1, file1095168B, stock64MiB batch,
automatic stop without STOP key. NativeREC0/HDMI greenSTBY confirmed. Complete
300-frame FFV1 archive115705373B SHA00977a5ad5234e3656b465e0b40bc5468038415806dd19412484e3ff4a7af40e
passes decoded RGB equivalence. First/middle/last DNGs parse atTIFFoffset0,
decode with LibRaw, and retain1008x672,12-bit,Compression1,crop992x662@(8,5),
FrameRate30000/1001. Short blurred-scene contacts are not complete mosaic or
calibrated FOV acceptance. Ten normal power cycles remain untested.

User reports manual SSD follow-up early stop. Every original file in host SSD
A001_277/278/279 was hashed without modification; selected original DNGs and
WAV/XMP preserved in `h2-ssd-host-evidence/`. A001_277 has1 aligned DNG.
A001_278/279 each have94 contiguous1095168B files; both have29 TIFF headers
at0,22 at19456 and43 at65536, with zero prefixes. Counts match but per-frame
runs differ by3frames. Byte0 TIFF parsing fails; temporary relative-TIFF tag
parsing is not a repaired image or whole-RAW integrity proof. This directly
establishes malformed file headers. No full HDMI or native stop trace exists
for these three manual takes, so94 files alone does not prove native vbuf.

19456 is reserved nativeDNGheader0x18000 minus actual0x13400.65536 is the SSD
scatter upper segment length. These are alignment clues, not a proven cause.
Full first128KiB-per-file scans find all earlier SSD274(136),275(128),276(134)
and original successful193(4809) atTIFFoffset0. Known v15 clip276 had CPU-header
and local4MiB guards; carrier/profile/batch also differ, so this comparison
cannot isolate CPU/DMA causality.

## Native source audit identifies two delayed acknowledgments

Event5 header preparation, event8 writer advance and event9 RAW/descriptor
return share the same native FIFO MRecMgr. Native C037DD50 holds the next
frame until C037DF40 -> C0376F20 clears creator+1C. Thus event8 waiting gates
the next write, while event9 waiting delays recycling. C03A55D0 only posts a
completion. There is no94-frame write-trigger condition in the native allocator.

Saved1MiB trace: firstevent8 post925.385ms/dispatch1049.591ms; next writer begins
1049.636ms. Firstevent9 post1054.664ms waits until1293.438ms, with36 header
starts between; vbuf1209.046ms happens earlier. RAW-free branch1293.680ms and
release entry1293.700ms follow dispatch. Four traces have matching notifications
and no allocation warning. GyroOFF returns7 RAW buffers before vbuf, so the
finding is insufficient/delayed recycling, not universally zero recycling.

**Correction to earlier summaries:**99990005 atC03A55C0 is writer RETURN, not
entry, exact submission or durable completion. Old 'submitted' labels must be
interpreted accordingly. Entry99990000 and I/O-before99990004 are separate.
DEBUG changes scheduling; delays after vbuf include synchronous stop/drain.
Release-entry and RAW-free logs precede allocator return; pool96/96 readback
is separate evidence and does not exclude every kind of memory leak.

New native SSD source trace identifies C0670338 as zero-copy scatter-address
retention; C0670690 consumes up to64KiB per segment. Accepted writes still
reference RAW until media completion, so direct free can overwrite unread data.
Strict original ARM execution confirms FIFO order, writer advance gating and
scatter continuity:3 tests pass. Initial fixture ABI/range errors and final
logs retained; actual scheduling, cache, DMA, TRBs and storage are not simulated.

`recycle-source-audit/REPORT.md` documents exact sources, full per-frame trace
hashes, SSD evidence and limits. Current m12_high_entry ignores H2 because its
VRATE0 despite sensor240; the concrete predicate gap is documented. No new
production changes or camera installation were made during this source audit.
Need same-build header destination, writer segment and SSD scatter addresses
to locate corruption. Sustained240/280 and full mosaic repair remain unresolved.
