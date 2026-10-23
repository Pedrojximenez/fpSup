# M12 239.76p 虛擬表模式，2026-10-12

已製作獨立 **M12240** 配方及普通／debug 開發卡，沿用現有 RCD／Virtual RCD、
RES-CUSTOM consumer 與共用 Loader v3。**本輪僅離線建置及模擬，未寫實體卡、操作相機、commit、push 或發布。**

## 配方與成功經驗

- M12／p13、1008×672 RAW／992×662 有效輸出、CinemaDNG 12-bit。
- 最高選項為 239.76p；sensor TW0=`014A014A`、TW1=`0006038E`，与原廠 M12 相同。
  72 MHz ÷ (330×910) = 239.76023976 fps；engine float 為 `436FC29F`，nominal 240。
- 使用共用 FPS 列，DNG FrameRate 為 `240000/1001`。低格率各有自己的時序，未提供 279.72p。
  本配方不包含 sensor240／native30 的 capture-timing 映射。
- 幾何沿用 2026-09-29 H2 的 25 組實機讀回與原廠 p13 defaults，239.76p 全部 65 個 canvas words
  由獨立歷史資料核對。RWZM 與 preview 為 2048／1024。
- 歷史 A001_193 的 4,809 幀與約 20 秒音訊支持過去的 240p 成功經驗；其精確旧 BIN 未找回。
  後來 H2S240 重建版仍提早停止，因此不能以繼承幾何宣稱已恢復持續錄製。

## 最小程式修改

`m12_240.py` 為可重建的資料 producer；`build_v3_rescustom.py --formats m12-240`
納入相同 RCD 編碼／驗證與 UI 資源路徑。`build_m12_240.py` 呼叫現行
`build_v3_reslab.py --virtual-rcd --card`，加入該 RCD，不另寫 loader 或錄影引擎。

consumer v19 修正一個實際框架問題：舊版僅憑 M12／992×662／高格率就把任何配方
覆蓋為後期 p83／r10 畫布，且強制縮小批次。現在核對**所選 variant 的 base row 是 p83**，
才套用這兩個既有試驗；p13 保留自己宣告的畫布及原生 64 MiB writer descriptor。
判斷不依賴 M12240 名稱、檔名或 producer id。其餘原有 eligibility／header-copy guards 保留。

Res Lab producer v18 位元組不變。RCD wire v3、Virtual RCD ABI 2、consumer core 4、
entry ABI 與 shared loader 契約不變。普通／debug 的 AutoRun、LOADER、producer
与前輪相同配置 v18 成品逐位元相同；比較基準是離線 v18，並未核對目前實機安裝版本。
使用本模式需搭配本輪 consumer v19；RCD 單檔放到旧 consumer 可能再次被舊試驗覆蓋。

## 驗證

最終結果記於 `test-results.json`。保留初輪失敗與修正後日誌，不以失敗當通過。

| 檢查 | 證據 |
|---|---|
| 新模式六項：歷史資料、磁碟載入、真實 FrameRate 函式、原生 FPS 回呼、真實 UI installer、通用 Virtual RCD Apply、journal／還原與 ABI | `test-mode-final.log` |
| 既有 p83 的全 65 字高／低格率畫布、header copy、local bulk 與 mutation 回歸四項 | `test-p83-regression.log` |
| exact debug card 的開機、picker、全 canvas、FrameRate、journal 和關機還原一項 | `test-debug-boot.log` |
| 共用 entry／composer refs：14 builds、3 AutoRun 比較、8 catalogue refs | `test-entry-chain.log` |
| 普通／debug 每個 manifest、source identity、ZIP member bytes，以及 standalone 與卡片 RCD 一致 | `artifact-comparison.json`、`source-changes.json`、`packages.json` |

新增負向檢查直接使用 exact frozen v18 consumer，SHA-256
`394c49780cf25a2086e599274e3b2a9162e8dd189b265ca1efcae43fadd45592`：
相同 p13 RCD 被改為 `canvas+88=4`；獨立歷史值為 0。正常 v19 完整 65 字相同，
p83 原有高格率行為也逐字保持。这是可重現的資料覆蓋缺陷，並非提前停止的根因證明。

初輪兩項失敗為 fixture 問題：parser 回傳空 `capture_timing` 清單，不是省略 key；
兩個原生 UI callback body 尚未宣告為 fixture 邊界。聚焦新 UI 檢查另先用了錯誤的
bit CSV 順序；原生列表是 8／10／12，12-bit-only 應只啟用最後一項。
三者皆只修正測試，未更改候選產品。意外被 unittest 掃到的四個既有 FrameRate 檢查亦通過，
正式六項套件已移除重複發現。沙盒內 Unicorn 無法配置執行記憶體，模擬經自動審查允許後
在沙盒外執行；沒有 USB／相機操作。

原生 FrameRate、ISP translator／predicate、CRCT selector、UI installer、loader、consumer
有實際 ARM 執行；設定 getters、UI 物件、OS／媒體邊界由 fixture 提供。
未模擬真實 sensor／DMA／FIFO 排程、SSD scatter、媒體持續速度或錄影畫面。

## 成品、使用與重建

- `../../cards/20261012-m12-240/M12240-plain.zip`：普通卡。
- `../../cards/20261012-m12-240/M12240-debug.zip`：包含既有 USB shell 的 debug 卡。
- `../../cards/20261012-m12-240/standalone/`：獨立 consumer／RCD 建置；本輪未另做 standalone ARM 開機模擬。

在 RES-CUSTOM → More Settings 啟用 `M12240.RCD`，重開後於 Resolution 選 M12240，
CinemaDNG 選 12-bit、Frame Rate 選 239.76p。磁碟列表與動態列仍由共用 consumer 管理。
記憶體 producer 可使用同一份資料經共同 REGISTER／APPLY，不需新增錄影入口。

| 普通／debug 共用檔案 | 大小 | SHA-256 |
|---|---:|---|
| M12240.RCD | 7,136 B | `971fe0f3c78966f2f8ca8c4246260612ff2852a9481eedfcf6d48b35a674490e` |
| 32RESCUS.BIN | 187,520 B | `0cb978b7f1568b3d39de4c6b465a548c442912e0962da1d9d8cb6b1304c87dc8` |
| Res Lab producer | 609,720 B | `19491eb0b4a8798ddf145cf73c2704558f1caee82d07dfd8f74da384a4138d00` |

從完整專案根目錄重建，輸出必須是新目錄：

```sh
python3 -B projects/open-gate/build/build_m12_240.py --out NEW_DIRECTORY
python3 -B projects/open-gate/build/build_m12_240.py --debug --out ANOTHER_NEW_DIRECTORY
python3 -B projects/open-gate/build/res-custom/build_v3_rescustom.py --formats m12-240 --out STANDALONE_NEW_DIRECTORY
VIRTUAL_RCD_CARD=/absolute/path/to/card PYTHONPATH=projects/open-gate/build:projects/open-gate/build/res-custom python3 -B -m unittest -v test_m12_240.M12Tests
```

完整來源快照與差異在 `source-before/`、`source-after/`、`changes.patch`。
持續 240p、完整 RAW 序列、實際 exposure cadence、預覽／FOV、反覆啟停和硬體暖開機仍待驗收。
