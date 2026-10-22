================================================================
 fpSup-Formats  fpsup-formats-v0.3.0a
 SIGMA fp -- six resolutions in one menu: Super 16 crop and
 3.5K open gate next to the stock and OG rows
================================================================

  Firmware Ver.5.02 only.  RAM only: delete AutoRun.txt, remove the
  battery, and the camera is stock.  Nothing is written to flash.

  Only AutoRun.txt and fpSup.BIN go on the SD card, in the root.
  Boot WITHOUT the USB cable attached.

  This version replaces fpsup-formats-v0.1.0a (2026-09-24).  The
  0.2.x builds were internal.  History: CHANGELOG.txt.

WHAT IT IS

  The Resolution menu gets six rows:

     UHD   FHD   S16   OG2K   OG3K   OG3.5K

  - UHD and FHD are the camera's own, untouched (Crop Mode included).
  - S16 is a Super 16 crop: 2112x1248 photosites read 1:1, no
    binning, no scaling (12.55 x 7.41 mm, crop factor 2.87).  The
    live view shows the crop in standby too.
  - OG2K and OG3K are the binned 3:2 open gates of the fpSup-OG2K and
    fpSup-OG3K cards, on the same card.
  - OG3.5K reads EVERY photosite of the 3:2 area and lets the ISP
    scale it by 1.75: more detail and less aliasing than binning,
    more rolling shutter (25 ms).  Its live view is the stock UHD
    one (hardware-binned), fluid, no reframing when REC starts.

  All six rows record CinemaDNG at 12-bit (8/10-bit: see below) and
  the LCD shows the right picture in standby and while recording.
  Settings and Quick Set show the six choices with native UI.

  row     sensor readout                    stored     DNG crop   fps           MB/s 12b 24p
  ------  --------------------------------  ---------  ---------  ------------  ------------
  UHD     stock                             3856x2170  3840x2160  stock         301
  FHD     stock                             1936x1090  1920x1080  stock         stock
  S16     2112x1248 window, 1:1             2112x1248  2096x1238  23.98..29.97   95
  OG2K    6048x4032 binned 3x3              2016x1344  2000x1334  23.98..100     98
  OG3K    6064x4024 binned 2x2              3024x2010  3008x2000  23.98..59.94  219
  OG3.5K  6062x4040 every photosite, /1.75  3464x2308  3456x2308  23.98..29.97  290

  Rolling shutter: S16 25 ms (the full readout still runs; the crop
  is the ISP's), OG2K 8.3 ms, OG3K 12.4 ms, OG3.5K 25 ms.

----------------------------------------------------------------
NEW SINCE v0.1.0a
----------------------------------------------------------------

  Formats
  - S16 and OG3.5K are new.  FHD+, 3K+, OG2K+ and OG3K+ are gone:
    OG3.5K replaces OG3K+ with a better live view, the others did
    not earn their place (SSD-only, or aliasing on the /3 rows).
  - OG3.5K goes through the stock UHD video profile: the live view is
    hardware-binned like UHD's, the recording is the ISP's /1.75.
    The DNG crop is centred by the camera ((raster - crop) / 2).

  Menu
  - Frame rates a row cannot record are greyed in the popup and in
    Quick Set, and the stored rate is kept (OG3K at 50 -> OG3.5K
    reads 29.97 -> OG3K reads 50).  OG2K tops at 100 and OG3K at
    59.94: 119.88 is greyed on both (selecting it recorded stock
    UHD30 through the firmware's error path).
  - Crop Mode is greyed and effectively OFF on the four new rows,
    stored value kept.
  - After a battery pull the card applies the saved row itself
    (~20 s after loading) and refreshes the display.

  Loader
  - Built on fpSup's shared loader of 2026-09-25: every firmware
    word the card changes is journaled at load and written back at
    power-off, so the camera powers off stock.  No USB shell.
  - Combines on the fpSup-Merge page with fpSup-Gyro, Gyro-Base, the
    shell and Fast Start 2 (checked on the page; not booted).  Not
    with fpSup-OG3K or fpSup-OG2K: this card already contains them.

----------------------------------------------------------------
INSTALL
----------------------------------------------------------------

  1. Confirm the camera is a SIGMA fp on firmware Ver.5.02.
  2. Power off, REMOVE THE BATTERY, and put the card in a reader.
  3. Copy AutoRun.txt and fpSup.BIN to the ROOT of the SD card.
  4. Insert the card and power on, USB cable unplugged.  Wait for
     the progress bar and the final message:  fpSup-Fmt-v0.3.0a!
  5. Recording format CinemaDNG.  Select a row from MENU ->
     recording -> resolution, or from Quick Set -> RES.  Choose the
     frame rate and the CinemaDNG quality normally.

  To remove: delete AutoRun.txt, power off, remove the battery, and
  power on.

  If the camera freezes: remove the card, take the battery out with
  the USB cable unplugged, and boot.  Switching it off and on is not
  enough after a freeze.

----------------------------------------------------------------
MEDIA SPEED  (measured with a Samsung T5 over USB-C, 2026-09-28)
----------------------------------------------------------------

  The camera never dropped a frame in any test: it records cleanly
  until its buffer (about 400-470 MB) is full, then stops the take.
  What decides is the drive's SUSTAINED write rate once its cache is
  full and it is warm, not the number on the box.

     format  bits  fps    MB/s   Samsung T5
     OG3K     8    100    616    2 s
     OG3K     8    59.94  369    42 s
     OG3K     8    50     308    58 s OK
     OG3K    10    50/48  384    23-30 s
     OG3K    10    29.97  230    OK
     OG3K    12    29.97  276    OK
     OG3.5K  12    29.97  362    81 s cold, 12-17 s warm
     OG3.5K  12    25     302    ~2 min
     OG3.5K  12    24     290    2m45 + 1m36 OK (fresh drive)

  Rule of thumb for a T5: about 275 MB/s sustained.  OG3.5K 12-bit
  at 24/25p works on a fresh, cool drive; 29.97 does not.  8-bit
  OG3.5K (192-240 MB/s) fits.  S16 and OG2K fit a fast SD card at
  24p; OG3K and OG3.5K need an SSD.  Rates are not limited by this
  card for bandwidth reasons: measure your own drive.

----------------------------------------------------------------
WHAT HAS BEEN VERIFIED
----------------------------------------------------------------

  On one SIGMA fp, Ver.5.02, external SSD, 2026-09-27/28, on the
  release-candidate cards of this exact payload (fpSup.BIN is byte
  for byte the tested rc10; AutoRun.txt differs only in the banner):

    - the six-row menu, closed-row texts, Quick Set tiles, the
      six-label strip with the cursor on the selected row
    - S16: standby live view cropped and centred; clips 2112x1248,
      crop 2096x1238 at (8,5), 203 frames, no drops
    - OG3.5K: live view fluid and complete while recording; clips
      3464x2308, crop 3456x2308, no drops; the first frame is
      identical to the second (an earlier build had a Bayer-phase
      flip on frame 1, fixed by the 6062x4040 window)
    - OG2K 2016x1344 and OG3K 3024x2010 clips, OG2K sustained at
      100 fps 12-bit
    - frame rates greyed per row with the SSD mounted; 119.88 greyed
      on OG2K/OG3K; the stored rate kept across rows
    - crop greyed/off on the new rows; UHD with crop ON comes back ON
    - switching rows in Quick Set updates the live view

  Offline: fpSup-Merge page checks pass alone and with Gyro,
  Gyro-Base, Shell and Fast Start 2; stage2 identical to
  fpsup-og3k-v0.2.6a's.

  Final validation on THIS EXACT FILE: see MANIFEST.txt, camera log.

----------------------------------------------------------------
WHAT IS NOT VERIFIED -- THIS IS AN ALPHA BUILD
----------------------------------------------------------------

  - 8-bit and 10-bit CinemaDNG on S16 and OG3.5K (OG2K/OG3K: as
    the fpSup-OG2K/OG3K releases).  A 10-bit OG2K take at 119.88
    fell back to stock UHD30 -- that rate is now greyed.
  - In-camera playback of S16 and OG3.5K clips: by eye only.
  - MOV with a new row selected; a still photo with a new row
    selected.
  - The combined cards from the merge page have not been booted.
  - Ten boot / power-off cycles and loading over another card
    (the loader's own test) on the final file: MANIFEST camera log.

  Known, and not fixed here:

  - Switching in Quick Set between a 3:2 row and a 16:9 row (or to
    or from S16) shows a one-frame Super35-crop flash: the card has
    to toggle the crop to make the camera rebuild the live view
    inside Quick Set.  Between OG2K, OG3K and OG3.5K there is none.
  - S16 stays at 29.97: the sensor timing cannot shrink below the
    full readout (48 fps froze the camera on a probe).
  - OG3.5K in standby previews through the hardware binning: the
    standby picture is the whole 3:2 frame, as in OG3K.

----------------------------------------------------------------
HOW IT WORKS, IN SHORT
----------------------------------------------------------------

  The firmware describes each video mode in one row of a parameter
  table plus one timing row per sensor mode.  The card adds no rows:
  while a new menu row is selected it BORROWS an existing profile's
  row (the 1:1 video profile for S16 and OG2K, the UHD 12-bit profile
  for OG3.5K, OG3K's own) and writes the window, the ISP ratios, the
  preview and the output sizes; leaving the row puts the stock
  values back.  A hook in the format picker supplies the sensor
  timing for the current frame rate; a hook in the canvas builder
  sets the stored raster, the DNG crop and the pixel format every
  frame, and in standby the S16 crop.  The menu is the camera's own,
  with its list extended to six rows.

----------------------------------------------------------------
WITH THANKS
----------------------------------------------------------------

  Bei (ijigen) for fpSup: the loader, the OG2K / OG3K open gates
  this card grew out of, the menu runtime, and the build rules.
  Vitaly Li got open gate out of a SIGMA fp first.
