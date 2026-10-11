# FHD lossless host trial

This is a host TIFF/RAW-format check, not a camera encoder, playback proof,
hardware timing benchmark, or deployable payload. Sources and the existing
slimRAW builder are never edited. Every invocation creates a fresh `run-*`
directory; a rejected preflight produces only `report.json`, not a DNG.

Run with explicit absolute paths (the working directory is irrelevant):

```text
/usr/bin/python3 -B /absolute/path/run_trial.py \
  --builder /absolute/path/research/slimRAW/mkcompressed.py \
  --run-parent /absolute/path/existing-run-parent \
  --source /absolute/path/frame1.DNG \
  --source /absolute/path/frame2.DNG
```

Up to four distinct sources are accepted. The trial is fixed to FHD RAW12
1936×1090, tile 512×368, predictor 1, 512-byte file alignment. It accepts packed
single-strip data and the documented stock final-row padding (12 bytes at this
raster); no other strip/tiling layout is guessed. BigTIFF, other byte order,
duplicate/unknown tags/types, multiple top-level IFDs, cyclic/shared IFDs,
nested image-storage IFDs, and metadata outside the retained header are rejected.

Before encoding, an independent TIFF reader protects root and nested IFD
structures, every out-of-line value, and recursive Exif/GPS/Interop/SubIFD
links. The existing builder's chosen insertion range is checked against the
complete set. An overlap is rejected, even if those bytes contain zeros. No
expanded allocator is monkeypatched into the original builder.

For the original-builder mode, a successful preflight would use that builder
unchanged. The separately selected safe-builder mode below appends metadata
instead. Validation in either case then
requires unchanged source hashes, original root-IFD bytes, non-layout root
tags/entries/values, nested graph/metadata bytes, all other retained header
bytes outside the approved insert and TIFF root pointer, exact tile layout,
file alignment, and LibRaw sample-by-sample equality. JSON distinguishes
`PASS`, `REJECTED`, and `ERROR`; failed outputs, if any, are explicitly labelled
unverified and never substituted for source files.

Guard regressions run without external files:

```text
/usr/bin/python3 -B -m unittest discover -s /absolute/path/fplossless_host_trial -p 'test_*.py' -v
```

## 2026-09-15 original-builder result: 4/4 rejected

Four real FHD frames were rejected before encoding: the existing builder chose
zeros inside the Exif MakerNote, whose declared range is **17684..72022**.
The zero-filled tail is not unreferenced TIFF padding. Therefore an earlier
LibRaw image equality result does not by itself prove preservation of nested
metadata. See `run-fr9l0bc1/report.json` for exact protected ranges and hashes.

The earlier `run-mf_dhf3d/report.json` is a preliminary rejected probe with an
overly strict packed-byte-count check. It is retained transparently; the
current harness additionally recognizes the documented stock last-row padding.
Neither run generated compressed DNG files. No camera or USB was accessed.

## Separate host-safe builder: 4/4 passed

`mkcompressed_safe.py` is an independent **host-only** builder. The existing
`research/slimRAW/mkcompressed.py` and its encoder dependencies remain unchanged.
Both local tools use `tiff_guard.py`; this avoids circular imports.

Select the safe path explicitly:

```text
/usr/bin/python3 -B /absolute/path/run_trial.py \
  --builder /absolute/path/mkcompressed_safe.py \
  --encoder-dir /absolute/path/research/slimRAW \
  --run-parent /absolute/path/existing-run-parent \
  --source /absolute/path/frame1.DNG
```

The original 78,848-byte header is retained verbatim except its root-IFD
pointer at bytes 4..8. The new 810-byte IFD/table block occupies
`78848..79658`, followed by zero padding; JPEG bitstreams start at **79872**.
This adds **1024 bytes of header**, and is not a compatible implementation of
the camera's current fixed-size-header writer.

Results in `run-sktn7053/report.json` (512×368, predictor 1, file alignment 512):

| Frame | Source bytes | Output bytes | Source/output |
|---|---:|---:|---:|
| A001_083 FHD f07 | 3,244,544 | 1,261,568 | 2.572:1 |
| pre-stage4 A001_001 f001 | 3,244,544 | 1,329,152 | 2.441:1 |
| pre-stage4 A001_002 f001 | 3,244,544 | 1,398,272 | 2.320:1 |
| stage4 A001_001 f249 | 3,244,544 | 1,389,056 | 2.336:1 |

All four pass LibRaw equality of **2,110,240 RAW samples per frame**, original
root-IFD bytes, non-layout tags/values, nested metadata bytes, unchanged source
SHA-256, and unchanged original-builder/dependency hashes. These are four
frames, not complete sequence, high-entropy worst-case, or sustained-encoding
tests. No camera playback or hardware throughput claim follows from them.

**Pixel-lossless does not mean original-file byte roundtrip.** TIFF layout,
root pointer, and encoded storage change. The stock FHD strip includes 12
non-pixel bytes after the final raster row; the report retains their byte count
and SHA-256, but the compressed output does not preserve those bytes as image
samples. The original source files remain untouched.

There are 11 local regression tests: eight in-memory TIFF/metadata guards and
three no-encoder checks for source-as-output, existing-output preservation,
and unsupported TIFF rejection before output creation.
