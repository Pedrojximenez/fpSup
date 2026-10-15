================================================================
 Open Gate formats (res-custom)  fpsup-res-custom-v0.1.4test
 SIGMA fp Ver.5.02 only -- Loader v3 card
================================================================

WHAT IT IS

  Extra movie resolutions for CinemaDNG, chosen like UHD and FHD in
  Settings (MENU > recording > resolution) and in Quick Set:

    OG2K    2000x1334  3:2  23.98-100     sensor 3x3 binning
    OG3.5K  3456x2304  3:2  23.98-29.97   full 1:1 readout, scaled in the ISP
    OG3K    3008x2000  3:2  23.98-100     sensor 2x2 binning
    OG4K    3840x2560  3:2  23.98-29.97   full 1:1 readout, scaled in the ISP
    S16     2096x1238  16:9 23.98-100     1:1 window (about 2.9x crop)

  One program file (fpSup\32RESCUS.BIN) and one small data file per
  format (fpSup\RESCUS\*.RCD).  The camera's own tables and settings
  are never changed: the camera only ever stores UHD or FHD; the format
  you chose is remembered in 32RESCUS.BIN itself.

  S16, OG3.5K and OG4K are Jose Hurtado's formats (fpSup-Formats
  v0.6.1), carried over as data.  Open gate on the fp was first done by
  Vitaly Li (FP3K).

HOW TO USE

  Copy AutoRun.txt and the fpSup folder (with fpSup\RESCUS inside) to the
  root of the SD card and start the camera.  To leave a format out, delete
  its .RCD from fpSup\RESCUS (at most six are used; the menu order is the
  file-name order).  To combine with other Loader v3 products, copy their
  fpSup folders over this one.

  Set the recording format to CinemaDNG.  Frame rates a format does not
  have are greyed out while it is chosen (your saved frame rate is kept
  and comes back when you change the resolution again).

  Crop Mode: OG3.5K and OG4K follow it -- with Crop Mode on they record
  the centre of the sensor 1:1, at the same DNG size.  For OG2K, OG3K and
  S16 Crop Mode is greyed out and off while they are chosen (your saved
  setting is kept).

  Cannot share a card with the older OG3K / OG2K cards (30OG3K, 30OG2K)
  or Jose's 31FMT. This standalone release does not include RES-Lab.

  Removing: choose UHD or FHD first, then delete the files.

WHAT CHANGED SINCE fpsup-res-custom-v0.1.3test

  - Refines the lower-left FPS display: the integer, decimal digits and
    FPS label keep their intended spacing and position. White text has
    a thicker black edge extending outward for readability.
  - Retains all five formats and their existing 8/10/12-bit options.

  中文：調整左下角 FPS 的位置、大小數字間距、小數與 FPS 標示，
  白字使用往外加厚的黑色描邊。保留五種格式與原有位深選項。

WHAT HAS BEEN VERIFIED

  Packaged without rebuilding from the accepted combined-fix12 artifact.
  The default-settings product BIN is 313216 bytes, SHA-256:
  d9a8e10050184424886afaca263279967ab2cc2c89314c44038fe4402a676355
  All five RCD files are identical to v0.1.3test.

  Camera visual acceptance covers 29.97 FPS in the medium CINE live-view
  layout after opening and closing Quick Set. The hardware test used the
  same immutable product code with the existing card settings preserved.
  This package uses builder defaults, without personal camera settings.
  Four layout parser paths and journal restoration were checked offline.
  Exact original-firmware typography and performance parity are not claimed.

KNOWN LIMITATIONS

  The first Quick Set opening after a restart still takes a while.
  This version has not been timed again and does not resolve that delay.
  This is not a cleanup of the earlier 280 fps work; dormant checks/hooks
  remain. Current FPS rendering and remaining overhead are not measured.
  Other rates/layouts have not all been visually checked on the camera.
  No recording or full physical power-cycle matrix was performed for this
  revision. The local Merge packaging is not a public release.

  中文：重開機後第一次開 QS 的延遲仍未解決；此版沒有清理先前
  280 fps 的殘留程式，也未重新量測效能。實拍驗收為中尺寸 CINE
  的 29.97 FPS，其他格率與版面未全部逐一上機；本次未實錄。
