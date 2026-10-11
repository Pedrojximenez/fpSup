# Res Lab（原 Sensor Lab）— 開發狀態

## 2026-10-12：可用位深由 RCD 宣告（離線版本）

RCD／producer 自己宣告允許的 8／10／12-bit；RES-Custom 只驗證、套用，
不再讓原生 SD／SSD 分類覆蓋已宣告的位深與實際格率項目。
新增 RCD section 13，required mask 1–7、MINCORE 4；wire v3、Virtual RCD ABI 2 保持原樣。
五份磁碟配方及 Res Lab 輸出各自宣告三種位深；未宣告的舊 RCD 保留原生限制。
consumer／producer payload v18 已完成離線建置，尚未寫卡或上機。
分工與相容性見 [RCD 契約](../open-gate/build/res-custom/VIRTUAL_RCD.md)，
成品、位深／選單／開機驗證見 [本輪紀錄](validation/20261012-rcd-bitdepth/RESULTS.md)。

## 2026-10-11：RES-CUSTOM 名額與重開提醒

最新 [v38 普通卡](cards/20261011-count-v38/plain/)與
[v38 debug 卡](cards/20261011-count-v38/debug/)已寫入相機；consumer header9、producer header17。
標題顯示 `RES-CUSTOM (已用/上限)`；成功啟用／停用後立即顯示 `Restart to apply`。
名額即時反映已保存的清單，解析度與 QS 在重開機後更新；RES-Lab 編輯仍即時套用。
實機 0/5 → 1/5 → 0/5、確認 popup 提示及完整讀回通過，已恢復本輪原先全部停用清單。

目前 virtual-capable 版固定留一格給共用動態列，磁碟五格；卸載 RES-Lab 不會自動歸還。
獨立 consumer 沒有動態列時為六格。本輪 producer、loader、AutoRun 與 v37／v35 相同。
範圍、成品與離線／實機證據見 [v38 紀錄](validation/20261011-count-v38/RESULTS.md)。

## 2026-10-10：RES-CUSTOM 使用 SupManager 列表版型

新成品為 [v37 普通卡](cards/20261010-files-v37/plain/)與
[v37 debug 卡](cards/20261010-files-v37/debug/)，consumer header v8。
RES-CUSTOM 的 More Settings 沿用 SupManager 的原生元件、標題、格線與字型：
上方數字分頁，每頁五個 RCD，檔名與 Enabled／Disabled 同列顯示，
按 OK／右鍵開啟 Enable／Disable，OK 確認。分頁列左右換頁。
底列顯示名額與重開提醒；滿額／寫入失敗／錄影中仍有原有保護。

producer／RES-Lab、loader、AutoRun 成品與 v35 完全相同。
頁面資料與變數仍由 consumer 擁有，RES-Lab 不管理檔案啟用。
離線與實機證據見 [列表改版紀錄](validation/20261010-files-v36/RESULTS.md)。

## 2026-10-10：RES-CUSTOM 管理儲存檔案

本輪開發成品為 [v35 普通卡](cards/20261010-save-v35/plain/)與
[v35 debug 卡](cards/20261010-save-v35/debug/)；RES-Lab header v17、RES-CUSTOM header v7。

- 完成編輯即套用記憶體配方，解析度／QS 的動態列顯示 **RES-Lab**；無須 SAVE。
  穩定內部身分仍為 `VRC000`，舊設定與共用 Virtual RCD ABI 2 保持相容。
- RES-Lab 的 SAVE 仍只有名稱與存檔；不管理啟用清單，也不改動調整好的 Mode。
- 從 **RES-Custom → More Settings** 開啟獨立 RCD 管理頁，以左右鍵選檔，
  在 RCD 列按 OK，或在 Enabled 列按 OK／右鍵啟用或停用，顯示已用名額；開啟時重新掃描已存的有效 RCD。
  重新開機後，啟用檔案加入解析度及 QS。管理清單不改動本次使用的虛擬配方。
- Virtual RCD 保留一格，另有五個檔案名額；滿額顯示 `List full: disable one`。
  獨立 RES-CUSTOM 沒有虛擬列時有六格，全部停用仍可開管理頁重新啟用。
  啟用記錄沿用 RCS1，寫完完整讀回核對；錄影中拒絕修改。
- 兩個 Sup 各有自己的設定頁與焦點狀態；共用 loader、AutoRun 與錄影公式維持原樣。

建置、離線驗證與上機範圍見 [本輪紀錄](validation/20261010-saved-rows-v29/RESULTS.md)。
v35 已寫入相機；實際儲存 A9 992×662、切換啟用清單、重開載入、原生選取與 QS 圖示皆通過。
已恢復原先五份檔案啟用，測試檔 A9 保留為停用。

## 2026-10-10：Mode 頂列與命名 SAVE

本輪成品為 [v25 普通卡](cards/20261010-save-v25/plain/)與
[v25 debug 卡](cards/20261010-save-v25/debug/)；Res Lab header v16。
res-custom、Loader 與 AutoRun 沿用上一版的相同位元組。

- Mode 移到右側獨立頂列，與 sensor 框分開；省略固定的 `Sensor 6064x4042`。
  左側格線保留，右側所有框仍共用像素尺度、中心和兩段角點虛線。
  示意區文字保持透明，依使用者要求移除會遮擋框線的文字底板。
- SAVE 只提供檔名編輯與 Save RCD。右上 Mode 為唯讀文字，無切換控制；
  編輯名稱、儲存不重新調整 Mode、裁切、binning、輸出或活動 Virtual RCD。
- 檔名為 1–7 個 `A–Z`／`0–9`，左右選位置，上下改字，OK／MENU 結束編輯。
  空白位置略過；全部留空時自動選 `LAB001.RCD`、`LAB002.RCD` 等未使用名稱。
  同名比對不分大小寫，已存在時顯示 `Name exists`，不覆寫；`VRC000` 保留給虛擬列。
  RCD 內的標籤、三種名稱圖示與檔名同步；res-custom 下次開機讀取。
- 放寬篩選時，先更新原生 Mode 選單上限，再公布原模式的新索引，避免被舊上限截斷。

驗證證據見 [本輪紀錄](validation/20261010-save-v24/RESULTS.md)。

## 2026-10-10：大字側欄、Mode 圖內切換與資料率

本輪成品為 [v23 普通卡](cards/20261010-controls-v23/plain/)與
[v23 debug 卡](cards/20261010-controls-v23/debug/)；Res Lab header v15、res-custom header v6。
兩者仍是不同 Sup，沿用同一個 Virtual RCD 服務。

- 左側採單行大字、保留 81 px 格線；右側 sensor 示意獨立右移，清除背後的選單格線。
  Mode 名稱置於圖內；從 Bit 往上移動焦點後，左右箭頭切換 Mode。
- FILTER 提供 12／14bit、全部取景範圍、寬度 K 級距、FPS 及畫質／FPS／RS 排序。
  K 級距以寬度判定：3K+ 從 2850、4K+ 從 3800、6K 從 5700 像素起。
- OUTPUT 為 Crop、binning、Desq、Output、MB/s 五列。裁切鎖定維持 Mode 原始取樣比例；
  輸出提供鎖定／自由，有非等向縮減時才提供 `a` 自動還原。
  Desq 常用倍率獨立套用；數字編輯結束後自動套用。
- 圖內 `Area`／`Keep` 依使用者指定改為 `Mode Corp`／`Output Corp`。
  所有圖框共用中心與像素尺度，兩段變形保留角點虛線。
- MB/s 最下一列以左右鍵查看 23.98、24、25、29.97、48、50、59.94、100、119.88、239.76、279.72 fps。
  使用實際 RAW 矩陣（包含邊界）× 位元深度 × FPS ÷ 8，以十進位 MB/s 四捨五入；
  這是未壓縮像素估算，不是媒體測速或 FPS 支援判定。查看估算不更改錄影 FPS，也不觸發套用。
- Binning 的六種係數與 std／soft 經共用 RCD 可選 section 11 傳遞；
  SAVE 使用同一配方，res-custom 可直接讀取。舊 RCD 仍相容。

本輪驗證與限制見 [測試紀錄](validation/20261010-controls-v17/RESULTS.md)。
以下為較早版本的歷史紀錄。

## 2026-10-10：側欄、自動套用與 SAVE

正式計算頁採用已選定的側欄配置，使用原生三分頁 **FILTER／OUTPUT／SAVE**。
FILTER 同頁篩選與切換 Mode；OUTPUT 同頁調整裁切、輸出與 binning。
右側以共同中心及像素尺度疊合完整 sensor、sensor 取景、Mode 原始輸出、二次裁切與最終輸出；
兩段變形以四組對應角點的點狀虛線連接，資料放在框內空白處。

- 移除 Apply 按鈕。Mode／選項變更自動套用；數字編輯時即時更新圖框，OK／MENU 結束該欄位編輯後自動套用。
  單純切欄位、切分頁或重複相同有效幾何不重新初始化 live view。錄影中仍由共用 consumer 拒絕切換，保留舊配方並顯示狀態。
- 裁切數字表示**保留的像素**，可自由裁切或維持 Mode 形狀；比例鎖定在原始像素座標計算，避免 M12 重複還原。
- Mode 還原只在水平／垂直縮減不同時顯示；一般 Mode 不顯示這列。
  變形鏡頭獨立開關，各 Mode 都可使用；開啟才顯示 1.01–4.00× 倍率。
  選自訂寬高時關閉自動鏡頭還原；開啟鏡頭還原時回到連動輸出。
- SAVE 的 **Save RCD** 匯出 `fpSup/RESCUS/LABnnn.RCD`，跳過既有檔名，寫完重新讀回完整長度與內容。
  仍為 res-custom 的 RCD1 v3，包含相同幾何、時序和尺寸圖示；虛擬套用與存檔使用同一個編碼器。
  儲存不切換正在使用的虛擬配方。檔案由 res-custom 在下次開機載入。

Sup 仍然分開：`50RESLAB.BIN` 為 producer／UI，`32RESCUS.BIN` 為 consumer。
上機排查已修正原生容器位移造成的側欄／圖框超界、狀態文字被背景遮住、
SAVE 成功訊息只顯示前綴，以及第六份儲存檔占滿列後讓 Virtual RCD consumer 無法載入。
consumer v5 先保留虛擬列，搭配虛擬工具時同時載入 5 份檔案＋1 個虛擬列；獨立模式仍支援 6 份檔案。
M12 首秒切屏修正沿用 v12 的等向預覽；loader 與 AutoRun 不需更新。
最新成品為 [v16 普通卡](cards/20261010-sidebar-v16/plain/)與
[v16 debug 卡](cards/20261010-sidebar-v16/debug/)，已寫入相機並核對載入版本。
實機側欄、自動套用、裁切／輸出數字編輯、條件欄位、SAVE 與儲存檔直接選用已通過；
詳見 [上機排查紀錄](validation/20261010-sidebar-v13/ON_CAMERA.md)。
M12／29.97p 短片完成 88／88 幀並正常按鍵停止；本次取景接近全黑，
首秒切屏的可見景物複驗仍待補做，不能以此短片宣稱畫質通過。
36 項整合／預覽回歸通過，最後一版原生頁面與還原 5 項通過；
[原始側欄離線驗證](validation/20261010-sidebar-v13/RESULTS.md)另保留
70 個 Mode 的 142,800 組公式與 1,750 組實際 ARM 幾何結果。
既有 consumer 的 32 個不同圖示 pack／4 MiB 上限仍適用；達上限會保留舊配方並顯示 Memory full。

以下為先前版本的歷史流程與驗證。

## 2026-10-09：Virtual RCD 直接套用

Res Lab 與 res-custom 是兩個獨立 Sup。從 SupManager 的 **RESLAB → Enable → 右鍵 More Settings** 開啟 Res Lab，
使用 FILTER／MODES／OUTPUT 設定模式、裁切、比例、寬高與 hbin／vbin，
再在 OUTPUT 的 **Apply** 按 Right 或 OK。配方在記憶體中產生，不需要匯出 `.RCD`。
成功顯示 `Applied`，res-custom 的同一個 **Custom** 列使用新幾何與虛擬表；MENU 返回 SupManager。

`50RESLAB.BIN` 只負責計算與自己的設定頁，`32RESCUS.BIN` 負責驗證、套用與錄影。
Res Lab 沒有第二套錄影引擎。其他工具可使用同一個
[Virtual RCD 契約](../open-gate/build/res-custom/VIRTUAL_RCD.md)，註冊工具不增加解析度列；Julien style 尚未接入。
目前 FPS 不支援、正在錄影、Custom 列未就緒或資料不合法時，Apply 拒絕並保留原配方。
consumer 支援 CinemaDNG 8／10／12-bit；RAW14 可以計算，尚不能套用。

參數與配方目前只存在本次開機的記憶體，關機後須重新設定／Apply。
各工具以自己的 Sup 由既有 SupManager 管理；Res Lab 參數保存及普通解析度啟用清單的前端仍待後續工作。
目前容量為 16 個已註冊工具，每次開機最多 32 份不同圖示 pack／合計 4 MiB；相同輸出重用圖示。
容量可擴充，沒有 Res Lab／Julien 兩套固定套用接口。

最新成品：[普通卡](cards/20261009-virtual-rcd-v9/plain/)與 [debug 卡](cards/20261009-virtual-rcd-v9/debug/)。
兩者的產品 BIN 相同，包含現行共用管理頁與 Loader service v4；實機原有管理程式及其他 Sup 保留。
上機過程已修正設定頁返回焦點、連續解析度列的 Help guard，以及 Apply 按鈕值與命令碼的共用問題。
[上機測試紀錄](validation/20261009-oncamera/RESULTS.md)保留每次成品讀回、UI 狀態與新錄影 DNG 的證據。
最新 [公式排查與修正](validation/20261009-formula-audit/RESULTS.md)修正固定比例超界、裁切零尺寸、預覽對齊、
縮放範圍及資料率估算。70 模式的 142,800 組公式、8,400 組資料率、1,750 組 ARM 幾何與
62 個支援模式的完整 ARM Apply 通過；[逐模式表](validation/20261009-formula-audit/MODE_MATRIX.md)保留每項結果。
最新 24 項整合回歸也通過。M98／hbin 3／2.76:1 與 M98 Free 1504×1006 的兩組修正案例，
在相機完成 12-bit／50p 短片實錄與首幀 DNG 核對。
host 連續讀回的共用程式快取錯誤已修正，實際重開後恢復、最後九份卡片檔案稽核與待機核對均完成。
後續 [FPS 列與反灰修正](validation/20261009-high-fps/RESULTS.md)修正共用 FPS installer 超過返回 slot 容量、
高 FPS 畫布被萬用項遮住，以及活動 Virtual RCD 沿用原廠 FHD／媒體上限的問題。
M12 的 239.76／279.72 已在原生選單成功選取，實機引擎與配置時序跟隨；切回普通 FHD 恢復原廠反灰。
65 項 consumer 回歸與真實 ARM UI installer 整合案例通過。240 的新片段仍寫原廠 119.88 DNG 標記，
且錄影很快結束，未完成可控持續啟停；240／280 的完整錄影驗收尚未完成。
離線掃描不代表所有模式、格率與完整畫質已完成實機驗收；先前 v5 的兩種尺寸 12-bit／29.97p 實錄仍保留在原紀錄。
錄影首秒切屏修正版：[v12 普通卡](cards/20261010-virtual-rcd-v12/plain/)與 [v12 debug 卡](cards/20261010-virtual-rcd-v12/debug/)。
v11 使用者截圖 SS__1616／1618 證實首秒底部錯位，對應歷史 r77 的同一個問題。
v12 恢復無 binning 的等向預覽；直接執行凍結 r78 成品，確認 M12 的 29 個公式欄位、
待機範圍及感測器時序一致。另修正不等向 binned preview 縮到上限時的比例計算。
離線邊界／ARM／選單回歸通過，v12 已寫入相機；2026-10-10 使用者確認 M12 AUTO／29.97p
的首秒切屏「正常了」。一次 90 幀短片正常按鍵停止，起始截圖及首中末 RAW 核對通過。
詳見 [錄影預覽排查](validation/20261009-recording-formula/RESULTS.md)。SSD 驗收尚未開始。
240／280 的提前停止與高格率 DNG 標記仍是獨立未完成項目。
[早期 v1 離線紀錄](validation/20261009-virtual-rcd-v1/RESULTS.md)僅代表當時版本，已由後續上機修正取代。

從專案根目錄建到全新目錄：

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --no-shell --out /tmp/reslab-vrc-plain-new
python3 -B projects/open-gate/build/build_v3_reslab.py --virtual-rcd --card --out /tmp/reslab-vrc-debug-new
```

省略 `--virtual-rcd` 保留下面的獨立計算／Save RCD 流程。

## 2026-10-09：純計算與 RCD 匯出（保留的獨立版本）

[`build_v3_reslab.py`](../open-gate/build/build_v3_reslab.py) 已拔除 res-lab
的錄影核心。`50RESLAB.BIN`（FSB1、id `RLAB`、version 2、最低服務版本 3）只保留
FILTER／MODES／OUTPUT 計算介面、私有狀態與檔案匯出；不安裝 recording picker、
resolution setter、感測器暫存器、時序或 profile table 補丁。
兩個共用 CHAIN hook 負責私有頁面的 GUI id 與首次頁面註冊；關機還原由 loader v3 管理。

操作流程：在 CINE 錄影設定頁按右側 Help 鍵開啟 res-lab，選讀出模式、裁切、
比例、寬高與 hbin／vbin，再到 OUTPUT 的 **Save RCD** 列按 Right 或 OK。
檔案自動命名為 `fpSup/RESCUS/LAB001.RCD`、`LAB002.RCD`……，跳過既有檔名，
寫入後重新開檔核對完整長度與每個位元組，成功顯示 `Saved LABnnn.RCD`。
儲存位於可到達的 OUTPUT 頁，沒有使用舊版尚不可到達的第四分頁。

輸出是 res-custom 的 **RCD1 v3**：stock donor 與格率上限、29 個錄影畫布欄位、
回放與待機幾何、高格率旗標，以及隨尺寸產生的 Quick Set／Settings／數字 XCI 圖示。
標頭常數直接由 res-custom 的 `ogc_layout.py` 產生。
把 `.RCD` 放進 res-custom 卡的 `fpSup/RESCUS/`，下次開機由 `32RESCUS.BIN` 載入；
實際套用與錄影由 res-custom 負責。res-custom 現行最多檢查 16 份資料、同時啟用 6 個格式，
請依其啟用清單管理格式。此輪驗證的是匯出後交給 res-custom 的流程，未驗證兩套選單同卡顯示。

14-bit 模式可以計算，但現行 res-custom 的錄影格式支援 8／10／12-bit，
因此 RAW14 匯出會顯示 `14-bit unsupported`。Binning 計算保留原生 CRCT 的 1／3；
舊錄影核心專用的 kernel／soft／std 控制不再提供。輸出尺寸須寬度 16 對齊、高度偶數，
並能容納於所選讀出模式的記錄矩陣。

成品：[普通卡](cards/20261009-calculator-v3/plain/)與
[debug 卡](cards/20261009-calculator-v3/debug/)。兩份產品同為 **444,480 B**，
常駐配置 **712,576 B**（包含匯出與讀回緩衝）。
[離線驗證紀錄](validation/20261009-calculator-v3/RESULTS.md)記錄實際 ARM、
原廠頁面解析、原生儲存回呼、res-custom 載入、還原與突變驗證。
未操作相機或寫實體卡；實際 LCD 顯示、SD 寫入時機與錄影仍待實機驗證。

從專案根目錄建到全新目錄：

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --card --no-shell --out /tmp/reslab-calc-plain-new
python3 -B projects/open-gate/build/build_v3_reslab.py --card --out /tmp/reslab-calc-debug-new
```

以下保留舊版錄影核心的歷史紀錄；其功能、測試數字與建置參數不代表現行純計算版本。

## 2026-10-08：loader_v3 遷移驗證（歷史錄影核心版）

當時開發建置使用 [`build_v3_reslab.py`](../open-gate/build/build_v3_reslab.py)，
輸出 `fpSup/50RESLAB.BIN`（FSB1、id `RLAB`、最低服務版本 3）。核心、變數與
SLMP 選單都放在同一個常駐區塊；143 筆 PC 相對改寫保留舊佈局內的距離，
297 筆 claim 保護核心、後期 UI hook、值補丁與執行期時序字。原來的 cave
座標只作建置計算，實際程式與變數不寫入該範圍。關機由 v3 loader 的 journal 還原。

本次補上 v3 選單的長度檢查：完整 SLMP 恰好填滿區塊時允許安裝；超長或不足
標頭的宣告在讀取欄位前拒絕。之前整卡測試以安裝器替身處理，未抓到恰好填滿
會被當成截斷讀檔的問題。現在直接執行產出的 ARM 安裝器與真實 recording picker。
建置器也改用現行共用 loader／AutoRun／UI 動畫，並可從專案根目錄執行。

成品：[普通卡](cards/20261008-loader-v3/plain/)與
[debug 卡](cards/20261008-loader-v3/debug/)；兩者的 `50RESLAB.BIN` 同為
468,048 B，常駐區塊 469,824 B，journal 21,508 B。
[驗證紀錄](validation/20261008-loader-v3/RESULTS.md)包含精確檔案雜湊、
21 項普通卡測試、4 項 debug 檢查、69 項選單回歸、兩張卡的完整映像寫入覆蓋檢查及三個 mutation。
沒有測試被跳過。**這是離線遷移驗證，尚未上機或寫實體卡。**

從專案根目錄建到全新目錄：

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --card --no-shell --out /tmp/reslab-v3-plain-new
python3 -B projects/open-gate/build/build_v3_reslab.py --card --out /tmp/reslab-v3-debug-new
```

第一次由舊架構切換需要更新 AutoRun 並改用 `fpSup/LOADER.BIN` 與
`fpSup/50RESLAB.BIN`；不再把產品附加到根目錄的 `fpSup.BIN`。
之後相容的 res-lab 更新只更換 `50RESLAB.BIN`，不綁 AutoRun 版號。
debug 卡另含 `00SHELL.BIN`，普通卡不含診斷 shell。
仍維持獨立 res-lab 核心；其他解析度產品佔用互斥位置時拒載。
Fast Start、實際 UI、感測器、RAW14、錄影及暖開機驗收仍需分別驗證。

## 2026-10-04：RAW14 全模式研究

Sensor Lab 的 RAW14 目標涵蓋原廠全部八個 RAW14 模式及可求解的輸出軸，不限於外部專案使用的 M100。[r86 測試卡](cards/20261004-b25-menu-r86-raw14-save/debug/)逐一檢查八個模式；r86 可選格率讓六個模式有 20 組合法配方。現行來源另已加入全高 M0／M141 的私有 18p 選值、picker 橋接與錄影前核對；MODE 清單仍只受 FILTER FPS 篩選，不受使用者當前錄影 FPS 影響。預設安全版會阻擋 18p 錄影，另有明確開關的短片診斷版；兩份 [safety 成品](validation/20261004-raw14/18p-bridge-report.md)及[四配置矩陣](validation/20261004-raw14/18p-bridge-safety-matrix/verification.json)均通過離線驗證。診斷版已寫入 fpSup2，但尚未重新開機或實錄；veto 版仍僅離線。時間碼與音訊仍待實錄核對。舊 reviewed 目錄僅保留作離線迭代歷史。

M0 已能與 AUTO 分開明確選取。r86 新增關機存檔時的 RAW14→RAW12 記錄正規化，離線成品測試通過。使用者回報上次修正後已實機測試，按 REC 不再立即凍結；本輪沒有該次測試模式或片段的獨立資料，因此不推論 RAW14 錄影或正常關機已驗證。四個靜照型接收器模式的黑位與增益也需實錄檢查。詳見 [RAW14 核對紀錄](validation/20261004-raw14/RESULTS.md)。fpSup2 的診斷安全版 BIN SHA-256 為 `8d00088d1db0c4246279c140ca0865579b18930848accaf745fcd7151174884d`，MANIFEST SHA-256 為 `297b717f36572165f859a090be3ed71179ad5233aad186d8ab5338fb6b01a5b6`，皆已逐檔讀回核對；AutoRun 及五個 FPSUPUI 檔案保持相符。原 r86 三個根目錄檔案保存於[寫卡備份](../../archive/fpSup2-20261004-pre-18p-safety/write_report.json)。

## 2026-10-04 更新：r81 錄影凍結與 cave 搬遷

Sensor Lab 已有局部實機驗證：r68–r79 的面板控制、數種 12-bit 錄影、
預覽比例和 Crop 操作見
[設計與實機紀錄](../open-gate/notes/IMX410_FULL_DESIGN.md)。
既有 r80 紀錄中的一次 USB 部署在暫存階段中止；使用者此次回報較早的
r80 固定位址版按錄影沒有立即凍結，需與這次的實際卡片和設定分開追溯。
這仍是測試產品，未完成驗收。

MODE 清單的規則是只由 FILTER 的 Frame rate 控制格率篩選；使用者的錄影
FPS 設定不應縮減 MODE 名單。r81 寫卡成品尚未包含這項更正；r83 候選卡
已通過離線驗證。選取 mode 後，錄影設定中的 Frame rate 仍應依
該 mode 的能力反灰。修正後的選單行為尚待實機驗證。

**歷史 r80 成品有已確認的安全阻礙：**其最終 `fpSup.BIN` 的五個區段進入
`0xC0732A40..0xC0732C84`，覆蓋原廠非零資料。此範圍不由共用 stage2
的關機 journal 還原；舊卡的固定 cave 佈局也不符合目前的
`CAVE_BUMP`／veneer 規則。這些舊卡仍不可作為新一輪驗收或發布的依據。

新建卡路徑已把核心程式與資料整理為 **9,040 B 的核心封裝**（B2_5
配置），連同 652 B journal guard（合計 **9,692 B**）複製到 USER 常駐區；
125 筆位址重定位後，19 個核心 hook 與 10 個後期 UI hook 只在
`CAVE_BUMP` 配置短 veneer；連同 6 個外部指標字，共有 35 個受保護的
原廠字位置。最終 BIN 不含 Sensor Lab 的固定位址 cave 區段。共用 stage2 在 journal
配置或普通／強制關機 callback 註冊失敗時會停止放置區段；常駐程式在武裝
hook 前另核對兩張清單與對應原廠字。最終八組配置（四種模式及各自的替代
AXIS 配方）均通過離線建置；普通／debug／Fast 普通／Fast debug 的 VBIN
分別為 **54,712／57,240／55,344／57,920 B**，均低於選單區塊起點
`0xF000`。

[搬遷後成品模擬](../open-gate/build/test_res_lab_migrated_boot.py)已執行
loader、兩個入口、USER 搬遷、hook／UI 安裝與關機回呼；普通版 **290 筆**、
debug 版 **297 筆**非 cave journal 記錄還原，`0xC0730000..0xC0735000`
的 **20,480 B 原廠資料保持原樣**。已保存的
[r81 debug 非 Fast 測試卡](cards/20261004-b25-menu-r81-user-relocated/debug/)
含 USB shell，通過當時的最終成品檢查及 15 種損壞成品測試；現因錄影
picker 錯讀與實機凍結，**僅保留作問題追溯，不應再作錄影驗收**。
這是獨立 Sensor Lab 卡，並非多產品合併卡。上述模擬結果均屬離線驗證。
2026-10-04 已寫入 fpSup2 並讀回核對兩個啟動檔；
[寫入紀錄](cards/20261004-b25-menu-r81-user-relocated/debug/SD_WRITE_20261004.txt)
保留重掛載後舊檔的備份位置與雜湊。

**r81 實機回報：按下錄影立即凍結。**使用者表示 r80 固定位址版沒有這項
立即凍結；這不能消除 r80 覆寫原廠資料的既有風險。對已寫卡的 r81
`fpSup.BIN` 逐位元組追查發現：`imx410_fmt` 的錄影 picker 仍使用搬遷前
`PROFILE_ID - RECIPE = 0x1AC` 的距離；USER 封裝後實際距離是 `0x1A4`，
因而把 `COLTAB+4` 的第二個指標 `0xC0BE3FA4` 當作應為 **87** 的 profile ID 寫入
`ENTRY`。這是具體的錄影路徑錯值，與立即凍結相符；當時修正後的實機結果
尚待重測。來源已改成經重定位直接讀 `PROFILE_ID`，並將後期 UI 的
`sl_excl_9` 程式槽位移開 8 B。新的
[r83 debug 非 Fast 候選卡](cards/20261004-b25-menu-r83-picker-reloc/debug/)
已通過八組建置矩陣、最終成品檢查、15 種損壞成品測試及整卡模擬；
直接執行封裝後 picker 時，r81 把 `0xC0BE3FA4` 寫到 `ENTRY+4`，
r83 則正確寫入 **87**。2026-10-04 再次讀卡時，fpSup2 上的 AutoRun、BIN、
MANIFEST 雜湊已與保存的 r83 精確相符。卡上亦有九段、共 699 幀的 12-bit
CinemaDNG；只憑檔案無法確定拍攝時的常駐韌體，或證明先前的立即凍結已
修復。詳見 [本次唯讀卡片稽核](validation/20261004-raw14/card-read-20261004.json)。
詳見 [錄影凍結定位紀錄](../open-gate/notes/CAVE_COMPLIANCE.md#7-r81-錄影立即凍結的定位與修正)。

B2_5 頁面 parser 在當時的整卡模擬中以成功回傳替身處理；該次離線測試未驗證感測器、
修正後錄影、實際 UI、開關機與 SD 卡上的行為。後續使用者已回報修正後按 REC 不再立即凍結，
但本輪沒有該次測試模式或片段的獨立資料。`1478` 顯示異常的原因
也未確認，不能因 cave 覆寫已修正就宣稱它已解決。細節見
[cave 合規調查](../open-gate/notes/CAVE_COMPLIANCE.md)。

以下內容是 **2026-09-30 的歷史收尾紀錄**，包含舊建卡命令、測試數字
和未完成項目，不代表新 USER 配置成品或 r80 的驗收狀態。現行限制以本節、
設計紀錄末尾與成品檢查結果為準。

---

# 2026-09-30 歷史紀錄：上機前收尾

更新：2026-09-30。**目前是可供下一輪驗收的測試產品，尚未完成產品驗收。**
這一輪只修改本機來源、建置與模擬；沒有連相機、寫實體卡片或發布。
使用者要求上機前先說明。本次上機範圍尚未確認。

Sensor Lab 的現行實作是 Custom Sensor 七軸引擎，沿用
[`../open-gate/build/imx410_plan.py`](../open-gate/build/imx410_plan.py)；
不搬動原本的程式，也不另複製載入器。
完整機制與實機歷史見 [IMX410_FULL_DESIGN](../open-gate/notes/IMX410_FULL_DESIGN.md)。

## 240 fps 主選單修補（本輪優先）

已補齊主選單第十列的原生轉換、CUSTOM CinemaDNG 下的媒體限制、收合摘要，
以及四種待機版面的格率文字。原本把 export 5 當成新格率，會進原廠 assert；
現行路徑是 row 9 → internal 8 → export 11 → `CUST240`。已初始化的原廠值表快取也已處理。
59.94、119.88 與離開 CUSTOM 後的原廠限制保留；15 fps 的隱藏狀態另保留。

最新驗證見 [240 修補紀錄](validation/20260930-240-menu/RESULTS.md)。
本輪測試卡使用 **H2：12-bit、2016×672 光柵、RWZM 2048/1024、1008×672 輸出**，
讓 240 有合法配方。一般 3032×2012 預設尺寸不支援 240；本次沒有新增自動改尺寸的行為。
**QS 的 240 圖示與動畫仍未補齊；本輪驗收入口是 Settings 主選單。**
實際 LCD 字體／位置、選單生命週期及開關機仍須上機確認，不能以離線解析冒充實機通過。

## 先前收尾完成

- 原生位深選單同步到 AXIS 後才重算配方；12/14-bit 共用 TAB3 時，14-bit 的鎖存值改為正確的 enum 1。只讀三個已核對原廠呼叫點的設定，其他呼叫不解參考未知 r6。
- 主機選單納入可求解的 RAW14 與第十列 240，統一正消隱預算。可求解不等於已上機。
- 連拍估計使用完整記錄矩陣；未量到可用 RAW 緩衝容量時，格數／秒數顯示未知。94 個描述子不再被當成保證下界；448 MiB 不作預設值。
- USB 安裝器補上短批次讀取的逐字回讀、寫後讀回失敗的有限重試，以及最後一次寫入結果不明時的還原。AXIS 九個執行期狀態字不再誤判成外來程式。
- 加入普通與 debug 測試卡 builder。70 個 donor 的兩個時序字與六個預覽高度，共 146 個執行期會改動的韌體字，先交給共用 journal 保存；PBFLAG 明確初始化。
- 實際卡片模擬抓到 stage2 入口的堆疊對齊缺口：現在呼叫 entry 前對齊 8 bytes，返回後恢復原 SP。兩個 pass、r0 自身位址與入口順序保留；loader bytes 與同配置的 AutoRun 不變。

## Build 規範與產物

遵循 [`fpSup/SUP_BUILD_RULES.md`](../../fpSup/SUP_BUILD_RULES.md)。
[`build_res_lab_card.py`](../open-gate/build/build_res_lab_card.py) 只把產品內容交給
共用 `build_autorun.py --loader`，以 `--vshl-entry 0xC0731600` 指定會返回的初始化入口。
普通版用 `--no-shell`；debug 由共用 `entries.S` 依序呼叫 worker → restore。
**普通與 debug 是獨立測試卡；Fast 是既有 builder 支援的開發組合，會寫持久設定區，未因本次離線驗證而獲准上機。多產品合併及其他產品已搬移 mode table 的情況不在支援範圍。**

最新 240 測試產物：[20260930-240-menu-r2](cards/20260930-240-menu-r2/)。
前輪產物 [20260930-preflight](cards/20260930-preflight/) 保留作比較，不含本次 240 修補。
`plain/` 是普通測試卡；`debug/` 帶 USB shell，供下一輪觀測。
各個 `*-alternate-axis/` 目錄僅作「換配方不改 AutoRun」的比較，不是建議上機版本。
每張卡的 `MANIFEST.json` 記錄來源與產物 SHA-256、entry、區段、journal 位址和限制；
[`verification.json`](cards/20260930-240-menu-r2/verification.json) 記錄精確成品的模擬結果。
沒有覆蓋 frozen release。

從專案根目錄建到**全新目錄**：

```sh
python3 -B projects/open-gate/build/build_res_lab_card.py --out /tmp/res-lab-plain-new
python3 -B projects/open-gate/build/build_res_lab_card.py --debug --out /tmp/res-lab-debug-new
python3 -B projects/open-gate/build/test_res_lab_card.py --axis-preset H2 --out /tmp/res-lab-verification-new
```

相容的配方／payload／entry 更新不要求換 AutoRun，已比較實際檔案。
這不表示可把普通版與 debug 版混搭；第一次部署仍須選用同一目錄的完整產物。
SHA-256 僅用於本機追溯，未加入 runtime 配對或版本檢查。

## 離線驗證

下表保留前輪基準；240 修補的最新通過數、突變測試、來源與產物雜湊見 [本輪紀錄](validation/20260930-240-menu/RESULTS.md)。

| 範圍 | 結果 | 證據 |
|---|---|---|
| 七組 Sensor Lab 測試 | 177/177：full 58、recipe 14、fmt 16、canvas 10、plan 39、load 27、menu 13 | [測試日誌](validation/20260930/) |
| 主機選單掃描 | 2,280 組、0 broken，包含 RAW14 與 240 | [掃描日誌](validation/20260930/menu-sweep.log) |
| 共用 boot/loader/splash | 29 項通過 | [共用測試](validation/20260930/shared-loader.log) |
| OG 入口與 catalogue | 14 種建置、3 組 AutoRun 比較、8 組 catalogue references 通過 | [報告](validation/20260930/open-gate-entry-chain.json) |
| Sensor Lab 精確 BIN | 普通／debug 各 12 項檢查，加上兩組 payload-only 比較 | [報告](cards/20260930-preflight/verification.json) |

精確 BIN 檢查涵蓋：入口 ABI、D/I cache 次序、146 字 journal、兩次關機還原、
保留 cave 的暖映像、保存的 CUSTOM 選擇、MOV guard、缺 BIN、原生 RAW14 picker。
故意刪掉 journal 宣告及 stage2 的對齊指令，檢查都能識別錯誤。
較早的失敗及修正原因記於 [收尾驗證紀錄](validation/20260930/RESULTS.md)。

模擬真正執行 loader、stage2、入口 trampoline、restore、selector 和 picker；
worker 建立、檔案／配置／快取／OS 服務、原廠 getter／setter body 與未啟動的 LV 使用 stub。
**這些測試不能證明實際快取、排程、USB、感測器、錄影或暖開機穩定。**

## 上機前交接

建議首輪使用 `debug/` 的精確產物，先驗證載入與選單連動：

1. 確認相機與卡片現況、保存原始檔案，讀回部署後的 SHA-256。
2. 本輪先固定 CinemaDNG／12-bit／CUSTOM／H2 幾何，從 Settings 選 119.88 → 240 → 119.88，再重入；核對選取、摘要、待機文字及 AXIS／RECIPE。QS、RAW14 與錄影另列專項。
3. 先做不錄影的開機→關機→再開約十輪，並另做上一張卡切到這張卡的暖開機驗證。
4. 前述穩定後，再分開安排基準 12-bit 短片、RAW14 封裝／曝光、CRCT I0/I 與高格率測試。

這是一份待確認的上機順序，尚未執行。RAW14、CRCT、≥100 fps SSD、
音訊／時間碼與每段不同幾何的回放都不能因為這次離線通過而標成完成。
機上 mode 選單、依 mode 反灰和完整回放仍有實作工作；最新缺口以
[`imx410_plan.MISSING`](../open-gate/build/imx410_plan.py) 與設計 §15 為準。
