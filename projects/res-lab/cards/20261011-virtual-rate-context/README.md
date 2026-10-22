# v12 development candidate

Corrects virtual-rate CinemaDNG FrameRate while preserving the native recorder
getter and avoiding interactive settings calls. Also contains the v10
same-carrier notification correction.

240/280p DNG samples now have correct tags. Sustained recording and preview
mosaic remain unresolved. This is not a production release or a claim that
240/280p recording is fixed.

Build commands and artifacts use the maintained `build_v3_reslab.py` pipeline.
Only the compatible32RESCUS.BIN update is needed; AutoRun, loader and producer
are byte-identical to the previous candidate. Preserve the user's96-byte CFG
through the reviewed update/readback process.

See `../../validation/20261011-virtual-rate-context/RESULTS.md` and
`../../validation/20261011-virtual-rate-context-live/RESULTS.md`.
