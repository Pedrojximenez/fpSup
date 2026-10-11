# Sample findings

## Confirmed target
Full-sensor-area 3000×2000, 12-bit CinemaDNG to USB SSD. Start with 24 fps; 25 and 30 fps preferred. Prioritize every sensor pixel contributing; skipping and other quality compromises are last resorts. Camera firmware 5.02, DarkPowerLabs enclosure. SSD model unknown; user reports it is not the bottleneck. No throughput measurement made here.

## Samples inspected
123 DNG files: one still and 122 video frames. Originals unchanged. All video frames share the dimensions, bit depth, compression, frame rate, and strip byte count below.

| Property | Still | Video |
|---|---|---|
| RAW raster | 6064×4042 | 1936×1090 |
| Default output crop | 6000×4000 | 1920×1080 |
| Crop origin | 32,21 | 8,5 |
| Bit depth | 14 | 12 |
| TIFF compression tag | 7 (JPEG family) | 1 (uncompressed) |
| CFA pattern | RGGB | RGGB |
| Frame rate | N/A | 24/1 |
| ISO | 3200 | 3200 |
| Aperture | f/4 | f/4 |
| Focal length | 45 mm | 45 mm |
| Exposure time | 1/40 s | 1/50 s |
| Software | SIGMA fp Ver.5.02.0.V91 | SIGMA fp Ver.5.02.0.V91 |

Each video file is 3,244,544 bytes, or approximately 77.87 MB/s at 24 fps before audio and filesystem overhead. RAW strip byte count is 3,165,372: 12 bytes more than the packed 12-bit 1936×1090 raster. The purpose of the extra 12 bytes has not been identified. A straightforward packed 12-bit decode from the strip start produces a recognizable image.

## Coverage
Visual comparison of the still's embedded full-size JPEG with an approximate video RAW preview is consistent with similar horizontal coverage and reduced vertical coverage in video. This is qualitative, not calibrated image registration; stabilization/crop settings are not independently verified. Video metadata contains only 10 extra raster rows, not a hidden full-height 3:2 image. Changing DNG crop tags cannot recover the missing field of view.

## Limits and implications
- Samples establish output layout, not whether the camera readout uses skipping, binning, or another reduction method.
- They do not establish full-sensor video readout speed or support for all-pixel reduction to 3000×2000.
- A 2× reduction along each axis must handle Bayer color samples appropriately; averaging arbitrary adjacent 2×2 RGGB blocks does not yield one valid Bayer sample.
- Stored video uses packed 12-bit samples, strengthening the relevance of the 216 MB/s (24 fps), 225 MB/s (25 fps), and 270 MB/s (30 fps) target payload estimates. These exclude sensor margins, metadata, audio, and transport/filesystem overhead.
- The preview is solely for geometry: simple same-cell RGB reconstruction, scene-average channel balancing and gamma; no camera color matrices or calibrated development. Color differences are not evidence of RAW quality loss.

## Artifacts
- sample-metadata.json: parsed metadata across all DNGs.
- inspect_dng.py: reproducible classic TIFF/DNG metadata reader.
- preview_samples.py: approximate preview generation using bundled Python/Pillow/NumPy.
- previews/comparison.jpg: still/video overview.

Next engineering step: decode firmware packaging and identify sensor/capture mode configuration, buffer dimensions, and RAW writer configuration. No patch location or recovery route has been established, and no modified firmware has been created.
