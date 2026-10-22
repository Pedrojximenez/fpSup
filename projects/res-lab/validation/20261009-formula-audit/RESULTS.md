# Res Lab 公式排查與修正 — 2026-10-09

修正版已寫入相機，完整讀回核對完成；兩組曾在離線重現出錯的 M98 設定均完成原生 Apply 與短片實錄。
最後確認相機為 CINE 待機，Custom 活動，世代 2，輸出 1504×1006。
Res Lab 與 res-custom 維持兩個獨立 Sup，配方由共同 Virtual RCD 接口在記憶體中套用。

## 找到並修正的問題

| 問題 | 修正 |
|---|---|
| 固定比例的第一個整數公倍數比可用矩陣還大，仍強迫使用第一步 | 沒有精確比例可容納時，選最近的合法對齊尺寸；M98／hbin 3／2.76:1 由非法 1104×400 改為 992×360 |
| 裁切只保留 64 像素，水平 /3 後全部被矩陣邊距用掉，會算出零寬度 | 裁切下限同時納入 binning、16×10 邊距與最小對齊輸出；避免減法下溢 |
| 預覽寬度向上取 16 的倍數，最後越過來源 | 對齊後再次限制來源，重算預覽高度；M98 Free 1504×1006 的預覽由 1536×1016 改為 1520×1008，來源為 1531×1016 |
| 小尺寸導致縮放值超出現有規劃器 1024..16384 範圍 | 限制在規劃器範圍，保留較大的記錄矩陣並使用中央有效裁切；此範圍不是本輪實測的硬體極限 |
| 資料率只按有效輸出估算，漏掉矩陣邊界及裁切後保留的完整矩陣 | 按實際記錄矩陣、模式位深與所選估算 FPS 計算，保持精確整數四捨五入 |

輸出前另核對記錄／預覽來源、binning、縮放、重複欄位、待機尺寸，以及模式資料是否與韌體 metadata 一致。
不合法資料明確拒絕，保留原來作用中的配方。RAW14 仍可計算，consumer 尚不支援套用。
992×360 是符合矩陣限制的最近對齊比例，並非精確 2.76:1。

## 逐模式離線驗證

| 驗證 | 結果與證據 |
|---|---|
| 70 個韌體模式，四組 binning、17 種比例、五組裁切、三組起始尺寸、兩個主導軸 | [142,800 組公式案例](after-domain-fix.json)通過，無越界、零尺寸、超出規劃器縮放範圍或重算後改值 |
| 70 模式 × 四組 binning × 三組裁切 × 十個 FPS 估算列 | [8,400 組資料率案例](all-rates.json)通過 |
| 正式成品 ARM 的 fit、panel、29 個 canvas 欄位及資料率 | [1,750 組案例](arm-all-modes.json)通過；每模式 25 組；62 模式編碼／解碼成功，8 個 RAW14 模式拒絕 |
| 真正 producer → Virtual RCD → consumer 編譯／套用 | [62 個支援模式](arm-all-apply.json)逐一成功，AUTO／1×1／24p；分三次模擬開機，遵守每次開機 32-pack 預算 |
| 刻意破壞尺寸、預覽、binning、縮放、模式與待機欄位 | [20 組 ARM 拒絕案例](arm-guards.json)全部保留原配方、世代、原廠表與 LV 狀態；還原後合法配方仍可套用 |
| 雙 Sup 與原生選單整合 | [24 項測試](v6-virtual-tests.log)全部通過，460.301 s，無 skip |
| Python profile 參考公式 | [12 項測試](profile-final.log)通過，保留原廠 78 組影片 profile 逐欄一致性；含新增來源邊緣對齊案例與九個突變 |
| 共用 legacy 選單 | [48 項測試](legacy-modes-first.log)通過；這項在第一輪幾何修正後執行 |

[70 模式逐項驗證表](MODE_MATRIX.md)列出每個模式的案例數、問題數與 ARM Apply 結果。
上述案例是系統掃描邊界與代表尺寸，並不涵蓋每一個可能的整數尺寸／裁切組合。
中間資料率報告曾有測試 fixture 的位深映射錯誤；最終統計以 `after-domain-fix.json` 與 `all-rates.json` 為準。

測試另以暫存副本故意撤掉修正：[四項幾何突變](geometry-mutations.json)、[舊資料率公式](rate-mutation.json)、
[跳過 ARM 產生器幾何核對](arm-guard-mutation.json)均被抓到。故障 ARM 成品未保留或上傳。

## 本輪實機驗證

使用原生選單與完整按鍵脈衝設定，沒有在 USB dispatcher 直接呼叫 Apply。
每組均先核對輸出與 canvas，再觀察錄影從 0→1→0，讀取新首幀 DNG。

| 案例 | 有效輸出 | 完整記錄矩陣 | 實錄 | 證據 |
|---|---|---|---|---|
| M98，hbin 3／vbin 1，2.76:1 | 992×360 | 1008×370 | 12-bit／50p，A001_006 | [UI 幾何](../20261009-oncamera/ui-formula-v6-m98-bin3-ratio276.json)、[Apply](../20261009-oncamera/apply-v6-m98-bin3-ratio276.json)、[實錄](../20261009-oncamera/record-v6-m98-bin3-ratio276.json) |
| M98，1×1，Free | 1504×1006 | 1520×1016 | 12-bit／50p，A001_007 | [UI 幾何](../20261009-oncamera/ui-formula-v6-m98-free-half.json)、[Apply](../20261009-oncamera/apply-v6-m98-free-half.json)、[實錄](../20261009-oncamera/record-v6-m98-free-half.json) |

兩次 Apply 前後寬高、裁切、比例一致；使用同一個 Custom 列。
實機 UI 的 `Data rate` 此時選 23.98p，分別顯示 13、56 MB/s，是估算列選值；實錄標頭為 50p。
[原生畫面](../20261009-oncamera/screenshots/1585-v6-m98-free-half-applied.jpg)顯示 Free、1504×1006、1×1、Applied。
只驗證兩組短片的開始／停止及首幀標頭，尚未逐幀解碼整段、驗收畫質、長時間錄影或其餘模式的實錄。

## 先前凍結及連續讀回恢復

使用者確認凍結發生在本任務操作期間，並已實際重開。先前 `final_audit.py` 在第二份檔案釋放緩衝區時逾時；
`getfile` 覆寫共用 CODE 後，`callfn` 的程序內載入快取仍可能跳過重新載入，執行到另一份程式。
`callfn.py` 已改為每次呼叫先寫入並驗證自己的程式；[兩項離線回歸](shared-callfn-final.log)包含舊錯誤的突變重現。
本輪找到的公式錯誤是獨立離線重現，未據此宣稱已證明它們造成先前那次凍結。

實際重開後恢復待機；修正版重啟後遇到 macOS PTP 占用，核對實際 SIGMA interface owner，
只釋放該 PTP 程序並重建本任務 USB daemon。沒有重播不確定的錄影／Apply／寫入。
見 [恢復紀錄](../20261009-oncamera/v6-usb-fresh-owner.log)。

[最後稽核](../20261009-oncamera/v6-complete-audit.json)在同一程序連續完整讀回九份檔案，全部通過且最後仍待機：
AutoRun、Loader、50RESLAB、32RESCUS 與 S16／OG2K／OG3K／OG4K／OG35K。
沒有產生 LABnnn.RCD；Loader 與五份原有 RCD 均完全相同。
res-custom 的程式位元組完全相同，其正常保存的 96 B 設定區記錄目前選取的 VRC000；
校驗、原有啟用清單與選取值另外核對通過。早先直接比整份 32RESCUS 的稽核曾因這段正常保存而停止，沒有傳輸凍結。
[設定區核對回歸](audit-settings-tests.json)確認不會放過程式變更、壞校驗、啟用清單變更或錯誤選取名稱。

## 成品身分

普通卡與 debug 卡的兩份產品 BIN 相同，建置來源雜湊與目前來源一致，見 [成品證明](artifact-proof.json)。

| 檔案 | 長度 | 原始產品 SHA-256 |
|---|---:|---|
| 50RESLAB.BIN，RLAB version 5，常駐區塊 720,576 B | 452,448 B | `bf3719a9e86dbbd08c77925ac60123e8112ebf6cc3285479771eeee84c213fe5` |
| 32RESCUS.BIN，獨立 consumer | 73,344 B | `95247f2cff9094f78bd3a829293ad2bf6d5a849b73fdbd05c7b9182a0abca2cd` |

含已保存選取設定的實機 32RESCUS 全檔 SHA 為 `c1fbf1b3eee0bc345f7c90993d287041fd8a39d1e586e2b351c2354d85cf9eaf`；
設定區以外與原始產品逐位元組相同。50RESLAB 全檔實機讀回與原始產品相同。
成品：[普通卡](../../cards/20261009-virtual-rcd-v6/plain/)／[debug 卡](../../cards/20261009-virtual-rcd-v6/debug/)。
本輪保留原卡其他 Sup，沒有發布或 commit／push。Julien style 尚未接入，參數與虛擬配方仍只存在本次開機 RAM。
