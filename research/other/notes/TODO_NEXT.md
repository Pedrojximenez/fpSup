# 明天任務列表（SIGMA fp — USB shell / DFD）

> **2026-08-24 更新**：8/23 那天的成果補記在 `notes/research/imaging-hw/../../imaging-hw/notes/IMAGE_CHANNELS.md` + `notes/research/display/../../display/notes/OSD_PERSISTENT_MARKER.md`
> （原 session 被 API safeguard 中斷、沒來得及歸檔）。

## ★ 現在的第一順位（接續 8/23 被中斷的地方）
1. **可切換多通道 live 影像工作台** —— 使用者最後的要求：「可以做成可以切換的嗎？我會想看每個不同通道」。
   - `push_ptr.S`（通用推送常式，切通道只改 `STATE+0x7C` 指標 cell）**已建好、已注入 @0xC072F600**，但還沒跑完就被中斷。
   - 通道：偵測影像（`0xC375D8C0`，320×240 灰階，**已驗證可解**）／線性 develop YUV（`0xC375C078`，1920×1080 YUYV，**需先確認活著**）／AF 綠 band（`0xC3404768`，1D 能量折線）。
   - 改 `dfd_image.py` 加通道切換；⚠️ **不能每幀下命令**（連續 BATCHPUSH 會 stall EP84）→ 要 worker 自驅動 push loop。
2. **持久 OSD 標記** —— 正解已找到（註冊自己的 DrawingObserver `FUN_c0528300`，先畫矩形），配方在 `OSD_PERSISTENT_MARKER.md`，尚未建。

---

## 任務 1：CinemaDNG 錄影旗標驗證（探針放慢）
**目標**：確認 CinemaDNG 錄影時哪個旗標會 0→1，讓 worker 能在錄影中正確 hold（不 re-arm→不 wedge）。
- 候選（fixed BSS 物件 `0xC351FF34`，MovRecFuncStateCinemaDng）：
  - **#1 主要** `0xC351FF35`（byte）==1 錄影 / 0 閒置
  - #2 `0xC351FF36`（byte）
  - #3 `0xC351FF38`（word）segment bitmask
- 方法：慢探針 poll `word(0xC351FF34)` + `word(0xC351FF38)`（間隔 ≥1s），你錄一小段 CINE，看哪個 flip。
- 背景：舊旗標 `0xC347E08F` 已證實錯（movie RecMgr `0xC358E2C0+0x163` 對 CinemaDNG 不動）。
- 找到後：更新 `camera/shell_rw_worker.S` 的 round_loop rec-gate 改讀正確旗標 → 重建 recsafe AutoRun。

## 任務 2：commSerial 全流量 hook — 重查鏡頭 DFD（可能推翻舊結論）
**動機**：out-of-band 讀鏡頭會觸發「鏡頭異常」提示 = 我們**繞過了握手/session lock**。之前判「DFD 不在鏡頭」的支柱是「大塊 0x011040/0x012023 讀出全 FF」，但**那 FF 可能只是因為我們沒做 unlock 握手，不是真的空**。
- **做法**：hook **`commSerial 0xC0359DD0`**（最底層，記每 byte：addr/len/dir/data 到 result ring）→ **重新裝一次鏡頭**觸發完整 init 握手 → dump 全程。
- **看兩件事**：
  1. 相機做了哪些 unlock/select 命令（我們漏的握手）
  2. 那些「對我們是 FF」的塊，在相機握手後是不是有真資料 → 若有，DFD 可能真的在鏡頭裡
- 一石三鳥：不撞匯流排（修掉鏡頭異常提示）+ 看正確 unlock 後資料 + 抓漏掉的查詢命令。
- 相關 EA：CmdRead `0xC0355BE0`、cmdReadMain `0xC0357188`、CommPacket `0xC035A1D8`、packet builder `FUN_c035a030`、optical download `FUN_c0347b90`、block parser `FUN_c0347a00`、lens_mgr `0xC347CB14`、mount ctx `0xC347D098`。
- 進階（風險較高，選配）：若要 fp 主動去問它平常不問的資料 → 注入自造查詢命令（CmdWrite `0xC0355E88` 到 0x000520 那扇門）。

## 任務 3（實驗性／未來）：USB-sustain-while-on 充電 patch
**發現**：「開機不能充電」是**軟體政策，不是硬體牆**（可 patch）。fp 系統與充電共用 VBAT 節點 → 「開機充電」＝「VBUS 供電續命」同一件事，灌入電流直接抵銷耗電。
**硬邊界（不可越過）**：
1. 沒有獨立 VBUS→VSYS 路徑 → 永遠不能拔電池純 USB 跑（只能抵銷耗電）。
2. 輸入限流寫死 **500mA（~2.5W）**，可 patch 到 2000mA，但…
3. 沒有 PD/BC 協商 → 限流拉高超過來源實供量 → **VBUS 垮 → brownout/重啟**。
**槓桿（常駐 RAM patch，非單一 flag）**：
- spoof 充電 gate：NOP `FUN_c0202258`@0xC0202258:1813 與 `FUN_c0202318`@0xC0202318:1851 的 `return 0`，或改 decoder `FUN_c0024630`@0xC0024630 強制 flag[6]/[7]=0（PWRS 來自 co-processor mailbox `0x2D000308/30C`，直接 poke `_DAT_c31d86b0` 無效，會被重寫 → 必須 code patch）。
- 保持 OZ8075 charge-enable：`v7`@0xC0203D38 的 enable 分支；充電角色與 data 角色互斥（role factory `FUN_c0040320`@0xC0040320）→ tether 模式充電 task 未實例化，需讓它在非充電角色下也活著。
- （選配）拉高限流：`v2` init@0xC0203A40 的 `FUN_c0206000(dev,500)` → 改 code4=2000mA（`v6`@0xC0203C98 reg4 mask 0x07）。
**★ PTP / shell 模式下充電（我們的實際用途）**：充電角色與 PTP/data 角色互斥 → PTP 模式下充電 task 未實例化，光 spoof gate 無效。需做**角色無關的充電維持器**（常駐 patch，獨立於 USB 類別）：(1) spoof gate；(2) 常駐保持 OZ8075 charge-enable（`v7`@0xC0203D38，I2C 可獨立呼叫）；(3) 保持 MM3556 電量計管理運作（更新電流、防過充）。有了它，**PTP + vendor composite（我們的 shell 模式）能邊跑邊續命** —— 這比「切到充電角色」更有用。VBUS 供電本身與資料類別無關（PTP 裝置一樣拿匯流排電）。
**測試順序（最保守）**：先在 **idle/回放/待機**狀態、接**真正 2A+ 充電器**（非筆電埠）測 gate spoof（維持 500mA）→ 觀察電池是否止跌 → 再考慮拉限流 → 最後才試 shell 模式下的 role-independent 維持器。
**用途**：減緩長 shell session 掉電（少換電池）。⚠️ 凍結復原仍需斷電 → 那條用 CN-21 假電池 DC，sustain 幫不上。
**其他 EA**：I2C rmw `0xC02061A8`、input-limit setter `0xC0206000`、gate snapshot `0xC0024188`、PWRS live `0xC0122D58`、board-variant gate `0xC00B8760`、OZ8075 vtable `0xC0203A40`。

### ⚠️⚠️ 安全紅線（本專案唯一可能造成物理損壞的任務）
- 至今所有 patch 最壞 = 凍結/拔電池，**不損壞**。充電 patch 搞砸 = **鋰電池過充 → 膨脹/起火**（不可逆，踩到「絕不 brick/burn」紅線）。無風扇機身另有發熱風險。
- **防過充是 MM3556 電量計 + OZ8075 termination 在管的。紅線：動 gate 可以，termination / 溫度保護 / JEITA 一個字都不能碰。** 危險只發生在「同時破壞終止邏輯」。
- **安全版本**：只 spoof「相機開機狀態」gate，完全不碰電池保護；若 gate spoof 後正常終止邏輯仍在滿電時自動停充 → 有界、安全。
- **做之前必須（純讀先行）**：
  1. spoof gate 後**純讀**驗證：讀 MM3556 gauge + OZ8075 reg，確認**滿電時它真的自己停充**。確認終止保險還在，才談常駐維持器。
  2. 加**我們自己的軟體上限**當第二道保險（例：電壓到 4.15V 主動關 OZ8075 `v7`）。
  3. 全程監控電壓/溫度；只在**有人看著、通風、可立即斷電**環境測。
- **優先級最低**。沒完成上面純讀驗證前，不碰。

---

## 背景參考（昨天成果）
- **DFD 大突破**：AF-C 吃 Bayer 綠通道，銳度指標 `saf_jdat_h/l`（0xC32985E8 / 0xC32986B4）可 peek → DFD 可繞開抽 Bayer 幀。完整見 `notes/research/autofocus/../../autofocus/notes/DFD_VIA_AF_STATS.md`。
- pre-disarm hook（`FUN_c01e62a8` @0xC01E62A8 → stub @0xC0727380）已建好部署，choke point 正確；但 worker re-arm 用錯旗標（任務 1 修）。
- 待接 DFD 採集工具：掃焦 + peek `saf_jdat_h/l` + `mposm`(0xC3291958) → Lorentzian → 深度。
