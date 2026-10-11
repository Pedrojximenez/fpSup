# 外接 SSD 的 USB 協定效率(2026-10-01,靜態分析,未上機)

[C]=程式碼證實 [I]=推論。基準:`sdcard test3 ext` 寫 390 / 讀 400 MB/s,Gen1 實用上限約 430–450。

## 協定
- 主機 MSC 驅動 0xC066xxxx–0xC0673xxx。介面選擇 FUN_c0672900:協定 0x50=BOT、0x62=**UAS**(限 SS),結果 0xC3821444(1=UAS)。[C]
- BOT CBW/CSW 0xC0672070;UAS Command IU / Sense IU:同步 FUN_c0672808、管線 FUN_c0672398、收尾 FUN_c0672650。[C]
- WRITE(10)/(16) 建構 FUN_c0671bf0。路徑:FS → FUN_c01f0fd0 → FUN_c01f47e0 → FUN_c06710d8(>4 KB 整個 D-cache clean)→ FUN_c0671bf0 → FUN_c0671fe8 → FUN_c066cd60;門鈴 FUN_c0670228 寫 0x21000480。[C]

## 每道指令長度
- 上限 0xC3821450 = 0x2000000/磁區/max(streams,1),封頂 0xFFFF(FUN_c0671400):BOT 32 MiB、UAS 4 streams 8 MiB。[C]
- 起始 0xC382144C = 0x1000 磁區(2 MiB),成功加倍(FUN_c0670d00)到上限後 0xC382145C 鎖定,錯誤減半(FUN_c0670d48)。[C]
- Block Limits VPD B0 會再往下壓(FUN_c06711f0 → FUN_c0671490,0xC2F16DD4)。[C]

## 管線與中斷
- BOT 不管線,CBW/資料/CSW 各等一次完成。Normal TRB 每段 ≤64 KiB,只有最後一段 IOC;每端點一次一個 TD(FUN_c066fca0)。[C]
- 環 0xC42F9840(IN)/0xC42FB9C0(OUT)各 0x2180 B = 535 TRB ≈ 33 MiB。[C]
- UAS 管線深度 min(2^MaxStreams, 4),4 是寫死的(FUN_c0672900),145C 鎖定後才走管線。[C]
- IMOD 0x21000464 = 0x01F401F4 → 每 125 µs 最多一次中斷(FUN_c066f088)。[C]
- 估算 BOT 每指令固定開銷約 0.3 ms:32 MiB 指令損失約 0.4%,2 MiB 約 5%。[I]

## 主機初始化 FUN_c066d418
- 只寫 GCTL=0x17701000、GUSB3PIPECTL=0x013A0004、GUSB2PHYCFG=0x2400、0xC170 清 bit17/20。[C]
- 不寫 GSBUSCFG0/1、GTX/GRXTHRCFG、GUCTL、GTXFIFOSIZ、PORTPMSC → U1/U2 timeout 0 = 關閉。[C/I]
- 端點 MaxBurst 照硬碟盒描述元(FUN_c066f390)。[C]

## 裝置模式 bMaxBurst=3
- ROM 範本 PTP 0xC0CF3748/3750(+2);其他 0xC072AFC0/AFC8、B0E4/B0EC、B1EC/B1F4;生效的是 RAM 物件 0xC37748C0 副本。GTXFIFOSIZn 從不設定(硬體預設)。[C]

## 候選調整(全為執行期,不寫設定區)
1. 先讀狀態:0xC3821444/143C/144C/1450/145C、0xC2F16DD4 → 確認 BOT/UAS 與實際指令大小。零風險。
2. IMOD 0x21000464 設 0 或 0x28,前後跑 test3 ext。指令 32 MiB 時約 +0.5%;被 VPD 壓小時 3–6%。低風險。
3. FS 層每次 write 約 6 ms 固定開銷(由 10/50 MB 跑分擬合 [I]):攢大塊、64 KiB 對齊再寫,可 +10–15%。零風險。
4. DWC3 全域暫存器(GSBUSCFG0 INCR16、GRX/GTXTHRCFG、GUCTL bit14):0–5%,DMA 出錯要重開機。
5. 強制加大指令(144C/1450 設大、145C=1):違反硬碟盒宣告,中高風險。
6. UAS 深度 >4、裝置端 burst 15:要改程式碼/搬環,排最後。
結論 [I]:32 MiB 指令下協定開銷 <1%;剩下 10–15% 主要是 Gen1 本身、硬碟盒(兩盒差 7%)與 FS 每次呼叫開銷。
