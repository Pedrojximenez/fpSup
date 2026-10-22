Sensor Lab r81 USER-relocated debug test card (SIGMA fp Ver.5.02)

KNOWN BAD (2026-10-04): On-camera REC freezes immediately. The picker reads
COLTAB+4 (0xC0BE3FA4) as profile ID instead of 87 after cave compaction.
Do not use this r81 card for another recording trial. Keep it only as the
reproducible incident artifact; the corrected source needs a new build and
hardware retest.

Copy AutoRun.txt and fpSup.BIN to the SD card root only when replacing its
current boot card. This is a standalone Sensor Lab build with the USB shell;
it is not a merge of the previous Open Gate/Gyro/Lossless card. Fast Start is
off, so this build does not write the persistent Fast settings block.

Offline checks (2026-10-04): final artifact and 15 damaged-file cases pass;
full-chain ARM emulation arms 19 core and 10 UI hooks, restores all 297 journal
records at power-off, and preserves all 20,480 factory bytes in C0730000..
C0735000. Early or late journal-gate refusal does not expose unsafe hooks or
the private B2_5 page. Source hashes match MANIFEST.json. Camera operation,
recording, warm retained-image behavior and the earlier 1478 symptom remain
unverified on hardware.

AutoRun.txt SHA-256:
5dc89b8506e8ce408276a9eab61fbb9fda94d4a194b65f2fd17c9e410b8fe642
fpSup.BIN SHA-256:
2c1ae8954be883e45f3d87bba25ec00d497aa29f0aea817cf229b4265aa3cf84
