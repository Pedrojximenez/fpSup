================================================================
 Tap to Zoom  fpsup-tap-to-zoom-v0.1.0test
 SIGMA fp Ver.5.02 only -- Loader v3 card
================================================================

WHAT IT IS

  Tap the LCD and the live picture zooms 2x around the point you
  touched; tap again and the whole frame is back. While zoomed, the
  command dials pick the factor: 2x, 4x or 8x (and never touch the
  exposure); with the full frame the dials work as always. It works
  during recording: the monitor zooms, the recorded file does not
  change.

  - Where: MENU > SHOOT 4 > "Tap to Zoom", ON / OFF (STILL and CINE).
    ON by default. OFF gives the touch back to touch AF.
  - The setting is remembered on the card, in \FPSUP.INI
    ("tapzoom.enable=on|off"), never in the camera's own settings.
  - With Desqueeze on the same card the zoomed picture fills the screen
    and keeps the desqueeze proportion.
  - The zoom is a digital crop of the live-view picture: at 8x the
    pixels are large. It is a framing and focus aid, not the camera's
    own magnifier, which keeps working as before.

  Author: Jose Hurtado (sigmafp-mods). Built from the fpSup tree with
  Bei's uishare and Lossless row runtime.

  中文:
  輕觸 LCD，即時畫面以該點為中心放大 2x；再點一次還原全畫面。放大時，
  指令轉盤可選 2x、4x、8x（不影響曝光）；全畫面時轉盤照常。錄影中也可
  用：螢幕放大，錄下的檔案不變。
  - 位置：MENU > SHOOT 4 >「Tap to Zoom」，ON / OFF（STILL 與 CINE）。
    預設 ON；OFF 時觸控交還給觸控對焦。
  - 設定記在卡上的 \FPSUP.INI（tapzoom.enable=on|off），不寫進相機設定。
  - 與 Desqueeze 同卡時，放大畫面填滿螢幕並保持還原比例。

HOW TO USE

  Copy AutoRun.txt and the fpSup folder to the root of the SD card and
  start the camera.  To combine with other fpSup products released for
  Loader v3, copy their fpSup folders over this one: every product
  carries the same LOADER.BIN and UI frames, and its own 42TAPZ.BIN.

  Upgrading from an older (single fpSup.BIN) card: delete the old
  fpSup.BIN from the card root.  A card from before Loader v3 cannot be
  mixed with this one.

  In live view: tap to zoom, tap to return. Zoomed: turn a command dial
  to change 2x / 4x / 8x. Menus, the Quick Set, playback and the
  camera's magnifier keep their own touch handling.

WHAT CHANGED

  - First release. (Development builds were named monitor-zoom /
    42MZOM.BIN; a card with one of those must drop that file.)

WHAT HAS BEEN VERIFIED

  Offline (host and the real LOADER.BIN in Unicorn, 22 + 3 tests, plus
  Desqueeze's chain test): the six claims (the picture hook as a CHAIN
  under Desqueeze, the touch and dial observer slots, the three string
  sites) journaled and put back at power-off; the row composed on
  MainB4 as the reference applier makes it; "tapzoom.enable=off" turns
  the row OFF and the tap reaches touch AF; a change is remembered on
  the card keeping the other lines.

  On the camera (Jose Hurtado, 2026-10-09, eight cards): zoom centred
  on the tapped point and back, 2x/4x/8x with the dials, during
  recording with the DNG unchanged, with Lossless, Gyro2, Res-Custom
  (OG2K, OG3K, OG3.5K, OG4K, S16), Desqueeze and RAW-View on the card,
  full screen over the desqueezed picture, the row on SHOOT 4 with its
  popup, cursor and navigation, ON/OFF remembered across power cycles.

  Not yet checked: EVF and HDMI; the first tap right after a cold boot
  before the live view has been rebuilt once (about half a second).

KNOWN PROBLEMS

  - Desqueeze's amber lines stay at the letterbox edge while the zoomed
    picture fills the screen.
