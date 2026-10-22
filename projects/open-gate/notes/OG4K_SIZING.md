# OG4K-4000 offline sizing evidence

Verified against fp V5.02 MAIN SHA-256
`92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4`.
No camera or USB transport is used by these tools.

## Private recording canvas

The p429 selector resolves to row 286. The following eight fields are the
recording-side overrides; other canvas fields remain stock in this sizing model.

| Canvas offset | Stock | OG4K | Stock column word |
|---|---:|---:|---|
| +00 | 3856 | 4016 | C0BE3F54 |
| +04 | 2170 | 2676 | C0BE441C |
| +24 | 3840 | 4000 | C0BE2C34 |
| +2C | 2160 | 2666 | C0BE30FC |
| +DC | 3856 | 4016 | C0BE35C4 |
| +E4 | 2170 | 2676 | C0BE3A8C |
| +64 | 1600 | 1536 | C0BE1914 |
| +D4 | 1600 | 1536 | C0BE1DDC |

`C0435918/C0435948` use +DC/+E4 as RAW dimension overrides. +D8/+E0
belong to the preview plane and do not replace these RAW fields.
The input pair +F4/+F8 remains **6064x3412** after these eight changes and
feeds separate process/preview configuration through C0434EF8 and C01D1630.
RAW acquisition in C031BE60 reads the current sensor geometry through
C032C860(...,0x77), then the RAW descriptor RWZM factors. The sentinel 0x77
means current mode, not M119. Thus the ten M151 front-end changes affect RAW
source height independently of the retained preview input. This is static
source evidence; actual optical coverage and preview behavior remain untested.

## Byte counts

Original `C03D9630 -> C03D9668 -> C01AAA30 -> C0135D40/C0135DB8`
executed without stubs, with only private stack writes permitted.

| Quantity | Bytes |
|---|---:|
| Packed 4016x2676 RAW12 pixels | 16,120,224 |
| Ordinary row stride | 6,024 |
| Final row | 6,032 |
| Stock size callback / expected StripByteCounts | **16,120,232** |
| Writer's 512-byte-aligned RAW payload | **16,120,320** |
| C04356B0 raw-plane size helper | 16,120,264 |

The final row first rounds its width to a multiple of 12 pixels and then
aligns bytes to four. Thus StripByteCounts includes eight bytes beyond the
packed pixels. Its 16-byte-aligned-plane helper has 32 bytes of additional
space relative to the stock RAW callback, but this comparison alone does not
establish which allocator serves the recording pixels.

## Recording allocation request

Original `C037A990` kind-1 code calls the RAW size callback, rounds it to 512
bytes, then adds `frame+0x128`. The CinemaDNG constructor `C0374268` sets
this allocation prefix to `0x15400` (87,040 bytes). Native execution of the
request path reaches `C001CFD8` at `C037AD28` with:

| Input | Pool | Requested bytes | Alignment |
|---|---:|---:|---:|
| Stock UHD RAW12 | 10 | 12,638,720 | 1,024 |
| OG4K RAW12 | 10 | **16,207,360** | 1,024 |

The extra 8,192 bytes relative to the conditional DNG file example below
belong to the allocation prefix. They are not evidence of a larger DNG header.
`verify_record_allocator.py` executes the original registry dispatch, byte
count and handle wrapper. It mocks the physical allocator, available slots,
and secondary-buffer decision, and checks allocation failure and cleanup.
This establishes a geometry-dependent request, with no fixed UHD byte cap in
that branch. It does not establish pool availability or safe ring depth.

## FieldAngle sizing is not the recording pixel pool

Stock p429 has **canvas+3C = 0**. `C0435428` writes zero into the recording
plane count and bytes, and `C0435588` excludes that plane. Changing RAW
dimensions therefore leaves its total unchanged. Reporting this total as
proof of sufficient recording RAM would be incorrect.

Original C0435428 executed in full. Original C0435588 executed through its
complete arithmetic, stopping at C043566C before its diagnostic logging call;
the final sum was read from r5. No size-calculation function was stubbed.

| Candidate / caller dimensions | FieldAngle bytes |
|---|---:|
| Stock p429 or eight-override OG4K / 1024x682 | 12,623,384 |
| Stock p429 or eight-override OG4K / 1620x911 or 1620x1080 | 14,004,760 |
| Stock RAW12 UHD playback p71 / those caller dimensions | 14,725,488 |
| p71 with exact OG4K playback geometry / those caller dimensions | 18,842,272 |

The playback candidate preserves its movie class and pixel-format fields,
sets preview raster/override to 4016x2676, visible dimensions to 4000x2666,
input raster to 4016x2676, and both plane scale pairs to 1024. This verifies
its size calculations, not actual playback routing or available pool memory.

## Playback file buffers

`C05C2D10` computes per-file capacity as `(file_bytes + 0x1FFF) & ~0xFFF`.
It allocates a separate 0x6F090 descriptor array (stride 0x5EC) and repeatedly
requests file buffers until the pool cannot satisfy another request. The
available count cannot be calculated from image dimensions alone.

**Conditional example only:** if the previously observed 78,848-byte DNG
header remains unchanged, OG4K file bytes are 16,199,168 and playback asks
for 16,203,776 bytes per file buffer. OG4K header size has not been measured;
do not hardcode this assumption into a recording payload.

`C05C0C38` requests at most the descriptor's capacity when reading a file and
asserts when returned length equals capacity. A full read buffer does not
prove that the entire file was loaded. Here the conditional file example
leaves 4,608 bytes of reader headroom.

## Validation

Run `test_og4k_sizes.py` with Python and Unicorn available. Eight tests pass:
the original column gather matches all **312 valid profiles** (194 selector
slots contain FFFFFFFF), twelve RAW callback cases cover stock/OG4K and row
boundaries, and both plane helpers plus 32 FieldAngle configurations agree
with the existing decompilation model. Firmware is mapped read/execute;
native writes and instruction counts are bounded.

`og4k_sizes.py` prints a JSON evidence report. `--arithmetic-only` explicitly
omits native execution and labels the report accordingly. Neither mode
asserts camera readiness. Live RAW allocation, source propagation, RWZM
output geometry, actual DNG header/descriptor propagation, and pool
availability remain separate implementation gates.
