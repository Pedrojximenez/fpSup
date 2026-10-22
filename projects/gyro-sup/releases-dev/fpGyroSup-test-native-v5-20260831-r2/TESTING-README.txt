fpGyroSup native lifecycle r2 — boot isolation test

Do not boot r1 again. Start with debug-card only. Do not mix files between the
two card sets or with an older release.

1. Switch the camera off and physically remove the battery for at least 30 sec.
2. Keep the USB cable unplugged.
3. Back up the SD root AutoRun.txt, VSHL.BIN and PGEN.BIN.
4. Replace those three files as one set with the contents of debug-card/.
5. Confirm GYRO/ exists. Existing files inside it may remain: r2 does not scan
   or modify old GYR files during boot.
6. Insert card and battery, power on, and wait for fpSup!.

If debug-card reaches fpSup!:
- Record one expendable 5-second CinemaDNG clip.
- Stop and let all card activity finish.
- Power off normally, then read the card.
- Do not try release-card yet; first inspect the new clip and GYR.

If debug-card still freezes at 90%:
- Do not retry.
- After the SD light is inactive, switch off and remove the battery.
- Read back the three boot files so their hashes can be compared.

Interpretation:
- debug boots, release later freezes: callback-context file loading is the cause.
- both boot: r1 recovery scan or skipped manager initialisation caused the freeze.
- debug still freezes after a real cold boot: inspect the actual card files and
  persistent hook/task state before changing the lifecycle code.

release-card is included only for the second A/B step. It uses the last-known
media-manager loader sequence and has no boot recovery, but still performs the
VSHL file read from the gyro callback.
