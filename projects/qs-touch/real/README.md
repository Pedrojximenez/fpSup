# Native QS Touch — first camera candidate

This is a Loader v4 SUP (`fpSup/ZQS.BIN`, id QSN1, services >=6).
It modifies the original QS_CINE resource (GUI 159); it does not register a
separate FT_ page or fpSup test-menu entry. Only ZQS.BIN is deployed to the
existing card. AutoRun and the shared loader do not need replacement.

FORMAT/DC/RES/FPS faces replace matching native slots. Other slots, original
QS entry/lifecycle, AEL actions and native setting subscribers remain in use.
A tap selects a slot. Footer -/+ and a horizontal footer drag adjust the
selected native value. Upward swipe requests the native QS close action.
No new animation is requested.

The first candidate uses actual MV_RecordingFormat, CM_DCCrop, MV_Resolution
and MV_FrameRate variables through the original notifying setter and reads
back the result. It does not subscribe a C callback over a stock owner.
Current labels cover CinemaDNG/MOV, crop OFF/ON, UHD/FHD and nine native frame
rates. Other resolution/frame-rate indices are shown explicitly as RES N or
FPS N, not as invented dimensions or rates.

Combined CDNG bit-depth choices, OG/HD/S35/APS-C crop presets and custom mm,
custom resolution dimensions, inline advanced controls, reorder/add/remove,
live-view downward opening and horizontal page navigation are NOT implemented
in this first native candidate. Existing Res-Custom records are forwarded at
their original positions; its data is not replaced by prototype values.

Run offline verification in a fresh directory:

    python3 -B projects/qs-touch/real/verify.py --out NEW_DIRECTORY

Verification executes the exact reference Loader v4 and SUP, original NBU
parser and native variable setter instructions. GUI scheduling, construction,
OS/heap/file services in the emulator are explicit substitutes. It does not
prove physical touch, display timing, cache lifetime or camera compatibility.
Physical evidence belongs under validation/20261024-camera/native-qs/.

Touch owns the same exclusive firmware slot as Tap to Zoom. The user's
existing authorization pauses Tap to Zoom during testing and restores it
when testing ends. No recording or persistent menu-save is part of this trial.
