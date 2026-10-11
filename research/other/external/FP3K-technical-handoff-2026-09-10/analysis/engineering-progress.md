# Engineering progress: local decoding and state diagnostic

## Completed
- Wrote a source-hash-pinned LZSS extractor for the supplied firmware; decoded MAIN (49,245,696 bytes, mapped at 0xC0000000) and DAT1 (236,032 bytes, mapped at 0xC2EF6E00).
- Verified byte-sum checksums over both compressed sections against their DFI records: MAIN 0xA434830A and DAT1 0x00CF6567. These are container integrity checks, not cryptographic authenticity checks.
- Output is bounded by declared uncompressed sizes. The last match extends one FF byte beyond MAIN and four FF bytes beyond DAT1; this is recorded rather than silently treated as zero padding. Exact loader end-marker semantics remain unverified; investigated code/table addresses agree with independent upstream anchors.
- Matched ARM vector, shell echo pointer, gyro call instruction, and USB descriptor bytes against fpSup documentation/source.
- Extracted 70 sensor geometry records (100 bytes each), 70 corresponding timing records (32 bytes), and 70 mode-class pairs. Counts and table bases come from the DAT1 descriptor at 0xC2F1E654. Geometry accessor 0xC0321028 confirms the 100-byte stride.
- Located the sensor singleton at 0xC343B588. The firmware's mode_now route is 0xC032C720 → 0xC0322E48 → the singleton, followed by 0xC03212F8, which reads +4. Thus 0xC343B58C is the current-mode field to observe (pending live confirmation on this camera).
- Located recording settings at singleton 0xC31F865C +0x40, corroborating newer fpSup source.
- Reviewed stock mem-save and sleep handlers from the decoded ARM code; saved excerpts beside the extracted firmware.
- Built diagnostics/fp-state-v001: 24 sequential snapshots of three small RAM areas, plus static table and completion fingerprints. 74 files, 19,352 content bytes. Only stock `mem save` and `ctrl sleep` commands; no executable injection or explicit memory/register writes.
- Seven offline tests passed: valid synthetic capture, missing marker, wrong static fingerprint, wrong file size, unexpected sensor descriptor, overlapping LZSS match, truncated LZSS input. These are not camera tests.

## New findings relevant to open gate
Geometry record index 2 / sensor mode ID 98 at 0xC0B59E88 includes a 3032×2012 RAW raster, 3000×2000 output crop, and crop origin (16,6). Mode 143 has matching geometry. These are not yet usable video modes. Several fields equal 2 where full-resolution records have 1, suggesting a reduction path, but skipping versus binning and every-pixel contribution are unresolved. Mode 11 has the same raster with zero default crop fields; it is distinct from mode 98.

Full-raster candidates include mode 3 and mode 121 at 6064×4042. Their presence does not prove all-pixel Bayer downsampling at the required frame rate or a compatible recording path. No prototype resolution patch has been created.

## Correction to earlier upstream-derived notes
0xC37CE210 is scratch geometry and can be zero or stale, especially at UHD. Newer fpSup source explicitly supersedes earlier claims that it is a reliable general recording geometry source. The diagnostic captures it as supplementary evidence only and also reads CameraMgrSetting. A zero there is not a failed test.

## Current status after returned FHD/UHD diagnostics
Live captures confirmed the sensor object and observed FHD mode 218 and UHD mode 151. See fhd24-findings.md and uhd24-findings.md for timing and capture limitations. UHD logging was incomplete and wrote to the active SSD. Further v002 runs are on hold. The user also reproduced stopping with AutoRun removed and reports similar behavior historically, including near full charge; the recording-stop cause remains unresolved.

## Offline register and input-window trace
Decoded all 70 low-level sensor mode records at 0xC0B5FDAC, each 648 bytes: mode ID plus 161 register values. The descriptor is 0xC0B5FDA4. Validated every table-fed register-write block in 0xC03258C8 and cross-checked every mode ID against the separate geometry table. Reproduce with `analysis/venv/bin/python tools/extract_sensor_registers.py`.

UHD mode 151 and full-height modes 3 and 121 have identical values for all 161 table-fed registers. Modes 98 and 218 differ from 151 in 28 and 27 table-fed registers respectively (see generated comparison for exact values). These comparisons exclude later dynamic writes and other mode-configuration functions; identical table values are not proof of identical complete sensor state.

The image-input window is separately configured at 0xC0320008 from the timing record halfwords at +0xA, +0xC, +0xE, +0x10. Returned UHD S006/S007 both show object+0xC8 = 0, selecting the direct-coordinate branch. This passes x=8..6072 and y=354..3766 for mode 151, versus x=8..6072 and y=40..4082 for modes 3/121. The differences match the documented 6064×3412 and 6064×4042 rasters.

The call to Thumb 0xC0635ED8 consumes this structure and at 0xC0635F76 writes `(y_start << 16) | y_end` to MMIO 0x30100024. The x values undergo division/alignment by 12 before another MMIO write. This is static evidence of a hardware input-window configuration path, not a live register capture or proof that widening this window alone is sufficient.

## Next implementation dependency
Trace the image-processing geometry and raw-buffer allocation downstream of the sensor mode change. Establish whether the UHD reduction path can process 6064×4042 into a 3:2 Bayer output without losing rows or overrunning buffers. Timing, preview, raw packing, DNG metadata and audio/recording state also need compatible settings. No executable resolution patch or flashable modified firmware has been produced. No additional camera recording is needed for the current offline work.

Original firmware remains unchanged; SHA-256 rechecked as c9fa76f32f523bb2dc9a3fbda39418c31573cab6a1aa5c56d28c371862066ed8.

## Public-source audit and processing trace, 2026-09-09

See `open-source-research.md` for reviewed projects, primary documentation, pinned source snapshots and applicability. The reproducible upstream comparison matched 11,270 register values, 1,680 geometry words and 210 timing parameters across all 70 modes. This is extraction corroboration, not a recording feasibility result.

Further static trace leads, not live-validated:

- `0xC031BE60` processes a request whose +0x1C is a sensor mode. The call at `0xC031BF88` reaches `0xC0313400`, then `0xC0314708`, when changing modes.
- `0xC031BF90` obtains raw-manager singleton `0xC375D840` through `0xC0436590`; `0xC04370E8` constructs a raw descriptor. Current source pointer is manager+8, obtained by `0xC04375C8`.
- `0xC031BFC8` obtains current sensor dimensions using `0xC032C860` with mode 0x77. Subsequent code divides dimensions using descriptor+0x50/+0x54 reduction parameters and applies +0x48/+0x4C zoom factors against 1024. It derives centered even offsets against descriptor words 0/4.
- `0xC0438018` populates this descriptor from `param = [source+4]`: zoom +0x48/+0x4C from param+0x64/+0xD4; reduction +0x50/+0x54 from param+0x5C/+0xC8. Its `0xC04381E8` geometry helper reaches `0xC04361A0`, then dimension getters `0xC0435918` and `0xC0435948`. Trace those getters and the assignment of manager+8 next.
- `0xC031C0F8` copies target dimensions into acquisition state `0xC343A950`+4/+8. This gives a better diagnostic lead than the stale scratch geometry previously captured.
- Saved `raw-processing-mode-selection.asm` contains rate-dependent 3856×2170 comparisons and mode selection around `0xC02C89B8`. Its role in active recording versus development/playback remains unresolved; do not patch it on the basis of constants alone.

A RAM-only sampler remains a design idea, not an implemented package. It would need validated allocation bounds, a verified payload loader, recording-state gating and delayed file output. Current v002 remains on hold.

## RAW profile extraction and emulation

`tools/extract_raw_profiles.py` now decodes the separate RAW parameter loader at `C0439D18`: 65 column arrays, each spaced 0x4C8 bytes, giving 306 parameter rows. A 500-entry profile-to-row mapping starts at `C0BD05D4`; all valid entries are in range and all rows are referenced. Constructor `C043A158` maps a profile ID through that table, fills inline parameters at object+0x5C, then `C0434EC0` assigns object+4 to that parameter block. These profile IDs are distinct from sensor IDs.

`tools/verify_raw_profiles_emulated.py` executes the original loader and dimension getters with Unicorn 2.1.4. All 306 rows × 67 words (65 columns plus fixed 6064/4042 trailing words) match, as do all dimension getter pairs. Explicit nonzero/zero override cases pass. Firmware is mapped read/execute; emulated writes are restricted to destination parameters and stack. The macOS sandbox caused Unicorn to crash during initialization; the same test passed with approved execution outside the sandbox. See `raw-profile-emulation.json`. No hardware or scaling engine is emulated.

`C0435918` returns param+0xDC when nonzero, otherwise param+0. `C0435948` similarly selects +0xE4 or +4. Crop fields are +0x24/+0x2C. Horizontal/vertical reduction enums at +0x5C/+0xC8 are converted by `C022EE10` (0→1, 1→3, 2→5) and `C022EE90` (0→1, 1→3). Zoom fields +0x64/+0xD4 are separate and use 1024-based arithmetic in capture setup; no inference that a divisor alone proves all-pixel filtering.

The movie RAW selector `C043B828` uses tables `C0BE5810`, `C0BE59B0`, `C0BE5B50`, each 26 records of 16 bytes. `C043CCF8` searches their name strings. Records contain class=5, processing profile, sensor mode and a name pointer. UHD24 normal routes use profiles 417/423/429 and sensor 151; UHD24CROP uses 420/426/432 and sensor 152. FHD24 normal uses 419/425/431 and sensor 218. Normal UHD profiles have zoom=1600 while cropped UHD profiles have 1023. Exact active processing profile still needs live confirmation. Do not use the cropped profile as a full-width starting point.

Outputs: `raw-profiles.json`, `raw-profiles.md` (selected dimensions), `movie-raw-routing.md`, `raw-manager.asm`, `raw-parameter-loader.asm`, `raw-descriptor-construction.asm`, `capture-raw-geometry.asm`.

Remaining: identify actual RAW buffer allocation and hardware scaling/filter semantics; make a bounded RAM capture before asking for another recording. Upstream logger documents recording flags at selector `C347D1D4`: if 0x21, byte `C3476609`, otherwise byte `C347E08F`; publisher `C0332480` partially checked. It also uses native XMP object pointer `C358E140` and MOV active byte `C35A952C` to avoid file output during finalization. Those gates need verification for a new sampler. A 128 KiB USER allocation result is stored as {base,size,type} at `C3757A7C`; allocation handler and wrapper `C001CFD8` confirm base+0,size+4,type+8. Use exactly `memmgr bufmem get 0 131072`, no fourth alignment argument (stock bug overwrites requested size).

## FPD003 idle preflight ready; waiting for camera result

Built `diagnostics/fp-state-v003/fp-state-v003-idle.zip` and README. First hardware run must stay idle throughout, configured UHD true24 / 12-bit CinemaDNG with SSD connected. FPD003 directories must exist on both SD and SSD because stock file routing can choose the active media. No recording test is requested yet.

The new component `tools/raw_snapshot.S` copies one 832-byte record: sensor object, camera settings, bounded current profile object/inline parameters, acquisition geometry, and both recording flags. Invalid or unsupported pointers are skipped. Source/parameter pointer and mode changes set flags; this is not an atomic snapshot. Ten emulated cases pass.

`tools/raw_capture.S` restores the borrowed echo handler on entry, checks a whole-payload additive checksum and validates a 128 KiB allocation. It captures 120 records at nominal 250 ms intervals, then waits for both movie flags, XMP and MOV lifecycle signals to clear, plus sensor mode 8. It requires 13 idle observations (three seconds) and times out after 60 seconds additional waiting without writing a capture. File output uses the stock mem-save handler once. No sensor changes, gyro hook, USB worker, or flash writes. Payload is 1020 bytes in a verified zero stock cave at C072DE64; tested SHA-256 `c03eac8185417b4c99dc1f72061fb9efc31d59dfe9c801af7ed333f88ebfcd40`.

Eight wrapper tests pass with simulated sleep/file handlers: short take, late stop, no take, persistent recording, persistent finalization, bad allocation pointer, insufficient allocation and corrupt payload body. Write guards enforce destination/stack/echo-slot bounds. The decoder is exercised against emulated capture output. Real file handling and camera scheduling remain untested, and a body checksum cannot guarantee that corrupted bootstrap instructions are safe. Initial hardware request is therefore idle-only.

`tools/build_raw_capture_package.py` assembles and matches the tested payload hash, audits emitted commands and writes the ZIP. Before arming, AutoRun saves POOL.BIN and LOADED.BIN. After return it restores the echo pointer again and displays FPD003_CHECK_FILES; that message does not guarantee STATE.BIN was saved. Expected files are 12, 1020 and 99904 bytes respectively. No filesystem commands follow capture return in AutoRun.

User return location: `diagnostics/v003-idle/SD/FPD003` and `diagnostics/v003-idle/SSD/FPD003`. Use `tools/read_raw_capture.py` to validate full output and code readback. If no STATE.BIN, first inspect POOL and LOADED and reported screen behavior. Do not repeat or advance to recording automatically before examining the first result.

Full-height recording remains unimplemented. Buffer allocation, Bayer filtering/every-pixel contribution, DNG packing and sustained recording still need work; the new profile/routing map narrows that work but is not an open-gate patch.

## Returned FPD003 idle test passed

Validated `diagnostics/v003-idle/SSD/FPD003`: exact loaded code, expected allocation, complete 120-record capture. All samples stayed at sensor mode 8, processing profile 5, recording flags zero, and all 67 parameter words matched stock. UHD setting dimensions remained 3840×2160. See `v003-idle-findings.md` and `v003-idle.json`.

Prepared one short recording test using the identical AutoRun/payload. Created both return directories under `diagnostics/v003-uhd24/{SD,SSD}/FPD003` before requesting the user to copy files there, per their standing preference. Need the active recording profile before deciding which full-height processing parameters to prototype. Do not build a resolution patch based solely on the idle profile.

## Confirmed UHD24 live recording baseline

The v003-uhd24-retry return completed all 120 samples and definitively observed sensor151/profile429 during recording, stock parameter match, RAW3856×2170/crop3840×2160/zoom1600. See v003-uhd24-retry-findings.md. No further recording is required simply to identify the profile. The clip stopped itself at ~3s and contains only ten24fpsDNGs versus2.875s audio; cause unresolved. Full clip preserved. User canceled USB remote-control work; daemon stopped, USB shell AutoRun replaced with original FPD003 diagnostic. Do not resume USB-control development unless requested. Next is offline buffer/reduction tracing from confirmed profile429.

## Offline full-height geometry trace

See fullheight-processing-trace.md and firmware/raw-geometry-emulation.json. Executed stock C0438018 descriptor builder and C0325228 sensor path selector for confirmed429 and hypothetical3032×2020 variants. Dimensions-only change atzoom1600 creates large crop offsets; zoom2048 gives3032×2021 pre-crop extent from6064×4042. Preview remains2016×1135, factors3/3; raw factors1/1. Traced ratio register programming and packed-row register C0630E90; tested widths3856/3032/3000/6064. Identified DMA destination register30182280 set byC0631B98 from capture request+38. Allocation ownership upstream ofC030CF98 still untraced; callersC0379180/C0379C28. No deployable resolution patch; filter/all-pixels behavior and full-height24 timing unproven.


## Stock RAW frame-size callback verified offline

See cinemadng-frame-size-trace.md and firmware/raw-frame-size-emulation.json. New verifier tools/verify_raw_frame_size_emulated.py executes unmodified C03D9630 through C0135D40 with stack-only writes. Twelve geometry/boundary cases pass. Stock3856×2170 returns12,551,292 bytes, matching StripByteCounts in all ten returned UHD DNGs; observed header plus512-rounded payload matches all complete file sizes. Candidate3032×2020 returns9,186,968 bytes (+8 beyond packed pixels), rounded9,187,328. Candidate file size with stock header would be9,266,176, but unchanged header is an assumption.

Mapped explicit MovRecFuncStateCinemaDng singleton C358DC80, frame handle lookup C03753C0 (96-entry manager C351FF44), and CinemaDngFile size call C03A540C. C069ADE0 writes a linked list of buffer/length pairs. Found descriptor-size comparison C0379FC0..C037A018: changing only one descriptor copy can trigger mismatch handling; exact live-route applicability remains unconfirmed. C03A4660 is a64-bit balance subtraction, not verified RAM allocation. Sensor timing, all-pixel filter semantics, actual DMA allocation and descriptor propagation remain unresolved. No camera package installed or requested; continue offline.


## SD-sized full-height alternatives and sensor-write sequence

User accepts lower output resolution as an intermediate; preserve full sensor area as goal and distinguish it from all-pixel contribution. See sd-fullheight-intermediate.md. New verify_sd_intermediate_emulated.py tests stockFHD431 plus1920×1280 candidates from429/431 and1728×1152 from429, using stock descriptor/path/size routines without stubs. All pass software geometry checks.1920×1280 uses RAW1936×1290,3,746,172B/frame,89.908MB/s24 before overhead;1728×1152 uses3,039,804B/frame,72.955MB/s24. Stronger ratios3200/3550 are unverified in hardware; stockRAW ratios never exceed1600. Thus smaller output helps SD bandwidth but is not clearly an easier patch than3K. Sigma officially supports FHD12-bit up to59.94fps on UHS-II; custom mode/card maximum remains unknown.

New verify_sensor_table_sequence_emulated.py passes16 cases of165 sensor-register requests, with I/O explicitly mocked. CE=0 andD1-D3 encode fixed software toggle0x2FFFA/0x2FFFB atC2F1E7B0, independent of mode. Optional override flag sensor+58 iszero in all120 existing UHD snapshots. This narrows dynamic table-tail uncertainty, not all mode-transition/timing behavior. No further camera request, installation, or remote-control work.


## FP3K G1 cropped geometry hardware test ready; media needed

User chose3K and requested completion. Built an actual guarded RAM test package in diagnostics/three-k-g1/fp3k-g1.zip, AutoRun in card/AutoRun.txt. This is explicitly NOT the final full-height patch: it retains sensor151 and RAW zoom1600 while changing profile429 base/override dimensions to3032×2020 and crop3000×2000. It is a live buffer/writer validation step before sensor-height changes. No sensor/flash changes or remote control.

Payload tools/three_k_geometry.S is492B atC072DE64, status16B atC072E800. Hash86962614345637ca9a96ef0b6fca4e22d8adbad34da56e5c962ea76afb8e17d3. Restores echo on entry, checks additive checksum, checks sensor8/both recording flags/XMP/MOV idle, compares all six expected stock words before writes, rechecks idle, writes six words, readback/rollback on mismatch. Offline tests pass16 cases including every stock-word mismatch, busy guards, corrupt body, second-check race, already-applied and forced readback rollback. After success stock loader tested all306 profiles: only429 changed. Descriptor/crop offsets16,10/zoom1600 and RAW byte count9,186,968 confirmed. Bootstrap corruption and concurrent camera execution remain limitations.

AutoRun12,826B, hashb6783dd5db576951de42866f256d5bea42f20cc87b46972d6ac8cad61e5cf756. It writes LOADED.BIN before running and STATUS.BIN plusWORD0..5.BIN after; all file writes precede green FP3K_G1_TEST. TEST means returned, not guaranteed application. No background worker. Single requested2–3sec REC take in UHD true24(not23.98),12-bit CDNG, crop mode off, SSD. If self-stops do not retry. Need one DNG or complete short clip plus diagnostic folders from both media. Destination directories already created under diagnostics/three-k-g1-return/{SD,SSD}/FP3KG1 and clip. Decoder tools/read_three_k_geometry.py validates exact payload/status/readbacks and refuses incomplete/numbered mixed generations. Decoder cases and ZIP integrity checked.

No removable media mounted (/Volumes onlyMacintosh HD andTimeMachine snapshots); package NOT installed. Next user action: mount SD and SSD so we can install and verify files, preserving prior AutoRun/results. Remove/rename AutoRun after the test; reboot restores stock tables but would reapply if file remains. Full-height sensor timing, RAW filtering/all-pixel contribution and actual new recording results still outstanding.


## FP3K G1 installed for first camera recording test

Verified SD UUID<SD_UUID> (disk10) and SSD UUID<SSD_UUID> (disk11). Installed hash-verified12,826B AutoRun only on SD; clean FP3KG1/INFO.TXT folders on both. Prior AutoRun files preserved locally in diagnostics/three-k-g1/install-backup/20260909-183447; original disabled files remain on SD. Existing FPD003 and clips untouched. Installation record diagnostics/three-k-g1/installation.json. Both media ejected successfully. Await one2–3s REC take after FP3K_G1_TEST using UHD true24,12-bit CDNG, crop off, SSD. This is cropped3K geometry validation, not full-height. Return both media to collect results, verify status/payload/words and DNG, then disable AutoRun.

## First G1 hardware result: cropped 3K recorded; text layout updated

Collected SD (UUID<SD_UUID>, now <MEDIA_MOUNT_B>) and SSD (UUID<SSD_UUID>, now <MEDIA_MOUNT_A>). Mount names swapped from installation; identified by UUID before any writes. Diagnostic results were on SSD, SD INFO only. All result bytes verified locally. SSD A001_002 copied in full:121 files,119 DNGs plus audio/sidecar, hashes in diagnostics/three-k-g1-return/clip-manifest.json. Readback status16, exact492B payload, all six replacement words correct. All119 DNGs report RAW3032x2020, crop origin16,10, visible3000x2000,12-bit uncompressed,24fps,9,186,968 strip bytes. Every strip fits file extent.119 frames=4.9583sec, consistent with user five-second take. First/middle/last approximate uncalibrated previews show coherent scene, not comprehensive quality validation. See frame-metadata.json/readback.json/preview.jpg in return folder. Full sensor area remains unimplemented; sensor151/zoom1600 unchanged. This hardware result validates cropped geometry and short recording only, not sustained operation or every-pixel contribution.

User requested status label upper middle below record control. Builder temporarily changes verified5.02 text handler x to208,y96 (width384), clears three OSD buffers and draws, then restores both original instructions after final label. Original firmware words asserted; replacement ARM instructions disassembled; ZIP checked. Payload unchanged. Revised13,354B AutoRun SHA256d649a09ee74c95d2a9ba6a6aa28fb6de0d2248e7ae7cde0503f2617239d52866 installed and readback verified on SD. Exact new position not yet visually confirmed. Previous package backed up in layout-original-backup; results retained locally and renamed on each medium FP3KG1-complete-20260909-114403; fresh FP3KG1 folders prepared. layout-installation.json records current revision; installation.json refers to first revision. No additional recording needed just to check text placement. Official fp FW5 manual advises waiting for busy/access lamp to stop lighting/flashing before removing media; power off normally first.

## F1 full-height candidate built; awaiting media for installation

User authorized full sensor coverage work after G1 success. See fullheight-f1.md. Found and coordinated additional56-byte receiver record beyond prior timing/geometry hypothesis. Built18-word guarded F1 patch: native mode3 full-height geometry/input/receiver windows applied to151, stock true24 timing preserved, profile4293K dimensions andratio2048.636B payload;28 guard/rollback tests pass. Native setup emulation verifies four cases: F1 input and receiver arguments exactly match native3, timing remains445/6740/tail1145. All306 processing rows validated; descriptor and byte count match expected3K. Sensor I/O/receiver endpoints mocked for capture comparison; actual full-height coverage, all-photosite filtering, Bayer phase and stability remain untested. Stock preview/auxiliary record retained, LCD may crop to16:9. Package diagnostics/three-k-f1/fp3k-f1.zip READY NOT INSTALLED; return folders created. Current G1 with revised label is still on ejected SD. Need SD and SSD remounted; verify UUIDs (names swap), preserve data, replace SD AutoRun with F1 and createFP3KF1 on both. Request one short REC take after setup; collect same-position stock still later to verify full coverage. No firmware flash or USB remote control.


## F1 installed for first full-height recording test

Verified both known media UUIDs after SD reinsertion. Installed F1 AutoRun17,202B, SHA2564484099a87bae417d8df862b1fec71357662b0e9fe304bf8097b189403593cbd on SD only. Fresh FP3KF1/INFO.TXT on both; previous AutoRuns and current diagnostic folders backed up in diagnostics/three-k-f1/install-backup/20260909-115959; clips and other results untouched. Readback and ZIP checks pass. Both media safely ejected; installation.json records details. Await one2–3sec REC take at UHD true24fps,12-bit CDNG,SSD,crop off after FP3K_F1_TEST and access lamp off. No retry if corruption/self-stop. Maintain camera/lens position for later stock still reference. Full-height acquisition and image quality are unverified until camera return.

## First F1 camera return collected; AutoRun disabled for reference still

See fullheight-f1-return.md. User booted twice (Q menu on first), GUI flickered but live image did not; user stopped recording manually. One surviving diagnostic generation shows status16, exact payload, all18 words applied. SSD clipA001_003 has158 consecutive12bit24fpsDNGs,3032×2020/crop3000×2000,6.5833seconds. All160 clip files hash verified locally; strip sizes valid. First/middle/last approximate previews coherent, camera pans. Actual full sensor FoV still unproven: need stock full-resolution3:2DNG reference from same focal length/position/scene. Returned SD AutoRun backed up and disabled; no new patch installed. Prepared but did not install same-payload no-overlay variant to isolate GUI flicker later. Do not equate UI-only flicker with verified reducer/preview cause or claim it is fixed. Return folders and reference-still directory already exist.

F1 return collection completed: verified no active AutoRun on either medium, both ejected successfully. User next action: normal STILL-mode full-resolution3:2DNG reference of same scene/position/focal length; no modified recording needed.

## Handheld stock still collected; fixed-camera comparison now needed

See fullheight-reference-comparison.md. PreservedSDIM0165.DNG35,479,217B SHA256b9982e555a531c7cb9661723ca68d4a1653502531c32aeee06c6a92b5f03b826. Actual full-resolution14bitRAW6064×4042/crop6000×4000,45mm matching video metadata. Still's tighter apparent framing also exists in actual RAW, not just embeddedJPEG. User says seated in same spot and offers stationary test. Feature registration finds matches but scale/pose mismatch; cannot certify sensor FoV from handheld pair. Do not assume camera moved closer or call full-height confirmed. Next user action: stationary stock3:2DNG baseline, manual focus locked, same lens/camera position retained; returnSD+SSD while leaving body/support untouched. AutoRun remains disabled. After baseline collection install previously prepared no-overlay F1 candidate for paired video/UI-flicker isolation. Created diagnostics/three-k-static-return/{reference-still,clip,SD/FP3KF1,SSD/FP3KF1}. New patch not installed yet.


## No-overlay F1 installed for user-requested two-boot stationary test

User requested installation now to avoid returning between still/video. Installed active no-overlay AutoRun on SD only:16,462B SHA256d2003f2a0af1d845394c5fc3747f1325f8c6b23977159034be4388430df75a59, unchanged636B F1 payload. Verified media UUIDs, backed up disabled AutoRuns/results, renamed priorFP3KF1 on each medium and created freshFP3KF1/INFO.TXT. Both safely ejected; record diagnostics/three-k-static-return/installation.json. IMPORTANT next sequence supersedes earlier disabled-file/rename suggestion: stock still to SSD with SD REMOVED; camera off; insert prepared SD and switchCINE; reboot, waitTHREE MINUTES plus busy/access lamp off (NO onscreen TEST in this variant); one2–3sec UHD true24/12bit CDNG take, crop off. Keep body/focal length/manual focus fixed throughout, return both media once afterward. SSD contains no active AutoRun, ensuring first boot stock. User need not return or rename files between takes. Observe whether GUI flicker persists; no-overlay is an isolation test, not proven fix.

## Stationary FoV comparison supports full-frame3:2; no-overlay run had no flicker

See fullheight-static-findings.md. BothSSD stills0166(overexposed)/0167 preferred were taken withoutSD, no battery removal; user reports slight camera movement.207 consecutive12bit24fpsDNGs=8.625s,3Kdimensions/strip sizes valid. ActualRAW registration against full6Kstill matches scene scale near1.0 (best211inliers,0.70pxmedian residual; local1.0016/0.9942). Strong practical full-frameFoV evidence, not every-photosite/filter/quality certification. No GUI flicker reported withoutoverlay.

IMPORTANT reset correction: new exact-payload diagnostics status4 becauseC0BE3F54 already3032; all18readbacks already F1targets. Refused redundant/stock-mismatch invocation, not evidence of unset geometry. Decoder now reports invocation_result andreadbacks_match_target separately. RetainedRAM versus duplicate invocation remains unresolved. Normalpoweroff+SDremoval is NOT verifiedstock reset; previous blanket claims are superseded. Reset-notice files added. Preparing same no-overlay payload for cold-start30second recording while media mounted, to test clean application and longer stability; no new still needed. Newreturndirs created diagnostics/three-k-coldstart30-return.

Cold-start30second test installation complete: exactsame no-overlay AutoRun hashd2003f2a0af1d845394c5fc3747f1325f8c6b23977159034be4388430df75a59, payloadunchanged. PriorstaticFP3KF1 results preservedlocally andrenamedonbothmedia; freshFP3KF1 folderscreated. Both safelyejected; diagnostics/three-k-coldstart30-return/installation.json recordsdetails. ActiveAutoRun onSD, noAutoRun onSSD. Askone30secondtakeafterbattery/externalpower cold reset and3minuteidlewait; no onscreenTEST. Earlierstaticcollectionautorun_disabled describescollectionphase, notlatestinstallation.

## No-overlay F1 30-second return verified

See fullheight-coldstart30-findings.md. SSD A001_005: 730 consecutive 12-bit24fpsDNGs, RAW3032×2020/crop3000×2000,30.4167s; WAV30.5018s. All732files6.770GBcopied and source/destination SHA256verified. Allframe metadata/strip bounds pass;730distinctRAWstrip hashes. Ninepreviewsshowcoherentsoftindoorimagery,noobvioustearing/blankregions; cannot assessfine-detailquality. Exactpayloadstatus16,all18targetreadbacks: cleanapplicationthisinvocation. Asyncquestionpendingforbattery/externalpowerreset,manualstopandGUIbehavior. SameSDno-overlayAutoRunretainedunchanged,hashverifiedandbackedup; no newtestinstalled. Full-frameFoV supportedbypriorstationarycomparison; allphotosite/filtersemanticsandlongdurationremainunverified. Evidence/collectionrecord:diagnostics/three-k-coldstart30-return.

User confirmed battery removed, recording stopped manually, and no flicker or other problems. Both media safely ejected; same active no-overlay F1 remains on SD.

## FP3K 0.1 playable prototype packaged

User prioritized a finished prototype to experiment with. Created prototype/fp3k-0.1 and deterministic prototype/fp3k-0.1.zip. Camera AutoRun and636Bpayload are byte-identical to the no-overlay successful30.42s test; no new camera runtime changes, no new framerates. START HERE documents menu remainsUHD,visible3K12bit24,3minuteidlewait eachboot,nooverlay,stockpreviewcrop,storage222MB/s,reset and unsupportedsettings. EVIDENCE distinguishes full-frameFoV from unprovenallphotositequality. Helpers Enable/Disable/Check Last Boot use stockmacOSPython3+diskutil, exactuserSD/SSDUUIDs, verifiedbackups, preserveclipsandoldlogs, rejectotherAutoRuns, ejectoncompletion. Eight temporary-media lifecycle/negative tests passed using/usr/bin/python3. Package hash list and ZIP extraction checks pass. Build tool tools/package_fp3k_prototype.py; tests tools/test_fp3k_desktop.py. No media mounted, no new install this turn; existing ejectedSDstillhasidenticalworkingAutoRun. Asyncreconnectrequest pending, but reinstallnotrequired to shoot withtheseinstructions. Need preserve results and verifyUUIDbeforeanyfuturemediaaction.

FP3K0.1 installed after user reinsertedbothmedia. Helper verifiedUUIDs,backedup priorAutoRunanddiagnostics toprototype/fp3k-0.1/backups/20260909-135720-109170, preservedoldmediaresults, refreshedFP3KF1both, installedandverifiedexacttestedAutoRunSDonly. Both disks11/10ejectedsuccessfully. Latestrecordprototype/installation.json. ReadyforuserplaywithinUHDtrue24/12bitSSD/cropoff;3minuteidlewaiteachboot.

## User requests native menu and smoother experience

Traced native MovieRecord MV_Resolution registration C057A448,selectioncallback C057A6A0,mapping C06BD9E0/providerC06BD960,default2pairtableC2E401FC(value0/index0,value1/index1;liveoverrideandUI-to-sizeenumadapterunresolved),native size tableC0742228(enum2FHD,enum3UHD). Savedstaticassertions/map/disassembly analysis/firmware/menu-integration; conclusions analysis/native-menu-integration.md. Actual settings target comes throughvirtualslot13C, stillunresolved. Unknownselectionmaps0,unknownsizegetsInvalidMovSize; thirdlabelaloneisnotmodeaddition. Native toggle needs guardedapply+restore,serializedidletransition,UIreadbackandprivate/persistencestate. Investigatedupstreamfile-backedloader as startupimprovementcandidate; currentAutoRun495memset/20save/1echo/sleep5s,3minuserwaitconservative. No UI/runtimechangesbuiltorinstalled; FP3K0.1unchanged. No newcamera action needed for ongoingstatictrace.

## Native movie callback execution and live-object diagnostic prepared

Resolved actual MovieRecord mapping provider via C0564248→C058C4D0,templateC2DEAD3C,vtableC2DEAD7C,+5C=C06BDA30;actualtableC2E4020C has3pairs(enum3/index0,2/1,4/2). Supersedesgeneric0/1mappinghypothesis. Thirdvalue NOT provenusableslot. FixedscreeninstanceC3785308,publishedC37B7538;native+44getterC05643F8returnsscreen+24settingsreceiver. Five actual callback emulationcasespass,settingssinkmocked; tools/verify_native_menu_mapping.py and firmware/menu-integration/native-callback-verification.json. Unknownlive+24receiverblocksreliabletransitionhookselection. Preparedread-onlyfixed-address menu-native-v1AutoRun(9smallmemsave,3sleep,nohooks/settingswrites);NOTINSTALLED. RequiresuseropenUHD/FHDmenu3minutes,noREC. Returnfolderscreated. CurrentmediaejectedwithFP3K0.1stillactive; requestreconnecttoinstalltemporarydiagnostic afterbackup. READMEhascoldresetandreturninstructions.

## Native-menu v1 diagnostic installed

After SD reinsertion verified both known UUIDs (SD <MEDIA_MOUNT_B> disk10, SSD <MEDIA_MOUNT_A> disk11). Preserved active FP3K0.1 AutoRun and prior FP3KF1/FP3KMN results in diagnostics/menu-native-v1/install-backup/20260909-141718-651590. Installed604-byte read-only menu AutoRun SHA256a7a8ac2823f8993141a5f827d83b9b62cfe493cf00e17719bf9eb170117abf91, freshFP3KMN onbothmedia, verifiedSDreadback. SSDhasnoAutoRun. Bothsafelyejected; latestdiagnostics/menu-native-v1/installation.json supersedes prototype/installation.json for activecardloader. Needbattery/externalpowerreset,bootCINE,opennativeUHD/FHDresolutionchoice,leaveopen3min,noREC,waitaccesslampoff,poweroffandreturnboth. Decoder tools/read_native_menu.py ready. Prototype temporarilynotloaded bythisSD.

## Menu v1 return analyzed; native setter verified; v2 diagnostic installed

V1 all9BINs onSSD copied/hashverified. Samples1/2 menu receiverC3768D84,screenC3785308/vtableC0D19654,enumproviderexpected. UseronlyUHD/FHD,scrubbedtoavoid sleep. Traced receiverconstructorC04ACDA8, vtableC0CDE064/slot13C=C04AAE70→C005C020→C00658E8→C0074EC8. ResolutionpropertyID0x69 atstorageC31AC59C+680=C31ACC1C, vtableC07421BC. NativepathwritesvalueandonlynotifiesC00911A0whenchanged. Sixemulationtests pass,includingreentrancyguard,invalidindexstorage0,thirdvalue4; notifications/backingstorage/service/loggingmocked. tools/verify_native_menu_setter.py. Need explicitrefresh3K↔UHDsameinternalenum3; nohandoffimplemented.

Nextruntimegap: native10subscriber notificationtable; identifyit beforeinferringpipeline restart. Preparedandinstalled menu-native-v2 read-only872BAutoRun SHA2561da6f4db6481398bc3cff5d87565221528578e5b8f598bf51ffd15daf16c7b14,5fixedregions×3samples(screen,receiver,service128,storageheader8,property28), no codeor settingswrites. Priorv1AutoRun/resultsbackedupunderdiagnostics/menu-native-v2/install-backup; originalFP3Kprototype remainsbackedup. Bothmediaejected; lateststate diagnostics/menu-native-v2/installation.json. Ask samebatteryreset,openCINEUHD/FHDlist3min,noREC,returnboth. Returnfoldersexist. Needv2decoder inspect service+24 ten pointers andproperty+8 mastercontext consistency; useactualcapturedvaluesbeforetracing observermethods. No actualmenupatchinstalled.

## Menu v2 return collected; native notification fanout verified

All15 expected BINs on SSD copied and hash verified in diagnostics/menu-native-v2-return. Three snapshots identical, property0x69 cached3, enabled contextC31AC540 subscribersC3765E14/C3762BF0. Resolved first to exclusion rules and second to embedded MovieRecordHandler observer, then native UI resolution refresh. Detailed addresses and caveats in native-menu-integration.md. New verify_native_menu_notifications.py passes three ARM emulation cases using captured context and constructor-derived observer state; UI/exclusion/getter boundaries mocked. This proves routing, not sensor restart or native choice insertion. No further duplicate menu test needed; native menu patch remains unfinished.

After collecting v2, restored byte-identical tested FP3K0.1 through its checked installer, preserving diagnostic AutoRun and logs. Both known media safely ejected. Current state prototype/installation.json supersedes menu-native-v2/installation.json. No native menu patch installed. Native widget event registration additionally traced to Thumb C05DCB18→C05D9EB8; named lookup C05DB418 resolves a node whose +0x18 holds an allocated callback pair. Widget list construction remains unresolved.

## User demands finished native list patch with no startup wait — development continues

User explicitly requests: finish patch, no startup wait, add resolution into native list. No completed menu patch yet; do not claim done. Built tools/fp3k_file_loader.S and build_fp3k_file_loader.py: 280-byte bootstrap at C072E264 loads the exact existing636-byte F1 from SD \\FP3K.BIN into C072DE64. Restores echo before file I/O, initializes media manager, pins volume1, bounds read to636, requires exact read count and additive checksum0 before cache clean and entry. Uses12-byte native file object+4-byte count on stack, destructor closes; no sleeps/tasks/overlays. 73 bootstrap commands (single memory writes; upstream triple repetition was for three OSD buffers, not proof mem writes require triple). Guarded F1 can refuse if boot is not yet idle, so this is ONLY an interim startup component, not a finished menu-selected mode.

verify_fp3k_file_loader.py passes8 ARM cases:valid,missing,empty,short,checksum,busy,wrongstock,stale-valid/short; actualF1runs, filesystem/cache mocked, capture table writes absent on failures, callee regs/stack/echo retained. Files in prototype/development/file-loader. Hardware boot latency and readiness remain unknown. Prepared diagnostics/fastboot-v1/card (75commands withtwo diagnostic memsave; no timedwait), manifest,README and diagnostics/fastboot-v1-return/{SD,SSD}. NOT INSTALLED. Current mounted media inventory has no SD/SSD. Asyncrequestsent to reconnect both for normal-startup test. User must removebattery30sec once for coldreset, then normalstartuprecord5sec withno3minwait. Their currently ejectedSDstillhasworkingFP3K0.1, not newloader. Do not install until matchingUUIDs verified, all oldAutoRun/payload/logs backedup, freshFP3KFBfolders both. Check returnedstatus (loaderK3L2codes21/22/23hex failure; successful loadedF1 overwritesstatusK3F1) andDNGdimensions to detect early-idle refusal. Need reportnativeitemunfinishedhonestly.

Menu work advanced while awaitingmedia: NBU resource reader indexes303599records, findsresolutioncontrol/list bindings but rowdatasource unresolved. New verify_native_resolution_ui.py proves nativeenum3/2/4→UIindex0/1/2throughC05931D0→C0593F30→C055DD10; actual56Bmessagecreationexecutes, queue delivery mocked. Detailedaddresses in native-menu-integration.md. Remaining blockers: native third row and label, private selection/readback, reversible18wordcapturetransition and mode-change/recording synchronization. No runtime menu modifications installed. No subagents used.

## Native list integration built, hardware demo next

See latest analysis/native-menu-integration.md and prototype/fp3k-0.2-native-menu/START HERE.md. User rejected separate fast-loader demo, so completed integrated three-row resource + reversible18-word resident + no-timed-sleep loader offline first. 105 resident,13 integrated boot,2 nativeCSV and3 localized-label cases passed, with boundaries documented. No native build camera-demonstrated or installed yet. SD is visible/UUIDverified; async request asks to connect SSD for integrated installation. New installer prepared in tools/install_fp3k_native_menu.py, return folders created. Do not claim finished general-use firmware: physical switches/presets/removal, UI cache/rendering and live transitions remain unvalidated; all-photosite behavior unknown.

## Native-menu demo installed — 2026-09-09 15:33

User connected SSD. Ran tools/install_fp3k_native_menu.py --eject successfully with verified SD UUID<SD_UUID> (disk10) and SSD UUID<SSD_UUID> (disk11). Existing patch/diagnostics backed up to prototype/fp3k-0.1/backups/20260909-153312-468405. Installed SD AutoRun4610B SHA2565e98742c34aff04c2918edc6a26c76aff89d7e1e640ddf0faf155876b04c2d13 and FP3KMENU.BIN2480B SHA2565ae073a63ac6626c97cf262a3d707738b343c73fb46f4cc3c3a0da877d2ff7b9, readback verified. FP3KM2 folders prepared on both. Both disks successfully ejected. Installation record prototype/native-menu-installation.json. Await integrated camera demo: initial battery30s reset, CINE/DNG12/true24/cropoff/SSD, inspect third resolution row,5s3K then5sUHD with REC/manualstop. No timed startup wait. Camera rendering and switching not yet verified.

## First integrated demo: third option absent

User reports no 3000x2000 option. Do not claim native-menu integration works or infer resource caching as the established cause. Both media currently unmounted. Requested SD+SSD reconnect to collect FP3KM2 startup snapshots and distinguish loader/install failure from resource/UI behavior. No repeat recording requested. Preserve current diagnostic evidence before any new installation.

## Native navigation correction

User clarified row appears after a second but cursor cannot reach it. Returned four SSD startup snapshots all verified in diagnostics/native-menu-demo-return: loader and residentstatus16, exactpayload, exactthree-rowCSV, noactive3K. Root-cause candidate verified in native controlValue execution: resource C1A7099C still maxindex1; nativehandler mapsrequest2→1. Correctedmax2 accepts2. Builtv0.2.1 with guarded/reread/rollback wordC1A709BC0x803F→0x40.107resident+13boot+2nativecontrollercasespass. Prepared correctedpackage and installer, new returnfolders diagnostics/native-menu-navigation-return. See analysis/native-menu-integration.md for exact evidence and mocks; do not claim camera selection works until user verifies. Prior v0.2 preserved in prototype/development/native-menu-v020.

V0.2.1 installation completed 2026-09-09 15:41:53. Readback verified AutoRun4655B SHAd36f359ef9f171d9a42a5d196d355406f7e7f772ab1260f996edd2496746fa13 and resident2564B SHA5265f2551f237c1488b4719d366e15783245771e30ce6114f33666692b3803fe. Backup prototype/fp3k-0.1/backups/20260909-154153-548344. Both disks successfully ejected. Await user camera test of third-row navigation/selection, then3KandUHDclips if selectionworks.

## V0.2.1 selected recording verified; follow-up UI/preview work

User successfully selected3K and recorded, forgot UHDrestorationclip. Reports HUD incorrectmode, QS lacks3K, previewstillcropped; adds missing shortlabel before3000x2000. Chose concisebadge3K (notOG/FSA, allphotositeclaimunproven). Bothmediafound/reidentified automatically; saved5SSDstartupfiles in diagnostics/native-menu-navigation-return/SSD/FP3KM2, collection.json. Loader/residentstatus16, CODEexact2564B SHA5265f2551f237c1488b4719d366e15783245771e30ce6114f33666692b3803fe, RANGEmax2. MENUactive0 is startupsnapshot beforeuserselection, not evidence of recordingfailure.

Copied entirelatestA001_009 into return/clips/A001_009:96files,871790890bytes, allsource/destinationSHAverified.94consecutiveDNGs,3.9167s atmetadata24fps,12bit,3032x2020RAW,crop16,10/3000x2000; WAV4.0058s. Validation/frame-metadata/contact-sheet saved under return/validation. Allformat/stripboundchecks pass. Viewed9green-plane samples: coherent handheldcolorcheckerontable, noobviousblankregions/tearing. Notcalibratedcolororallphotositequalityverification. Tools/inspect_fullheight_clip.py needsnumpy/Pillow: use bundledruntimePython <USER_HOME>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 (analysisvenvlacksnumpy). No repeat UHD-only test requested yet; UHDrestorationremainsunverified.

Offlinefollowup: tools/inspect_xci.py safelyindexesexact2259NBRrecords (not unboundedscan), extracts15resolutionassets, validatesXCheader payloadsizeplus32, decodesboundedLZ4block atoffset51 withlengthatoffset47. Alloutputsrasterwidth*height*2bytes; outputanalysis/firmware/ui-assets/{index.json,*.raw,nibble-planes.png}. Viewedstocklabels: set_resolution_1,font_menu_MB_resolution_1,qs_resolution_1_S,M_resolution_1 allUHD; HUD alpha includesoutline. Customassetencoding/native decoder nottested orinstalled. MV_Resolutionbinds mainmenuandseveralUIvariants; LV_Resolutionis separateHUDvariable. ARMpublishersC059C640andC059C9F0 mapstockenumusingC06BD988thenqueueLV_Resolution. Generic-screen resolution callbackC05824D0 mapsnativeenumwithC06BD9E0 and passesr2=1 tosetter, unlike mainmenucallbackr2=0; requirespreservingapplysemantics. MainC0580AD4 registers callback forMV_Resolution, unregistrationC0581164; screenactivepointerC37B75C8. Resolutionbindingindex analysis/firmware/menu-integration/all-resolution-bindings.json. NoHUD/QS/previewfixbuiltorinstalledyet. Previewdescriptor still2016x1135, separatefromRAW; seefullheight-processing-trace.md. ActiveHUD/QSlayoutneedsvisualidentificationamongvariants beforetailoringdisplayresources.

Media content left at workingv0.2.1; SDpayloadandAutoRunhashesreverifiedandbothverifieddevicesejected successfully. Nextuserinputrequested: photoofliveHUDandQSresolutioncontrolwith3Kselectedtoidentifyactivedisplayvariants. Thisisvisualcontext, notanotherrecordingtest. HUD/QS/badge/full-heightpreviewremainpending; nofuturebackgroundworkscheduled.


2026-09-09: BuiltFP3K0.3nativeUIcandidate; main3Klabel, twoHUDpublisherhooks, QSselection/three-valuebounds, privateNBRbadges, temporarynativeparserrecordextension. See native-menu-integration.md finalsection fordesign/testevidence. Offlineverificationpasses; nofullheightpreviewchange. Preparedpackage anddemo directories; installingonknownmediawithbackup/ejection. CameraUIstartup/caching remainsnextvalidationstep; no photo required.

Installation completed: 2026-09-09T17:11:38.708406. Version0.3-native-ui written and hash-verified; disk10(SD) anddisk11(SSD) safelyejected. Backup: <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-171138-656335. AwaitingcameraUIandUHDrestorationdemo.

## 2026-09-09 — v0.3 UI failure collected; v0.3.1 layout repair installed

User photos IMG_2209/2210/2211 (Downloads HEIC, decoded PNGs in diagnostics/native-ui-demo-return/photos) confirm settings summary literal `3`, live HUD UHD, overlapping QS resolution graphics. Both known media UUIDs reidentified; names had swapped (SD Untitled/disk10, SSD Untitled 1/disk11). Copied/hash-verified all five SSD FP3KM2 startup files; SD FP3KM2 empty. BOOT status16, payload12568B exactly v0.3. MENU state all-zero after status16 is startup-only, so it cannot establish later resource loading or private selection state.

Preserved all real files (excluding Finder dot sidecars) from A001_010..013 in diagnostics/native-ui-demo-return/clips, with hash readback. Frame counts16/79/147/117. First three: RAW3032x2020/crop3000x2000,12bit/24 metadata. Last: RAW3856x2170/crop3840x2160,12bit/24. Every parsed RAW strip fits file bounds. This supports private capture and return to UHD, not proof of actual sensor cadence or all-photosite reduction. A001_012 full validation and nine-frame green-plane contact sheet inspected, no structural errors; handheld scene varies normally.

Definite summary cause: native drawText record C1A6E777 has pool reference at+32 resolving to literal `3`; it is separate from the resolution CSV. New exact-hash parser-copy repair replaces that one field with synthetic FFFFFFF6 -> resident literal3K. No global digit or localized text is changed.

UI state audit found prior image-only extensions incomplete. tools/audit_fp3k_ui_layout.py resolves actual stock animation groups by screen/object/clip identity. Repair targets29 named Resolution /21_MV_Resolution groups: HUD state endpoint66->99; QS33->66. It appends a copy of the UHD key to EVERY property in all155 companion clips at the new endpoint, replacing only the intended resolution-image key with FP3K_L/M/QS. Thus visibility/collapse/position/rect travel with the private state. Other stock keys remain byte-identical. Scope excludes unrelated playback groups modified by the earlier broad image matcher. Largest replacement378B within512B stack buffer; counts/shape checked against firmware SHA and runtime FNV. Native record position/base restored; unaligned inserted fields use byte stores. This addresses a concrete omission consistent with the QS overlap; physical rendering remains unverified.

HUD update correction: C0593F30 stores r0 in r6 but never dereferences it; message delivery uses global queue. resolution_display now publishes LV alongside MV regardless of whether HUD observer entries ran after AutoRun. Native null-receiver message encoding tested4 values (queue delivery mocked). Old refresh's reliance on cached HUD pointers could miss startup-created receivers; startup-only logs cannot prove which path caused the prior UHD photo. Already-cached NBU instances and private NBR renderer initialization remain possible unresolved hardware issues.

New resident16016B, SHA46546de37287c9548e4f8f1ac57ae218169a741d8f42a69ee4daffbc67b00cb0. Final exact-payload tests:113 capture/install safeguards;13 integrated boot cases;205 UI hooks/guards including no-HUD-observer refresh;155 native animation parser cases. Existing six badge-decoder and resource-pack reports remain content-hash bound. Actual parser/key copying executes, while component registry/attachment, services and final display are partly mocked. Previous v0.3 also passed its narrower offline tests and failed on camera: do not claim v0.3.1 visually fixed until tested.

Current canonical UI/animation verification entry points forward to the v0.3.1 layout suites. Prior versions of those tests and core UI generator/assembly archived in prototype/development/native-ui-v030/sources; full v0.3 package remains intact. New package prototype/fp3k-0.3.1-native-ui plus zip; readable README and all reports included. Return folders diagnostics/native-ui-layout-return/{SD/FP3KM2,SSD/FP3KM2,clips} already created.

Installed with checked installer, verified both media UUIDs and backup/readback; both disk11 and disk10 safely ejected. Installation record prototype/native-menu-installation.json. No capture-table/preview changes in this update. Next required hardware action: remove battery30s once, boot supported CINE/DNG12/true24/cropoff/SSD, select3K, inspect main summary/HUD/QS; switch UHD and3K inQS. No recording required for this UI check. No timed startup wait or status overlay. Preview remains cropped;25/30fps and all-photosite quality remain pending.

Installed at 2026-09-09T17:38:15.221043; backup <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-173815-155581.

## 2026-09-09 — v0.3.1 hardware result; v0.3.2 complete QS candidate

User confirms live HUD now shows3K. Summary still3; QS tile still mangled and bottom choices onlyUHD/FHD. This narrows success to HUD publication/resources, not the whole prior UI repair. The previous summary cause diagnosis targeted the WRONG sibling item: C1A6E777 belongs B2_5_3. Actual resolution summary is C1A7246B, object IconText03 under IconText/MenuItem_Select/B2_5_4; sibling text IDs1516/1517. Builder now asserts the full ancestor chain and sibling IDs. Do not reuse earlier assertion that C1A6E777 was the resolution summary.

QS large resolution tile belongs20_MV_Resolution and usesfont_menu_MB_resolution_1/2,150x38. Previous repairs only covered21_MV_Resolution, the small resolution badge paired with frame rate. New audit extends both groups and their companion visibility/layout clips; HUDResolution remains. Total47 groups,380 changed records, plus2QS limits. NewFP3K_FONT150x38 replaces unused LH/MH assets in the private pack: five activeassets,5804B, SHAa5a32f4faa7d70e631ea3c439d0c5bbe8084e8ea8e910fab702695013ca75817. AliasFFFFFFF4 nowFONT. F5legacystringunused, no corresponding packresource needed.

Bottom QS options are a separate shared footer. At mode time700, first two slots use set_resolution_1/2. Third slot was collapsed and lacked a resolution image key. Newliteral-delta corrections insert third-slot collapse0 andFP3K_SET image at700, retaining733andothermodekeys. Two Cursor2 actions under each of the resolution controllers (C237244F andC25E400A) are redirected to existing Cursor3 (stockrange66) only forMV_Resolution. BothexistingQSmax2plans retained. Fouractions plus twofooteranimationrecords. This completes previouslyomitted visible-choice and cursor resources offline; actual rendering still needs camera validation.

Resident uses a compact12B per-record lookup: source address, packed size/kind/time/property/alias or delta offset, FNV. Exact source hashes plus immutable payload checksum guard bounded512B temporary copies. Footer edits use immutable ordered diff recipes with16bitoffset/remove/add fields andFFFFterminator; tested byte-exact against generatedrecords. Largestreplacement488B. A regression caught a build-time variable shadowing that temporarily replaced csv_stock with a UIrecord; corrected before anyinstallation. No failing build installed. No capture-table logic changed.

Final exact-payload reports:113capture/install cases,400UI hook cases,328actual nativeanimation parser cases (including2footerrecords),13integratedbootcases,5actualnativebadge decodes,5nativeNBRlookups; prior4nativepublishercases stillapplicable. UI registration/attachment, eventdelivery, hardware andfinalrenderer remain partlymocked. Reports bind payloadorpack hashes; passingtestsarenotproofcameraUIisfixed.

Package prototype/fp3k-0.3.2-native-ui andzip, resident15048B SHAc47af36a53728418d416f1efb9ad71bd88e5065e140f02400a9816264ba69529. Newreturnfolders diagnostics/native-ui-qs-return/{SD/FP3KM2,SSD/FP3KM2,clips} created byfinalizer. Prior0.3.1 package remainsintact; relevantprechange sources archiveddevelopment/native-ui-v031/sources. CanonicalUI/animationtestentrypoints runcurrentlayoutsuites.

SD initiallymountedalone; requestedSSD reconnect. AfteruserconnectedSSD, verifiedUUIDs, copiedall5SSDdiagnosticsinto diagnostics/native-ui-layout-return/SSD/FP3KM2;SDfolderempty. BOOTcoldstatus16,length0x3e90;MENUstartupactive0/context0isnotlateUI evidence. CODEmatchesv0.3.1 SHA46546de37287c9548e4f8f1ac57ae218169a741d8f42a69ee4daffbc67b00cb0. No newrecording requested or analyzed thisturn. Checkedinstaller dispatched forv0.3.2 withbackup/readback/ejection; finalinstallationrecordauthoritative.

Next requiredhardwarecheck: batteryout30s once, supportedCINE/DNG12/true24/cropoff/SSD, main3K; verifysettingssummary3K, HUD3K, QSlarge tile3K andbottomUHD/FHD/3K; cyclethroughall3QSchoices. No recordingneeded. Previewstillcropped;allphotosites/25/30fpsunfinished. Do not makeanotherUIcompletionclaimbeforehardwareconfirmation.


## 2026-09-09 — v0.3.2 confirmed; full-height preview trace prepared and installed

User confirms the v0.3.2 UI now looks correct. Capture remains the previously validated3K12-bit/24 prototype; all-photosite semantics remain unresolved. Current focus is full-height preview, including the user's suggestion of reusing photo preview geometry. See analysis/fullheight-preview.md for exact evidence and limitations.

Executed stock C0438018 for all306 profile rows. Crucial distinction: camera-observed standby profile5 already has2016x1344 raster, but2000x1125 visible crop and yoffset109. Photo profile1 differs in only PARAM+1C (2 vs1) and+28 (1334 vs1125). Recording profile429 actually uses2016x1135. PARAM+1C complete semantics not established; do not blindly label it aspect or replace whole pipeline.

New offline recording hypothesis changes+10,+28,+E0 to1344,1334,1344. Actual ARM descriptor, path selector and pool-size constructor execute without stubs. RAW descriptor remains byte-identical to current3K, preview factors remain3/3. Modeled sum of pool counts*size grows17,167,384 to20,321,416 bytes for supplied maximum6064x4042. This is NOT live reservation/DMA validation. No preview changes installed.

Refresh uncertainty: UHD and private3K use same nativeenum3. Stock setter skips changed-value notification for same value. QS apply flag follows a separate apply path; actual live preview reconstruction/caching remains unknown. Rather than an unverified direct live buffer change, built a trace retaining exactv0.3.2 resident and AutoRun prefix, separate1100B samplerC0731930..C0731D7C, below STATEC0732000. Reads existing bounded profile snapshot plus manager, two native processing configs, private state and display-mode RAM.56samples750ms,42seconds,129088B in128KiB allocation; no explicit startup delay, overlay or sensor/preview writes. Single delayed save after3seconds native idle, maximum60extra seconds. Nine emulator cases pass including corrupt body, bad/small pool, badsource, mode transitions, finalization and late stop. Decoder integrated with synthetic outputs and rejects truncation. Sleep/filesystem mocked; no hardware validation yet.

Both knownmedia discovered and backed up. ExistingSD AutoRun and resident exactv0.3.2 verified. Saved currentFP3KM2logs into diagnostics/native-ui-qs-return andbackup. Replaced onlySD AutoRun, keptresident byte-identical; createdFP3KPVfolders onbothmedia. Installation record: diagnostics/fullheight-preview-probe-v1/installation.json. ProbeSHAd9cc1beea6b90018a0f132d0a2eb0154089416330a1ab49a16ae2ed639c12164; AutoRunSHAf7768036f56bac5c8abd82c756f12dc3e8a2c6b806d6aa95a61fb705e522e83e. Bothdisks safelyejected.

Next needs camera: batteryout30s, bootCINE, promptly select3K/record5s/stop; selectUHD, switchSTILL5s, backCINE; leaveidle until90s afterstartup, thenonceaccessindicatoroff poweroffnormallyandreturnbothmedia. No stillphoto needed; one recordingonly. No new overlay. Completeactions promptlywithin42s samplerwindow. Target is live configuration/refresh evidence, not another UI or scene-framing test. Returnfolders diagnostics/fullheight-preview-trace-return/{SD,SSD}/FP3KPV alreadycreated. Newdecoder tools/read_preview_probe.py. Installation/baseline restore should use exactbackedupAutoRun; canonicalmenuinstaller currentlydoesnotallowprobeAutoRunhash, so preserve/restoreexplicitly rather than assumingnormalinstalleraccepts it.

Installed at 2026-09-09T18:23:02.992350; backup <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-182302-375891.


## 2026-09-09 preview trace returned; preview1 experiment installed

Both clips retained and validated in diagnostics/fullheight-preview-trace-return.
Native live-source reproduction and four-word preview hypothesis are documented in analysis/fullheight-preview.md.
Installed combined experiment from diagnostics/fullheight-preview-experiment-v1; both media ejected.
Backup: <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-184740-921639
125 resident,403 UI hook,13 boot,9 trace checks passed; physical preview framing not verified.
QS regression remains unresolved; instrumented four target record seen/extended bitmaps.
Next required camera pass: cold reset; stable scene; select 3K via settings, REC5s/stop and observe preview; select UHD via settings, REC5s/stop; inspect QS; remain idle until90s from startup and reconnect both. No still required.
Original v0.3.2 package hashes rechecked and unchanged. Canonical build tools now target experimental preview1; archived v0.3.2 sources in prototype/development/native-ui-v032/sources.


## 2026-09-09 preview1 returned; preview2 output experiment installed

User reports QS third choice present, framing unchanged, no stretching/flicker. Collected all logs and three complete clips under diagnostics/fullheight-preview-experiment-return.
Trace proves source and processing preview geometry changed; manager primary output stayed16:9. Main analysis/fullheight-preview.md records exact paths and findings.
New guarded primary-output accessor returns1620x1080 for two observed private3K policy objects. Camera behavior still unverified; no claim of finished preview.
Installed diagnostics/fullheight-preview-experiment-v2 (resident0.3.4-preview2); both devices ejected. Backup: <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-190809-568577
Validation:126 resident,403 UI,13 loader,14 output-hook,2 native pool comparisons,9 trace cases. Originalv0.3.2 and preview1 binaries unchanged.
Next needed: camera cold reset30s; stable scene3K5s REC/stop thenUHD5s REC/stop via Settings, compare framing/borders; idle until90s from boot and reconnect media. No QS test or still needed. Fresh return directories diagnostics/fullheight-preview-experiment2-return already created.


## 2026-09-09 preview2 returned; preview3 display-layout experiment installed

User reports unchanged preview, successful QS 3K selection, and black bars above
and below the image. Both new clips and all diagnostic files were preserved in
diagnostics/fullheight-preview-experiment2-return. Clip019:144 frames/6s in 3K;
clip020:212 frames/8.833s in UHD. All DNG metadata and strip checks pass. The trace
confirms source and primary output are already 3:2 in private mode; QS seen and
extended bitmaps are5/5. Do not repeat source-height changes.

Found native XC_DisplayZoomParameterW71C1 branch C0306EA0 forcing aspect enum3
(16:9). New mid-function hook passes enum2 (3:2) only for private3K/device kind1.
The remaining native fit runs normally. Registers/flags are preserved. Adds
latched reached/applied bits at STATE+56 and last descriptor pointer at+60;
state is now64 bytes, sampled by the bounded probe. Native fixture calculation
shows stock1620×911/Y84 and patched1620×1080/Y0; environment selectors are mocked,
so runtime branch execution and physical full-height framing are still pending.

127 resident,403 UI,13 loader,14 output-hook,28 display-layout and9 trace cases
pass for the exact payload. Prior packages remain hash-verified unchanged.
Canonical tools target prototype/fp3k-0.3.5-preview3 and combined experiment
 diagnostics/fullheight-preview-experiment-v3. Previous tools archived under
prototype/development/preview2/sources. Probe has only68 bytes remaining before
STATE; account for this before further resident growth.

Installed and safely ejected both known media. Backup: <WORKSPACE>/prototype/fp3k-0.1/backups/20260909-193658-489156
Resident SHA: 8cf489ef8ad5e4c8723adac4dd421f6943a5d4f6338c030f70148764901b243e
Combined AutoRun SHA: 0bda00b04fa09ff34c16c43f587626291aec2610db1354696cc66edc3aaadfca

Next needs camera: battery out30s; fixed scene;3K REC5s/stop, UHD REC5s/stop; observe extra scene coverage and bars; finish interactions within40s, leave idle until90s after boot, power off normally after media activity ends, return both media. No still or separate QS test. Return folders already created at diagnostics/fullheight-preview-experiment3-return.


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

## Reduction-method investigation — 2026-09-09, after full-height preview

User prioritizes resolving the reduction method before compression. Preserved
0.3.5 everyday package unchanged. New tools/trace_reduction_method.py executes
three native descriptor/routing/register cases with bounded RAM MMIO and firmware
SHA checks. 3K uses native CrctRwzmToBufA,2048/2048, zero upper phase terms, RAW
reduction factors1/1. Stock DC Crop/profile432 records through CrctCrmfToBufA
before RAW zoom, even though the zoom block remains configured for preview.
Sensor descriptor+114 has TWO56B records atC0B5F770, not mode-indexed rows.
Record1 used for3K/full-widthUHD,record0 forDC Crop. Complete native report and
limits: analysis/reduction-method/native-trace.json and FINDINGS.md.

Exploratory temporal noise analysis of40frames each fromlatest3K/UHD return,
separately on all4CFA phases, shows pronounced16-position variance cycle for
UHD25/16ratio and essentially constant cycle for3K2:1. Same-phase adjacent noise
correlations ~0.01–0.03 in3Kgreens vs~0.09 UHD. This is evidence of phase-dependent
resampling, NOT unique kernel identification. Nonoverlapping averaging and sample
selection both permit low output covariance. Earlier optical pair alignment
(~0.698px at1500-wide) cannot resolve single-sensor-pixel weights.

Kernel/all-photosite contribution remains UNRESOLVED. Prepared four-take
same-CINE flat-field control protocol at1/50 and1/100 forUHD DC Crop and3K;
no new AutoRun required. Created diagnostics/reduction-method-return with
SD/FP3KM2,SSD/FP3KM2,clips and TEST-INSTRUCTIONS.md. Need hardware captures before
claiming an effective contributor count; exacttap support may need a subsequent
synthetic-input experiment. No media changes/installations this turn.
