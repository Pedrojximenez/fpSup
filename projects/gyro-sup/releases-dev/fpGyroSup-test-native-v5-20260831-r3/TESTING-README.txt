fpGyroSup native lifecycle r3 — BOOT TEST ONLY

Use release-card first. Do not use debug-card for the first test.

This build adds an ordinary lifecycle-state precheck before LDREX. At idle,
the gyro callback now returns without issuing any exclusive access against the
DMA-backed bufmem pool. Recovery remains disabled and the known media-manager
initialisation path is retained.

Test:
1. Remove the camera battery for at least 30 seconds.
2. Keep USB unplugged.
3. Install AutoRun.txt, VSHL.BIN and PGEN.BIN from release-card as one set.
4. Cold boot and report whether the display passes 90% and reaches fpSup!.
5. DO NOT RECORD with r3. The recording edge still contains the diagnostic
   exclusive pair; r3 exists only to prove or reject the boot hypothesis.

If it freezes, do not retry. Power off once the SD light is inactive, remove
the battery, and return the card to the reader.

