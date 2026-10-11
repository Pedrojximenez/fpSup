Sensor Lab r86 debug B2_5 offline test card (2026-10-04)

Exact artifact SHA-256:
  AutoRun.txt  5dc89b8506e8ce408276a9eab61fbb9fda94d4a194b65f2fd17c9e410b8fe642
  fpSup.BIN    28ac9adb81a0070b979066a43aa81d7d8f5b71f240c2ea092b181ffc19db81ce
  MANIFEST     ca82441fe8314c939d210462baddfe91aad8b44e2d6fd1403a7c52bb9548b45b

This exact card adds a SaveOn v2 hook. When the native RAW14 bit enum is 1,
the seven serialized setting fields are normalized to stock RAW12 enum 0
for the pending save, then restored in the live source record. An exact-card
offline Unicorn test confirms the separate working bank remains 14-bit.

Artifact and migrated-boot checks pass: 21 core hooks, 10 late UI hooks,
299 journal records restored, and all 20,480 factory cave bytes preserved.
The exact RAW14 picker/recording-preflight matrix passes for 20 combinations
of six sensor modes with the presently selectable rates. M0 and M141 have
an 18p recipe in the engine but no private-rate recording bridge in this
artifact, so they are not selectable for recording. No 14-bit movie recording,
normal shutdown/restart, black-level or receiver calibration is proven on
camera by these offline tests.

On 2026-10-04 this exact debug card was written to fpSup2, then all eight
boot/UI files were read back and SHA-256 checked. Only fpSup.BIN and
MANIFEST.json differed from r83. The r83 boot assets are backed up at
archive/fpSup2-20261004-pre-r86/; its write_report.json records every hash.
The 699 existing CinemaDNG frames and nine WAV files remain on the card.
Keep AutoRun.txt, fpSup.BIN, MANIFEST.json and FPSUPUI from one build together.
Do not use older r80/r81/r84 artifacts for trial.
