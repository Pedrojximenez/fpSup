# FHD 12-bit / 24 fps live diagnostic

Returned folder: diagnostics/fhd24/FPD001. User reports normal recording and only operating video record/stop (no still shutter or half-press).

## Validation
All 74 expected files are present at exactly the specified sizes. GEOM.BIN matches all 7,000 bytes of the extracted sensor geometry table. Every sensor object has the expected descriptor pointer. Corrected checker result: PASS.

The original checker incorrectly required the completion marker's first 64 bytes to match the on-disk reset vectors. Exactly one word differs: 0xC0000020 contains 0xC03DA130 rather than 0xC0000600. Stock boot code at 0xC0000630 loads that value from 0xC000076C; the store at 0xC000063C targets 0xC0000020. The checker now requires the exact stock runtime prefix (not a broad byte mask). All eight offline tests pass, including a one-bit mutation at that pointer being rejected. This was a host-side validation bug, not evidence of a bad capture.

## Observed sequence
| Snapshot indices | Sensor mode | Timing-table index | Table raster |
|---|---:|---:|---|
| 0–4 | 8 | 52 | 2016×1344 |
| 5 | 3 | 3 | 6064×4042 |
| 6–15 | 8 | 52 | 2016×1344 |
| 16–20 | 218 | 66 | 3032×1708 |
| 21–23 | 8 | 52 | 2016×1344 |

Recording configuration reports 1920×1080 throughout. The sustained switch to 218 and back is consistent with the user's test take and confirms a working current-mode read. Exact start/stop timestamps were not recorded and are not inferred from wall-clock guesses. The single mode-3 sample is an unexplained transition; the user denies a still capture. It does not establish full-resolution video output or sustained throughput.

All scratch geometry snapshots from 0xC37CE210 are zero. That supports the newer upstream warning against using this as a general dimensions source; live CameraMgrSetting supplied usable dimensions.

## Implications
The FHD recording path uses a sensor table raster larger than its final DNG output but with roughly 16:9 proportions. This does not identify whether or how binning, skipping, or all-pixel reduction is implemented. Full sensor-height information is not established in the recorded frames. Do not change dimensions or mode IDs alone: buffer layout and downstream processing remain unverified.

## Next comparison
A stock UHD12/24 recording to SSD with the same RAM reads. Package fp-state-v002 changes only version labels and output directory (FPD002), so the first diagnostic output is preserved. This measures which sensor path the stock UHD mode selects before pursuing an all-pixel 3:2 reduction path. No camera-side memory or sensor writes are introduced.
