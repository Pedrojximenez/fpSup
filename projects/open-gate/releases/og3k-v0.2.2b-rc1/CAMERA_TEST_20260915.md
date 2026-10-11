# OG3K v0.2.2b-RC1 camera result — 2026-09-15

## Exact artifact

The card-root files match the frozen no-shell RC1 exactly:

- `AutoRun.txt`: `8836b3703f5196e948739a49cd11877191ce8f540d8aaedf81a429713d95384c`
- `VSHL.BIN`: `da1c94e05828c7fec423fed044856d54ba839532d38a5bd2e446942778062cd7`

This is the artifact whose VSHL differs from public v0.2.2a in exactly seven 32-bit words, all in the `fmttable` r1-to-r5 fix.

## Recorded evidence

The card was mounted read-only for analysis at `/Volumes/fpSup`. The three new 25 fps / 180-degree clips were identified by creation order, geometry, and Sigma MakerNote `0x011c = 180`.

| Clip | Frames checked | Mode | Raster | Default crop | Bits | FrameRate | ExposureTime | Exposure | ISO | Result |
|---|---:|---|---|---|---:|---:|---:|---|---:|---|
| `A001_187` | 45/45 | OG3K | 3024 x 2010 | 3008 x 2000 at 8,5 | 12 | 25.000 | 0.020 s (1/50) | M, 180 degrees | 800 | PASS |
| `A001_188` | 20/20 | UHD | 3856 x 2170 | 3840 x 2160 at 8,5 | 8 | 25.000 | 0.020 s (1/50) | M, 180 degrees | 800 | PASS |
| `A001_189` | 35/35 | FHD | 1936 x 1090 | 1920 x 1080 at 8,5 | 12 | 25.000 | 0.020 s (1/50) | M, 180 degrees | 800 | PASS |

All 100 main-image IFDs were checked, not only representative frames. There were no geometry, bit-depth, frame-rate, shutter-time, exposure-mode, ISO, or shutter-angle outliers.

`A001_186` was not included in the 25 fps / 180-degree result: it is a 37-frame OG3K clip at 29.97002997 fps and 1/60, but its Sigma MakerNote angle value is 0 rather than 180.

## Conclusion

The exact no-shell RC1 passes the reported 25 fps / 180-degree case in OG3K, UHD, and FHD. FHD and UHD also return correct stock geometry after leaving OG3K, so the non-OG3K pass-through exercised by the r1 fix is working in this run.

This result supports promoting the seven-word r1-to-r5 fix as v0.2.2b. It does not establish that every report of lighting flicker has the same cause, and it does not validate OG3K with Super35/crop enabled.
