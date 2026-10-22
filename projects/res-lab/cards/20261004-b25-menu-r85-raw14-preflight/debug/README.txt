Sensor Lab r85 debug B2_5 — offline RAW14 preflight candidate (2026-10-04)

AutoRun.txt and fpSup.BIN are a matched pair. Their exact hashes are recorded
in MANIFEST.json and validation/20261004-raw14/RESULTS.md.

This card has NOT been written to fpSup2 or tested on a camera. The three
identified REC-start events are guarded before native preparation, but the
sensor, actual RAW14 DNG output, gain, and stop behavior remain unverified.
Full-height M0/M141 do not have a selectable safe recording rate yet.

Important native-settings behavior: choosing 14-bit changes the camera's
real eRawBitType setting. Automatic 14->12 restoration before the stock
power-off save is not implemented in this build (WITH_BIT_POFF=False).
Leaving CUSTOM resets it to 12 through the existing resolution setter;
ordinary shutdown while still at 14-bit/CUSTOM may persist 14-bit. The
user-approved abnormal-shutdown risk does not establish ordinary-shutdown
restoration. Do not treat this candidate as normal-shutdown-safe RAW14.

The current fpSup2 was read as r83 and contains nine 12-bit clips. Preserve
its baseline before any later SD-card write.
