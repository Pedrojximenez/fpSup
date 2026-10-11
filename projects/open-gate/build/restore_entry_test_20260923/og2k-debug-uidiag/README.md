# OG2K native UI runtime candidate

This package is coupled OpenGate test material, not a product release.  It carries the same 360-record native UI payload, private NBR pack and three UI hooks as the OG3K package, with OG2K drawn into the three private tiles.  The resource names inside the pack stay OG3K_QS / OG3K_SET / OG3K_FONT because the stock UI records look them up by name; only the drawn glyphs are target-dependent.

This README makes no camera claim for OG2K.  See the project notes for whatever hardware evidence that target has.

The UI parser-copy mechanism itself was camera-proven for OG3K on this firmware; that proves the mechanism, not this target.

Warm restart and hot reinstall are neither tested nor supported; begin only from a battery-out cold boot.  Do not run size_ctl, cfgring, cfgsnap, appendobs, elemobs, xcitrace, the 0xC0733400 log family, zoomlog, og3ktile, or livepatch while it is resident: those diagnostics overlap its state/code ranges.  The firmware's built-in `gui image log` and `display capture` are safe.

Install only `AutoRun.txt` and `fpSup.BIN` at the card root, then perform a battery-out cold boot.  Removing or renaming `AutoRun.txt` followed by another complete cold boot restores stock firmware behaviour.
