# 格式化的叢集大小與對齊、掛載時的檢查(fw 5.02)

離線靜態分析(blk_c06.c / blk_c03.c / blk_c04.c + MAIN_c0000000.bin)。[C]=程式碼裡讀到,[I]=推論。

## 結論

- 叢集大小**只看容量**,照 SD Part 2 的 SDXC 表,超過 2 TiB 再往上延伸;SD 與 SSD 共用同一張表,沒有使用者選項。[C]
- 版面:分割區從 BU 開始,FAT 在分割區內 +BU/2、長 BU/2,cluster heap 在分割區內 +BU,所以絕對位置 = 2×BU。[C]
- 觀察到的 SD 128 KiB = 32–128 GiB 的卡;SSD 512 KiB = 512 GiB–2 TiB 的碟。兩者都符合這張表,不是特例。[I]
- 掛載時**不檢查叢集大小是不是「標準」值**:只要 2^SPCshift × 磁區 ≤ 32 MiB 就收。PC 格式化、128 KiB 叢集的 SSD 會照常掛上,不會被拒絕、也不會被重新格式化。[C]

## 呼叫鏈(格式化)

| 位址 | 作用 |
|---|---|
| shell `format [slot]` → FUN_c040adc8(表項 0xC0BC26E4) | 呼叫媒體物件 vtable+0x18 |
| FUN_c036aef8 / c036b038 → FUN_c036ad88 | 媒體層的格式化;先跑 c036ab20(SD 抹除指令 0x1085/0x1086) |
| FUN_c063d288 → **FUN_c0648c30** | 算參數 → 寫 MBR → 呼叫 FS 格式化 |
| **FUN_c0648ab8** | 依媒體 id 選算法:0xE、0x16、0x32 → c0647e00;0xB、0x11 → 如果 DAT_c2f2e660 ≠ -1 就用 c06485d8(SD 專用、只到 2 TiB、可以強制 FAT32/exFAT),否則用 c0647e00 |
| **FUN_c0647e00** | 通用的容量→參數表(下表);磁區大小只接受 512/1K/2K/4K |
| FUN_c063b0e8 → FUN_c06441e8 | 類型 <3 → FUN_c06437f0(FAT);==3 → **FUN_c0642a28**(寫 exFAT 開機區) |
| FUN_c0642a28 | 寫入 OEM 名稱 "EXFAT   "(0xC2E34758)、BytesPerSectorShift(9..12)、SectorsPerClusterShift=log2(SPC)、NumberOfFats=1、DriveSelect=0x80、0x55AA、第 9 磁區的 flash 參數 GUID(0xC2E34764)+EraseBlockSize、第 11 磁區的 checksum |

媒體 id → 磁碟區索引:FUN_c0644b68(0xB→0;0xC/0xD/0xE→1;0x16 等→2;7/0x11/0x17→3;0x12/0x18→4)。SD(索引 1)走 0xE,SSD(索引 3)走 0x11。[C]

## 容量 → 參數(c0647e00,單位換算成位元組)[C]

| 容量 C(512 B 磁區數換算) | 檔案系統 | 叢集 | BU(boundary unit) |
|---|---|---|---|
| ≤ 8 MiB / ≤ 1 GiB / ≤ 32 GiB | FAT12/16(≤2 GiB)/FAT32 | 8 / 16 / 32 KiB | BU 另外分級:≤8M 8K、≤64M 16K、≤256M 32K、≤2G 64K、≤32G 4 MiB |
| ≤ 128 GiB | exFAT | **128 KiB** | 16 MiB |
| ≤ 512 GiB | exFAT | **256 KiB** | 32 MiB |
| ≤ 2 TiB | exFAT | **512 KiB** | 64 MiB |
| ≤ 4 / 8 TiB | exFAT(GPT,分割區類型 0xEE) | 1 / 2 MiB | 128 MiB |
| ≤ 16 / 32 TiB | 〃 | 4 / 8 MiB | 256 MiB |
| ≤ 64 TiB / 更大 | 〃 | 16 / 32 MiB(上限 32 MiB) | 512 MiB,每 4× 容量再翻倍 |

- 叢集表以 512 B 為單位,再除以 (磁區大小/512),所以 4Kn 碟的叢集位元組數一樣。[C]
- exFAT:FatOffset = FatLength = BU/2,heap = BU(相對分割區),分割區起點 = BU;如果 FAT 長度 > BU/2 就把 BU 加倍。>2 TiB 時磁碟區長度 = 總長 − 2×BU(尾端留給備份 GPT)。[C]
- 界線用「≤」:剛好 0x4000000 磁區(32 GiB)仍是 FAT32。實際標示 128 GB 的卡(≈119 GiB)→ 128 KiB;256/512 GB → 256 KiB;1 TB → 512 KiB。[I]
- c06485d8(SD 版)在 ≤ 2 TiB 給出相同的 exFAT 值,只差不會為了 FAT 大小把 BU 加倍。DAT_c2f2e660 沒有任何寫入點,初始值從映像讀不到(該區不是 .data)。[I] 推測是除錯用的強制選項,預設 -1。

## 掛載時的檢查

FUN_c0644a30(掛載)→ FUN_c0644560 → **FUN_c0644470** / FUN_c0644348:[C]

1. 第 11 磁區的開機區 checksum 要一致,否則回傳 -3。
2. OEM 名稱不是 "EXFAT   " → 回傳 0 → 改走 FUN_c0644698(FAT 解析)。
3. BytesPerSectorShift **必須等於裝置的磁區 shift**(vol+0x1464,由 ioctl 0x1004 取得)。
4. 2^SectorsPerClusterShift ≤ 0x2000000 / 磁區大小(叢集 ≤ 32 MiB)。
5. 0x55AA、VolumeLength < 2^48、ClusterCount < 0xFFFFFFF5。
6. FUN_c0644650:FAT[0] 的第一個位元組要是 0xF8。

沒有比對 SD 表、FatOffset、heap 對齊或分割區起點。不合格的結果是掛載失敗(錯誤碼 -9),**韌體不會自己重新格式化**。[C]

副作用:如果 PercentInUse ≠ 0xFF,掛載時會把主、備開機區(第 0、12 磁區的 +0x70)都改成 0xFF;這個欄位不算在 checksum 裡。[C]

磁碟區欄位:vol+0x1460 是磁區大小(位元組),+0x1464 是磁區 shift,**+0x146C 是每叢集磁區數**,+0x1458 是 heap 起點,+0x145C 是叢集數。[C]

## AU 對齊:不合格只會降級,不會被拒

FUN_c064ad18:從 ioctl 0x109 取得 AU(拿不到就用 vol[0x51B] = SPC,等於 1 叢集)。以下兩種情況會把 +0x1FF0 設成 2,然後退回「1 叢集/AU、從叢集 2 開始」:[C]

- AU 和叢集大小互不整除;
- heap 的絕對起點(+0x1434 + 0x1458)沒有對齊 AU。

條件都成立時,+0x1FEC = AU/SPC 就是「每 AU 叢集數」,配置器(c064a040)用它做 AU 對齊的連續配置。[C]

所以 PC 格式化的碟只要 heap 有對齊,就能拿到同樣的 AU 配置;沒對齊只會少掉 AU 分組,不影響掛載。對寫入效能的實際影響未量測。[I]
