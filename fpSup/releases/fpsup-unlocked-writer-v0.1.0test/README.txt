================================================================
 Unlocked Writer  fpsup-unlocked-writer-v0.1.0test
 SIGMA fp Ver.5.02 only -- Loader v3 card
================================================================

WHAT IT IS

  While recording, the camera collects frames into batches and writes
  each batch to the card while holding its file-system lock.  Nothing
  else on the file system can run during that write: not the
  cluster bookkeeping, not opening the next frame's file.  The two
  take turns.

  Unlocked Writer replaces only that last step.  A full batch is
  handed to a dedicated writer task, which sends it to the card
  without the file-system lock; the camera goes straight on with the
  next frames.  The card is written straight from the camera's own
  frame buffers (no copy).  What goes into a batch, the CinemaDNG
  files and the file system are all the camera's own.

  It works the same way for the SD card (CMD20 video recording) and
  for an SSD, whenever the camera records in batches.  An SSD
  formatted in the camera's Standard layout is written frame by
  frame by the camera itself; Unlocked Writer then stays out of the
  way.

  The batch is 8 MB, so frames reach the card sooner and in smaller
  steps than the camera's own 64 MB.  Your settings are not touched;
  nothing is saved anywhere.

HOW TO USE

  Copy AutoRun.txt and the fpSup folder to the root of the SD card and
  start the camera.  There is no menu item: it is on whenever the file
  20ULWR.BIN is on the card.

  To combine with other fpSup products released for Loader v3, copy
  their fpSup folders over this one: every product carries the same
  LOADER.BIN and UI frames, and its own NNNAME.BIN.

  Upgrading from an older (single fpSup.BIN) card: delete the old
  fpSup.BIN from the card root.  A card from before Loader v3 cannot
  be mixed with this one.

WHAT CHANGED

  - First release.

WHAT HAS BEEN VERIFIED

  20ULWR.BIN is the development build RECW 0107f8d6 with only its name
  changed (sup ID, task and event-flag name); the code is the same.
  These exact bytes (MANIFEST.txt) have not yet run on the camera.

  On a SIGMA fp, Ver.5.02, 2026-10-15, with RECW 0107f8d6 together with
  Lossless, FCAP and Res-Custom on the same card:

    - SD (UHS-II), FHD 59.94p, Lossless ON, 8 s: 448 frames, every
      frame written, no write error.  Sample frames decode on a
      computer; in-camera playback normal.
    - SD (V60), OG3K 29.97p, Lossless ON, six takes run until the
      camera stopped them itself (card too slow
      for the format): every frame
      finished, the camera returned to standby each time.
    - SD (200 MB/s), OG3K 23.98p, Lossless ON: 8532 frames, all
      finished.
    - SSD (2 TB, Custom layout), OG3K, Lossless ON, stopped by the
      button: 7958 frames, all finished, no write error.

  Offline: the writer's queue, the firmware adapter and a whole
  recording through the real Loader v3 and the camera's own file
  system and SD driver code (CPU emulation) -- 31 tests, including
  the stop-while-writing race found during the camera tests.

  A stop could leave the camera stuck at "writing" with an earlier
  build (a race in the camera's own stop path that the writer made
  more likely); fixed in 0107f8d6 and not seen again in the takes
  above.

  NOT verified: these exact bytes on the camera; recording without
  FCAP; UHD; SSD in the Standard layout with this file (the camera
  does not use batches there).  Test build: make and inspect a
  disposable recording before using it for important footage.

================================================================
