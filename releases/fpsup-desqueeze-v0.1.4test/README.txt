================================================================
 Desqueeze  fpsup-desqueeze-v0.1.4test
 SIGMA fp Ver.5.02 only -- Loader v3 card
================================================================

WHAT IT IS

  Anamorphic preview. With an anamorphic lens, the screen (LCD, EVF,
  HDMI, the magnifier too) shows the picture with its real proportions:
  the whole frame, letterboxed, while the camera records CinemaDNG as
  always. The recorded files are not changed in any way.

  - Where: MENU > SHOOT 2 > "Desqueeze", in CINE and in STILL.
    Off / 1.33x / 1.6x / 2.0x.
  - The Frame Guide is scaled with the picture.
  - The magnifier's white frame is scaled with the picture too.
  - Two amber lines mark the top and bottom of the desqueezed frame and
    the factor ("1.6x") is shown under the battery, only over the live
    view and a playing clip (never over a menu, the Quick Set, the
    thumbnail mosaic or a paused clip).
  - The factor is remembered on the card, in \FPSUP.INI
    ("desqueeze.factor=off|1.33|1.6|2.0"), never in the camera's own
    settings. Take the card out and the camera is back to normal.
  - At power-on the view is rebuilt once so the factor applies without
    opening a menu.
  - Works together with Tap to Zoom (42TAPZ.BIN): the zoomed picture
    fills the screen and keeps the desqueeze proportion.

  Author: Jose Hurtado (sigmafp-mods). Built from the fpSup tree with
  Bei's uishare and Lossless row runtime.

  中文:
  變形鏡頭預覽。裝上變形鏡頭時，螢幕（LCD、EVF、HDMI，放大檢視也是）
  以真實比例顯示整個畫面（上下留黑邊），相機照常錄 CinemaDNG；錄下的
  檔案完全不變。
  - 位置：MENU > SHOOT 2 >「Desqueeze」，CINE 與 STILL 都有。
    Off / 1.33x / 1.6x / 2.0x。
  - 構圖線與放大檢視的白框都跟著畫面縮放。
  - 兩條琥珀色線標出還原後畫面的上下緣，電池圖示下方顯示倍率
    （「1.6x」），只畫在即時檢視與播放中的影片上。
  - 倍率記在卡上的 \FPSUP.INI，不寫進相機設定；拔卡即回原狀。
  - 開機時自動重建一次畫面，不用進選單倍率就生效。
  - 可與 Tap to Zoom（42TAPZ.BIN）同卡。

HOW TO USE

  Copy AutoRun.txt and the fpSup folder to the root of the SD card and
  start the camera.  To combine with other fpSup products released for
  Loader v3, copy their fpSup folders over this one: every product
  carries the same LOADER.BIN and UI frames, and its own 41DSQZ.BIN.

  Upgrading from an older (single fpSup.BIN) card: delete the old
  fpSup.BIN from the card root.  A card from before Loader v3 cannot be
  mixed with this one.

  After changing the factor, the magnifier's frame takes the new size
  the next time the live view page is rebuilt (leaving the menu does
  that).

WHAT CHANGED SINCE fpsup-desqueeze-v0.1.0test

  - 0.1.1test: the picture hook (C02E828C) is a CHAIN claim, so Tap to
    Zoom (42TAPZ.BIN, loaded after this file) stacks on it; alone,
    nothing changes.
  - 0.1.2test: the magnifier's frame follows the factor on the screen:
    it is drawn by the live-view page, not by the magnifier page, so
    its objects in all six live-view pages are now rewritten too (85
    sites, claimed as 14 ranges so the loader's log keeps room for the
    other products' lines).
  - 0.1.3test / 0.1.4test: the frame's vertical position, measured on
    the camera: y = 171 + (340 - h) / 4 (the frame rises a quarter of
    what it loses in height).
  - The indicator (lines and "1.6x") is painted only over the live
    view and a playing clip; the magnifier box objects of LV_Magnify
    were already covered since 0.1.0test.

WHAT HAS BEEN VERIFIED

  Offline (host and the real LOADER.BIN in Unicorn, 39 + 18 tests):
  every firmware word changed is claimed first and put back at
  power-off; a site held by another product releases this one with
  nothing written; the row on MainB2 equals the reference applier; the
  file sets the factor and the task remembers it; the Frame Guide,
  indicator and magnifier words follow the factor; the chain with Tap
  to Zoom in either directory order.

  On the camera (Jose Hurtado, 2026-10-09, on cards with Lossless,
  Gyro2, Res-Custom, Tap to Zoom and RAW-View): letterbox, amber
  lines, Frame Guide, row in SHOOT 2 CINE/STILL, no marks on the
  mosaic or a paused clip, the magnifier's frame flattened and centred
  at 1.6x and 2.0x after a menu round trip, the chain with Tap to Zoom,
  the recorded DNG unchanged.

  Not yet checked: whether the magnifier frame is already right on a
  cold start before the first menu round trip; EVF and HDMI.

KNOWN PROBLEMS

  - In CINE the magnifier's 4x/8x switch sometimes does nothing (STILL
    is fine). Not traced to this product; see the Res-Custom notes.
