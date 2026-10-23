# 感測器 mode 與錄影 profile：韌體從哪裡查、誰在讀（Ver.5.02）

2026-10-14。靜態稽核加實機讀回。用途：判斷新增 mode id 或 profile id 時，
哪些表要複製、哪些地方會漏接。
標記：**[F]** 程式碼或實機讀回直接證實；**[I]** 推論。
完整稽核：[PARITY_AUDIT.md](../../../projects/res-lab/validation/20261014-parity-audit/PARITY_AUDIT.md)；
實機比對：[20261014-parity-live](../../../projects/res-lab/validation/20261014-parity-live/RESULTS.md)。

## 1. mode id 存在哪裡

- **[F] 感測器物件** `XC_ImageSensorIMX410` 在 `0xC343B588`，+0 指向**描述子** `0xC2F1E654`。
  +0xC/+0x10/+0x14 是查表後快取的列 index。
- **[F] 第二份 mode** 在 ImgMode 物件 `0xC343A6D8` +0，由 FUN_c0314708 寫入。約 118 個讀者（AF、AE、PDAF、ContSet 等），
  最後都走進查表 wrapper，或只做「相等／有沒有變」比較。
- **[F] 其他快取**（`C31D8A04/08/0C`、`C2F1E1E0`、AE 物件 +0x48 等）都只用來偵測變化，或轉交給查表函式。

## 2. 以 mode 為鍵的表（描述子欄位）

每張表 70 列，列 ID 順序一致；列的第 0 字是 mode id。

| 欄位（base／count） | 位址 | stride | 查表函式 | miss 時 |
|---|---|---|---|---|
| +0x00／+0x04 TIM | 0xC0B59500 | 0x20 | FUN_c0320BA0 | 0 |
| +0x08／+0x0C META | 0xC0B59DC0 | 100 | FUN_c0320B38 | 0 |
| +0x10／+0x14 R10 {value, mode} | 0xC0B5B918 | 8 | FUN_c031FFA0（回傳 value，FUN_c0320008 用它設讀出） | 0 |
| +0x24／+0x28 R28 | 0xC0B5BB48 | 0x28 | FUN_c0320E90 | 0 |
| +0x40／+0x44 R38 | 0xC0B5C638 | 0x38 | FUN_c0320F60 | 0 |
| +0x48／+0x4C R14 | 0xC0B5D588 | 0x14 | FUN_c0320EF8 | 0 |
| +0xF4／+0xF8 R68 | 0xC0B5DB00 | 0x68 | FUN_c0320C00 | 0 |
| REGDESC 0xC0B5FDA4 {base, count} | — | 0x288 | FUN_c0326DB8 | **0xFFFFFFFF** |
| +0x128／+0x12C ZOOM（放大鏡） | 0xC0B5F7E0，只有 2 列（mode 10、3） | 0x5C | 沒有查表函式，6 處 inline scan | — |
| +0x114／+0x118 | 0xC0B5F770，2 列 | 0x38 | FUN_c032d9a0，index 由呼叫端給 0/1 | 不看 mode |

- **[F] REG 查不到時回 0xFFFFFFFF**，其他查表回 0。若 REG 查表失敗，FUN_c03258c8 會從 `base − 0x288` 讀 160 多個值寫進感測器暫存器。
  新增 mode 時，REG 一定要有列。
- **[F] 描述子 +0x50..+0x140 的其他欄位是純量**，不分 mode（由 FUN_c0322ea0 從 0xC0B5F898.. 複製）。
- **[F] 不經過查表、直接看 mode 的地方**都不影響錄影：
  - 名稱表 `PTR_ACQ_c2f1e2dc[mode]`（FUN_c031fd70，222 筆）：只用於除錯 log 和 shell dump，mode ≥ 222 會讀過表尾。
  - IMX410 v33／v34 的小集合判斷：{102,108,124,152}、{58,89}。
  - AF 的常數比較。
  - 除錯用的暫存器 override：`imager+0x58` 旗標加上 `+0x5C == mode`，預設關閉，shell 指令 `imager_reg_add_flag`（FUN_c03eaec0）才會打開。
- **[F] 沒有任何時脈、DMA 或 buffer 的閘門以 mode id 為鍵。**

## 3. 錄影 profile（pid）

- **[F] picker 表項** {5, pid, mode, keyptr}，stride 0x10。原廠 CinemaDNG 三張表（0xC0BE5810、59B0、5B50）用 pid 131..190、417..434。
  M12（MONIT1_240）對應 p13。
- **[F] profile 物件**（`XC_LiveViewFieldAngleTable`）由 FUN_c043a158(obj, pid) 建立：
  - obj+0 = pid；
  - obj+0x5C = 67 字的 **PARAM 記錄**，由 FUN_c0439d18 填入：65 個欄陣列各取 `[MAPPING[pid]]`，最後兩字固定 0x17B0、0xFCA；
  - **MAPPING `0xC0BD05D4` 全映像只有一個讀取點：C043A18C**；
  - obj+0x168 = class 位元，由 FUN_c043a1c8 依 pid 範圍計算：1..4 → bit0；5..11 → bit1；101..129、191..197、301..312、401..416 → bit2；
    131..190、417..434 → bit3（raw movie）；29..40 → bit4；17..28 → bit5；記錄 +0x84 == 0xB → 0x100。
    p13 和空槽 41..100 都是 0。
- **[F] C043A19C**（`mov r0,r4`）位在填記錄之後、算 class 之前，是改寫記錄最好的位置。
- **[F] pid 的其他讀者**都只做相等比較或寫 log：C03A6238（LV 重啟判斷）、C040ECEC（logger）、C0428B84（assert）。
  FUN_c0429910 把 pid 寫進通道設定，FUN_c01d1630 存到 0xC31DF3BC，目前沒找到讀者（Thumb 側未查完）。
- **[F] raw movie class（bit3）有兩個讀者：** C03A6734（FUN_c03a66b0）和 C03A6DE8（增益分派 FUN_c03a6dd8）。
  p13 不在 raw movie 範圍內。9/29 的原型同樣如此，仍然錄得很穩。

### 原廠 p13 的 PARAM 記錄（MAPPING[13] = 6，離線由映像算出）
`0C=1920 10=1280 1C=2 20=1904 28=1270 30=60.0f 38=1 60=1023 64=1023 80=10 84=10 B4=1 C0=1 D0=1023 D4=1023 D8=1920 E0=1280 F0=2 F4=2016 F8=1344 FC=3.0f 100=3.0f`，其餘 0。
9/29 錄 239.76p 時又覆寫 25 組（尺寸 1008×672／992×662、0x60/0x64=2048、0x80/0x84=7、0xB0=1、FC/100=2.0f…），
並把 +0x30 設成 239.76f。2026-10-14 實機抓到的虛擬 p74 記錄和這份重建值逐字相同。

## 4. 對新增 mode／profile 的意義

- 複製 TIM、META、R10、R28、R38、R14、R68、REG 這 8 張表，並攔截 8 個查表函式，就足以讓韌體把新 mode 當成 donor。
  ZOOM 只有 donor 本身有列時才需要。
- 新 pid 用 MAPPING 的空槽（class 0 的 41..100），PARAM 記錄在 C043A19C 改寫。
- 2026-10-14 實機：虛擬 mode 230 的 7 張 clone 列和 mode 12 逐字相同，只差 mode 編號。
