# Full-height processing trace after confirmed UHD recording

## Findings

The hardware return establishes profile429/sensor151 as the baseline. This pass executes stock descriptor construction, pure path selection, and packed-row register programming offline. It does not generate or install a resolution patch.

### A dimensions-only change would crop the field of view

C031BFD0..C031C0AC obtains the current sensor raster, applies reduction factors, rounds each dimension using `(dimension*1024 + zoom/2)/zoom`, and derives even centered offsets against the RAW target. Stock input6064×3412 with zoom1600 yields3881×2184, then offsets12,6 for3856×2170. Full-height6064×4042 with the same zoom and target3032×2020 yields3881×2587 and offsets424,282: a substantial crop. Changing width/height alone therefore does not achieve the user’s goal.

A hypothetical zoom2048/2048 produces3032×2021 and offsets0,0 for3032×2020. With a3000×2000 visible crop, descriptor crop origin is16,10. This is geometry arithmetic, not proof of correct Bayer phase, all-pixel filtering, timing or a supported hardware ratio.

### RAW and preview have separate configuration

C0438018 constructs the0xC0-byte descriptor from the actual profile parameters and vtable. Its RAW half carries3856×2170, zoom1600/1600 and reduction enums0/0 (factors1/1). Its preview half carries2016×1135, clamped zoom1024/1024 and reduction factors3/3. These preview factors do not by themselves establish that the RAW output skips pixels.

C031D988 builds two seven-word groups and dispatches sensor-vtable slot+0x9C. For this camera it resolves through C0B5FD5C to C0325228. Executing this selector produces enable bytes[0,0,1] for stock429 and both hypothetical cases. It routes the RAW ratio into output+0x34/+0x38 and preview factors into+0x24/+0x28, rather than rejecting the hypothetical dimensions.

Changing only the six candidate RAW fields leaves preview dimensions2016×1135 unchanged. Preview field of view/aspect therefore needs its own treatment with full-height sensor input.

### Hardware programming reached

C031D988 -> C0320AF0 -> C032D9A0 builds reduction hardware configuration using descriptor+0x114’s56-byte entries. The ratio wrappers C0635DE0/C0635DF8 lead to C0633E60/C0633F20. These enable ratio blocks at300F0900/300F2900 and write horizontal/vertical ratio plus phase words at300F0908/090C and300F2908/290C. Their code does not disclose the actual spatial filtering kernel or guarantee every input photosite contributes.

The selected acquisition branch at C031C820 builds a crop window and calls C06319E0. C031C944 passes request+0x38 to C0631B98, which converts a cached/uncached address to a bus address, divides by4, and writes30182280. This identifies a DMA destination programming point, not the allocator that owns its storage.

C031C9C4 invokes C0630E90 with the RAW width and acquisition-format enum. For enum0 (the12-bit descriptor format), emulation gives a row-transfer register equal to floor(3*width/8). Interpreted as32-bit units this is the expected packed12-bit row size:

| Raster width | Transfer units | Packed bytes/row | Chunk register |
|---:|---:|---:|---:|
|3856|1446|5784|728|
|3032|1137|4548|576|
|3000|1125|4500|568|
|6064|2274|9096|760|

These are writes to a RAM model of registers, not measured DMA behavior. For3032×2020, packed pixels alone total9,186,960bytes/frame, or220.48704MB/s at24fps; metadata/alignment/audio are additional. Smaller output size does not establish a safe allocation: buffers upstream of reduction, queue counts and lifetimes remain untraced.

## Validation and limits

`tools/verify_raw_geometry_emulated.py` executes stock code with firmware read/execute protection, bounded instruction counts and destination/stack write guards. No firmware subroutines are stubbed for descriptor construction or path selection. Packed-register tests model the register page as RAM. Three descriptor/path cases and four packing widths pass. Results: analysis/firmware/raw-geometry-emulation.json. Hypothetical fields/table locations: fullheight-geometry-candidate.json; this is deliberately incomplete and not an installation package.

The stock full-height sensor modes3/121 have nominal30/25fps timing. Selecting one is not a demonstrated24fps full-height recording configuration. The existing UHD24 timing and full-height receiver window still need coordinated analysis.

## Outstanding trace

1. DMA buffer allocation/queue ownership: request+0x38 originates upstream of C030CF98; direct callers C0379180/C0379C28 are identified. In the latter path it is copied from caller object+0x4C into stack+0x30 before the eight-byte request wrapper. Which path supplies the active CinemaDNG writer and how it sizes/reserves RAW buffers still need proof.
2. Reduction/filter implementation behind the ratio-register blocks, including whether ratio2048 preserves all-pixel contributions and Bayer structure.
3. Full-height timing, preview and DNG writer sizing/metadata coherence.

No additional camera run is requested by this pass. No firmware file or camera setting was modified.
