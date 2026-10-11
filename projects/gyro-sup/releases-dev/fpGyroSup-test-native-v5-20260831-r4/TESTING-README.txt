fpGyroSup native lifecycle r4 — SD/CDNG TEST

Use release-card first. Do not use debug-card for the first test.

r4 removes every LDREX/STREX/CLREX instruction from the native logger and PGEN
images. PGEN is the sole lifecycle phase writer. The callback claims S_FILE and
latches a publication generation; the writer opens a GYR only when the attached
generation still matches the published path and volume.

Recovery remains disabled. Existing GYRO files may remain on the card.

Test:
1. Remove the camera battery for at least 30 seconds and keep USB unplugged.
2. Install AutoRun.txt, VSHL.BIN and PGEN.BIN from release-card as one set.
3. Cold boot and confirm fpSup! appears.
4. Record exactly one expendable 5-second CinemaDNG clip to SD.
5. Stop recording. Leave the camera on while the SD activity/protection remains
   active; r4 drains GCSV/JSON stages continuously without an intentional gap.
6. As soon as SD activity is fully idle and recording is unlocked, power off,
   remove the card and read it back.

Do not test MOV, USB SSD, rapid consecutive takes or boot recovery in this pass.
If the camera freezes, do not retry. Once the SD light is inactive, power off,
remove the battery and return the card to the reader.

