# 壓縮硬體盤點 與 QR 碼接收器（計畫）

2026-10-06。fp Ver.5.02。證據等級：**[實測]** 本機跑過、**[靜態]** 反組譯/字串、**[估計]** 未量。

## 1. fp 沒有通用解壓縮硬體

- **沒有 LZMA / LZMA2**，硬體軟體都沒有 [實測]：`FP__V502.bin`、`MAIN_c0000000.bin`、`lzss_full.bin`、
  `IPL.raw`、seg1/seg3 掃 XZ 檔頭 `FD 37 7A 58 5A`、7z 檔頭、LZMA 屬性 `5D 00 00 80 00` 全部 0 筆；
  字串、RTTI、原始碼路徑也沒有 lzma/xz（`SIG_GHS_XZ01` 的 XZ01 是 SoC 代號，和 xz 格式無關）。
- **韌體是 LZSS，不是 LZMA2** [實測]：DFI seg0（方式碼 1）、seg1（方式碼 0x11）用 xz / .lzma / 純 LZMA2
  三種格式解都失敗；用 Okumura LZSS 解出的結果與 `out/seg0_c0000000.bin`、`out/seg1_c2ef6e00.bin`
  逐 byte 相同。格式見 [FORMAT.md](FORMAT.md)。
- **LZSS 是 IPL 裡的軟體迴圈，不是晶片** [靜態]：`IPL.raw` 約 0x925C 起
  （`movw r7,#0xfee` → 旗標 `orr fp,r3,#0xff00` → `ubfx r7,r3,#0,#0xc` →
  `and r3,r3,#0xf0` / `and r3,ip,#0xf; add #3` → `sub r6,r6,#0x1000`），CPU 逐 byte `ldrb`/`strb`，
  沒有寫外設暫存器；視窗直接回讀輸出緩衝。0x8EDC 有第二個 `movw r7,#0xfee`，應是另一份 LZSS，
  未逐條確認。迴圈看起來沒開最佳化（每 byte 存回堆疊再讀出），冷開機解 47 MB MAIN 的耗時**未量**。
- HAL 模組清單（`src/hal/*`）沒有壓縮引擎。真正的壓縮硬體只有 **RawCD 無損 JPEG**
  （靜態 DNG，見 `research/imaging-hw/notes/HW_LOSSLESS_JPEG_CODEC.md`）；另有 `XC_SigproJpegDecomp`。
- 其他軟體解碼器：`.xci` 圖示的 RLE / LZ4（LZ4 在 `0xC05A7278`，見 [BOOT_OPENING_LOGO.md](BOOT_OPENING_LOGO.md)）。

### LZSS 壓縮率 [實測，主機端]

| 方法 | seg0 49.25 MB → | 比例 | seg1 比例 |
|---|---|---|---|
| LZSS（原廠） | 24.38 MB | 49.5% | 50.8% |
| lz4 -1 / -12 | 22.49 / 18.06 MB | 45.7% / 36.7% | 36.6% / 32.6% |
| zlib -9 | 16.01 MB | 32.5% | 25.9% |
| bzip2 -9 | 13.44 MB | 27.3% | 28.2% |
| xz/LZMA2 -9e | 9.78 MB | 19.9% | 17.7% |

差的原因：4 KB 視窗、最長匹配 18、沒有熵編碼；seg0 內約 2.9 MB 的 `.xci` 已是 LZ4。
換 IPL 解壓器＝動開機最底層，不值得；修改卡繼續用原廠 LZSS 重壓。

## 2. 原廠 QR 碼功能 [靜態]

- 類別：`QrCodeReadThread`（`c0381460`，執行緒名 `QrReadTh`）、`PlayQrReadExe : XC_QrCodeReadExecutor`、
  `MenuQrCodeReadHandler`、`MenuQrCodeCreateHandler` 等；選單 `Y5_ReadQR`、`Y5_CreateQR`。
- 用途是**相機設定碼**：讀 → 套用設定（`Y5_ReadQR_SaveSettings`、`MenuQrCodeSelectApplyTargetHandler`）。
  讀進來的資料**不會寫成檔案、也不會被執行**。
- debug shell 有現成命令：`qr lv_read`（從即時取景讀）、`qr play_read`（從播放的照片讀）、
  `qr make [data]`，以及 `dump y8 / yuv when qrcode decode`。→ 韌體的 QR 解碼器可以直接借用。
- 設定碼解析器有沒有可利用的漏洞：**沒分析過**。

## 3. sup 用 QR 傳輸的容量帳 [實測，主機端]

ARM BCJ + LZMA2（dict 64 KB）。QR v40-L ≈ 2,953 B；手機螢幕給相機拍較可靠的 v25-L ≈ 1,270 B。

| sup | 原始 | LZ4 -12 | zlib -9 | LZMA2 | v40-L | v25-L |
|---|---|---|---|---|---|---|
| usbshell 3.3.0 | 2,921 | 2,080 | 1,598 | 1,503 | 1 張 | 2 張 |
| gyro 1.14.0 | 15,564 | 9,053 | 7,321 | 6,179 | 3 | 5 |
| raw-view 0.2.2test | 25,336 | 11,415 | 9,544 | 7,886 | 3 | 7 |
| og3k 0.2.8a | 23,196 | 18,187 | 15,646 | 14,027 | 5 | 12 |

（「原始」＝ `fpSup.BIN` 去掉尾端 0x00/0xFF 填充。）

## 4. QR 碼接收器 —— 計畫（未來會做）

**目標**：不用電腦就能**更新** sup。**第一次安裝仍要用電腦寫卡**——原廠 QR 只套設定，
sup 又必須以 `AutoRun.txt` + `fpSup.BIN` 在卡上（Fast Start 3 的設定區也只是跑短 AutoRun，
最後仍從卡載入 `fpSup.BIN`）。除非日後在設定碼解析器找到漏洞，否則沒有「零電腦首裝」。

草案：
1. 常駐接收器做進 shell 或 loader；呼叫韌體的 QR 解碼（沿 `qr lv_read` 的路徑）。
2. 主機/手機輪播多張 QR，每張帶：魔數、總張數、序號、本片 CRC32；最後驗整檔 sha256。
3. 收齊 → 解壓 → 驗 sha256 → 寫新的 `fpSup.BIN`（舊檔先留備份）→ 重開機生效。
4. 進度顯示走現有 OSD（四格開機條或 UI 段落）。

壓縮選擇：先用 **zlib 或韌體自帶的 LZ4**（`0xC05A7278`，零額外程式碼）。LZMA2 比 LZ4 每個 sup
只省 1–4 KB（約 1–4 張 v25 碼），但接收器要多帶解碼器，估計 5–8 KB 碼 + ~30 KB RAM [估計，未編譯量]。
張數真的成為困擾再換。

待查：
- [ ] `qr lv_read` 的呼叫鏈、解碼輸出緩衝位址與長度上限（從 `QrCodeReadThread__v1 @ c0381460` 往下）
- [ ] 解碼器支援的最大版本 / 二進位（byte mode）模式能否原樣取出
- [ ] 即時取景解碼速率（決定輪播速度）
- [ ] 寫 `fpSup.BIN` 時與 loader 正在讀同一檔的衝突
- [ ] （另案）設定碼解析器的輸入檢查
