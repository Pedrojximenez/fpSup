# Virtual RCD v2

2026-10-09。Res Lab 是第一個產生器，res-custom 是唯一的套用者。
Julien style 尚未接入；以後的新工具沿用本契約，不增加專用套用入口或常駐解析度列。

## 使用流程

`32RESCUS.BIN` 先由共用 Loader v3 安裝，`50RESLAB.BIN` 再註冊產生器。
兩個產品是獨立 Sup。從 Res Lab 自己的「More Settings」開啟設定頁；
res-custom 不提供 Res Lab 的設定入口。Res Lab 的選項變更與數字編輯結束時自動產生完整 RCD1 v3 記憶體資料。
res-custom 核對資料、格率與資源，再替換同一個共用列使用的虛擬表；Res Lab 使用時顯示為 **RES-Lab**。
不需要先匯出 `.RCD` 或重開機。普通磁碟 RCD 仍走原本的載入路徑。

工具可以使用自己的手動幾何、公式或資料表。consumer 只接受共同 RCD 格式與
`virtual_rcd.h` 的產生器描述，不解讀 Res Lab 或 Julien 的專用參數。
模式、profile 與表格資源依當下編譯的配方配置，註冊工具數不增加錄影表數。

## 一個介面

以 [`virtual_rcd.h`](virtual_rcd.h) 為唯一 ABI 定義；ARM 32-bit，ABI 2。
ABI 2 擴充 settings callback 的 open 參數；ABI 1 的描述會明確拒絕。

| 操作 | 輸入 | 結果 |
|---|---|---|
| `REGISTER` | `vrc_provider`，唯一非零 id、context、build 與選用 settings callback | 複製描述；同一 owner 可重複註冊，其他 owner 不可接管 id |
| `APPLY` | 已註冊 id | 呼叫產生器，驗證並套用配方；錯誤保留原表 |
| `STATUS` | 已填 bytes／abi 的 `vrc_status` | 活動產生器、成功世代、最後套用結果、detail、註冊數與圖示用量 |
| `SETTINGS` | 0 | 在 UI thread 呼叫活動工具的 settings(context, 1)；未套用前使用第一個工具 |

`build(context, input, blob)` 的 input 提供目前 FPS rank 與 recording format。
callback 回傳 0 表示成功，輸出完整且 4-byte 對齊的 RCD1 v3；非零成為
`VRC_BUILD` 的 detail。consumer 在 callback 返回後立即複製資料。
輸出緩衝至少保持有效至本次 `APPLY` 返回，無須跨套用保持有效。
input 本身只在 callback 期間有效。context、callbacks 與 provider 使用的狀態須
常駐至本次開機結束；目前沒有解除註冊或卸載。

呼叫限 UI thread；build 不可重入 Apply、呼叫錄影 setter 或更改原廠表。
`settings(context, 0)` 是唯讀 readiness 查詢，回傳 GUI parent id 或 0；
`settings(context, 1)` 由工具自己送出原生 application request 與 view-state event，
回傳共同結果碼。工具自行宣告從設定選單到私有頁的狀態轉移。
SupManager 的按鈕沿用 Loader service v4；核心最低 service v3 保留相容，
可操作的管理頁入口需要 v4。普通卡和 debug 卡均包含管理頁。
`capabilities`／`reserved` 必須為 0；bytes 與 ABI 不符明確拒絕。
RCD 仍須符合現行 validator 的長度、校驗、donor、畫布、時序、section 與 NBR 規則。
目前最多 128 KiB／份，CinemaDNG 8／10／12-bit。RAW14 尚未接入 consumer。

每個 producer 自己註冊 SupManager 按鈕。共同 `SETTINGS` 操作仍可供未來前端選擇工具，
目前的使用者入口放在工具自己的 Sup。原生錄影設定頁的 Help 保持原樣，
格率清單由 consumer 共用安裝，工具不另加自己的 FPS 選單。
Res Lab 的 GUI parent 使用 B2_5 的控制器類型，返回目標明確宣告為 FT_LIST；
不能只返回 B2_5，因為從 SupManager 進入時原生錄影設定頁的焦點未初始化。

## 發現與載入

consumer 在自己已 claim 的 recording picker veneer 後附加 16-byte endpoint。
metadata 在 picker hook arm 以前填妥並 publication。producer 先查 loader holder，
再以共用 cave 的實際界線呼叫 `vrc_find(first,end)`，核對 branch、對齊、veneer、
magic 與 ABI。原廠／其他 picker 或舊 consumer 不會被當成服務指標。
沒有新 firmware 全域指標、固定服務資料槽或 Loader ABI 擴充。

消費者尚未載入時 Apply 回 `NOT_READY`。本版 Res Lab 在 entry 註冊一次；因此
合併時保持 consumer 先載入。維持共用 Loader v3 的檔名排序即可。
相容 payload 更新只換 BIN。獨立 Virtual RCD 卡使用現行共用 AllSups Loader 與管理頁，
不維護分叉的 loader；本次實機已有相容管理程式，因此只更新兩個產品 BIN 與既有 RCD 的格式版本。

## 套用與資料壽命

先把借用 RCD 複製至非活動緩衝，沿用正式 `rcd_check` 與 `fill_s` 在自有 scratch
編譯。必須支援相機目前 FPS，且所有 mode／profile／記憶體預算都通過。
consumer 將列的 label／enum 正規化為穩定的共用身分，保留既有 UI slot 與圖示 id。

Custom 列未成功安裝、錄影、XMP／MOV 活動、重入、無效 RCD、格率不支援或記憶體不足都拒絕。
停止 live view、配置新圖示後，再於 IRQ 保護下核對 busy，才提交完整候選表。
停止後的拒絕會重啟原 live view 並還原 scheduler；未發佈的新配置會釋放。
成功後經真正的原生 resolution setter 設定 stock backing value、重算格率反灰、
重啟 live view。原廠感測器表仍保持原樣，錄影 reader 使用 consumer 的表複本。

已套用且作用中的 Virtual RCD 以實際 picker entries 決定 FPS 可選性。
六份原生格率 CSV 的提供項設為可選、缺少項設為反灰；normalizer 與列表分類
依提供項的最快原生 enum 重算，不沿用普通 FHD 的上限。
尚未 Apply 的 Custom 列不放寬限制，切回普通解析度後恢復各原生分類的反灰值。
宣告下述 bit-depth policy 的磁碟 RCD 也依實際 picker entries 決定格率，避免原生媒體／位深
分類把 RCD 提供的格率反灰。未宣告 policy 的舊磁碟 RCD 保留既有分類限制。
以上判斷在共用 consumer，不依賴 Res Lab 的 provider id。

NBR bytes 對本次開機保持不可變，避免原生 reader 留存的指標遇到被覆寫資料。
相同 pack 按 hash、長度與完整 bytes 去重，只重用完全一致資料。
表格與 RCD staging 會重用；已發佈圖示在本次開機不回收。

## 本版容量與設定保存

- 16 個已註冊 producer，可調整 consumer 容量，wire 描述不需要改成多套接口。
- 一個共用動態列；與普通磁碟格式合計最多 6 列、16 個 virtual mode、32 個 profile variant。
- 每次開機最多 32 份不同圖示 pack、合計最多 4 MiB。重複相同輸出不佔新 pack。
- producer 與 consumer 常駐區塊均由共用 loader 配置；NBR 按需要配置，沒有預留 4 MiB 檔案/BSS。

Res Lab 活動參數與配方存在本次開機的記憶體。SAVE 只將同一配方存成 `.RCD`，不更改啟用清單。
磁碟檔案的啟用／停用由 **RES-CUSTOM 自己的 More Settings** 管理；重新開機後更新解析度與 QS。
管理頁與 SupManager 使用同一原生版型：每頁五檔、數字分頁、同列顯示狀態、Enable／Disable popup。
標題顯示 `RES-CUSTOM (已用/上限)`，成功改變啟用清單後立即顯示 `Restart to apply`；
底列的重開提醒常駐。名額反映已保存的下次開機清單，不表示活動解析度列已即時更新。
原生元件由相同 builder 產生，但檔案變數全部使用 consumer 的 `RC_` 命名空間；不寫 SupManager 的 `FT_` 變數。
管理頁在開啟時重新讀取有效 RCD，且不依賴 Res Lab 的設定頁或 provider callback。
本版保留一個共用動態列，另有五個磁碟檔案名額；滿額時拒絕啟用並提示先停用一份檔案。
獨立 consumer 沒有動態列時提供六個磁碟檔案名額，全部停用後仍保留自己的管理入口。
目前 virtual-capable 成品固定保留動態列；停用或卸載 Res Lab 不會自動改成六個磁碟名額。
res-custom 原有的選取身分記錄無法代替配方；開機時不會只因存有共用列名稱就啟用
bootstrap 尺寸。各工具的啟用沿用 SupManager；載入已存 RCD 不會反向回填 producer 的編輯狀態。
容量是明確預算，並非宣稱工具／配方數量無上限。

## 可選 CRCT binning 配方（consumer core 3）

RCD1 wire 仍為 v3、Virtual RCD ABI 仍為 2。新增 section 11 `SEC_BINFILT`，
五個 little-endian u32：`h taps, v taps, h kernel, v kernel, mode`。
taps 各為 1 或 3，kernel 各為 0–5，mode 為 0（soft）或 1（std）。
六個 kernel 依序對應 `(1,1,1), (1,2,1), (1,4,1), (1,6,1), (1,14,1), (0,1,0)`。
帶此 section 的檔案宣告 `MINCORE >= 3` 並標為 required；舊 consumer 明確拒絕，避免靜默丟失設定。
未帶此 section 的既有檔案保持原本處理。

consumer 在編譯各列及虛擬表提交時一起複製配方。共用 selector hook 在原廠計算後
修正 branch C 的重複水平 /3，並選 soft/std；兩個 driver writer hook 只修改暫存結構的
H /64、V /4096 係數，不寫原廠 reduction table。三個 hook 均宣告於共用 loader journal。
這是 RCD 的共用能力，不辨識 producer id；Res Lab 沒有新增錄影 hook。

## RCD 宣告可用位深（consumer core 4）

可用位深由各 RCD／producer 宣告；RES-Custom 只驗證並套用，不依 SD／SSD、解析度或
格式名稱自行決定開放哪些 bit。RCD1 wire 保持 v3、Virtual RCD ABI 保持 2。
section 13 `SEC_BITDEPTH` 是一個 little-endian u32 mask：bit 0 = 8-bit、bit 1 = 10-bit、
bit 2 = 12-bit。有效值為 1–7；不能空白、不能有其他 bits。必須標為 required 並宣告
`MINCORE >= 4`，讓舊 consumer 明確拒絕，避免靜默忽略設定。
Python producer 使用 `bit_depths=(8, 10, 12)` 或所需子集；Res Lab 的每份輸出也包含本 section。
目前五份磁碟配方 OG2K、OG3K、S16、OG35K、OG4K 各自宣告 8／10／12-bit。

consumer 在載入及 Virtual RCD Apply 時將 mask 編譯進所屬列。活動 CinemaDNG 列的
兩份原生 bit CSV 複本依 mask 反灰；位深 normalizer 保留已允許的請求，不允許時依
原生選單順序選第一個已允許位深。picker 拒絕 RCD 未允許的位深。
位深與格率分類在切換配方後一起重算；切回原生解析度或 MOV，CSV 複本恢復各自原值，
原廠 CSV 與錄影表不被修改。兩個新增 native join hooks 沿用共用 loader 的 journal／還原。

為相容既有檔案，未包含 section 13 的舊 RCD 仍使用原生位深規則；要使用新宣告需重新產生
RCD 並搭配 core 4（本次 payload v18）。開放選項與媒體實際能否持續錄影是分開的驗證項目；
本次位深政策變更僅完成離線驗證。

上機與最新離線證據見 [本次驗證紀錄](../../../res-lab/validation/20261009-oncamera/RESULTS.md)。
僅將該紀錄列出的模式、格率與錄影視為已驗證，其他模式仍需逐項測試。

## 宣告格率（2026-10-20）

核心只負責錄影，不改原生介面。原廠 9 個以外的格率由 RCD 的 `SEC_RATES` 宣告
（`{rank, num, den, cycles, carrier, nominal, engine}`；預設 = 239.76／279.72 載在 119.88、17.98 載在 23.98），
picker entry 用載體的 key，所以只在相機設定為載體格率時才會被問到。錄哪一個由服務選：
`VRC_RATES`（列出現用格式的宣告格率、目前選擇、是否在載體上）與 `VRC_RATE_SET`（rank，0 = 原廠格率），
選擇記在 32RESCUS.BIN 的紀錄、不寫相機設定。DNG FrameRate、最慢快門、角度換算跟著選擇走；
`SEC_WRITER`（寫檔策略）、`SEC_CAPTURE_TIMING`（載體以別的感光元件格率錄）同為必要 section。
格率選單、LV 格率文字等介面不在核心，封存於 [`archive/virtual-rate-20261020/`](../../archive/virtual-rate-20261020/README.md)。
