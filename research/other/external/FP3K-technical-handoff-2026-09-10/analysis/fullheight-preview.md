# Full-height preview investigation — 2026-09-09

The user confirms v0.3.2 main-menu summary, live HUD and QS now look correct.
Preserve that camera-tested package. The new preview1 experiment is built below; physical full-height preview is not yet established.

## Photo reference and separate standby/record paths

`tools/trace_preview_profiles.py` executes the unmodified ARM descriptor
constructor C0438018 for all306 stock profile rows with read-only firmware and
bounded destination/stack writes. No firmware functions are mocked.

Stock profile1 builds a2016x1344 preview with2000x1334 visible pixels and centered
offset8,5. Profile5, observed repeatedly in the earlier camera standby logs, is
identical to profile1 in all65 table words EXCEPT PARAM+1C (1 vs2) and PARAM+28
(1125 vs1334). It already builds a2016x1344 descriptor, but with centered vertical
offset109 and2000x1125 visible pixels. Earlier generic statements that preview is
always2016x1135 applied to the recording profile429, not this standby profile.

PARAM+1C is propagated to the native processing config+68. Its complete meaning
has not been established; do not call it a proven aspect selector or blindly copy
it from the photo profile. Some other stock profiles with value1 have3:2 visible
dimensions. Photo profile IDs are not sensor mode IDs.

Recorded UHD uses profile429/sensor151, verified by earlier camera traces. Its
preview raster is2016x1135, crop2000x1125. Current3K capture changes leave this
preview half unchanged. The photo reference therefore suggests a shared geometry
approach, but replacing the whole running video pipeline is unnecessary and unproven.

## Native geometry and allocation evidence

C0438268 builds the preview half at descriptor+58:

- C0435858: preview width from PARAM+0C, overridden by nonzero+D8, then aligned.
- C04358D0: height from PARAM+10, overridden by nonzero+E0, plus+88/+8C margins.
- C0436138: centered crop offsets from raster minus PARAM+20/+28, divided by2.
- Preview zoom comes from PARAM+60/+D0; reduction enums from+58/+C4.

`tools/verify_preview_candidate.py` executes stock constructor, selectorC0325228
and buffer-size constructorC0435428 for stock429, the exact current8 RAW-profile
changes, a hypothetical additional{+10:1344,+28:1334,+E0:1344}, and photo references.
The hypothetical recording preview becomes2016x1344, crop origin8,5, retains
the exact current RAW descriptor, and retains selector enablebytes0,0,1 and
preview reduction factors3/3. No sensor or preview table has been changed on media.

C04356B0 computes the preview allocation from the same height getter. Other pools
also use this height throughC0435978/C0435AF8. With caller-supplied maximum dimensions
6064x4042, the sum of computed count*size entries rises17,167,384→20,321,416 bytes
(+3,154,032). This is a modeled pool request, NOT proof of the live reserved pool
or DMA safety. The preview RAW buffer itself becomes4,064,296 bytes (12-bit plus
native40-byte overhead). Actual reservations and reconfiguration remain to check.

Native source creationC043A158 reloads the table atC0439D18 and then invokes
C0434EC0/C0435428 before use. C0434EF8 exports geometry and computed sizes into
a1B0-byte processing config. C04299EC calls it, then C0429A04 dispatches to Thumb
C01D1630, which copies these fields to channel configurationC31DF564 (stride1B0).
Config+28/+2C overrides, +30/+34 visible crop, +38/+3C base raster, +68 kind,
and+148 onward pool sizes are useful diagnostic fields.

## Refresh uncertainty and prepared camera trace

Native property pathC005C020→C00658E8→C0074EC8 suppresses ordinary notification
when the backing resolution enum has not changed (C0074FD4). Private3K uses enum3,
same as UHD. QS apply flag1 additionally invokesC00A8DE0→C0091288; whether that
rebuilds the live preview when the enum is unchanged is not proven. Simply patching
profile tables could affect the next recording yet leave the current preview stale.

Prepared `diagnostics/fullheight-preview-probe-v1` combines the EXACT camera-tested
v0.3.2 AutoRun/resident with a separate1100-byte RAM diagnostic atC0731930. Its end
C0731D7C is below resident stateC0732000; the resident endsC073192C. It uses the
previously camera-tested capture wrapper structure, with56 RAM samples750ms apart
(42 seconds), 2304-byte records, total129088 bytes in a128KiB diagnostic allocation.

Additional fixed RAM reads: managerC375D840+100, native processing configs
C31DF564+360, private stateC0732000+48 and display stateC31D2800+100 (mode value at
C31D2858 is read by native getterC00DEA80). Source/profile copies retain the earlier
pointer bounds and change flags. Copies are sequential, not atomic.

The probe introduces no explicit startup sleep, overlay, sensor-mode write or
preview change. It saves one trace after sampling and3seconds of native idle
observations; waits at most60additional seconds if busy. No second recording may
start during its final-save window. Native scheduling and file I/O are not emulated.
Nine emulator cases cover transitions, late stop, idle, always-recording, finalizing,
bad/small allocation, corruption and invalid source. Guards allow writes only to
the diagnostic allocation, stack and temporary echo handler. Adjacent code/state
canaries and captured extension contents pass; decoder rejects truncation.

Needed hardware pass: start CINE, select3K, record5seconds and stop; selectUHD,
switchSTILL for5seconds, returnCINE and remain idle. Complete the interactions
promptly, ideally within the42-second sample window. Leave powered on90seconds
from startup and wait for media activity to end before normal poweroff. No still
capture is needed; this pass measures preview state changes, not framing quality.
The prepared trace must be inspected before deciding which cached/live fields to
change. Full-height LCD framing and recording preview still need a later visual test.


## Returned hardware trace and preview1 experiment

The returned FPV1 trace is hash-verified and decoded in
`diagnostics/fullheight-preview-trace-return/decoded.json`. All56 source copies
have flags1 with stable observed sensor IDs. Both user recordings are retained,
SHA-verified and inspected: A001_014 has133frames, A001_015125frames; all are
3032x2020 stored, crop16,10/3000x2000,12-bit,true24fps, contiguous frame numbers,
valid strip bounds. The extra recording did not invalidate the pass.

Nominal sample transitions:3K standby0s, record3.75s, standby9.75s,
private off12s, private on18.75s, record21.75s, standby27.75s,
private off28.5s, photo profile1 at36.75s. Both recordings used profile429
with3K active. No installer error appears; resident is byte-identical tov0.3.2.
This does not identify which control deselected3K.

Actual SOURCE maxdimensions are1620x911 in CINE standby(profile5),1920x1080
recording(profile429),1620x1080 in STILL(profile1). These supersede hypothetical
6064x4042 maximum-dimension pool totals above. `verify_preview_live_sources.py`
replays the captured parameters and source headers through the native descriptor,
pool calculator, and config-export prefix up to C04353EC. Original count/size
arrays and direct-copy geometry match the camera exactly. Exporter's later
device-dependent tail is not executed; it writes config+190.

Crop-only standby expansion leaves pool sum12,515,416 bytes unchanged. Recording
height expansion increases14,659,096→17,353,864 (+2,694,768). RAW descriptors
remain exactly the corresponding observed descriptors. These are calculated
requests, not proof of actual reservations, DMA or on-screen framing.

The changing display pointer at C31D28E4 points into C31D2938's0x400-stride
palette tables (see C00E1B38); it is not established as an aspect/layout selector.
Do not swap it as a preview fix. Config+68 maps to C31DB0F0 through C01A6130;
one consumer C01A5C3C tests zero/nonzero, treating1 and2 alike. Other semantics
remain unknown; preview1 leaves this field unchanged.

`preview_candidate.py` adds only four guarded source-table changes: one in
profile5 and three in429. The standard transition/rollback machinery now derives
its22-entry count from generated PATCH_COUNT. It never changes a live source or
live allocation. In particular, selecting3K while already inUHD may not refresh
standby until a native recording transition. UHD exit likewise needs that
transition for the cached preview to refresh. This is an experimental limitation,
not an accepted final user experience.

The UI plans/assets remain those ofv0.3.2. An apparent third stock QS footer
screen C23E1F9C contains still controls and no MV_Resolution selector actions;
do not indiscriminately add a resolution choice there. Only the two movie QS
controllers were found. To distinguish caching from other runtime behavior,
the resident now keeps seen/extended bitmaps at STATE+48/+52. Bits0/1 identify
C237249F/C25E405A limit records; bits2/3 C23535A3/C25B9EF1 footer clips. Bits
are diagnostic only; they do not reparse cached screens or repair the regression.

Preview1 resident15236bytes SHA
c6c1f1e771c5a0a69586e6a3158b13548c0a44760e8dc753c8799d6ae07b7bce.
Probe1100bytes at C07319F0..C0731E3C, below STATE C0732000, SHA
b5fe887c220b7ae791706590d400c950128ce50e48e49e485c586551e6c7498e.
Combined AutoRun SHA10204ada9c92b5bbeb798495fac13bb40dc1490ed3cd797b54ead0ef4f1d3747.
125 transition/guard,403 UI-hook,13 integrated boot and9 trace cases pass.
The test instructions and limitations are in
`diagnostics/fullheight-preview-experiment-v1/README.md`.


## Preview1 return: source change works, visible framing does not

User reports third QS choice present, no taller framing, no stretching/flicker.
Returned BOOT status16, resident15236 bytes matches preview1. FPV1 capture SHA
006aa8721725e7d961cecc94c2b481d5da3dfa0b49cb6cd52e90e55ff951e92e.
All56 source copies have flags1. Samples0–2 and13–22 record with private3K;
samples3–12 and23–39 are standby with private3K. In both states source and
processing config report2000×1334 visible crop and2016×1344 raster.
Recording pool-size fields report4064296 and2580488, exactly the predicted
larger requests. Actual allocation completion is not logged by this probe.
Private state clears at sample40; source reverts at41, processing config at42;
stock UHD recording appears at46. This proves refresh can occur after selection
with a short delay in this pass, not only on record transitions.

Three full clips preserved and SHA-verified (455 files,4,695,886,721 bytes).
A001_016:132 frames;017:159 frames, both3032×2020/3000×2000 crop,12-bit/24fps.
A001_018:158 frames,3856×2170/3840×2160 crop origin8,5,12-bit/24fps.
All frames passed metadata and strip-bound checks with consecutive numbering.
Sparse green-plane previews for016/017 are generated; these checks do not certify
all-photosite sampling or cadence. No repeated camera test was requested merely
because there were three clips.

QS seen/extended bitmaps are0 throughout. The user opened QS after other steps;
the timing of that opening versus the sampling window is not established.
Do not infer a cached-screen failure or a successful instrumented parse from0.

## Preview2: primary output template, not another source-height increase

Manager C375D840's primary output descriptor at+18 still carries1620×911 in
standby and1920×1080 recording. Photo reference carries1620×1080. Its template
is44 bytes at manager+1C; channel stride is34hex, last channel flags at+30.
Native C0436538 copies all44 bytes from the policy template into this descriptor.
C0436D98 obtains the template through policy object vtable+0C -> C0438490 ->
vtable+1C -> C0437E98. C0437E98 returns object[channel*8].

Observed policy root C375E8DC is initialized by C043A2D8. Standby child at+28C
(C375EB68) references the template at root+58(C375E934), constructed1620×911.
Recording child at+460(C375ED3C) references C2F21494 (runtime RAM, beyond MAIN's
file range), copied to the manager as1920×1080. The constructor establishes these
pointers at C043A690 and C043A8C0. Photo child+268 references root+2C1620×1080.
Photo/video differ in another flag; preview2 deliberately preserves video flags.

The hook at C0437E98 checks private-active==1, channel0, these exact two owners,
the expected template pointer, and FNV of all44 source bytes. Expected hashes:
standby AED11366; recording E0255ED6. Only on complete match does it return a
private immutable44-byte template with1620×1080 raster and visible dimensions.
Standby changes two height words; recording changes two width words. All other
fields, including format4, limit3FC000 and flags1/1, match the camera values.
UHD/inactive state, other owners/channels and changed templates use native code.
No live buffer or original template is edited. Exact pointer gating may cause a
fallback on another native layout; this must be checked in the returned trace.

verify_preview_output.py executes the installed hook, displaced/native fallback
and native channel copy across14 cases, with bounded writes. Policy objects are
reconstructed from constructor evidence; source templates come from the trace.
The two native pool calculations reproduce original requests then confirm the
1620×1080 maximum dimensions increase no count or per-buffer size. Final LCD
composition, output-template lifetime, allocation and hardware rendering still
need validation. Do not call this a finished full-height preview.

Resident 4e357ef32f8228dc80c01dd19f776384d65b712106f1786ede8319c49cb0ede4; probe cb4f244f34fd38a450d0faa55f8c9cb6678b31fe266f61d58ab357c1e19b3f9c at 0xc0731b00; combined AutoRun fe6ceb25a444ef7e758b5f57cbb740a582c7c1a951785edfdeac5b18fc5431cb.
Reports and test instructions: diagnostics/fullheight-preview-experiment-v2.


## Preview2 return (2026-09-09): source AND manager output change, screen does not

Capture SHA bc16578671c78873d5eb29b7487da2872e71bb0db1014c80982dfbd146d98004,
resident exact 4e357ef3…ede4. All56 source copies flag1. Private3K source and
processing crop2000×1334, primary manager template1620×1080 in standby and
record. Stock UHD restores1620×911 standby and1920×1080 record. Mode changes
are sequential, with a transitional sensor151/source5 sample12. Private clears
sample30; source restores31. User reports unchanged framing and successful QS
3K access; later notes black bars at top/bottom, suggesting masking/layout.
Do not increase source height again or claim these dimensions prove LCD coverage.

Clips A001_019 (144 frames,6s,3000×2000 crop) and020 (212 frames,8.833s,UHD)
are preserved with hashes:360 files,4,014,881,366 bytes. All356 DNG frames passed
12-bit,true24 metadata, numbering and strip bounds checks. Reports and original
files in diagnostics/fullheight-preview-experiment2-return. These tests do not
certify all-photosite sampling or cadence.

Display RE: C0428690 converts manager primary geometry to a0x38 engine request;
C0429AC8 calls ThumbC01D69D0 with channel0, storing dimensions at C31E0DD4+324/+328.
Native XC_DisplayZoomParameterW71C1 vtables reference C0306DF8. That method calls
C0307280, then C0307408; when the latter is true it unconditionally requests
aspect enum3 at C0306EA0, via C02DAFA0. Enum table C0B4CAB8 maps2→3:2,3→16:9.
C02F43A8/C02F4410 fit the native destination rectangle; writes at+7C..+82 are
visibleW/H and X/Y. This is distinct from the source/output template dimensions.
C0307408 examines live state+1F8==2, CameraSetting+44!=0, and display device type.
Its exact on-camera branch execution has not been captured yet.

Frame-mask class C03055B0/C0300ED8 is controlled by runtime+23C (0/1/2) with
additional director-viewfinder behavior; do not blindly disable it. NBU maskH
records nearC2258AE9/C2277E78 bind PB_DVF_MaskH (playback DVF), not proven live
movie bars. Aspect-frame C02F8350 uses CameraSetting+3C; do not globally change
photo aspect settings to fix movie framing.

Preview2 QS bitmaps are5/5 throughout: first QS limit and first footer were both observed and extended during the capture. This supports the user's successful QS selection report.

## Preview3 display-fit candidate

New hook C0306EA0 is a mid-function branch over the stock mov r0,#3. It selects enum2 only for private-active==1 and [display-policy-owner[0]+8]==1. Other devices/states retain enum3. It preserves r1-r3,ip,lr,stack and flags, then resumes atC0306EA4. No live buffer or mask object is edited. STATE size64: +56 latched reached/applied bits, +60 last descriptor pointer. The sampler captures both; do not dereference a stale stack descriptor pointer as if current.

Native C0306DF8→C02F43A8→C02F4410 executes in the verifier with explicit environment-predicate fixtures. Stock geometry is1620×911 at0,84 (integer floor, not912). Patched3K/device1 gives1620×1080 at0,0. Other-device, inactive and non-movie branches preserve stock results.28 layout cases pass, including register/flag preservation; no LCD rendering or runtime selection is emulated.

Resident 8cf489ef8ad5e4c8723adac4dd421f6943a5d4f6338c030f70148764901b243e; probe 59a48cdbb9f0f1b620e0cd4250270c49752ef0fba1da8bd67fe4166fec90310d at 0xc0731b70; combined AutoRun 0bda00b04fa09ff34c16c43f587626291aec2610db1354696cc66edc3aaadfca. All127resident,403UI,13loader,14output,28layout and9trace cases pass. Hardware validation pending.


## Preview3 camera success; everyday package prepared

User reports: "money. test was successful, preview looks great". This confirms
visible full-height preview in the tested setup. The camera report does not
establish all-photosite filtering or extended reliability. No further preview
experiment is needed merely to repeat this visual confirmation.

Prepared prototype/fp3k-0.3.5-fullheight using the exact successful resident and
the already-verified base loader. No temporary sampler and no 90-second routine.
The loader is the exact prefix of the tested combined AutoRun, with only the
appended diagnostic commands absent. Resident and loader hashes were checked
against the existing verification reports; no firmware code was changed.

Neither removable device is mounted. Everyday package is NOT installed yet.
Next: collect preview3 return logs/recordings from both known media, preserve
hashes, then install the everyday loader. Existing installed combined AutoRun
SHA 0bda00b04fa09ff34c16c43f587626291aec2610db1354696cc66edc3aaadfca;
resident unchanged SHA 8cf489ef8ad5e4c8723adac4dd421f6943a5d4f6338c030f70148764901b243e.


## 2026-09-09 returned preview3 reviewed; everyday loader installed

User explicitly requested review before installation. All returned data was
copied and hash-verified first. Trace SHA
c05a837a9f8cfba35e8dc71698fd374bd63a6f97bb4ac20fe4dd261b63a09994.
Boot status16, expected 15,620-byte resident and 1,100-byte probe hashes match;
all56 source copies valid, no patch/UI error fields. Layout reached/applied bits3
confirm hook execution. Stable private3K source/native crop2000×1334 and primary
output1620×1080. UHD source/native crop2000×1125 restored, output1620×911 standby
and1920×1080 recording. QS bitmaps5/5. The trace does not include active3Krecord;
3K recording is validated directly from the saved clip. A transitional profile23
and short stale dimensions after selection are recorded, not silently discarded.

A001_021:135frames/5.625s,3000×2000 crop. A001_022:144frames/6s,UHD3840×2160crop.
All279DNG frames pass12-bit/24fps metadata, consecutive numbering and RAWstrip
bounds. All RAWpayloads are unique within each clip. Audio files readable.
Nine3K and threeUHD sampled green-plane images inspected: no obvious corruption.
283recordingfiles totaling3,071,995,478bytes plus8diagnosticfiles preserved.
Report: diagnostics/fullheight-preview-experiment3-return/REVIEW.md andreview.json.
No conclusion about exact sensor cadence, all-photosite filtering or long runs.

Only after this review, installed the non-sampling AutoRun from
prototype/fp3k-0.3.5-fullheight. Resident was already exact and NOT rewritten.
New AutoRun SHA c63eae39730677b1582bd1ca5a7093ddff684f2d58237e0b93b43e9b6be34760.
Resident remains8cf489ef8ad5e4c8723adac4dd421f6943a5d4f6338c030f70148764901b243e.
Temporary sampler commands removed; no startup delay or90-second routine.
Old log folders archived on both media and newFP3KM2folders created. Both
known disks ejected successfully. Installer tools/install_fp3k_everyday.py
binds verification hashes, reviewed logs and exact expected installed files.

Backup: <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-195154-658800
Next user action: one30-second battery removal to clear the old diagnostic run, then normal use. No further test requested.
