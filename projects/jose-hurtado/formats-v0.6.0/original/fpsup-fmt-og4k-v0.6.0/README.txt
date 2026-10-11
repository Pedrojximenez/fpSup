================================================================
 fpSup-Formats-OG4K  fpsup-fmt-og4k-v0.6.0
 SIGMA fp -- Open Gate 4K as its own sup
================================================================

  Firmware Ver.5.02 only.  RAM only: delete AutoRun.txt, remove the
  battery, and the camera is stock.  Nothing is written to flash.
  Test build.  By Jose Hurtado (El Cacharrista, https://elcacharrista.com); questions and
  bugs to the author.

WHAT IT IS

  One of the five fpSup-Formats packages:

     fpSup-Formats-S16    fpSup-Formats-OG2K    fpSup-Formats-OG3K
     fpSup-Formats-OG3.5K fpSup-Formats-OG4K

  OG4K: the whole 3:2 sensor read 1:1 and scaled by the ISP to exactly
  3840x2560.  With the camera's Crop Mode ON: a 1:1 crop of the sensor
  centre, the same DNG size (crop factor 1.57), like UHD Crop.  23.98 ..
  29.97 fps.  354 MB/s at 24p 12-bit uncompressed, less with
  fpSup-Lossless.  Needs an SSD.

  Put any of them on one card -- one, two, ... all five -- with or
  without Gyro, RAW-View and Lossless.  The Resolution menu (Settings
  and Quick Set) shows the stock UHD and FHD plus exactly the formats
  on the card.  Frame rates, bit depths (8/10/12-bit CinemaDNG) and the
  rates a format cannot record (greyed) travel with each format.

  Not with the older fpSup-OG2K / fpSup-OG3K cards: they take the same
  menu slot.

NEW IN v0.6.0

  OG4K and OG3.5K follow the camera's Crop Mode (Settings or Quick
  Set): OFF = the whole sensor, ON = a 1:1 crop of the sensor centre
  with the same DNG size.  Standby, AF, the magnifier and REC show the
  framing that is recorded.  The core changed, so all five packages are
  new: do not mix them with v0.5.0 packages.

  Boot refresh: at power-on the camera builds its standby view before
  the card has applied the saved format, so a format could come up
  without its framing until the magnifier, AF or the menu was used.
  Once per load, as soon as the format is applied, the core restarts
  the camera's live-view signal process (MovSigProcess), which rebuilds
  the view with the format.  Never while recording; stock formats are
  left alone.

HOW IT COMBINES

  Every package carries the same core byte for byte; fpSup-Merge folds
  identical records, so it lands once.  The core knows there are six
  slots, not which formats exist: each format brings its registry data
  (and its Crop Mode record), its menu entry and its own icon pack, and
  the core's entry (an absolute address, called once per package,
  idempotent) builds the menu at every load from the formats on the
  card.  A new format is a new package; the others do not change.

USE

  Compose on fpSup-Merge (tick one or more fpSup-Formats tiles) and copy
  what the zip holds to the root of the card, the FPSUPUI folder
  included.  Boot WITHOUT the USB cable attached.

VERIFIED (camera, 2026-10-05)

  v0.6.0, on the author's camera:
  - Boot: S16 (any format of the card) shows its framing in standby
    right after the card loads, without touching anything (the boot
    refresh below).
  - OG4K and OG3.5K with Crop Mode OFF and ON: standby, AF, the
    magnifier at 4x and 8x and REC show the same framing; the crop
    follows Crop Mode at once, also when switching between OG4K Crop
    and OG3.5K Crop, from the menu and from Quick Set.
  - fpSup-Lossless-Mem: the setting survived a battery pull (test
    build with the same mechanism).
  v0.5.0 (same formats, earlier core): the five formats on one card,
  switching between all five; OG4K 10 of 10 takes with a clean first
  frame, DNG 3840x2560 12-bit.
  Host: every combination of the five formats runs in an emulator on
  the 5.02 image, cold and after a warm restart, including the Crop Mode
  paths; the fpSup-Merge checks pass with Gyro, RAW-View, Lossless and
  Fast Start in every combination (496 compositions).

NOT VERIFIED

  Every combination on the camera; long series of takes; the first
  frame of crop takes over a long series.  S16 and OG2K at 100 fps do not
  record with Gyro logging; with fpSup-Gyro-Data set to OFF they do (camera).
