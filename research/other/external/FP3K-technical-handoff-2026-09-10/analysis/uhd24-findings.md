# UHD diagnostic: useful partial capture, recording stops unresolved

## Inputs and validation
- diagnostics/uhd24/FPD002: 46 BIN files, understood from the user's message to be the SSD copy.
- diagnostics/uhd24/FPD002 (from SD card): INFO.TXT only; no diagnostic BIN files.
- diagnostics/uhd24/A001_002_20500316_000006.DNG: original UHD video frame.
- GEOM.BIN exactly matches the 7,000-byte stock sensor table.
- All 15 returned S/C/G snapshot groups (indices 000–014) have the expected sizes and sensor descriptor pointers.
- Groups 015–023 and DONE.BIN are missing: 28 expected files absent. This remains an INCOMPLETE capture, not a passing complete run. Why the script did not finish cannot be determined from these files.

## Sensor transitions
- 000–005: mode 8, timing-table index 52, raster 2016×1344.
- 006–007: mode 151, timing-table index 64, raster 6064×3412.
- 008–009: mode 8.
- 010–011: mode 151.
- 012–014: mode 8.
The two recording-mode intervals are consistent with the user's two short recording attempts. Snapshot intervals include I/O delays and are not exact timestamps; no precise stop duration is calculated from them.

## Original frame
12-bit, uncompressed Bayer RGGB. Exactly 24 fps. Stored raster 3856×2170; default crop 3840×2160 at (8,5). File size 12,630,528 bytes: 303,132,672 bytes/s at 24 fps if all frames have this size, before audio/filesystem overhead. ISO 3200, f/8, 1/50 s, 45 mm.

UHD recording settings report 3840×2160 throughout. Scratch geometry at 0xC37CE210 instead remains 1936×1090 / 3,244,544 bytes throughout: demonstrably stale FHD data. Use CameraMgrSetting and frame metadata, not this scratch block.

## Diagnostic interference and correction
The diagnostic did NOT remain isolated to SD. Its files appeared on SSD, so its separate small-file operations shared the same filesystem/device used by UHD recording. Low total byte volume does not exclude latency, locking, or scheduling interference. My earlier expectation that SD logging would isolate these operations from USB SSD recording was wrong.

This is a plausible contributor, not proof that it caused the seven-second stops. The user reports similar stops historically. Need one stock UHD12/24 recording with AutoRun removed to distinguish a baseline recording failure from instrumentation-related behavior. Preserve partial outputs and avoid re-running v002 until this is understood.

## Implications for open gate
The measured UHD path selects a mode whose table raster retains the full 6064-pixel width with a 3412-row 16:9 region. This is a better starting point than the FHD mode 218 raster of 3032×1708 for investigating the user's preferred all-pixel route. It does not yet establish that every pixel contributes or explain the exact reduction algorithm. Full height would require changing the readout/processing path, not merely DNG crop tags.

Static next step: trace mode 151 selection, compare its timing/ROI configuration to full-height modes 3 and 121, and locate processing dimensions and buffer stride. The lone 3856×2170 constant pair at 0xC096F580 is referenced by 0xC02C0388; the inspected code compares dimensions and changes a processing parameter, so this is NOT yet a scaler configuration or a safe patch location. Saved geometry-reference-candidates.json for follow-up.
