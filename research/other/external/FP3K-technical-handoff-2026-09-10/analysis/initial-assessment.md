# Sigma fp full-sensor 3000×2000 investigation

## Target
Full sensor width and height, reduced to approximately 3000×2000 (3:2) for video. Confirmed: 12-bit CinemaDNG to USB SSD, 24 fps initially, 25/30 fps preferred. Every sensor pixel contributing is the priority; skipping is a last resort. See sample-findings.md for the subsequent sample analysis. Secondary goal deferred.

## Original firmware (unmodified)
- File: FP__V502.bin
- Actual size: 25,692,160 bytes
- SHA-256: c9fa76f32f523bb2dc9a3fbda39418c31573cab6a1aa5c56d28c371862066ed8
- ASCII header: LENGTH=24503296 w71c1 VER=V91 DVR=5.02 SUM=2768501654 IPL PTBL DAT1
- @DFI marker at 0x100.
- The LENGTH field is 1,188,864 bytes smaller than the file; its meaning is not established.
- macOS file identifies an old tar archive, but this has not been validated and should not be treated as the actual format.
- No ELF, gzip, XZ, or ZIP signatures found by a simple byte scan.
- Printable fragments include IMX410Z at approximately 0x6ece2c, sensor and cinema fragments, and resolution fragments. These are leads, not confirmed hardware identification or patch locations.
- Sampled 64 KiB block entropy roughly 7.42–7.63 bits/byte. Compression, encoding, encryption, executable architecture, and packaging are not yet established.
- No extraction, patching, checksum reconstruction, signature verification, or camera flashing performed.

## Bandwidth arithmetic
Uncompressed image payload only, decimal MB/s; excludes metadata, audio, filesystem overhead, and link overhead.
- 3000×2000, packed 12-bit, 24 fps: 216 MB/s.
- 3000×2000, packed 12-bit, 30 fps: 270 MB/s.
- 3000×2000, 16-bit storage, 24 fps: 288 MB/s.
- 3000×2000, 16-bit storage, 30 fps: 360 MB/s.
- 3840×2160 has 8,294,400 pixels; 3000×2000 has 6,000,000 (about 72.3% as many).
These calculations do not prove sensor readout, processing, or firmware support. Full-area reduced-resolution capture can still be described as open gate; full native resolution is a separate requirement. Bayer RAW cannot be reduced with arbitrary RGB-style scaling while retaining valid raw samples.

## Official references consulted
- https://www.sigma-global.com/en/support/firmware/fp/ — version 5.02 and official updater procedure. Older firmware is rejected by the documented updater; a recovery/downgrade route is not established.
- https://www.sigma-global.com/en/cameras/fp/?local=table&tab=support&table_id=11934 — portable SSD support up to UHD 12-bit 29.97p with recommended media.

## Next steps
1. Obtain camera firmware version and desired frame rate, format, bit depth, and destination.
2. Obtain untouched still DNG and a few original CinemaDNG frames of the same static scene, with unchanged camera/lens position and crop disabled, plus settings and media details.
3. Decode firmware packaging and identify architecture, integrity checks, and update validation.
4. Locate sensor mode configuration, processing dimensions, buffer allocation, and CinemaDNG writer configuration.
5. Establish recovery options before attempting a modified firmware installation. No flashable modified firmware is currently available.
