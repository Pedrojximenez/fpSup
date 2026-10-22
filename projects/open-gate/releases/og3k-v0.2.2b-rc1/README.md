# OG3K v0.2.2b-RC1 — OFFLINE-ONLY candidate

This exact package has passed offline structural, pairing, and regression checks. It has not been installed or tested on a camera. Do not treat it as a public release.

The change from public v0.2.2a is deliberately narrow: seven 32-bit words in the `fmttable` hook preserve the stock FHD/UHD table pointer. The shutter-angle calculation itself is unchanged. The package is built without the USB worker or USB shell.

Do not install while the camera is in use. When hardware testing is authorized, begin from a complete battery-out cold boot and follow `RC1_NOTES.md`. Only `AutoRun.txt` and `VSHL.BIN` belong at the card root. Removing or renaming those files and performing another complete battery-out cold boot restores stock firmware behavior.
