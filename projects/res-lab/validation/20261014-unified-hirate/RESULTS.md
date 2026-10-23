# 統一公式：239.76／279.72 改走錄影路徑預覽 — 2026-10-14

## 問題
統一公式（r78 規則）在 M12 239.76p 宣告預覽以 2000 寬、縮放 1023／1023（不縮）、
window 2016×672、reduction 3.0／6.0、class1／0x88=0。原廠 CRCT 選擇器因此走
enabled[0,0,1]／mux[1,3]／record1（獨立全寬預覽）。
兩次成功的 240（9/29 H2 A001_193、10/01 r10）以及原廠 100/120p CinemaDNG profile（p379/p389）
都是「預覽縮放＝錄影縮放、預覽光柵＝act＋邊距」，路由 [0,1,0]／[1,4]／record0。
consumer 只在 12-bit 用 m12_legacy_canvas 補 r10，10-bit／8-bit 全走 r78 → 使用者回報 10-bit 切畫面。

## 修改（producer RLAB v18→v19，`changes.patch`）
`rl_encode` 的 rate canvas：23976／27972 兩個選擇器各寫 20 組欄位
（0x0C/0x10=act+16/+10、0x1C=2、0x20/0x28=act、0x38/0x58/0xC4 預覽 bin＝錄影、
0x60=0x64=錄影 H 縮放、0xD0=0xD4=錄影 V 縮放、0x88=4、0xB0=1、0xD8/0xE0、
0xF4/0xF8=錄影矩陣、0xFC/0x100=2.0）。100／119.88 及更低不變（r78）。
RCD 格式、consumer、wire/ABI 不變；rate canvas 段移到 912（428 B），pack 移到 1344。

## 驗證
- 新 `test_reslab_hirate_canvas.py`：8／10／12-bit × 239.76／279.72，consumer 套用後 65 字
  與 r10 封存畫布逐字相同（排除 0x30 FPS、0x80/0x84 位元平面）；原廠路由 [0,1,0]/[1,4]/record0；
  119.88 仍 r78 路由。舊 producer 跑同測試：4 項失敗（10/8-bit），見 mutation log。
- 實際部署檔 HS280-hirate.RCD 經 consumer 載入：10/12-bit 240 同 r10。
- 回歸：formula_guards OK、formula_arm OK、test_virtual_rcd 24/24 OK。
  test_reslab_preview_route 2 項失敗在修改前就存在（期望 240 引擎 60fps，現行為實際 239.76）。

## 上機
- producer v19 取代卡上 v18（19491eb0…），完整讀回；HS280.RCD 以同配方加上 240/280 欄位取代
  （原檔備份 ../20261013-m12-240-native-dma/card-HS280.RCD，SHA 42024e62…）。
- 重開後 consumer v20 常駐碼核對；HS280／239.76p 選取；相機記憶體中目前使用的 240 欄位清單
  即上述 20 組（0x0C=1008、0x60=2048、0xF4=1008、0xFC=2.0…）。
- HDMI 無訊號，錄影畫面未由主機驗證；待使用者 SSD 12/10-bit 試錄與目視。

## 2026-10-14 03:08 使用者 SSD（HDMI 接上、shell 啟用）
A001_319 87 幀、A001_320 92 幀，12-bit，檔頭全在 0。A001_320 原生日誌：停止原因 `lens`（過去 174 次 vbuf、
從未出現 lens），ui factor Button；寫入健康（逐檔 3–4 ms、273–365 MB/s、在途穩定約 47）。
之後 LV 全黑、movie_recording 卡 1（xmp/writing 0）。HDMI：錄影中有影像，停止重載待機時黑屏（T--）。

## 03:15 主機自測（重開後，同 BIN/RCD、HDMI、shell，SD）
- 12-bit 239.76 SD：94 vbuf（SD 頻寬），停後 LV 正常，idle 0/0/0。
- 10-bit 239.76 SD：94 vbuf（64MiB 首批約 72 張），LV 全程正常；放大錄影中 HDMI 幀未見切畫面、FOV 與待機一致
  （場景失焦，判斷力有限）。兩段都沒有 lens 停止或黑屏。黑屏/lens 尚未在 SD 重現。

## 03:20 使用者 SSD 第二輪（HDMI、shell 啟用，乾淨開機）
A001_321 10-bit 213 幀；A001_322 12-bit 161 幀，檔頭全在 0。無黑屏、無 lens 停止，停後 idle 0/0/0。
HDMI（hdmi-ssd-trial2.mkv）REC 段 47.0–49.6 s（10-bit）、78.7–80.9 s（12-bit）：10-bit 錄影中畫面清楚、
FOV 與待機一致、未見切畫面（靜止場景，無法判斷動態卡頓）。
A001_322 原生日誌：vbuf/161，req=fin=161，逐檔 3–4 ms；請求送出速率約 188 fps（A001_320 約 204 fps）
< 239.76 → 瓶頸在 MovRec 交給 writer 之前（每幀約 5.3 ms）。A001_314/315（同 v20、無 shell、無 HDMI）12–14 s。
待測：無 shell、無 HDMI 的新畫布 SSD 長度。

## 03:3x 使用者 SSD 第三輪（無 shell、無 HDMI、只留 RES-Custom，新畫布）
- A001_323：12-bit 1566 幀、WAV 13.12 s、每秒約 120 張（119.88p 的片段）。
- A001_324：12-bit 239.76p 3509 幀、WAV 14.67 s，每秒 239–249 張，檔頭全在 0（與 A001_314/315 的 2792/3394 同級）。
- A001_325：10-bit 239.76p 21799 幀、WAV 90.92 s，每秒 238–245 張穩定到結尾，21799 張檔頭全在 0。
停止方式待使用者確認。
使用者確認：A001_325 為手動停止，LCD 上沒有卡頓或切畫面。A001_323 為重開後格率回到 119.88（240 選擇未跨重開保存）。
