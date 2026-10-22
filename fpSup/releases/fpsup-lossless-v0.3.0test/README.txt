================================================================
 Lossless CinemaDNG  fpsup-lossless-v0.3.0test
 SIGMA fp Ver.5.02 only -- Loader v3 card
================================================================

WHAT IT IS

  The fp has a hardware lossless codec it never uses for video.  This
  card puts it to work: with Lossless RAW on, each CinemaDNG frame is
  compressed losslessly (DNG Compression 7, tiled) while you record.
  An FHD 12-bit frame of 3.2 MB typically becomes about 1.0-1.1 MB.

  Every frame either is compressed or is written exactly as the camera
  writes it today.  When the codec cannot finish a frame in time the
  frame goes out uncompressed, so a clip can mix compressed and
  uncompressed frames.  Nothing is dropped to make room.  The first
  frame of every take is always uncompressed (DaVinci Resolve plays a
  mixed clip only when its first frame is).

  Compressed clips play back in the camera: the player decodes them
  with the same hardware.

  Use it together with FCAP (30FCAP.BIN).  Without FCAP a compressed
  take stops by itself after about 94 frames (about 1.5 s at 59.94p,
  3 s at 29.97p): the camera only hands files to the card in batches
  of 64 MB or 128 files, and small compressed files reach neither in
  time.  FCAP makes the batch 40 files.  On the fpSup-Merge page,
  ticking Lossless ticks FCAP too.

HOW TO USE

  Copy AutoRun.txt and the fpSup folder to the root of the SD card,
  add FCAP's fpSup folder (or build the card on the fpSup-Merge page)
  and start the camera.  SHOOT menu, page 2 (CINE), below Audio
  Recording: Lossless RAW  OFF / ON.

  Your choice is kept across power-off.  It is saved in this card's own
  file (fpSup/10LOSS.BIN), a second or so after you change it, while
  the camera is not recording; nothing is written to the camera's own
  settings.  Copying a fresh 10LOSS.BIN onto the card sets it back to
  OFF.

  To combine with other fpSup products released for Loader v3, copy
  their fpSup folders over this one: every product carries the same
  LOADER.BIN and UI frames, and its own NNNAME.BIN.

  Upgrading from an older (single fpSup.BIN) card: delete the old
  fpSup.BIN (and the FPSUPUI folder, if there is one) from the card
  root.  A card from before Loader v3 cannot be mixed with this one.

WHAT CHANGED SINCE fpsup-lossless-v0.2.0test

  - Uses less of the camera's processor: the code now runs from
    cached memory, the compressed frame's table is prepared once per
    take inside the DNG header instead of rewritten into every frame,
    and the codec is switched on once per take instead of for every
    frame.  About 1 point of CPU over Lossless OFF at FHD 29.97p.
  - New compressed-frame layout: the header is 1 KB longer (it holds
    the compressed frame's table in a private tag); the pixels follow
    it.  Uncompressed frames of a Lossless take carry the same longer
    header and are otherwise unchanged.  Takes with Lossless OFF are
    exactly as the camera writes them.
  - The batch-size change that v0.2.0test made to avoid the 94-frame
    stop is gone; FCAP now does that job, for every format.
  - A frame whose header is not the one prepared for its take is
    written uncompressed rather than risk a wrong file.

WHAT HAS BEEN VERIFIED

  On a SIGMA fp, Ver.5.02, 2026-10-15, with this release's 10LOSS.BIN
  (same SHA-256 as MANIFEST.txt, except the 16-byte ON/OFF record set
  to ON), FCAP 30FCAP.BIN d2b22eda..., this release's AutoRun.txt and
  UI frames, the USB shell, and a LOADER.BIN of the same Loader v3
  built with the management page (8,248 B, 3c9a6b36...):

    - FHD 12-bit 29.97p to SD (UHS-II): two 4 s takes and one 15 s
      take (434 frames): every frame after the first compressed, none
      refused by the codec, no stall.
    - FHD 12-bit 59.94p to SD (UHS-II): two 4 s takes and one 15 s
      take (869 frames): the same.
    - Sample frames from both 15 s takes (first, middle, last) decode
      on a computer (LibRaw) to the full 1936x1090 picture.
    - In-camera playback of the 59.94p take: plays; 660 compressed
      frames decoded by the card, none refused.

  With earlier test builds of the same file layout (2026-10-15): DaVinci
  Resolve played the clips; without FCAP a 59.94p compressed take
  stopped after about 2 s, with FCAP an 8 s take ran to the end.

  NOT verified: OG2K/OG3K and other Res-Custom formats, UHD, 10-bit,
  frame rates above 59.94p, SSD recording, this exact build in DaVinci
  Resolve, this release folder copied onto a fresh card as-is, other
  fpSup products on the same card.  Test build: make and inspect a
  disposable recording before using it for important footage.

================================================================
