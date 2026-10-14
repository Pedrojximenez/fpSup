================================================================
 Open Gate formats (res-custom)  fpsup-res-custom-v0.1.3test
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

WHAT CHANGED SINCE fpsup-res-custom-v0.1.2test

  - RCD-owned bit-depth availability makes 12-bit selectable for OG3.5K
    and OG4K, while retaining 8-bit and 10-bit. The five supplied RCDs
    each declare 8/10/12-bit; stock media rules return outside these formats.
  - Versioned test release of the standalone consumer and five RCDs
    previously offered on Merge as dev-r19. Their bytes are unchanged.
  - RES-Lab remains in development and is not included in this release.

  中文：OG3.5K、OG4K 可選 12-bit，同時保留 8-bit、10-bit。
  可用位深由各 RCD 宣告；離開這些自訂格式時恢復原廠限制。
  原先 Merge 的 dev-r19 獨立 consumer 與五個 RCD 保持相同檔案，
  改以 v0.1.3test 發布。RES-Lab 維持開發中，不包含於本版。

WHAT HAS BEEN VERIFIED

  Exact product bytes and all five RCDs match the manifest-verified
  res-custom-20261013 snapshot previously served by Merge.
  Offline loading, bit-depth policy and output-format checks are recorded
  in validation.json. Firmware I/O and media boundaries are modeled.
  These exact files have not been recorded on a camera. Enabling 12-bit
  does not establish the sustained throughput of an SD card or SSD.

  中文：產品 BIN 與五份 RCD 已核對快照 manifest，並保留原始位元組。
  離線驗證結果見 validation.json；I/O 與媒體邊界使用模型。
  這些檔案尚未實錄驗證，開放 12-bit 不代表儲存媒體的寫入速度已驗證。
