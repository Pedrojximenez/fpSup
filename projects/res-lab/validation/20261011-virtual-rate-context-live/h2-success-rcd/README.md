# September29 H2 recording comparison

H2S240.RCD reconstructs the archived M12/p13 parameter family: RAW1008x672, crop992x662,12-bit, RWZM2048/1024,25 archived live canvas pairs. Select H2S240 and native29.97p (30). That carrier alone requests sensor239.76p and capture-engine239.76p; the menu/container retains29.97p, like A001_193.

Requires the development32RESCUS.BIN productv16. A required section makesv15 and earlier reject this file instead of silently ignoring its capture timing. The file belongs at `\fpSup\RESCUS\H2S240.RCD`. Do not select280p for this historical comparison.

The exact old binary and full FPS-latch snapshot are unavailable. Geometry matches the archived live25 pairs and independent nativep13 defaults. Engine cadence follows the preserved predecessor code and is explicitly an inference. This is a hardware test artifact, not a confirmed repair.

2026-10-11 hardware result: exact v16 consumer/RCD, normal-menu enable and
post-reboot H2 state verified. SD A001_086 automatically stopped at req94/fin94
with native vbuf/raw1; nativeREC0 and HDMI STBY confirmed. First/middle/last
SD DNGs have aligned headers and the expected native30 tags. The manual SSD
follow-up was reported to stop early. Host-mounted A001_278/279 each contain94
DNGs;65 per take have the TIFF header displaced by19456 or65536 bytes.
Original files/hashes are preserved; exact per-take native stop logs unavailable.
See `../recycle-source-audit/REPORT.md` and `../RESULTS.md`. Sustained recording
has not passed acceptance.
