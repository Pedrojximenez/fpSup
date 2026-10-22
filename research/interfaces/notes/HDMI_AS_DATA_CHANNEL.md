# 把 HDMI 當第二條資料出口(2026-10-02,構想 + 既有證據,未上機)

USB 已到 Gen1 天花板(390 MB/s,控制器 DWC_usb3 3.00a 只到 5 Gbps,見 USB_LINK_SPEED.md)。
HDMI 是另一個實體通道,和 USB **同時**可用,方向是相機 → 主機。

## 已知事實(引 HDMI_RAW_FORMAT.md)
- TX 為 HDMI 1.4 級,韌體天花板 297 MHz / 8.91 Gb/s,24 bit/px 有效 7.128 Gb/s ≈ 891 MB/s。
- RAW 模式只是把 framebuffer 內容換掉,時序是標準 CEA/HDMI_VIC → **framebuffer 放什麼位元組,線上就送什麼**。
- 目前線上容器固定 colour format 3(TX 0x30190004 bits[14:12]),framebuffer 2 B/px。
- 2 B/px 時:UHD29.97 = 497 MB/s、DCI4K24 = 425、UHD23.98 = 398、FHD59.94 = 249。
- RAW 模式光柵利用率 75%(每幀約 521 行閒置)→ 實際酬載要 ×0.75,除非自己填滿。

## 可能的容量
| 做法 | 估計酬載 |
|---|---|
| 現行容器(2 B/px)、UHD29.97、自己填滿整個光柵 | ~497 MB/s |
| 改 colour format 成 RGB 4:4:4(fmt0/4,3 B/px)、UHD29.97 | ~746 MB/s(未驗證 TX 能否在 297 MHz 下送) |
| USB 390 + HDMI 497 並行 | ~890 MB/s 到主機 |

## 代價與風險
- 單向,無重傳:TMDS 位元錯誤不會被糾正 → 要自帶 CRC/FEC 與序號。
- 擷取端必須逐位元無損收下(4:2:2 不能被轉 4:2:0、不能縮放/色彩轉換):PCIe 擷取卡或 Gen2 USB 擷取,USB 3.0 擷取卡收不了 UHD30。
- 需要相機端程式把資料寫進 HDMI framebuffer(類似 HDMI RAW 的換內容點)。

## 下一步
1. 用一般輸出確認擷取鏈 bit-exact(兩者容器相同)。
2. 靜態查 0x30190004 其他 format 值與 TX 通道切換(FUN_c00E5FE0、FUN_c00E2508)。
3. 找 RAW 模式把 Bayer 放進 HDMI framebuffer 的那一點,改成放任意資料。
