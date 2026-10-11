# Sensor Lab：240 fps 主選單修補

2026-09-30。本輪只修改本機來源、建置與離線模擬，沒有操作相機、寫實體卡片、commit／push 或發布。
目前完成 Settings 主選單與待機文字的離線修補；實機操作、畫面渲染與設定生命週期尚未驗收。
QS 的 240 圖示／動畫仍不完整，不能把本輪結果稱為整套選單完成。

## 修正內容

舊實作只在收合摘要映射追加一列，且錯用 export enum 5；真正的選列輸入仍是九個可見值。
export 5 會進原廠 assert，internal 5 則是 59.94，兩者都不能當成 240。
現在補上 **row 9 → internal 8 → export 11 → 原廠 suffix `240` → `CUST240` → summary state 9**。

- 補齊選列輸入、排序／export、合法值、Settings／QS 值清單及 CUSTOM CinemaDNG 的格率限制。
  已初始化的原廠 BSS 合法值快取也能取得新表；不直接覆寫未宣告的 BSS 快取。
  非 CUSTOM 或 MOV 的清單與媒體限制仍走原廠路徑。
- Settings 借用空白圖示物件，補上第十個 literal `240` 文字子物件。
  原生可見性函式能選到新子物件 4458，不再因只有九個子物件而退回第九項。
- LV_CINE／LV_STILLlike 的 LARGE／MEDIUM 四個版面改用同頁數字字型與原生文字動畫。
  原前九個格率保留，狀態 9 顯示 `240`，隱藏 `15` 保留於狀態 10。
  每個 draw＋clip 的總長保持原大小，後續 record 與集合位址都不移動；只需 437 words／52 runs。
- 生成功能全部位於 BIN，使用既有 `build_autorun.py --loader`。
  本輪沒有修改 loader、stage2、entries 或 Fast 模板，也沒有放寬 MAXLEN。

詳細原廠地址、枚舉與機制見 [共用設計 §8.11](../../../open-gate/notes/IMX410_FULL_DESIGN.md)。

## 驗證

七組 Sensor Lab 回歸共 **180/180**，新增原生／摘要／LV 測試 **25/25**，合計 **205/205 通過**。
普通、debug、Fast 普通、Fast debug 四種精確成品各 **16/16 檢查通過**；另有四組 payload-only 比較通過。

| 範圍 | 結果與證據 |
|---|---|
| full／recipe／fmt／canvas | 58／14／16／10 項通過；[full](test_imx410_full.log)、[recipe](test_imx410_recipe.log)、[fmt](test_imx410_fmt.log)、[canvas](test_imx410_canvas.log) |
| plan／load／menu | 42／27／13 項通過；[plan](test_imx410_plan.log)、[load](test_imx410_load.log)、[menu](test_imx410_menu.log) |
| 原生格率路徑 | 4/4 通過，含 8 組突變與 11 個原字守衛，無跳過；[紀錄](native.log) |
| Settings 摘要 | 11/11 通過，含缺子物件等負向控制，無跳過；[紀錄](summary-ui.log) |
| 四種 LV 版面 | 10/10 通過，含四頁非零尾端 padding 控制、錯文字鍵控制，無跳過；[紀錄](lv-ui.log) |

原生函式測試執行選列轉換、排序、export suffix、合法值、媒體限制及摘要狀態。
UI 測試分別執行原生 visibility、NBU clip 解碼、字串池讀取、尾端 padding 跳讀、curve 選值、drawText setter 與 dirty callback。
原生 clip 解析所得的 11 個時間／字串指標直接送入原生 curve／setter；300 與 316 顯示 `240`，333 與 334 顯示 `15`。

完整卡片檢查從同一個 `fpSup.BIN` 解出安裝字，交給原生選單／摘要／LV 檢查，
再執行該成品的 picker，確認 AXIS 從 120 更新到 240、配方有效，以及 FrameRate 為 `240000/1001`（約 239.76）。
同時檢查 entry 的 r0／SP、D/I 次序、146 個執行期字的 journal、兩次關機還原、保留 cave 的暖映像、
CUSTOM 保存值、MOV guard、缺檔、RAW14 picker，以及移除 journal 宣告／SP 對齊的負向測試。
新增的原生指令與 NBU 修改都由 pass 1 區段記入 journal，並逐字比較關機還原結果。

### 模擬界線

- 真正執行 loader、stage2、entries、Sensor Lab restore／selector／picker 及上述原廠函式；不是只檢查 Python 預期值。
- worker 建立、檔案／配置／快取／OS、原廠 getter／部分 setter、UI 建構／物件查找／儲存等服務有明列替身。
  整頁解析只證邊界；另外的原生 clip reader 才驗證內部 key／pool 解碼與 padding。
- 沒有執行實際 renderer；不能證明 LCD 字型、位置、刷新、真實設定事件、儲存／重入、硬體格率或錄影。
  Fast 各卡會走本輪普通 loader 的精確 BIN 檢查；持久設定區命中及暖 loader-hook 流程沿用共用測試的既有證據，本輪未另重跑。

## Build 規範、產物與追溯

遵循 [SUP_BUILD_RULES](../../../../fpSup/SUP_BUILD_RULES.md)。
使用全新 [20260930-240-menu-r2](../../cards/20260930-240-menu-r2/) 目錄，未覆寫舊卡或 frozen release。
測試卡預設 **H2：12-bit、2016×672 光柵、RWZM 2048/1024、1008×672 輸出**。
一般 3032×2012 預設幾何不支援 240；本輪沒有自動縮小使用者的尺寸。

在 `projects/open-gate/build` 執行：

```sh
python3 -B test_sensor_lab_card.py --axis-preset H2 --out ../../res-lab/cards/20260930-240-menu-r2
```

成品矩陣與 payload-only 的 AutoRun 比較見 [verification.json](../../cards/20260930-240-menu-r2/verification.json)，
執行紀錄見 [card-r2.log](card-r2.log)。各卡的 `MANIFEST.json` 記錄實際來源、產物 SHA-256、區段、entry 及限制。
每次建置在準備 payload 前取來源雜湊，結束後再核對來源未變；沒有加入任何 runtime 配對檢查。

| 成品 | BIN 大小 | fpSup.BIN SHA-256 |
|---|---:|---|
| plain | 32,768 bytes | `dc6df61013ab7ebc3da1c19f8fe59d8dc3df66deb6054bdf19fc931e9afef663` |
| debug | 32,768 bytes | `0ebda984eba90047e0622db9d6867a01482b839bec45f4e10baafb1c0326ec9b` |
| fast-plain | 32,768 bytes | `34406124507e794c3cf66664046d64e3c01f940b16ce5fc2978b48eb75e86e4d` |
| fast-debug | 32,768 bytes | `b877d17413b4c1d4780e954283595f3c66e0a2adeaa0b631cd63e931a6b5821d` |

四組替代配方均只改 BIN、AutoRun 完全相同。普通／debug 的 AutoRun 也各自與前輪 preflight 逐位元組相同，
兩者的共用載入鏈來源雜湊與前輪一致；相同配置下部署本修補只須更新 BIN。
所有本輪來源及產物雜湊已重新核對；完整 AutoRun 雜湊與比較結果見 [artifact-audit.json](artifact-audit.json)。

普通與 debug 各自是獨立測試卡；Fast 仍是既有開發卡組合，使用持久設定區。
`*-alternate-axis` 只供配方更新的 AutoRun 比較，不是建議上機版本。

### 本輪失敗與修正

第一版 LV 重建搬動了大量後續位元組，造成 BIN 455,556 bytes，超過既有 61,440 bytes 上限；
共用 builder 正確拒絕，保留 [失敗紀錄](card-large-resource-failed.log) 與原失敗輸出目錄。
修正為局部等長修改，利用原生解析器支援的 clip 尾端跳讀，沒有放寬任何容量守衛或手改生成的 BIN。

來源差異相對於本輪開始前的七個檔案備份，另含七個新檔：
[changes.patch](changes.patch)、[source-changes.json](source-changes.json)。
共用載入鏈在工作區原本已有的修改維持原狀；本輪未把它們重做或回退。

## 上機前待確認範圍

目前沒有實機驗收通過的結論。依使用者「上機前要跟我講」與 Build §6，部署前另外確認。
建議使用本輪 `debug/`，固定 CinemaDNG／12-bit／CUSTOM／H2，先在 Settings 切換
119.88 → 240 → 119.88 並重入，檢查 popup、摘要、待機字樣和 AXIS／RECIPE。
先不錄影，另按 Build 規範完成約十輪開關機及跨卡暖開機。
QS、RAW14、錄影、SSD 高格率、時間碼／音訊與不同幾何回放不因本輪離線通過而視為完成。
