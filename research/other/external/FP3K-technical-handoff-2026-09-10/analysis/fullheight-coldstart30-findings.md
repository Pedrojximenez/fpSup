# F1 no-overlay 30-second recording return

SSD A001_005 contains 730 consecutive DNG frames, one WAV and one XMP (732 files, 6,770,166,059 bytes). All files were copied and SHA256 verified against the media. Evidence is in diagnostics/three-k-coldstart30-return/.

Every DNG reports 3032×2020 RAW, visible crop 3000×2000 at (16,10), uncompressed 12-bit CFA and 24 fps. All declared strips fit their files and contain sufficient bytes. Duration from frame count and metadata is 30.4166667 seconds; WAV duration is 30.5017708 seconds. All 730 RAW strip hashes are distinct; no missing frame numbers. These checks do not independently measure sensor cadence.

The returned exact 636-byte payload has status16 (applied_this_invocation), no mismatch, and all 18 readback words equal the intended F1 configuration. This supports clean entry from the expected stock table values, unlike the preceding status4 already-present return. User confirmed battery removal and manual stop. External power disconnection was not separately confirmed.

Nine RAW green-plane previews spanning the whole take show a coherent indoor scene and later camera movement, with no obvious tearing or blank regions. The scene is substantially out of focus and exposure is low (previews normalized), so this take is not suitable to certify fine detail, color, aliasing or reduction quality. User reports no flicker or other problems during this run.

Combined with the preceding stationary full-resolution still comparison, the evidence now supports full-frame 3:2 field of view at 3000×2000 and a successful 30.42-second 12-bit 24 fps capture. This is a tested RAM prototype, not a verified all-photosite reduction or long-duration reliability guarantee. 25/30 fps remain unimplemented. No new patch was installed on this return; active SD AutoRun remains the exact no-overlay F1 version. No media files were deleted or changed.

Next engineering work: trace the RAW reducer configuration and establish sampling/filter semantics before making an all-photosite claim. A sharply focused, fixed-camera fine-detail reference will be needed to test image quality; repeating this soft-scene take would not resolve that question.

Both media safely ejected after collection.
