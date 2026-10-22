# Sigma fp full-height 3K RAW: technical handoff

**Snapshot: 2026-09-10. Target: original Sigma fp, firmware 5.02 only.**
This document is the current synthesis. Files in `analysis/` preserve the research
history and may contain superseded status statements. They are evidence and
reference material, not instructions to run every historical experiment.

## 1. Project goal and current result

Ultimate goal: internal SD recording of **3000×2000, 12-bit, losslessly compressed
CinemaDNG**, using the full sensor field of view, with every photosite contributing
ideally. True24 fps first;25/30 desired later. Initial deliverable is uncompressed
3K to SSD. User prefers native camera controls and no timed startup routine.
Remote camera control was explored and then explicitly deprioritized.

**Working prototype: FP3K0.3.5-fullheight.** Camera-tested native third resolution
choice in Settings and QS,3K HUD label, full-height LCD preview, and3K12-bit24fps
CinemaDNG recording to SSD. “Open gate” means full-height3:2 field of view here;
it does not mean full-resolution6K recording. All-photosite reduction is unresolved.

This is an SD-loaded RAM patch, not a flashed replacement firmware. AutoRun loads
FP3KMENU.BIN at a fixed cave address, validates expected code/data, and installs
reversible hooks. There is no timed sleep or temporary sampling routine in the
current everyday AutoRun. Small immediate FP3KM2 startup dumps remain.

| Item | Current evidence/status |
| --- | --- |
| Full-height3:2 field of view | Supported by actual RAW still/video registration |
| 3000×2000 visible12-bit24fps SSD recording | Actual DNG files checked |
| Settings/QS/HUD | User confirmed working after successive fixes |
| Full-height LCD preview | User confirmed; matching layout/config trace |
| Selecting stock UHD restores geometry | Trace plus stock UHD recording |
| All photosites contribute / exact filter | **Unresolved** |
| Internal SD3K, compression | **Not implemented** |
| 25/30fps, full-height HDMI | **Not implemented** |
| Long-run reliability, physical switches/presets/removal | Incomplete qualification |

## 2. Start here: files and provenance

- `prototype/fp3k-0.3.5-fullheight/`: exact tested AutoRun, resident and loader;
  offline verification reports. Its original manifest retains some obsolete
  nested “pending” labels; this document and final return review supersede those.
- `tools/`: source, generated assembly includes, RE utilities and verification
  harnesses. Historical experiments coexist with the current code.
- `prototype/development/native-ui/`: custom badge pack and supporting build data.
- `analysis/reduction-method/`: newest reduction trace and RAW-noise analysis.
- `analysis/internal-compressed-cdng-roadmap.md`: compression development stages.
- `analysis/fullheight-preview.md`, `analysis/native-menu-integration.md`:
  detailed chronological investigations, including corrected failed approaches.
- `analysis/firmware/`: extracted tables, disassembly and offline reports.
- `evidence/latest-return-review.md`: final reviewed hardware-test summary.
- `diagnostics/reduction-method-return/TEST-INSTRUCTIONS.md`: pending four-clip
  reduction test. No new AutoRun is required. The test has NOT been returned.
- `INDEX.md`: archive inventory. `SHA256SUMS.txt`: hashes of all other files.

The archive excludes personal photos/video/audio, raw camera diagnostic dumps,
full stock firmware images, local media installers, and upstream third-party
source trees. Text references to the original user's machine/media are redacted.
Consequently, some historical tests require fixtures not present in this archive.
It is a findings/source handoff, not a claim that every old test is self-contained.

## 3. Exact firmware and binary identity

All addresses below are for **5.02 original fp**, not fp L.

| Input/output | SHA256 |
| --- | --- |
| Supplied stock update,25,692,160bytes | `c9fa76f32f523bb2dc9a3fbda39418c31573cab6a1aa5c56d28c371862066ed8` |
| MAIN atC0000000,49,245,696bytes | `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622` |
| DAT1 atC2EF6E00,236,032bytes | `0dcaca8f5441fe4ddc6ed801cb888e325df4e76006e4f53a1c3219809b22ce7b` |
| Everyday AutoRun.txt,5401bytes | `c63eae39730677b1582bd1ca5a7093ddff684f2d58237e0b93b43e9b6be34760` |
| FP3KMENU.BIN,15620bytes | `8cf489ef8ad5e4c8723adac4dd421f6943a5d4f6338c030f70148764901b243e` |
| loader.bin,652bytes | `cd62c3f482db7a56d53190a0a92f89686ee3f7b50a745f2e86cecc3c8c81c219` |

The update has a DFI container and LZSS segments. `tools/unpack_fp.py` is pinned to
its SHA. Compressed-segment byte sums match container fields; these are not
cryptographic signatures. Bounded decompression records final-match overshoots
of1FF byte for MAIN and4FF bytes for DAT1. See extraction.json.

**Source consistency checked on2026-09-10:** assembled current resident, applied
its additive checksum, and compared every byte against the distributed resident;
exact match. Assembled loader also matches exactly. No rebuild installed.

## 4. Runtime layout and loading

| Address | Meaning |
| --- | --- |
| C072DE64 | Resident base |
| C0731B68 | Current resident end |
| C0732000 | Resident state,64bytes |
| C0732100 | Loader entry / bootstrap region |
| C0732500 | Bootstrap status |
| C0BAC2F8 | Temporary echo-handler entry used to invoke loader |
| C03D99A0 | Stock echo handler restored after invocation |

Resident STATE DWORD offsets:
`+0 magic K3M1; +4 status(16 success); +8/+12 errors; +16 private3K active;
+20 settings UI receiver; +24 internal setter bypass; +28/+32 HUD receivers;
+36 NBR context; +40 pack state; +44 UI error; +48 QS seen bits;
+52 QS extended bits; +56 layout reached/applied latched bits;
+60 last display descriptor pointer`.
The last pointer can address a temporary stack object: do not dereference it later.

The successful temporary preview probe occupied C0731B70..C0731FBC: only68bytes
before STATE. Resident growth requires relocating/reducing that probe. Everyday
AutoRun does not load it. Mixed/old hooks are rejected, not blindly overwritten.
Warm power-off can preserve RAM state. For installation/removal, disconnect all
external power and remove battery30seconds once. Normal operation has no such wait.

## 5. Capture: what changed and why

Processing profile429 and sensor mode151 are distinct namespaces. Stock429 is
UHD true24/12-bit; RAW3856×2170, crop3840×2160, ratio1600/1024 in both axes.
Sensor raster is6064×3412. Dimensions-only3K would crop the field of view.

Original full-height patch has18 DWORD changes, generated by
`tools/fullheight_candidate.py`:

- Eight profile429 changes: RAW3032×2020, visible3000×2000 and2048/2048 ratios.
- Ten sensor geometry/receiver/window changes based on native full-height mode3.
- Preserve mode151 identity and24fps timing: HMAX445, VMAX6740, tail1145.
  `445*(6740-1)+1145 = 3,000,000` cycles,24fps at72MHz.
- All161 table-fed sensor register values for151 match native full-height3/121;
  no programmed sensor register table bytes needed changing. This agreement is
  not a complete interpretation of every sensor register or readout behavior.

Profile429 replacements:
`C0BE3F54=3032; C0BE441C=2020; C0BE2C34=3000; C0BE30FC=2000;
C0BE35C4=3032; C0BE3A8C=2020; C0BE1914=2048; C0BE1DDC=2048`.
Other addresses/expected old values: `analysis/firmware/fullheight-f1-plan.json`.

Stock geometry table C0B59DC0 stride100; receiver C0B5C638 stride56;
timing C0B59500 stride32. Sensor151 is row64, full-height3 is row3.
Native input window becomes6064×4042. Arithmetic at2:1 gives3032×2021;
recording requests3032×2020. DNG crop origin16,10 gives3000×2000.

Current resident adds four preview DWORD changes for22 total table entries:
profile5 PARAM+28:1125→1334; profile429 PARAM+10 and+E0:1135→1344;
profile429 PARAM+28:1125→1334. See `tools/preview_candidate.py`.

Capture anchors:
- C0438018:0xC0 descriptor, RAW half then preview half at+58.
- PARAM+64/+D4:RAW ratios; +5C/+C8:RAW reduction enums.
- PARAM+60/+D0:preview ratios; +58/+C4:preview reduction enums.
- C031BFD0:scaled dimensions and even centered crop arithmetic.
- C031D988 → C0325228:path selection; C032D9A0:reduction setup.
- C031C820 → C06319E0:RAW crop/window; C031C944 → C0631B98:DMA target30182280.
- C031C9C4 → C0630E90:packed transfer units;12-bit row is width*3/2bytes.
- Raw strip is9,186,968bytes for3032×2020:9,186,960pixel bytes plus8bytes.

## 6. Reduction: verified path, unresolved filter

`tools/trace_reduction_method.py` now executes actual native descriptor/routing/
configuration instructions, including Thumb MMIO writers, with peripheral pages
represented as guarded RAM. It does not simulate pixel transformations.

3K records via **CrctRwzmToBufA**, not the named Hbin/Vbin recording outputs.
RAW descriptor reduction enums0/0 become factors1/1; ratios2048/2048 become2:1.
Native C0633E60 programs300F0900=1,300F0908=00000800,300F090C=00000800.
Ratio words' computed upper phase terms are zero. Bit8 of300F0004 is set from
sensor reduction record+2D; its precise semantic meaning is not established.

The descriptor atC2F1E654 has+114→C0B5F770: **two56-byte reduction records**,
not70 sensor-indexed records.3K/full-widthUHD use record1, DC Crop uses record0.
The binning-driver arguments are identical for3K and stock full-widthUHD;
ratio arguments differ. Native DC Crop/profile432 records at the earlier
CrctCrmfToBufA output with RAW unity scaling; its zoom block still serves preview.
An enabled zoom register therefore does not by itself prove the recording route.

Existing3K/UHD RAW temporal-noise analysis found a16-position variance cycle in
UHD (ratio25/16) and an essentially constant cycle in3K (ratio2).3K green neighbor
noise correlations are~0.01–0.03 vs~0.09 in UHD. This supports phase-dependent
resampling but does NOT distinguish all candidate integer-ratio filters.
Nonoverlapping averaging and selection can both produce low covariance.

The fpSup developer's message, relayed by the user, says her mod **seems** to
use the same2×2 downsampling, notes possibly noisier shadows than UHD, and says
she is not completely sure. Treat it as corroboration of the scale interpretation,
not independent confirmation of four-sample averaging or all-photosite use.

Pending: four5second flat-field clips, ISO3200, manual aperture fixed, steady
light, strongly defocused plain wall; UHD DC Crop at1/50 and1/100, then3K cropoff
at1/50 and1/100. Compare per-CFA signal scaling, temporal variance slopes and
covariance. No new patch required. Exact tap identification may need a fixed
sharp target or a synthetic impulse through the actual hardware.

## 7. Native UI integration

Third UI index2 maps privately to stock internal enum3 (UHD); it is not a new
unknown enum sent through firmware. Stock UI index0 maps enum3, index1 maps enum2.
Private activation requires CinemaDNG format0,12-bit quality0, true24 rate12,
crop0, SSD route5, and idle acquisition. Incompatible settings wrappers restore
stock table values first. Busy recording/finalization blocks transitions.

Eight core hooks: C057A6A0 selection; C05931D0 resolution readback;
C005C020 resolution setter; C005BE58 format; C005BEF0 quality;
C005C0B8 frame rate; C005BB60 crop; C0062EC8 media.
Six UI hooks: C05824D0 QS selection; C059C640/C059C9F0 HUD publishers;
C05E84D8 NBR load; C05E6400 record parse; C05E5B58 string resolution.
Last three are Thumb entry hooks. Total with two preview hooks:16.

Relevant fixes and traps:
- Adding a CSV row alone made the option visible but unselectable. Settings
  controller max atC1A709BC had to become float2 instead of1.
- Labels use a private NBR pack with FP3K_L/M/QS/SET/FONT assets. It avoids
  overwriting stock UHD/FHD badges. NBR native memory loader: C05E84D8.
- Changing only resolution-image keys broke QS. Every companion layout/visibility/
  animation property needs the new state, not only the image property.
- Current repair covers47resolution groups,380resource changes plus2QS limits.
  Delta edits keep temporary record copies within512bytes (largest488bytes).
- Correct settings-summary record: C1A7246B under B2_5_4; C1A6E777 was wrong.
- QS footer records C2278C02/C24D1DC8 require third slot700 and proper cursor range.
  Similar C23E1F9C group belongs to still controls; leave it alone.
- Native NBU baseC18C0460, poolC18C0474; parser edits are guarded by original-byte
  fingerprints and applied to temporary copies. Preserve ABI and unaligned fields.
- Physical CINE/STILL, presets and actual media disappearance are not fully
  intercepted. User currently must select stock resolution before those actions.

## 8. Full-height LCD preview: the successful fix

Source geometry changes alone did not fix LCD framing. The final solution has
three parts: source tables, primary output template, and native display fit.

1. Four preview table words described above yield visible2000×1334 from native
   source2016×1344, centered8,5.
2. HookC0437E98 (`push {r4,r5,lr}` original) returns an immutable1620×1080 primary
   output template only for private3K/channel0 and exact owner/template fingerprints.
   Standby ownerC375EB68/templateC375E934/FNV AED11366; recording ownerC375ED3C/
   templateC2F21494/FNV E0255ED6. Preserve format4, allocation limit3FC000,
   and video flags1,1. Still template flag differs: do not swap it blindly.
3. **Decisive LCD fix:** C0306EA0 inside C0306DF8 (`XC_DisplayZoomParameterW71C1`)
   forces aspect enum3(16:9). Hook uses enum2(3:2) only when private3K and native
   display device kind1. Stock fallback remains3. Preserve all live registers,
   SP/LR and flags except intendedr0; resumeC0306EA4. Native rectangle fitting
   then runs normally. No broad mask removal is needed.

Aspect table C0B4CAB8,8-byte entries: enum1=4:3,2=3:2,3=16:9,4=1:1.
Native fit C02F43A8→C02F4410; destination visible W/H/X/Y halfwords at
+7C/+7E/+80/+82. Physical destination dimensions+78/+7A; source dimensions+60/+62.
A1620×1080 fixture fits stock to1620×911,Y84 and patched to1620×1080,Y0.

Primary managerC375D840; source+8, primary geometry in channel structure+18,
channels stride34hex. Engine exported configsC31DF564, two channels stride1B0.
C0428690 converts manager output request; C01D69D0 writes engine output dimensions
atC31E0DD4+324/+328. C31D28E4 is a palette pointer, not an aspect selector.

## 9. Hardware results and validation boundaries

Latest returned3K clip:135DNG frames,5.625seconds at declared24fps; stored3032×2020,
crop3000×2000 at16,10. UHD control:144frames,6seconds,stored3856×2170,
crop3840×2160 at8,5. All279DNGs passed sequence/metadata/strip-bound checks;
all RAW payloads unique within each take. Audio was readable, durations5.7124s
and6.0751s. Sparse actual RAW previews showed no obvious corruption.

Latest56-snapshot trace: successful resident/boot hashes, no patch/UI errors,
QS bitmaps5/5. Stable3K source/config2000×1334 and output1620×1080; stock geometry
returns on deselection. Layout applied bit is latched, not continuous rendering.
Trace does not include active3K recording; direct recording files supply that
part of the evidence. User separately confirmed full-height LCD and manual stop.

Earlier matched still/video registration supported full field of view, but median
error0.698px at1500×1000 is too large for identifying individual filter taps.
An earlier full-height capture recorded730frames/~30.42seconds successfully;
its low exposure/focus made it unsuitable for fine-detail certification.

Offline reports for the final resident:127resident cases,403UI-hook cases,
13loader cases,14output-hook cases,28display-layout cases; temporary probe9cases
and2pool comparisons. These execute selected firmware paths with documented
mocks. They do not establish physical timing, thermal behavior, every UI path,
real allocator behavior, sensor cadence, or all-photosite processing.

## 10. Recording stops and unresolved reliability

User saw3–7second automatic stops with a beep back to standby and no warning.
This also happened historically and with AutoRun absent. Removing SD once helped
but a later attempt still failed. Both cable and direct enclosure connections
were affected. Sigma battery, medium/low charge observed; user also recalls near
full charge failures. SSD mostly empty. Do not label USB, power, SSD or patch as
proven cause.

One preserved retry had tenDNGframes (~0.417seconds at declared24) but~2.875seconds
of audio. Needed diagnostics: native stop reason, writer errors/completions,
queue occupancy and latency, correlated with capture state. Repeated blind retries
or guessing from time-to-stop are not adequate diagnosis.

## 11. Compression and internal SD roadmap

Still DNG compression is real: supplied full-resolution still was14-bit lossless
JPEG compressed,6064×4042, crop6000×4000. That proves a still encoder exists, not
sustained video throughput. fpSup identifies0x300D0000 and wrappersC05A6890/
C05A6920 as hardware lossless-JPEG leads. Clock/throughput/concurrency estimates
must be independently verified; source notes contain retracted earlier assumptions.

At current stored raster, packed12-bit payload is220.487MB/s at24fps,
229.674 at25 and275.609 at30, before overhead. Exactly2:1 would halve these,
but lossless ratios vary with scene/noise. Need measured encoder throughput,
latency, output capacity, input layout, alignment/cache/IRQ ownership and actual
SD write latency. Changing DNG Compression tag alone does not compress pixels.

Sequence: harden current mode transitions/stops → isolated single-frame encode
with sample-exact decode comparison → sustained encode benchmark → proper
compressed DNG packaging → compressed SSD video → internal SD integration →
long-run qualification. Retain working uncompressed SSD baseline.

## 12. Continuing development without repeating mistakes

- Treat current HANDOFF as status; historical headers and generated manifests can
  say “not tested” despite later validation. Read chronological findings to the end.
- Use a separate working copy. Builders overwrite generated includes and often
  execute substantial work on import. Run dependent builders sequentially.
- Current main package builder targets **fp3k-0.3.5-preview3**, not everyday folder.
  The everyday package was a verified copy; don't silently overwrite its baseline.
- `build_preview_experiment.configure()` must set current package/STATE64 before
  importing old preview-probe decoders/verifiers; defaults can targetolder0.3.2.
- ARM/Thumb boundaries matter. C0633E60 and adjacent low-level drivers are Thumb.
  Disassembling them as ARM gives garbage. `disasm.py --thumb` is provided.
- `arm_index.py` finds aligned ARM references, not all Thumb/ADR references.
- `inspect_fullheight_clip.py` is hardcoded for3K and may print errors without
  failing the process. Do not use it as an unchecked UHD validator.
- Avoid `inspect_uic_resources.describe` on giant records: it scans every byte.
- **Do not call still_raw_dump atC343A624.2:** upstream reports it hangs.
- Native buffer allocation, DMA ownership and stop/start serialization need proof
  before changing live geometry or invoking an encoder on recording buffers.
- Emulation of MMIO as RAM proves register writes only, not hardware behavior.
- We have not established a flashing/repacking/signing/recovery workflow. Continue
  with reversible RAM experiments rather than treating update checksum as signing.

## 13. Build/reassembly entry points

Needed: Python3, ARM-capable clang, upstream fpSup `fp_usb_shell/armasm.py`.
Capstone/Unicorn for disassembly/emulation; Pillow for badge generation;
NumPy/OpenCV/rawpy for image analysis. Versions should be recorded by the recipient.
Some local image scripts refer to a temporary dependency directory; adapt that path.

Acquire fpSup separately into `research/fpSup`, preserving its provenance.
For exact source reproduction run `python tools/verify_shared_source.py` from the
archive root. It only assembles/checks the included generated source and asset pack;
it does not regenerate UI assets or require full firmware images. Compare payload
hashes above. The same assembly procedure was verified before packaging.

For deeper RE, obtain the matching5.02 stock firmware independently, then:
`python tools/unpack_fp.py /path/to/firmware --output analysis/firmware`.
The extractor rejects nonmatching SHA. Full builders and emulator scripts require
these images; some also need omitted personal diagnostic fixtures. Review each
script's imports and fixture paths before running. Installation utilities tied to
the original user's media UUIDs are intentionally excluded.

Useful current source: fp3k_native_menu.S, fp3k_native_ui.S,
fp3k_preview_output.S, fp3k_preview_layout.S, fp3k_menu_boot.S and their generated
includes. Primary build entry: build_fp3k_menu_package.py. Main offline checks:
verify_fp3k_native_menu.py, verify_fp3k_layout_ui.py, verify_fp3k_menu_package.py,
verify_preview_output.py, verify_preview_layout.py, trace_reduction_method.py.

## 14. Public references

- [ijigen/fpSup](https://github.com/ijigen/fpSup): foundational fp reverse engineering,
  shell/RAM loader, sensor tables, gyro logger and RAW research. Neither this patch
  nor this handoff should be represented as an official fpSup release.
- [fpSup RAW research](https://github.com/ijigen/fpSup/blob/main/projects/raw-sup.md):
  compression leads and explicit retractions; not a measured continuous codec result.
- [Sigma fp specifications](https://www.sigma-global.com/en/cameras/fp/): still RAW
  compression and stock recording/media modes.
- [Sony IMX410 flyer](https://www.sony-semicon.com/files/62/pdf/p-13_IMX410CQK_Flyer.pdf):
  full-height sensor feasibility; not the full register/ISP programming manual.
- More evaluated projects and documentation: `analysis/open-source-research.md`.

No contact with the collaborator is implied or performed by this archive. Share
this file and ZIP as project context; have the recipient verify evidence before
making new camera changes.
