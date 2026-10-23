# RES-Custom 左下角 FPS：保留文字方式，接近原廠排版 — 2026-10-15

**後續實機更新：** 最初候選保留原樣；目前卡上為 `combined-fix12`，黑框往外加厚約 3 px，白字與 fix10 調好的間距維持不變；開關 QS 後實拍完整 `29.97 FPS`。對比色確認外擴後已完整還原黑色。
1910 是更新前原廠畫面，先前據此作出的外觀一致判定已撤回；目前字形仍有差異。
共用安裝器容量與提前停止解析已修正，完整成品與限制見 [2026-10-15 run7](../20261015-qs-first-open/on-camera/run7/RESULTS.md)。
以下是最初離線候選階段的紀錄。


使用者要求保留文字繪製。候選版將整數、小數與 FPS 拆成三個原生 drawText 元件；整數較大，小數與單位較小，使用 px、左對齊與共同的底部對齊。原廠格率、四個虛擬格率與隱藏 15p 共 14 個顯示狀態；整數格率的小數段為空白。Settings 與 QS 的格率文字不改。

## 排版與實作

- 大／中取景畫面各有一組字級與位置，涵蓋 CINE 與 STILLlike 四種資源集。
- 數字 1 使用較窄的寬度。標準格率的配置總寬度，與原廠 XCI 圖片寬度相差最多 4 px；這是排版目標，不是原生 renderer 的像素比對。
- 沿用既有 NBU record hook。原有 FrameRate 物件、位置、可見性、app-variable binding 與事件 ID 保留；新增文字元件使用未占用的 8／9。
- 不新增圖片、字型或 hook site。四個較大的 allocation header 與 draw／clip 記錄留在 consumer 自有常駐 block，解析時交給原廠 interpreter。原始資源集與相鄰記錄的位址不搬動。
- 2324 B 韌體範圍由既有 Loader journal 管理；其中也包含舊版文字 installer 會改的字，使正常暖開機可還原。大型 allocation header 不整塊寫進 journal，避免超過既有容量。
- 啟用前核對全部 12 個原始記錄的長度與內容雜湊，任一不符就不改 LV 物件／群組；未知配置容量不承接新增文字。
- 表格 12 筆、42,296 B；單筆及總長度、文字標記、component 數量均有 build-time／runtime 邊界檢查。未知原始記錄透傳，不套用私有替換。
- 暫存 core state 的 BODY 移到 0xB00，以容納 29 個字串 id；持久化設定區與 Virtual RCD ABI 不改。

## 成品

只交付 `final/32RESCUS.BIN`：Virtual RCD consumer v21 的文字樣式候選版。

- 大小：232,512 B。
- SHA-256：`22655ada516e0ec652501e5a6caceaf35bbdbf4d376372657b3f6139c935c965`。
- 建置：`python3 -B projects/open-gate/build/res-custom/build_v3_rescustom.py --virtual-rcd --out projects/res-lab/validation/20261015-fps-text-style/ready`。
- 已逐位元組確認 BIN 內的 12 個 resident 替換記錄就是最後來源產生的資料，完整雜湊符合 build.json。
- 共用 loader、AutoRun 產生器與 Fast 選項未修改；相容產品更新不需更換 AutoRun。需重新開機才重新解析 UI。
- `provenance.json` 保存交付 BIN 與來源雜湊。`source-before/` 保存修改前來源；中間成品已移除，雜湊留在 `superseded-artifacts.json`，不要交付。

## 離線測試

- 新文字資源測試與 core 選單測試：5／5 通過，包含原廠 NBU interpreter 完整解析四個取景資源集；建構／繪製外部服務為明列替身，未實際繪圖。
- 最後字距調整後：6／6 聚焦測試通過，涵蓋 14 個文字狀態、四種配置、原廠寬度目標、12 筆常駐記錄的 ARM 掛鉤、關機還原、未知記錄透傳與放大鏡回歸。
- 負控制：在模擬器停用 LV_RECORDS，三段文字 assertion 確實失敗；沒有修改共用來源來做 mutation。
- 大範圍 core／RCD 測試首輪：72 項，70 通過，2 項失敗。其一是既有 v21 時脈 C0189440 的 claim 期待值漏列，已補正，單項重跑通過；其二是本次新增 assertion 暫時放錯測試函式，已移至 FPS 選單測試，相關兩項及最後六項重跑通過。不把首輪記為全套一次通過。
- 最後增加整組原始記錄檢查後，正常安裝、未知 allocation header 拒絕與記錄透傳 3／3 通過；交付的實際 BIN 亦完成載入、12 筆替換、reader 還原與關機 journal 還原。
- Virtual RCD 兩個 Sup 的整合測試：24／24 通過（888.427 s）。最後整組 header 守衛則由上述 3 項與實際交付 BIN 檢查覆蓋，未重跑整套整合測試。

## 上機狀態

本輪沒有操作相機、寫卡、重開、實錄、commit／push 或發布。文字仍由相機的原生字型繪製；字形、抗鋸齒、實際字級、底線與相鄰欄位間距尚待相機畫面驗收，不能宣稱和原廠圖片逐像素相同。初版字級為大畫面 43／26、中畫面 35／25；可在確認原生字型的實際 metrics 後微調，不改格率數值或錄影邏輯。
