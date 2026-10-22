fpGyroSup native lifecycle AutoRun test — SIGMA fp Ver.5.02 only

This is a no-USB-shell test build. Replace AutoRun.txt, VSHL.BIN and PGEN.BIN
as one set. Never mix one of these files with an older release.

Before the first boot:
1. Back up the card's existing AutoRun.txt, VSHL.BIN and PGEN.BIN.
2. Power the camera off, remove the battery, and remove the SD card.
3. Copy everything inside card/ to the SD-card root.
4. Confirm that the SD root contains GYRO/.
5. Reinsert the card and battery, then wait for fpSup! before recording.

First test:
1. Record one expendable 5-second CinemaDNG clip.
2. Stop and allow the camera to finish all card activity.
3. Record two short CinemaDNG clips as soon as the camera permits each start.
4. After card activity finishes, power off and inspect GYRO/ plus the clip folders.
5. Test MOV only after the CinemaDNG pass is clean. SSD is a separate later pass.

Expected files for a clean CinemaDNG take:
  GYRO/A001_ddd.GYR
  CINEMA/A001_ddd/A001_ddd.gcsv
  CINEMA/A001_ddd/A001_ddd.json

Emergency stop / rollback:
- If the camera freezes, stop testing and remove the battery after card activity
  has ceased or cannot make progress.
- To disable injection, remove AutoRun.txt and cold boot.
- To restore the previous build, replace all three boot files from the backup
  as a set, then cold boot. Do not delete GYRO/ or recorded media.
