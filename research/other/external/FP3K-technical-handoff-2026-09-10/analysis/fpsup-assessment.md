# fpSup assessment and next experiment

Source: https://github.com/ijigen/fpSup
Local snapshot: research/fpSup
Commit: 8c70895cb2b817690bd4c3ddb433bd3cc3e567bf
Inspected source and documentation only; no upstream executable run and nothing installed on the camera.

## What changes the approach
The project's source and release documentation describe AutoRun.txt loading ARM code and applying patches in RAM on Sigma fp firmware 5.02, without reflashing. A memory dump from the running camera could also bypass the need to independently decode the update container first. RAM loading is not equivalent to arbitrary hardware operations being harmless; the shell includes persistent calibration writes and documented hang-inducing commands.

The project describes itself as reverse engineering. No complete Sigma-published, buildable camera firmware source was found in this investigation. Availability of community extension source or a camera-control SDK does not establish that the camera firmware is largely open source.

## Specific leads
The source index.html presets array lists these research-derived modes:
- 6064×4042, RAW12, 29.973648 fps.
- 6064×4042, RAW12, 39.157249 fps.
- 3032×2012, RAW12, 105.402 fps.
These are upstream claims, not independently extracted mode records or measurements on this user's camera. The entries lack complete mode IDs/register tables. Near-30 fps is not exactly 30 fps. Dimensions alone do not prove full field of view, pixel contribution, or a compatible recorder path.

projects/sensor-lab-sup.md identifies recording geometry at 0xC37CE210 as 1936×1090 and 3,244,544 bytes/frame. These values exactly match all 122 supplied FHD frames. That corroborates its output geometry, not all its register/address claims.

projects/firmware-map.md describes MAIN at 0xC0000000 and several callable firmware APIs. Detailed notes named FORMAT, ISO_FIRMWARE_COMPLETE, and SECURITY are referenced but were not found as standalone files in the downloaded repository. The supplied firmware container still needs extraction or a runtime MAIN dump to independently verify addresses.

The root README names USB shell v2, while fp_usb_shell/README.md names v3. Pin the commit and inspect/build the actual chosen implementation instead of treating version labels as a compatibility guarantee.

## Preferred implementation route
1. Verify/read the relevant firmware code and mode records. If a local unpacker cannot be recovered from the available sources, use a narrowly scoped camera-memory capture via a reviewed AutoRun script or USB shell.
2. Establish baseline state in normal still, FHD12/24, and UHD12/24. Inspect RAM-backed structures and ROM tables. Do not enumerate arbitrary MMIO reads: register reads can have side effects.
3. Trace 6064×4042 RAW12 modes into the capture pipeline and locate any Bayer-aware reduction stages. Full native readout plus every-pixel reduction is preferred. At 24 fps, 6064×4042 RAW12 itself is about 882 MB/s internally before reduction, so output USB arithmetic alone does not settle feasibility.
4. Evaluate the 3032×2012 mode only after resolving sensor ROI and sampling. It may be cropped, binned, or skipped. Its height is not half the still's stored height (4042/2 = 2021), another reason not to equate it automatically with perfect full-area 2× reduction.
5. Design a RAM-only mode modification with matched sensor timing, DMA buffer sizes/stride, Bayer pattern, black-level treatment, RAW writer dimensions and DNG crop metadata. Start at 24 fps, then test 25 and 30 separately.
6. Validate a single frame first, then a short sequence, then sustained SSD recording and image quality against stock.

## First camera interaction to prepare
A diagnostic capture, not a resolution patch. Preferred scope: firmware identity and selected code/table/state memory only. No firmware updates, EEPROM/flash writes, sensor gain/mode writes, or raw-capture commands with documented hangs. A USB shell needs the USB port connected to the computer, so it cannot be assumed to coexist with USB SSD recording; later SSD-state collection should log to SD through an on-camera observer.

Needed hardware when the diagnostic package is ready: spare SD card, card reader, charged battery, USB data cable to Mac. No disassembly or SSD model identification required now. No ready-to-run diagnostic card has been produced in this pass; source review and address validation come first.
