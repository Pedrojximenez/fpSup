# OG3K native UI release test package

This package contains the same OpenGate core, 360-record native UI payload, private NBR pack, and three UI hooks as the camera-tested debug candidate. It is built with `--no-shell`: no USB worker, USB interface/endpoint patches, or worker state block remains resident.  It is still a test release and must pass faster-media duration, playback, and inactive UHD/FHD regressions before promotion.

Install only `AutoRun.txt` and `VSHL.BIN` at the card root, then perform a battery-out cold boot.  Removing or renaming `AutoRun.txt` followed by another complete cold boot restores stock firmware behavior.
