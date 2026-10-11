fpGyroSup native lifecycle r5 — SD/CinemaDNG TEST

Use release-card first. Do not use debug-card for the first test.

r5 keeps PGEN as the only lifecycle-phase writer. The recording callback claims
the file slot without exclusive memory instructions, then validates the same
publication generation on both sides of an acquire barrier. Before publishing a
native path, PGEN also revalidates the native token/path and repeats the volume
lookup after every blocking call. A GYR can open only after native media is
established and its attached generation still matches the published descriptor.

Recovery remains disabled. Existing GYRO files may remain on the card.

Test:
1. Remove the camera battery for at least 30 seconds and keep USB unplugged.
2. Install AutoRun.txt, VSHL.BIN and PGEN.BIN from release-card as one set.
3. Cold boot and confirm fpSup! appears.
4. Record exactly one expendable 5-second CinemaDNG clip to SD.
5. Stop recording and leave the camera on continuously while SD activity or
   recording protection remains active. r5 runs its GCSV/JSON stages without an
   intentional idle gap.
6. As soon as SD activity is fully idle and recording is unlocked, power off,
   remove the card and return it to the reader.

Do not test MOV, USB SSD, rapid consecutive takes or boot recovery in this pass.
The volume lookup is stable during publication, but SD/SSD binding still needs a
separate SSD test before SSD support is claimed.

If the camera freezes, do not retry. Once the SD light is inactive, power off,
remove the battery and return the card to the reader.
