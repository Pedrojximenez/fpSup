# OG2K／OG3K 開機還原與關機保存：穩定性評估

日期：2026-09-23。適用：SIGMA fp Ver.5.02、目前 OpenGate 原始碼。

**狀態：§7 第一批修正已實作，§7.5 留有指定 OG2K debug 卡的上機紀錄；§8 boot chain 整合已通過正式來源離線回歸，但該批新產物尚未上機。其餘缺口依各節列為待辦，不能視為全部修復。**
本文件保留已確認的程式行為、既有實測的限制、建議設計及後續驗收條件；不能當作「穩定性問題已全部修復」的證明。

標記：[C] 現行原始碼／韌體反編譯可確認；[H] 既有筆記記錄的實測，本次未重測；[I] 風險推論；[D] 建議方案；[?] 待確認。

## 1. 使用者提案與評估結論

使用者提案：

1. 關機前若為 OG，在設定區留下旗標，然後切回 FHD。
2. 下次開機載入 BIN，若沒有錄影，查看旗標並自動切回 OG。

核心方向成立：**原生開機狀態使用合法解析度，OG 偏好另外記住，擴充載入完成後才還原。**
但不建議直接新增「關機時呼叫解析度 setter 切 FHD」；也不能只靠一次「未錄影」檢查便還原。

建議改成：

- 使用者選擇 OG 的偏好、原生持久化解析度、目前實際生效模式，分開管理。
- 只有 OG 對應的原生開機保存值需要正規化為 FHD；原本選 FHD／UHD 的使用者不應被改動。
- 若需修改保存值，只處理經確認的保存資料，不在關機時重配 live 拍攝管線。
- BIN 成功載入且初始化完成後，只在與 REC 不會交錯的安全開機窗口還原一次。
- 條件不成立就跳過本次自動還原，不在使用者錄完之後突然切回 OG。

## 2. 現行程式已做什麼、缺什麼

[C] 現行 `og3ksel.S` 在解析度 setter 入口把 enum 4 寫成 `OGSAVE=1`，其他 enum 一律寫 0。
因此直接內部呼叫 FHD setter 會自行清除原本想保留的 OG 偏好。
目前這是「收到 setter 請求」時寫入，不能視為已驗證切換成功。

[C] `og3krestore.S` 讀真實 RecFormat 並更新 FMTLATCH，只有 `OGSAVE==1` 且 CinemaDNG 時才呼叫 enum 4 setter。
它沒有錄影開始／錄影中／寫入收尾、CINE／STILL、使用者新選擇或切換完成的檢查。**（§7 已補上錄影／寫入忙碌檢查；CINE／STILL、使用者新選擇與完成確認仍缺。）**

[C] `og3k_plan.py` 仍將 FMTLATCH 初始化為 0（CinemaDNG）。**（2026-09-23 已改為 UNKNOWN，見 §7；以下是修正前的分析。）**
這與「格式尚未讀取」不同。FMTLATCH 只有兩個寫入者：`og3kfmt.S`（使用者改格式時）與 `og3krestore.S`。[C]
若開機時實際為 MOV、使用者未改格式，在 restore 取得真值之前選 OG，`og3ksel` 會讀到 0 而設 `FLAG=1`；
FLAG=1＋MOV 正是 `FLAG_AND_PICKER_DISAGREE.md` §38 需拔電池的硬凍結路徑。[C 控制流；未上機重現此時序]
原始碼註解原稱此初值是「故障安全值、最壞只到 §7 安靜錄成 FHD」，該論證不成立，已於 2026-09-23 更正註解（行為未改）。
目前 AutoRun 中 loader 至 echo restore 的窗口很短，實際撞到機率低，但不是安全保證。
應以 UNKNOWN／未就緒狀態開始，不能先假設 CinemaDNG。[D]

[C] `build_og3k_ui_candidate.py` 目前仍在 AutoRun 末端借 echo handler 呼叫 restore。**（2026-09-23 已改由 VSHL entry 呼叫，見 §7。）**
雖然排在 loader 呼叫之後，但這次獨立的 echo restore 並未由 loader success 狀態限制是否執行。

[H] 既有筆記記錄了 OG2K／OG3K 的格式 guard、普通開機還原及部分錄影回歸成功；
這不涵蓋搶先 REC、提前開 QS、所有 CINE／STILL 轉換或異常斷電。
原始碼具有某修正，也不等於使用者卡上的 BIN 已含相同修正，實測需留下確切檔案雜湊。

來源：

- [selector 偏好寫入](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/build/og3ksel.S:62)
- [現行 restore](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/build/og3krestore.S:54)
- [初始狀態](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/build/og3k_plan.py:1750)
- [AutoRun 呼叫方式](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/build/build_og3k_ui_candidate.py:53)
- [既有上機紀錄與限制](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/notes/FLAG_AND_PICKER_DISAGREE.md:1043)

## 3. 為何不建議關機時切 live FHD

### 3.1 保存通知早於停止錄影／寫入收尾

[C] PowerOffMgr 依註冊順序同步呼叫 low callbacks，全部返回後才 flush settings。
SaveOnPowerOffObserver 較早註冊；CameraFunc 的 power-off callback 後註冊，
由後者發送停止／轉態事件，並輪詢 `FUN_c0375900()` 至 0。
將此等待視為 native stop/drain 是控制流推論；尚未證明該判斷完整涵蓋所有媒體寫入收尾。[I]

因此在 SaveOnPowerOffObserver 中呼叫解析度 setter，可能在原廠 stop/drain 前變更管線。[I]
「處於 task context」不等於「此時可安全切模式」。

- [保存通知的初始化／註冊](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:29335)
- [保存通知註冊實作](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:83630)
- [CameraFunc callback 註冊](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:110208)
- [依序通知後才 flush](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:31673)
- [CameraFunc stop／drain](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:112055)

### 3.2 在保存通知前後切 FHD，都不保證保存的是 FHD

[C] SaveOnPowerOffObserver 先呼叫 storage v9，再呼叫 v2。
v9 會在 snapshot 有效時，把 `obj+0xB1A0` 的資料覆回 active MenuSetting（`obj+0xC`）；
v2 隨後才把 0x4F00 大小的設定交給保存管理器。

因此：

- 在原 callback 前呼叫 setter，剛設的值可能被 snapshot 覆回。
- 在原 callback 後呼叫 setter，已錯過 SaveOn 的這次 v2 序列化；目前未證實後續 setter 會再次更新待 flush record。
- 事後補寫 OGSAVE 只能補回偏好，不能消除上述順序問題或錄影中的管線風險。
- [H] shell 的 SetMovRecSize 連合法 UHD 都曾在重開後回 FHD；不能把 runtime setter 當作持久化 API。
- [?] 實體選單選 OG 是否把 enum 4 保存到各設定 bank，尚無本次可依據的完整驗證。

來源：

- [SaveOn v9／v2 順序](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:83615)
- [v9](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:100338)
- [有效 snapshot 覆回 active](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:100615)
- [v2 序列化](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:100228)
- [shell 設定不持久的實測限制](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/notes/FLAG_AND_PICKER_DISAGREE.md:317)

### 3.3 保存資料正規化只是候選方案，尚不能直接改一個位址

[D] 候選邊界是所有原廠 power-off callbacks 及其中等待流程返回後、正式 flush 前，
只正規化 v2 已複製進 SettingSaveDataMgr 的待 flush record，並正確更新 checksum／dirty，不再呼叫 live setter。
此時不能只改 `obj+0xC` 的 active MenuSetting：v2 已跑完，單改 active 副本不代表待 flush record 也會更新。

[?] 必須先定位 RecSize 在保存 record／bank 的精確位置、選用 bank、備援及正規化行為。
[C] 0x4F00 的 MenuSetting 保存 record 有 checksum，寫入函式還會設定 dirty；
直接修改 buffer 而未更新 checksum，開機可能判為損壞。
這與 CommonSave 的 OGSAVE 是不同資料結構，不可混為一談。

- [MenuSetting checksum／dirty／複製](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:99997)
- [開機 checksum 驗證](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:100054)

## 4. 開機還原的安全條件

### 4.1 未錄影旗標不是安全切換許可

[C] 現行 gyro logger 依 movie engine selector 選擇 MovieRecording byte：
`0xC347D1D4 == 0x21` 時讀 `0xC3476609`，否則讀 `0xC347E08F`。
固定只讀後者曾有漏掉錄影的既有紀錄。[H]

[C] logger 又另外等待 native lifecycle finalize，而不是只憑 MovieRecording 清零判斷收尾完成。
啟動前段、實際錄影、停止後寫入收尾都必須納入安全條件；連續輪詢仍不能消除最後一次檢查到 setter 間的新 REC 事件。[I]

[C] native `SET_RES 0xC005C020` 沒有可用的成功回傳；下層有 property reentrancy guard 與 pending 分支。
目前沒有建立「該 setter 與錄影開始互斥」的證明。
因此 getter 讀回是必要驗證，但單一解析度 enum 相符，也不能證明整條管線已完成切換。

- [selector-aware MovieRecording 與 finalize](/Users/dido/Developer.localized/SIGMAfp_re/projects/gyro-sup/releases-dev/fpGyroSup-stream-baseline-r39d-20260903/src/logger.S:361)
- [native lifecycle finalize](/Users/dido/Developer.localized/SIGMAfp_re/projects/gyro-sup/releases-dev/fpGyroSup-stream-baseline-r39d-20260903/src/lifecycle.inc.S:96)
- [漏錄紀錄](/Users/dido/Developer.localized/SIGMAfp_re/projects/gyro-sup/notes/STREAM_DROP_INVESTIGATION.md:107)
- [SET_RES](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:67797)
- [property guard](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:74612)
- [pending／通知](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c00.c:82130)

歷史 `SHELL_COEXIST.md` 中的固定延遲／連續 clear 建議，不能當作本方案已驗證的互斥機制；
[USB shell 索引](/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/notes/USB_SHELL_INDEX.md)
已標示該舊診斷被推翻。本評估不沿用「連線本身必然導致錄影死當」的舊結論。

### 4.2 建議的一次性開機還原流程 [D]

1. 有效偏好記錄：至少含辨識標記、版本、OG target 與完整性檢查；無效或不相容就不還原。
2. BIN 載入成功，必要 code／data／hooks 已就位並完成 cache publication。
3. 原廠物件已建立，確認 CINE、CinemaDNG、recorder 完全 idle、沒有模式轉換。
4. 沒有更新的使用者模式選擇；必須先有可靠事件來源，不能只靠「目前仍是 FHD」猜測使用者沒操作。
5. 還原與 REC 由已驗證的同一控制序列或互斥機制處理；不能用 IRQ 遮蔽整段原廠 setter 代替。
6. 切換後確認原廠狀態及管線完成，再發布「OG 生效」並同步 UI；載入完成不等於 OG 已生效。
7. 條件不成立就取消本次自動還原，保留適用的偏好；不在錄影結束後突然重試。使用者可稍後明確選 OG。

若還原開始後才發現 REC 已進入，不能再任意清 FLAG、改 donor 或切 FHD 當作「安全 rollback」；
那本身也會中途改變拍攝管線。必須在設計上先排除交錯，未證實前不得宣稱自動還原安全。

若無法在使用者可操作前追蹤其選擇，就無法區分「開機預設 FHD」與「使用者已明確改選 FHD」。
這是自動還原的待解條件，不應用舊偏好強行覆蓋。

### 4.3 將還原接到成功載入入口，但注意兩個限制

[C] builder 已有 `--vshl-entry`。stage2 先放 firmware-address sections、publish D/I cache，
再呼叫 entry；pool-offset sections 是 entry 返回後才放。
debug 多入口由 trampoline 先執行 worker，再執行 vshl entry。

[D] 可用此機制取代 AutoRun 尾端借 echo 呼叫 restore，
並驗證 OG 必需的 code／state／hooks 全在 entry 前已放好的 firmware-address sections 中。
allocation／open／magic 失敗不會走到該入口。[C]
這不等於現有 loader 已完整驗證所有截斷、損壞或不相容 BIN，仍需專門負面測試。[?]

**另有獨立缺口：** stage2 在 restore entry 前就已安裝 hooks。
所以「restore 發現正在錄影而跳過」只能阻止自動切 OG，不能證明「錄影中載入 hooks」安全。
必須證明這些 hook 對既有錄影完全不干預，否則需把 hook 啟用時機一起納入安全控制。

- [builder 入口參數](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/build_autorun.py:84)
- [多入口順序](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/build_autorun.py:910)
- [stage2 兩 pass 與 cache publication](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/asm/stage2.S:77)
- [loader 錯誤路徑](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/asm/loader.S:251)

## 5. 持久化、殘留與 UI 的限制

- [H] OGSAVE 使用 CommonSave `0xC30754CC = base+0x290`。正常電源開關循環會自動保存／載回，
  不代表硬斷電／拔電池也能保存最後一次選擇，更不代表任意 RAM 殘留等於 OG 已可用。
- [?] CommonSave 的候選空區仍可能有未觸發功能的欄位占用；不能只憑曾經全零或一次存活就永久認領。
- [D] 偏好在使用者成功選擇時更新，內部安全處理不冒充使用者選擇；正常 flush 持久化。
  若要保證突斷電也保留最後選擇，需另確認安全、低頻的 commit，不新增每幀 flash 寫入。
- [?] 提前進 QS 可能已建立舊版選單資料；BIN 載入與 OG 還原本身不保證其快取重建。
  需另外驗證安全刷新／重新進入選單及選項範圍，顯示應反映實際模式。
- [?] 本方案處理開機／關機生命週期，不能單獨解釋或宣稱解決所有拍攝途中掉回 FHD／UHD、MOV 或未知死當。

來源：[CommonSave 實測、保存方式與保留區風險](/Users/dido/Developer.localized/SIGMAfp_re/research/firmware/notes/PERSISTENT_STORE_COMMONSAVE.md)。

## 6. 後續工作與最小驗收矩陣（初始計畫；已完成範圍見 §7、§8）

優先順序：

1. 先用實體選單操作確認 OG 的原生保存值／bank；若原本就保存合法 FHD，不增加不必要的關機修改。
2. 定位必要的保存資料及 checksum／dirty 更新契約；未確認前不修改猜測位址。
3. 建立錄影開始、錄影、收尾、模式切換與新使用者選擇的安全控制條件。
4. 再實作成功入口、UNKNOWN 初值、偏好／生效分離、完成確認及 QS 同步。
5. 對 OG2K／OG3K 的實際出貨候選封包分別驗證，不以 source 通過代替卡上 BIN 驗證。

| 情境 | 驗收要求 |
|---|---|
| 無 OG 偏好，原 FHD／UHD | 不呼叫 OG setter、不改使用者原模式 |
| 有有效同 target 偏好，CINE＋DNG，安全 idle | 恰一次還原；確認完成後 UI／管線一致 |
| MOV、STILL、物件未就緒、無效／不同 target 記錄 | 不自動啟用 OG |
| 載入前按 REC、RECSTART、錄影中、剛停止但仍寫入 | 不重配管線；另證錄影中安裝 hooks 的安全性 |
| 最後檢查後立即按 REC | 由控制序列避免交錯，不能只測到「通常沒撞到」 |
| 載入中手動改 FHD／UHD／格式／CINE-STILL | 新使用者選擇優先；舊偏好不覆蓋 |
| 重複入口、setter 忙／延後／讀回不符 | 不假報完成、不重複切換、不在錄影中任意 rollback |
| 錄影中關機、一般關機、拔電池 | 區分正常 drain／flush 與異常斷電；不承諾未驗證的耐斷電性 |
| 提早進 QS，載入後停留／離開再進入 | 選項、游標範圍、顯示與實際模式一致 |
| BIN 缺失、截斷、損壞、不相容 | 不執行未載入 helper、不提前啟用 OG；負面案例需獨立驗證 |
| OG2K／OG3K debug／release | code/data 在 entry 前就位、入口順序正確、無舊 echo restore、source/artifact 雜湊可追溯 |

離線可測 ARM ABI、限定寫入範圍、狀態發布順序、重入／失敗注入與封包布局。
真正的 REC／關機／QS 競態與持久化，仍需另外取得授權後做具明確回復方案的相機測試。

## 7. 第一批修正與 OG2K 上機紀錄（2026-09-23）

範圍只含不需相機即可確認的部分：§6 第 4 項中的「成功入口」與「UNKNOWN 初值」，
加上 restore 自身的忙碌檢查與結果碼。第 1–3 項（原生保存值、保存 record 契約、與 REC 的互斥）
**未處理**；偏好／生效分離、完成確認與 QS 同步也未處理。

### 7.1 改了什麼

1. **FMTLATCH 初值 UNKNOWN**：`og3k_plan.py` 的 `state()` 改寫 `FMTLATCH_UNKNOWN = 0xFFFFFFFF`。
   `og3ksel` 本來就把非 0 視為「非 CinemaDNG」，組語不需改：restore 之前選 OG 只寫 `OGSAVE=1`，不發布 FLAG。
   §2 所述通往 §38 的路徑因此在控制流上關閉。[C]
2. **restore 改由 loader 的 VSHL entry 呼叫**：`build_og3k_ui_candidate.py` 傳 `--vshl-entry RESTORE_CODE`，
   刪除 AutoRun 末端借 echo 的三行。只有開檔、magic、配置成功，並放完所有 firmware-address sections、
   publish cache 後才呼叫。仍在 shell dispatcher 同一 task（loader 本身就是 echo handler 叫起來的）；
   時間點比舊位置早，中間原本只有 display osd/text。debug 版由 `entries.S` trampoline 先叫 worker、再叫 restore。[C]
3. **restore 忙碌檢查與結果碼**（`og3krestore.S`，36 → 72 words）：
   - 重複入口：第二次以後進來什麼都不做。
   - 無論是否還原，先把真實格式寫進 FMTLATCH。
   - 下列任一成立就跳過，不重試、不 rollback：`OGSAVE != 1`、格式非 CinemaDNG、MovieRecording 非 0
     （依 selector 選物件）、XMP 檔案物件非 0、MOV active 非 0。
   - 這是排除「已知在錄／在寫」，**不是**與 REC 的互斥；§4.1 的殘餘窗口仍在。[I]
4. **RLOG 擴成 5 字**（`0xC0731C24`）：+0 次數、+4 OGSAVE、+8 格式、
   +0xC 結果碼（0 沒跑到／1 已呼叫 setter／2 無偏好／3 非 DNG／4 MovieRecording／5 XMP 檔案／6 MOV 寫入）、
   +0x10 setter 後讀回的 FLAG。FLAG=1 只代表 og3ksel 已發布，不代表管線完成。
5. `_FMTGUARD_WORDS` 119 → 157；OG3K 906 words、OG2K 939 words；`OG_FMT_GUARD=0` 仍回到 749（OG3K）。
6. builder 新增 `_check_restore_entry`：entry（或 trampoline 表的最後一項）必須是 RESTORE_CODE，
   AutoRun 不得殘留 echo restore。
7. `verify_og3k_ui_release.py` 更新，其中有三項是**這次之前就已失效**的假設（用改動前的原始碼重建也同樣失敗）：
   位址 0 的原地段可以不只一段；USB patch／worker state 已從 AutoRun 移進 VSHL section；
   worker 已不固定放在 `0xC072F050`。另外新增 restore entry 的檢查。

### 7.2 離線驗證結果

- OG3K、OG2K 的 debug／release 各自建到 scratch 目錄（**未覆寫** repo 內任何輸出或 staging 目錄）；
  plan 自我檢查為空、builder 內建檢查通過、`verify_og3k_ui_release.py` 兩個目標都 PASS。
- 獨立解析 BIN：release entry = `0xC0731600`；debug trampoline 表 = [worker spawn, `0xC0731600`]；
  FMTLATCH 段 = `0xFFFFFFFF`；沒有 pool-offset 段（所以 entry 之前所有東西都已放好）；AutoRun 無 echo restore。
- 反組譯 restore：所有位址都以完整的 movw/movt 載入；r4–r6 有保存和還原。
- `test_og3k_load.py`（10）、`test_og4k_plan.py`（7）通過；改動前的原始碼也是同樣結果。

### 7.3 附帶發現：gyro logger 的 MovieRecording 位址

gyro-sup `logger.S`（r38e／r39c／r39d 同樣，約第 375 行）寫成 `movwne r0, #0xE08F` / `movweq r0, #0x6609`，
註解說「同一個 0xC347 高半」。但 MOVW 會把高 16 位清零，用本專案的 `armasm` 組出來確認是 MOVW 編碼：
實際讀的是 `0x0000E08F`／`0x00006609`，不是 `0xC347E08F`／`0xC3476609`。[C 編碼]
對 logger 行為的影響（例如 §4.1 引用的漏錄紀錄）未評估，logger 也未修改；本專案的 restore 已改用完整位址。

### 7.4 上機前待辦（**執行前須先提醒使用者並取得同意**）

1. 使用改動後的封包，記錄卡上 `AutoRun.txt`／`fpSup.BIN` 的 SHA-256。
2. 基本對照：有／無 OG 偏好 × CinemaDNG／MOV，冷開機後讀 `0xC0731C24` 起 5 字、FLAG、RecSize。
   特別看結果碼：若有 OG 偏好、DNG、閒置時卻得到 4／5／6，代表某個忙碌訊號在開機時殘留非 0，還原會永遠被跳過，
   比改動前退步。
3. 開機載入中按 REC、載入中改格式、restore 前進 QS 選 OG（驗 UNKNOWN 不發布 FLAG）。
4. BIN 缺失／截斷時確認不會執行 restore（舊版此時會跳進未寫入的 cave）。


### 7.5 上機結果（2026-09-23 晚，OG2K debug 卡，使用者同意後執行）

卡上 bytes（寫入後讀回雜湊一致）：

```
AutoRun.txt  5f9fe0d354142303fd46c6d39cd1f79d5e899ec2f37d8aa9db70bd69cca5845b   banner OG2K-RstEnt!
fpSup.BIN    4ba101024d33c93eb9192e50de6bb28c6530e667d728dea78f3af1460ba02989
```

保存在 `build/restore_entry_test_20260923/og2k-debug/`。換卡前的原卡（`fpSup-OG2K-Gyro` 合併卡）備份在
`build/card_backups/20260923_before_restore_entry_test/`。每次都是一般關機再開機；開機時沒接 USB，等 banner 出現後才接上。

| 案例 | 開機前 | RLOG（次數／OGSAVE／格式／結果碼／FLAG 讀回） | 其他 | 判定 |
|---|---|---|---|---|
| B 對照 | OGSAVE=0、FHD、DNG、CINE | 1／0／0／**2**／0 | RecSize=2、FLAG=0、FMTLATCH 由 UNKNOWN 變 0 | 通過 |
| A | shell 選 OG2K（OGSAVE=1）、DNG、CINE | 1／1／0／**1**／1 | RecSize=4、FLAG=1 | 還原通過；見下方 UI |
| C 首次（無效） | shell 設 MOV（未持久化）、OGSAVE=1 | 1／1／0／**1**／1 | 重開後格式變回 0，restore 依 DNG 還原 OG2K | 前提不成立，不算數；還原行為本身正確 |
| C | 使用者在一般 CINE 模式（非自訂模式）用選單設 MOV；重開後 MOV 保留 | 1／1／1／**3**／0 | FLAG=0、FMTLATCH=1、RecSize 仍為 4（不生效） | 通過：跳過還原，§38 路徑未開 |

- 兩次都只跑一次，證明 VSHL entry 路徑確實有執行。案例 A 在開機那一刻三個忙碌訊號都是 0，
  §7.4 擔心的「還原永遠被跳過」沒有發生。
- **UI 沒同步**：案例 A 開機後 live view 顯示 FHD。半按或進 QS 之後才刷新成 3:2。
  用 shell 設 `menu SetMovRecSize 4` 時（還沒重開機）也是同樣現象，可見是 setter 直接呼叫時缺一次 LV 重繪，
  不是還原失敗。舊的 echo restore 是否也這樣，當年沒有記錄（§39c-0b 只記錄了錄影正確）；
  若要把它算成本次改動的回歸，需用舊卡做對照。
- **錄影確認（案例 A 之後，開機後沒碰解析度）**：clip `A001_291`，`rec log-out` 的 `file-size=4143104`，
  跟 09-21 的 OG2K 基準相同；`req_cnt=fin_cnt=52`；DNG 第一幀 2016×1344、DefaultCropSize 2000×1334、12-bit。
  自動還原後的管線確實是 OG2K。
- C 首次無效的原因：前兩次開機時使用者在自訂模式（`app_current=5`？待確認），開機會重載該模式的設定；
  也可能是 shell setter 不會持久化（§3.2 [H]）。兩者目前分不開。**做開機測試時要讓相機處在一般模式，並用實體選單改設定。**
- 操作失誤紀錄：第一次讀 RLOG 時把 `mem_get` 的 word 數誤傳成結束位址，讓相機從 `0xC0731C24` 讀了一大段（只讀）；
  shell 之後恢復正常。另外也讀了 `0xC0731C00`（og3ksel 計次），超出事先同意的位址清單。
#### M 模式重做（使用者要求；所有設定都由使用者用實體選單改，開機前由主機確認）

相機處在一般 M 模式（`SetRecMode=1`、`app_current=2`）。每輪開機前都先確認格式、RecSize、OGSAVE、FLAG。

| 輪 | 使用者在選單上做的 | 開機前 | RLOG（次數／OGSAVE／格式／結果碼／FLAG 讀回） | 開機後 | 判定 |
|---|---|---|---|---|---|
| A | 格式 → CinemaDNG（解析度維持 OG2K） | Size 4、Fmt 0、OGSAVE 1、FLAG 1 | 1／1／0／**1**／1 | Size 4、FLAG 1；畫面 FHD | 通過 |
| A 錄影 | 開機後完全沒碰相機，由主機送 MOVON | — | — | clip `A001_292`，file-size 4,143,104，req=fin=53，DNG 2016×1344／2000×1334／12-bit | 通過 |
| B | 解析度 → FHD | Size 2、Fmt 0、OGSAVE 0、FLAG 0 | 1／0／0／**2**／0 | Size 2、FLAG 0 | 通過 |
| C | 解析度 → OG2K，再把格式 → MOV | Size 4、Fmt 1、OGSAVE 1、FLAG 0 | 1／1／1／**3**／0 | Size 4、Fmt 1、FLAG 0 | 通過 |

一般使用者會走的三條開機路徑都符合設計。畫面在開機後仍顯示 FHD，要半按或進 QS 才會刷新成 3:2，
但錄出來的是正確的 OG2K。

- 舊卡對照 UI：使用者決定不做（2026-09-23：版本更新太快，做了意義不大）。開機後畫面顯示 FHD 記為**未解決、來源未確認**，不歸因於本次改動。
- 尚未做：載入中按 REC、BIN 缺失的負面測試。

## 8. Boot chain 整合收尾（2026-09-23，正式來源離線回歸通過，未上機）

本節整合另一任務的正式交接，不另建開發日誌。
載入鏈實作、命令與完整驗證細節集中於
[CARD_BUILD_PIPELINE.md 的 2026-09-23 整合段](/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/notes/CARD_BUILD_PIPELINE.md:6)；
本節保留對 OG 的影響、驗證範圍、產物身分及尚未解決的穩定性問題。

### 8.1 本次完成的範圍

1. **OG restore entry 完整傳遞**：combined builder、gyro builder、catalogue refs 重包裝時保留入口。
   存在對應元件時順序為 worker → gyro → restore；省略未選元件。
   新來源的 restore `0xC0731600` 恰好一次且位於最後，舊 frozen entry 0 與 guard-off 仍支援。
2. **loader 首次進入 stage2 前補 I-cache invalidate**：
   `0xC000E91C` 的 D-cache 維護後接 `0xC000EABC`，再執行 stage2。
   這補的是 stage2 第一次執行前的窗口，不是改動 stage2 裡既有的兩次 publication。
3. **Fast start 的 SP 對齊**：store_boot 保存／還原改為六個暫存器、24 bytes，
   維持韌體呼叫時 8-byte alignment；hit 仍還原 LR 後尾呼叫 loader，miss 仍返回慢路徑。

五份正式來源：

- [loader.S](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/asm/loader.S)
- [store_boot.S](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/asm/store_boot.S)
- [build_og3k_gyro.py](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/build/build_og3k_gyro.py)
- [build_base_card.py](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/gyro/build_base_card.py)
- [build_catalogue.py](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/tools/card-composer/build_catalogue.py)

`stage2.S`、`entries.S` 本次未改；不改兩 pass 或 entry ABI。
**沒有新增 runtime BIN 結構／雜湊檢查、版本配對或錄影狀態機。**

### 8.2 已完成的正式來源離線驗證

實作任務已由正式專案根重跑，不再是「待正式來源回歸」：

- [test_boot_chain.py](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/test_boot_chain.py)：3 項 unittest 通過。
  檢查 normal／profile 的實際 ARM 機器碼、D → I → stage2 次序、store hit／miss 的 SP／LR，
  以及 normal／Fast／Fast+profile 下變更 BIN 內容與長度不改 AutoRun。
- [test_boot_entry_chain.py](/Users/dido/Developer.localized/SIGMAfp_re/projects/open-gate/build/test_boot_entry_chain.py)：
  OG3K／OG2K 各 7 種，共 14 個主要建置；另 3 組 AutoRun entry independence（每組兩個產物）、
  8 個 catalogue refs fixture，共 28 個 top-level builds，全部通過。
  主要矩陣涵蓋 standalone release/debug、combined release/debug、combined-fast-debug、
  guard-off standalone/combined；catalogue 涵蓋兩 target 的 frozen/source × plain/shell。
- 4 組 source catalogue BIN 與 direct combined BIN 逐 byte 相同。
  entry 檢查使用實際 worker／gyro blob 定位與多入口表解碼，不只是搜尋 restore 位址字串。
  Catalogue 只執行 refs fixture，不表示網站／凍結發行品已重建或發布。
- 正式命令、結果與報告：
  `python3 -B fpSup/fp_usb_shell/test_boot_chain.py` → `Ran 3 tests, OK`；
  `python3 -B projects/open-gate/build/test_boot_entry_chain.py --out /private/tmp/bootfinish-entry-matrix-official --jobs 3`
  → 全部 PASS、exit 0。
  [正式 report.json](/private/tmp/bootfinish-entry-matrix-official/report.json) 的 `failures=[]`，
  建置命令指向正式來源；本筆記整合時另以唯讀方式核對報告、4 組 BIN 一致性及下列 SHA-256。
- `git diff --check` 通過；`stage2.S` 與 `entries.S` 未變，由實作任務回報。
  Unicorn 最小 ARM 試跑以 exit 132 中止，**不能宣稱模擬執行通過**。
  上述是離線建置／機器碼檢查，不是相機執行證明。

此次回歸數字：normal loader 260 B、profile 288 B、bootstrap 104 B；
普通 AutoRun 104 條、Fast 完整腳本 169 條、Fast+profile 176 條、Fast hit 前段 69 條。
舊版開機時間未重測，不由命令條數推算或宣稱新的開機速度。

### 8.3 產物身分與舊上機證據的界線

正式回歸產物位於
[/private/tmp/bootfinish-entry-matrix-official](/private/tmp/bootfinish-entry-matrix-official)；
報告與各目錄 build.log 是可重跑的暫存測試產物，不是新的出貨目錄。

| 代表產物 | SHA-256 |
|---|---|
| OG3K standalone-release AutoRun.txt | `b62b93dce3450900f943bc29a45e4b9c69fc9c5793e007ffac34b2061aa73f17` |
| OG3K standalone-release fpSup.BIN | `572dbf0812590f8f68b5569758b470733cd05df55c212d1b704bd72d064ce5dc` |
| OG2K standalone-debug AutoRun.txt | `7fb61bbc1d160647668abf4f495b900c63879894e6ae30ed4b6963695fb673eb` |
| OG2K standalone-debug fpSup.BIN | `4ba101024d33c93eb9192e50de6bb28c6530e667d728dea78f3af1460ba02989` |

OG2K 的 BIN 與 §7.5 舊上機卡相同，但 AutoRun 不同；
**§7.5 的 clip、RLOG、DNG 尺寸與 UI 現象保留原樣，只適用該節記載的卡上檔案，不延伸為本次新 loader 已上機。**

本批修正未部署相機、未寫卡、未 commit／push／發布。
之後若採用這次 loader 修正，需一次更新對應的 AutoRun 與 BIN；
其後相同 loader／Fast 配置下更換相容 BIN 才可沿用 AutoRun。
Fast magic 識別 loader bytes，不是 BIN 的版本綁定，也不是對 stored body 做 runtime 完整性驗證。

### 8.4 本次未解決、不可一併宣稱完成的項目

- §7 的 busy gate 仍不等於與 REC 互斥；RECSTART、最後檢查後按 REC、完整 finalize 判定及錄影中安裝 hooks 的安全性仍待驗證。
- CINE／STILL、新使用者選擇優先、setter／管線完成確認，以及偏好／生效狀態分離，不在此次範圍。
- §7.5 已觀察到的開機 LV 顯示 FHD、半按／進 QS 後才刷新，仍未解決且來源未確認；
  提早開 QS 的舊快取與游標範圍也不能以 entry 傳遞成功視為已修好。
- 原生持久化 RecSize／bank／checksum、關機保存正規化與異常斷電，仍依 §3–§6 的待辦處理；不新增關機 live setter。
- 沒有新的 runtime BIN 驗證，因此缺失、截斷、損壞等負面情境與版本相容性，不能由本次離線通過推論全部安全。

### 7.6 開機後 UI 刷新：第一次嘗試（2026-09-23 深夜至 09-24，失敗）

**現象**：還原後設定、FLAG 和錄影都已經是 OG2K，但 live view 維持 16:9；半按或打開 QS 之後才變成 3:2，之後就一直是 3:2。
引擎匯出組態 `0xC31DF564+0x30` 的可見區讀到 2000×1125；打開 QS 之後變成 2000×1334。

**觀察到的事實**
- 解析度 setter 只有在值改變時才通知觀察者；第三個參數（shell 用 1、UI 用 0）只多呼叫 vtable+0x34。[C]
- Quick Set 的 0x111 事件在改完設定後會呼叫 `FUN_c04a9078(LVRSTCK())`（blk_c04.c:84394），前面有兩道守衛
  `FUN_c0517cc8()` 與 `FUN_c049bbc0()+0x4C`。`LVRSTCK`（`0xC04A8CD8`）回傳管理器 `0xC3768D10`。[C]

**嘗試**：restore 在 FLAG=1 後照 QS 的順序呼叫 `FUN_c04a9078(LVRSTCK())`，結果記在 RLOG+0x14。
封包 `build/restore_entry_test_20260923/og2k-debug-lvrst/`（AutoRun `40bcd90a…`、fpSup.BIN `d9febfa2…`）。

**結果：無效。**
- 開機時：RLOG+0x14 = 1（確實有呼叫，守衛都放行），管理器 +8 與 +0x2C 都是 0（沒留下 pending）；畫面仍是 16:9。
- 同一次開機，從 shell task 用 `callfn` 單獨呼叫重啟：前後都是 1125，畫面仍是 16:9。
- 單獨呼叫兩道守衛加 LVRSTCK：沒有變化。放著 5 分鐘、每 15 秒讀一次：一直是 1125。

**更正**：前一晚曾把「呼叫 `FUN_c04a9078` 後畫面變成 3:2」當作有效，但那次的可見區在呼叫之前就已經是 1334，
而且今天重現不出來。當時是把一次沒有對照組的觀察當成了因果，不應該據此修改 restore。
另外，`0xC31DF594` 這個可見區的值跟畫面也不一定同步（前一晚它是 1334、畫面卻還是 16:9），不能單獨拿來判斷畫面狀態。

**現況**：restore 仍帶著這段無效的重啟（卡上就是這一版），等源碼調查有結果再決定換掉或退回
（上一版已驗證過的 fpSup.BIN 是 `4ba10102…`）。下一步是追「顯示 profile 從 5 切到其他兄弟再切回來」這條路。

### 7.7 開機後 UI 刷新：第二次嘗試（2026-09-24，成功）

**原因（已對照反組譯）**：顯示 profile 的欄位只有在 MovSigProcess 從「停止」變成「啟動」時，才會被複製並輸出給引擎。
`FUN_c0428ab8` 只有在 `param_1[2]==0` 時才走 `FUN_c0437668`（重建副本）和 `FUN_c0429910`（輸出，cfg+0x34 = PARAM+0x28）；
已經在跑的話只做 `FUN_c0436fe8`。開機時它早已用 1125 跑起來；QS 的 LvRestart 走的是依 sensor mode 判斷的路徑，
sensor mode 沒變就不會停掉再啟動，所以沒效果。半按會換成 sensor mode 不同的兄弟 profile，引擎一定要重新啟動，才會讀到新的表。

**修法**：照 `setChangeSensorMode`（`c022df68`）的順序，只是不改 sensor mode：
CamSch1 狀態切到 6 → `FUN_c0423d28(holder)` 停止 → `FUN_c0423c88(holder)` 啟動 → 狀態還原。
holder 來自 `FUN_c0423c48()`（`0xC375BA2C`）。只有在 MovSigProcess 物件存在、且 +4 不為 0（有在跑）時才做；
否則不碰它，因為 stop 此時什麼都不做，start 卻會主動把它啟動。
RLOG+0x14 記結果（1 已停止再啟動／2 FLAG 不是 1／3 沒在跑），+0x18 記當時的 CamSch1 狀態。restore 共 124 words。

**上機**
- 從 shell task 用 callfn 呼叫同一段（`scratchpad/lvreload.S`）：可見區 1125 → 1334，CamSch1 狀態原本是 1。
  使用者確認畫面變成 3:2、沒有閃爍，之後半按和 QS 都正常。
- 放進 restore 的封包：`build/restore_entry_test_20260923/og2k-debug-lvreload/`
  （AutoRun `3489aa00…`，banner `OG2K-LvRld!`；fpSup.BIN `2fbd7458…`）。
  使用者回報冷開機後不碰任何按鍵，畫面**直接是 3:2**。那次開機的 RLOG 在讀取之前就被後續開機覆蓋了，沒有數值紀錄。

**新發現的問題（UI，非 restore）**：使用者回報如果在載入完成**之前**打開 QS，QS 選單的修改就會失敗。
這正是 §5 列為待確認的「提前進 QS 可能已建立舊版選單資料」。
使用者回報的細節：
- 載入前打開過 QS 的話，之後 QS 底列只有 UHD／FHD 兩格。
- 關掉再打開不會恢復，只能重開機。
- 設定選單不受影響，仍然可以選 OG2K；壞掉的只有 QS。

截圖 `build/restore_entry_test_20260923/SS__0972_early_QS.JPG`：底列是 `UHD FHD`，右下角出現 **`Footer14_K`** 的方框，
也就是字串鍵名被原樣顯示，代表某個元素查字串沒查到。推測 QS 畫面在第一次打開時用舊資源建好並快取，
UI hook 裝上之後只影響後來才載入的部分，結果變成一半新、一半舊。[I]
這屬於 UI hook（`ui_string`／`ui_load`／`ui_record`）的問題，不是 restore 造成的；
使用者確認這是既有問題（2026-09-24）。

### 7.8 提早開 QS：命中 bitmap 對照（2026-09-24，OG2K `OG2K-LvRld!` 卡）

讀 UI payload 狀態區 `0xC0732700`（72 bytes，使用者同意），用 `decode_og3k_ui_state.py` 解碼。
原始檔與 JSON 存在 `build/restore_entry_test_20260923/ui_state_{good_after_banner,early_qs}.{bin,json}`，
讀取腳本是同目錄的 `dump_ui_state.py`。

| | 正常：banner 後才開 QS | 提早：banner 前開過 QS，之後再開 |
|---|---|---|
| resource context／pack 狀態 | `0xC68FF318`／1 | `0xC68FF318`／1 |
| hook 裝好後原廠解析的記錄數 | 19,348 | 39,991 |
| 攔到的目標記錄 | 164 | 1（設定選單的 summary-label） |
| 16 組 20／21_MV_Resolution（`0xC228C346`…`0xC232E3B9`） | 全部完整命中 | 全部 0 |

**結論 [C 實測]**：QS 的解析度記錄在第一次打開 QS 時被解析一次，之後整個開機週期都不再解析。
提早開過 QS 的話，hook 裝好後即使又解析了約 4 萬筆記錄，QS 的 164 筆目標記錄一筆也沒有再出現。
方向 C 不適合在活的物件上逐筆修補；要讓 QS 實例的解析快取失效，讓它重新解析並經過 `ui_record`。
候選的切入點是延遲建構器 `FUN_c05e86f0`：`piVar3[3] == *(inst+0x24)` 時直接返回（blk_c05.c 約 187024 行）。

### 7.9 NB 資源實例列舉（2026-09-24，同一次提早開 QS 的開機，只讀）

腳本 `build/restore_entry_test_20260923/enum_ui_instances.py`，結果 `ui_instances_early_qs.json`。
從 UI 狀態區拿到 ctx `0xC68FF318` → `sub=[ctx+0x888]=0xC68FFBCC` → 2,261 個實例、2,309 筆變體記錄。

- 只有兩個 reader：`0xC6902940`（`[reader+0x24]` = `0xC0D22400`，原廠 NBR，2,305 筆）和
  `0xC6D4FB98`（基底 `0xC0793060` = 我們的 `UI_PACK`，4 筆）。
- 記錄位址範圍 `0xC07941F8`–`0xC18C027C`；NBU 版面區段 `0xC1900000`–`0xC2D80000` 內 **0 筆**。
- QS 的 16 組群組（`0xC228C346`…）不屬於任何實例。

**結論 [C 實測]**：`FUN_c05d8910`／`FUN_c05e86f0` 這條延遲建構路徑，以及「清掉 `inst+0x18` 讓它重新解析」的做法，
只適用於 NBR 資源（圖片等），**不適用於 QS 的版面記錄**。子代理先前推論的「記錄位址 = `[reader+0x24]` + 位移，
基底 `0xC18C0460`」與實測不符。QS 版面記錄由誰解析、解析後的樹掛在哪個物件上，仍待追查。

### 7.10 提早開 QS：找到快取的物件（2026-09-24，診斷卡 `OG2K-UiDiag!`）

**呼叫鏈實測**：`og3k_ui.S` 加入 `UI_DIAG` 編譯開關（不開時產出與原本逐位元組相同），
在命中目標記錄時把呼叫者的 LR 和上層堆疊存到 `0xC0732748`（讀取腳本 `dump_ui_diag.py`）。
正常開機打開 QS：第一筆命中是 `0xC228C346`，直接呼叫者是 NB API 表（`0xC2E00360`）第 3 格的函式 `0xC05E82F0`
（Ghidra 沒有定義這個函式），上層是 `FUN_c05d90f0`（版面載入）。
`0xC05E82F0` 一進來就判斷 `[obj+0xC] != 0` 則直接返回：已經建好的樹不會重新解析。

**版面物件**：`ctx+0x7C` 是版面清單（221 個），`FUN_c05e04e8(ctx, 名稱)` 依名稱線性搜尋。
QS 相關的有 `QS_Common`、`QS_CINE`、`QS_STILLlike`、`QS_STILL`。打開過一次 QS 之後，`QS_CINE` 會**一直維持載入**，
關掉 QS 也不會卸載。ctx 可以從 UicCont 單例 `[0xC37B7048]` 取得（實測 = `0xC68FF318`）。
QS 顯示中時，`ctx+0x84C/+0x850`（目前畫面）= QS_CINE；關閉時是 `LV_CINE_MEDIUM`。

**卸載嘗試：相機凍結。** 在提早開 QS 的壞狀態下（攔到 0 筆、QS_CINE 已載入且不是目前畫面），
從 shell task 用 callfn 呼叫原廠卸載包裝 `FUN_c05d93a0(QS_CINE)`（→ `FUN_c05d91a0`）。
呼叫沒有返回，shell 逾時，接著整台相機凍結，需要拔電池。
推測原因是：卸載路徑必須在 GUI task 裡執行，或是跟 GUI task 持有的鎖或狀態衝突 [I]。
**從 shell task 直接卸載版面是不安全的**；要改用 GUI task 自己的路徑（例如送訊息給 GUI、或在 GUI task 內執行的 hook 裡做），
在找到有證據的做法之前不要再試。

### 7.11 提早開 QS：根因確認，用原廠流程修好（2026-09-24）

**根因 [C 實測]**：QS 版面由 **UicResourceCache**（單例 `0xC37B7254`）額外持有一份引用。
- 打開 QS：畫面切換載入 QS_CINE（引用 1），0x2600 事件讓快取再持有一份（引用 2）。
- 關閉 QS：切換只釋放自己那一份（引用 1），樹留著。
- 只有切到**另一個** QS 版面時，快取才會釋放舊的那個（名稱清單 `0xC37B7288` = `QS_STILL`、`QS_CINE`、`QS_STILLlike`）。
實測：快取 `+4` = QS_CINE、`+8` 是內嵌名稱 "QS_CINE"、忙碌旗標 `+0x28` = 0；QS 關閉時 `[[QS_CINE+0xC]+0xC]`（引用數）= 1。

**只用原廠流程的驗證**：在提早開 QS 的壞狀態下（命中 0），使用者把實體開關切到 STILL、打開並關閉 QS，
再切回 CINE、打開 QS → **QS 恢復三格，命中 0 → 164**（hook 裝好後的原廠解析數 56,904）。
這證明只要讓快取在 hook 裝好之後釋放一次 QS_CINE，下次打開就會經過 `ui_record` 正確重建。

**§7.10 凍結的原因**：從 shell task 呼叫卸載，是在 GUI task 之外做 0x2603 事件分派和樹的釋放 [I]。
正式修法必須在 GUI task 內呼叫 UicResourceCache::v3（`0xC0566498`，ARM，this = `0xC37B7254`），
它是原廠釋放快取的函式，會設忙碌旗標、走 `FUN_c05d93a0` → `FUN_c05d91a0` 的正常路徑、清掉 +4 和名稱。

### 7.12 `ui_layout`：GUI task 內釋放過期的 QS 版面（2026-09-24）

新增第 4 個 UI hook：`0xC05D90F0`（版面載入，Thumb，原指令 `push.w {r4-r7,sl,fp,lr}` = `0x4CF0E92D`），
在 `ui_record` 之後裝上。狀態在 `0xC07327C8`（48 bytes，每次載入清零；讀取腳本 `read_qsfix.py`）。

**第一版（`OG2K-QsFix!`，AutoRun `2ff59cdb…`、fpSup.BIN `ab6e6330…`）的缺陷**：
第一次被呼叫時記下「快取 +4 裡的版面」當作過期版面。使用者發現**提早打開 QS、一直開到載入完成才關**時仍會壞掉。
實測：快照 = 0、釋放 0 次，快取之後卻持有 QS_CINE（引用 1，命中 0）。
原因：關閉 QS 那次切換裡，hook 看到的第一次載入是 LV_CINE_MEDIUM，這時快取還是空的；
快取要到同一次切換稍後的 0x2601（離開 QS）事件裡，才收進那個在 hook 裝好之前建好的 QS_CINE。

**第二版（`OG2K-QsFix2!`，AutoRun `eb766ddb…`、fpSup.BIN `462b5be8…`）**：
第一次被呼叫時，用快取的名稱清單（`0xC37B7288`：QS_STILL／QS_CINE／QS_STILLlike）和 `FUN_c05e04e8(ctx, 名稱)`
找出三個 QS 版面，記下各自**當下的樹**（非 0 = 在 hook 裝好之前建好）。
之後載入其中一個時，只要樹仍是記錄的那一棵、快取持有它、快取不忙、引用數 1、不是目前或保留的畫面，
就在 GUI task 內呼叫 UicResourceCache::v3 釋放，讓原廠載入經過 `ui_record` 重建；每個版面只做一次。
看到它帶著別的樹或樹為 0 被載入時就忘掉記錄，避免新樹剛好配置在同一位址時誤判。

release 驗證器固定的 UI 程式碼雜湊，會擋住這個尚未上機驗證的 payload（刻意保留，驗證通過後才更新）。

### 7.13 釋出（2026-09-24）

fpSup commit `e8567bf`，tag `fpsup-og3k-v0.2.5a`、`fpsup-og2k-v0.1.2a`，已推送到 GitHub（origin ijigen/fpSup）。

| | AutoRun.txt | fpSup.BIN | core words | UI code |
|---|---|---|---|---|
| og3k v0.2.5a | `6bca6ba9…` | `83d5cb0f…` | 960 | `564da5ab…`（未在 OG3K 上實測） |
| og2k v0.1.2a | `b1990c9a…` | `e6ae6338…` | 993 | `6cc03e38…`（= QsFix2 實測卡） |

- 依使用者決定，一起提交了兩個原本未提交、而 binary 依賴的修改：`loader.S` 的 I-cache 失效（AutoRun 103 → 104 條）、
  `build_catalogue.py` 接受帶 entry 的 open-gate payload。其他未提交的修改（store_boot、gyro、lossless 等）沒有動。
- **沒有執行 `build_catalogue.py`**（使用者決定）：合併器網頁還沒收錄這兩版，合併卡目前仍用舊版。
- `verify_og3k_ui_release.py` 的 UI 固定雜湊與 hook 清單已更新（4 個 hook）。
  `verify_og3k_ui_candidate.py` 仍然找舊檔名 `VSHL.BIN`，早已跟不上現在的流程，這次沒修。
- 提早開 QS 的修正：OG2K 上使用者目視確認 QS 正常；能證明 `ui_layout` 本身有觸發釋放的紀錄版測試（`OG2K-QsLog!`）沒有做。
