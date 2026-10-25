# LUT sup

2026-10-09。需求：用戶可選 `.cube`，相機 Live View 預覽，將 LUT 和設定存入 CinemaDNG；
希望擴充 MOV、STILL DNG 與 JPG。**目前有離線基準與原生色彩路徑實測，機內 LUT 產品尚未完成。**

2026-10-21 Ole2026 離線工作：已實作並用 Resolve Studio 21.0.4.5 實際 CST 浮點輸出核對
三節點子鏈，2,048 筆樣本最大 code 誤差 5.84e-7。另完成固定 Rec.709／Gamma 2.4 監看與
曲線／矩陣拆分；直接合成的 33³／65³ 硬裁切 cube 未過精度門檻，僅保留研究檔，沒有裝入卡片。
這不是 Camera RAW、作者最終 DRT 或 Pyxis 色準驗證；沒有相機 I/O，也沒有變更既有 sup。
[實作與重跑方式](../../fpSup/lut/README.md#ole2026-離線-cst-驗證2026-10-21)、
[最終數值報告](validation/20261021-ole2026-offline-01/final/report.json)、
[合成樣本比較圖](validation/20261021-ole2026-offline-01/final/comparison.png)。

## 使用者範圍

2026-10-21 使用者確認本對話負責 **color 容器**；RAW View 未來可能納入。
LUT 與後續 RAW View 若觸及相同色彩／UI 位置，由 color 統一協調；目前沒有搬移或改動 RAW View。
[容器責任與整合邊界](../../fpSup/projects/color-sup.md)。Loader v4 只管理 fpSup 首頁；
私有頁面改用 `fpsup-ui`，不依賴已廢棄的 uishare 執行層。

使用者試機後要求首頁不展開全部設定：目前只登記一個 `Color >` 入口，管理清單、選擇與逐份設定放私有頁面，
MENU 逐層返回 fpSup。機內不新增說明頁；[各項設定說明](../../fpSup/lut/README.md#color-設定說明)整理在文件與對話。
私有頁面需要 loader v6 的 `file_read`／`borrow`，本版 LUT 的最低服務需求改為 v6。

現行共用來源為 [`fpSup/loader-v4`](../../fpSup/loader-v4/README.md) 與
[`fpSup/fpsup-ui`](../../fpSup/fpsup-ui/README.md)；LUT 建置與測試使用新路徑，舊成品與驗證快照保持原樣。
[搬移後驗證](validation/20261021-layout-update-01/report.json)：24 項原生／UI 測試通過，所有 AutoRun／BIN／LUT 資料與已驗證開發包相同。

先前通過離線驗證的單份 UI 開發包為
[`20261021-color-single-entry-01`](cards/20261021-color-single-entry-01/)，
其[來源與實際成品驗證](validation/20261021-color-single-entry-01/results/report.json)包含
88 項測試、7 個可偵測故障副本；首頁只有 Color 入口，八項設定在私有子頁。
新版尚未再寫卡或實機驗收，Live View 後端仍未接通。
先前 [`20261021-color-v4-private-ui-04`](cards/20261021-color-v4-private-ui-04/) 與
[86 項驗證](validation/20261021-color-v4-private-ui-04/migration.json)保留作為改版前基準。

2026-10-22 依使用者要求增加 **逐份 cube 設定與啟用清單**：Color 內只有 Active LUT、LUT manager、
監看開關；管理頁可逐份 Enable／Disable／Settings，目前使用清單只列已啟用者，一次選一份或 Off。
依使用者最新要求，色域／Gamma 直接更新該 `.cube` 的註解；啟用／目前選擇／強度才存現存 LUT.BIN。
錄影中、來源缺失／被替換、資料變更或讀回失敗會拒絕寫入。只改已準備的純註解區塊，數值與其他作者內容不變。
內容 SHA-256 排除管理的色彩註解，所以改名／修改這些註解不會變成新 LUT；檔名只作標籤。
作者可在 cube 以自訂 `# FPSUP_INPUT_COLOR_SPACE`／`# FPSUP_INPUT_GAMMA` 註解提供設定，
使用者改後就替換它，下次匯入／開機仍以該 cube 的值為準；無標示則未設定。固定輸出仍為 Rec.709／Gamma 2.4。
本開發版明確限制 32 份；需先在主機準備原生素材，還不是相機直接掃描文字 cube。
[設定、作者約定及重建前取回機內設定的方法](../../fpSup/lut/README.md#每份-lut啟用清單與作者標示2026-10-22)。

最新註解寫回開發包為 [`20261022-color-comments-01`](cards/20261022-color-comments-01/)，
[成品驗證](validation/20261022-color-comments-01/report.json)含 119 項通過、無跳過與 17 個故障副本偵測。
已核對實際 ARM 成品的註解寫回、重啟讀回、可攜重新匯入及來源資料 bytes 不變；
AutoRun 與共用 LOADER／SUPMGR／UI 不變，沒有操作相機或寫卡，監看仍未接通。

**2026-10-24 第一次上機**（加入使用者的多 sup 卡，沿用卡上 loader）：載入、Color 入口、選擇與重開讀回、cube 註解寫回與重開讀回、啟用清單、監看拒絕、MENU 返回都通過；找到 4 個 UI 導航問題（兩個焦點掉出頁面，需 S1 退出）。[紀錄](validation/20261024-oncamera-01/README.md)。

先前 BIN 保存版的離線開發包為 [`20261022-color-library-03`](cards/20261022-color-library-03/)，
[最終驗證](validation/20261022-color-library-01/final/report.json)包含 114 項通過、無跳過與 13 個故障副本偵測。
實際成品的切換、個別設定保存／重載與 MENU 路徑通過模擬；AutoRun、共用 loader／SupManager／UI 與單一入口包一致。
另用同版核心的獨立素材核對 35 × 161 筆，最大通道 code 差 7.01e-5，不是示範 LUT 清單本身的畫面精度。
未寫卡、未驗機內 UI 或 SD 掉電行為，Live View 仍未接通；示範包內三份小型 LUT 只是診斷素材。

2026-10-15 使用者收斂監看需求：**機內 `.cube` 只接受 Rec.709 輸出**。
使用者為每份 LUT 指定預期的輸入色域／gamma，相機先完成輸入轉換，再執行 LUT；
選單只提供輸入設定，輸出固定為 Rec.709。LUT 輸出後接 LCD 適配，場景到顯示的轉換由
LUT 或其輸入預設完成，不在 LUT 後重複套用。這是產品契約，`.cube` 格點本身無法可靠驗證輸出色域。

使用者指出 fp 機內有多個可利用的處理區塊；不能用「未找到單一 3D LUT 名稱」否決整個功能。
機內實作同時考慮 ISP 與 display 端，評估原生矩陣、gamma、CUVAREA、CUVCONT 等組合。
完整來源與本次修正：[LUT 原生區塊補查](../../research/imaging-hw/isp-colour-blocks-20260927/LUT_BLOCKS_2026-10-09.md)。

2026-10-09 使用者決定：**未來 color 功能整合成一個 sup 統一管理**。
RAW View 的輸入校準／tone、使用者 LUT、原廠色彩路由與 DNG 外觀設定由同一個 owner 管理；
不讓多個 sup 分別覆寫同一組色彩 hook、root table 或 ISP 參數。
使用者已自行卸載 RAW View 並重新開機，這次上機先確認原廠路徑，再量測 native 色彩模式。

## 已完成的第一層

維護程式在 [`fpSup/lut`](../../fpSup/lut/README.md)：

- 嚴格 `.cube` 匯入，保留完整 1D／3D／shaper，不以矩陣擬合取代原檔。
- 全 RGB 四面體內插、domain、強度、離線 sRGB 預覽，作為機內結果的真值基準。
- CDNG／STILL DNG 副本嵌入原始 `.cube` 與設定，精確取回；影像 payload 和原生校準不變。
- 可選標準 RGBTables，明列 32³ 限制與重採樣誤差；後製 reader 效果尚未驗證。
- ISP 地圖工具修正，直接從具名診斷函式與 descriptor 串出 MMIO／shadow，不靠排序猜位址。

第一版沒有相機操作、寫卡、native hooks、AutoRun 產物或發布。
驗證紀錄在 [`validation/20261009-offline.json`](validation/20261009-offline.json)；單元測試 17 項，地圖測試 3 項。

## 2026-10-09 上機結果

使用者授權上機測試，並自行卸載 RAW View、重新開機。
卸載前只讀辨識：RAW View v3 常駐程式與本地版本逐 byte 相同（排除 launcher 填入的三個 chain-next），
flag/eff 均為 1；未知 hook 防護在任何 setter 之前停止，未覆寫既有功能。
重開後確認 `C0075CF4`、`C0313244` 回到 ROM 原指令，沿用原 fpshd 3.2.0。

條件為 **CINE 待機，CinemaDNG 12-bit，MONIT1_60，2016×1344，relative gain 1170**。
完整掃描原廠色彩 enum 0–15；最後一輪每模式等 1 秒、連讀三份兩個 ISP shadow bank 和 LCD CSC/gamma。
本次沒有直接相機記憶體寫入、ARM 注入、拍攝、錄影或寫卡。

下列結論僅採用：同模式三份數值相同，且四份 OFF 基準相同的 word。
原始讀取是 sequential，**不是原子 frame snapshot，也沒有像素量測**。

| 區塊 | 本次可靠觀測 |
|---|---|
| RGBLMAT 第二組 | 所有非 OFF 的 native 矩陣皆逐係數吻合 ROM `C0B39CC8` 中的某筆 9×s16 表；enum 11 為 identity。這確認實際配置路徑，不只名稱引用。 |
| RGBLMAT 第一組 | enum 14 另有 6 個穩定變動 word。 |
| YCMAT | 多數模式有 2 個穩定變動 word；enum 15 與 OFF 相同。 |
| CSUP、C_SAT_C | enum 11/14 分別有 3/6 個穩定變動 word，是多區塊處理的實機證據。 |
| APSUP | enum 14 有 2 個穩定變動 word，其他暫態差異排除。 |
| CUVAREA | OFF 的一份重讀中有 6 個 word 變動，不能歸因為色彩模式；本次未確認 mode 耦合或 pixel 能力。 |
| CUVCONT、RGBMAT_PL、LCD CSC/gamma | 本次模式掃描無穩定 mode 相關差異；不能據此認定區塊永遠不用或不可設定。 |
| shadow context 1 | 本次 CINE 待機掃描未見變動；不直接命名為 MOV／STILL bank。 |

較早兩輪有 IGAMMA／CEQ 等 OFF 首尾差異，沒有把它們當成 mode 效果。
最後一輪 OFF 首尾全部相同，所有取得的原設定均恢復；最後獨立再查仍為 OFF、未錄影、gain 1170、同 boot。

證據：

- [穩定差異與 ROM 矩陣核對摘要](validation/20261009-native-colour-summary.json)
- [16 模式 × 3 份原始量測及完整 command transcript](validation/20261009-native-mode-trial-05/report.json)
- [獨立最終復原確認](validation/20261009-final-camera-state.json)
- [實際執行的程式原檔](validation/20261009-native-mode-trial-05/native_mode_trial.py)，SHA-256 與 report 一致
- [目前測試程式](probes/native_mode_trial.py) 與防護測試（8 項；另加 reboot 防護，拒絕在不同 boot 套用／復原）

**尚未將新 `.cube` 套入 Live View，也未測 LUT 的機內 CDNG metadata、MOV、STILL/JPG 烘入。**
這輪建立 unified color sup 的原生 backend 候選與配置基準；不能視為 full 3D LUT、像素算式、HDR/REC 路由或吞吐已驗收。

## 2026-10-16 監看輸入轉換基準

已按使用者提供的 CinemaDNG 選單修正 [`fpSup/lut`](../../fpSup/lut/README.md#選擇監看-lut-輸入)：
色域為 ACES、Adobe RGB、Blackmagic Design、P3 D60、P3 D65、Rec.2020、Rec.709、sRGB，共 8 項。
非 Blackmagic 共用 Adobe RGB、Gamma 2.4、Gamma 2.6、Linear、Rec.709、sRGB 六項 Gamma；
Blackmagic 另用 Blackmagic Design Film／Extended Video。兩欄獨立保存，跨組搭配會拒絕。
[三張原圖及 hash](validation/20261016-cdng-menu-01/evidence.json)是選單依據；畫面版本與啟用狀態未另驗。

桌面流程：明確來源 RGB／XYZ → 曝光尺度 → 所選線性色域矩陣 → 所選 Gamma → 原始 cube
→ 固定 Rec.709 D65／Gamma 2.4 監看。已實作 7 色域 × 5 曲線 = 35 組標準數學參考；
ACES 採 AP0／D60，並未隱含 ACES 顯示渲染。全部模型尚待與 Resolve 成對顯影核對，
不能把標準原色／曲線吻合當成 CinemaDNG 解碼已等價。
Resolve 的 Rec.709 Gamma 精確公式、Blackmagic 的兩組 CinemaDNG 色彩模型仍待確認，
選單保留但拒絕產生數值結果；不以 BT.709 OETF 或 Film Gen5 代替。
ARRI／Sony 等數學參考僅保留作通用計算回歸，已移出 CinemaDNG 產品選單。

`monitor-presets` 提供 UI 輸入清單；`monitor-preview` 產生有 sRGB ICC 的預覽，
`monitor-render` 保存未裁切的浮點 709 結果與 lookup 範圍報告，`monitor-prepare` 保存原始 cube、
設定、轉換矩陣／曲線描述及選定 LUT 輸入域的 float32 查表。監看指令不提供輸出空間選項。
0% 與完整 LUT 結果在同一 709／Gamma 2.4 空間混合；基準為明訂的線性裁切＋Gamma 2.4，
不是原廠 fp／Resolve／ARRI 的顯示渲染。

機內 backend 依序接 fp 校準／WB／曝光、所選輸入矩陣／transfer、查表與 LCD 適配。
曝光留在表前，強度可烘入同輸入域的查表。將整條跨色域流程預合成到 DWG 格點的實驗，
在極端飽和色上即使 65³ 仍有大誤差，因此保留解析式前轉換及原始 LUT 域。
shaper／格點重採樣／強度合成的誤差逐包報告，不自動當作硬體可精確表示。

[更新後驗證報告](validation/20261016-cdng-monitor-01/report.json)保存選單與 35 組數學參考狀態。
通用計算回歸對照既有 14,648 筆 ARRI Classic 參考資料，最大 RGB code 差 3.01e-14；
同輸入域 33³ float32 表的 9,217 筆獨立樣本最大差 2.90e-8。
53 項選單／色彩／LUT／預覽／殘差測試通過；先前另有 5 項既有 ARM CEQ 模擬回歸通過，native 程式未變更。
這輪沒有新的相機操作或卡片產物；fp live frame 的輸入校準、owner 交接、原生係數／曲線近似與
機內 UI 仍按下方「尚待完成」接入，不能將桌面參考數值視為相機畫面誤差。

## 2026-10-21 Loader v4 開發 sup

使用者要求開始製作 sup、參考 Loader v4。程式與 builder 在
[`fpSup/lut`](../../fpSup/lut/README.md#loader-v4-開發-sup2026-10-21)：FSB4、最低服務 v5、
快取常駐記憶體與 `page_add()`，沿用現有 v4 builder，沒有改共用載入器。
`LUT.BIN` 只放原生程式／設定，`LUT/ACTIVE.LUT` 獨立保存準備後的矩陣／Gamma／完整 LUT 節點，
`LUT/source.cube` 保留原檔。更換素材不要求更新 AutoRun。

本版實作檔案驗證、8 色域與相依 Gamma 選擇、五段強度、8 列設定註冊，及實際 ARM Q20
XYZ→輸入色域／Gamma→1D＋四面體 3D→Rec.709 強度混合。只接受呼叫者自己擁有的分離樣本，
沒有影像 hook 或原廠 ring 寫入。監看啟用回報 `NO_BACKEND`；校準後的 Live View 路由、
原生硬體主要處理＋CPU 殘差、設定寫回與實際效能仍未完成。
本版尚未上機；不能把「Loader 載入成功／數值核心可跑」當成「機內監看已套用」。

[第一份開發包](cards/20261021-loader-v4-01/)與[當時驗證](validation/20261021-loader-v4-01/report.json)保持原樣：
66 項通過、無跳過，5 個突變全部被抓到；涵蓋 65³、4096 點 1D、shaper／domain、所有四面體順序、
8 列群組回呼、滿額／衝突清理、Fast／除錯卡與保留映像後的初始化。
35 模型的 5,635 筆 ARM／float64 比較最大 code 差 7.01e-5，不能視為相機色差。
實際輸出的 LUT／LOADER／SHELL／SUPMGR 檔已另跑一次載入、拒絕監看啟用與關機流程，並核對 hash。

接續使用者更新 Loader v4 進度，現在 `--card` 預設包含共用 fpSup／SupManager 畫面，
8 列 LUT 設定加管理入口共 9 列，沿用首頁排序和兩頁配置。色域群組切換會立即更新相依欄位；
Blackmagic 使用自己的兩個 Gamma，未核實模型維持 pending。監看 On 仍明確拒絕並重繪 Off。
沒有修改共用 v4 程式，也沒有相機操作。

[含 UI 的新開發包](cards/20261021-loader-v4-ui-04/)與[新驗證](validation/20261021-loader-v4-ui-04/report.json)：
82 項通過、無跳過，6 個突變全部偵測；新增 10 項 LUT／UI ARM 整合和 6 項共用頁面檢查，
包含所有色域／Gamma／強度、分頁、管理頁、缺檔處理、立即更新及關機還原。
測試使用實際 ARM 核心／回呼／UI 資料與模擬原生 GUI，另以原生 interpreter／matcher 核對頁面與 MENU 路徑。
實際輸出的完整開發包也再載入驗證並保存 hash；數值核心與第一份開發包相同。
此包固定在驗證報告的來源版本；[驗證結束後的共用來源變動](validation/20261021-loader-v4-ui-04/post-validation-source-state.json)
另行記錄，不改動已驗證的成品。先前來源變動或建置未完成的嘗試以 `incomplete.json` 標記，未列入驗收。
**LUT 設定畫面仍待上機驗收，Live View 後端仍未接通。**

## 2026-10-09 補充：色彩資源與方法清單

使用者要求再確認 fp 機內其他可利用的色彩晶片／方法。
本次只做離線韌體、既有量測與官方規格盤點，沒有新的相機操作或部署。
**目前確認的是 XZ01 平台的多個處理區塊和原生介面；尚未確認另一顆可供 sup 使用的獨立色彩晶片。**
MMIO 區塊、SIGPRO 類別和韌體分割區都不能各自算成一顆實體晶片。

下表「上機」只指先前 native 模式改變時的穩定配置證據，並非自訂 LUT 已成功運行。
「靜態」指韌體中的 descriptor、setter 或 job 呼叫已辨識，仍需像素／影像路由驗證。

| 資源 | 能考慮的用途 | 證據與限制 |
|---|---|---|
| RGBLMAT 兩組矩陣 | 色域、通道混合；原生 LUT 近似 | 上機配置已驗；自訂係數、負像素、clamp 與色差未測。 |
| SIGSEQ 一／三通道 tone 表 | 一條或三條 2048×u16 曲線，作非線性 shaper 候選 | 靜態 dispatch 確認；三通道 1D 不等於 RGB 3D。原生 scratch/cache 有 owner。 |
| IGAMMA、PSTIGAM、GAMDEC、GAM_BAS | 曲線與數值尺度候選 | 分段參數與 packed 控制已辨識；硬體索引、精度和像素公式未驗。 |
| YCMAT、RGBMAT_PL | 亮度／色度與輸出轉換 | YCMAT 上機有變化；RGBMAT_PL 似 601 類 YUV→RGB 是係數推論，不能當另一級 RGB look。 |
| CUVAREA、CUVCONT | 色度區域選擇與控制候選 | resource 0x17/0x18、原生 setter 已找到；任意 hue remap 未證，setter 同時涉及 APSUP。 |
| CSUP、C_SAT_C、APSUP；ECSUP | 色度、飽和與外觀控制候選 | 前三區上機有 native 模式穩定變化；ECSUP 只有靜態證據。完整硬體公式未知。 |
| CEQ、CEQ24、YGAM、KNEE、OFFSET、CLIP 家族 | 額外曲線、原始／目標資料、knee/clip 控制候選 | 具名 MMIO/descriptor 已核對；另有 4096 項 CPU 曲線展開，不證明任意 3D LUT。 |
| PST_TOP Y_GAMMA、CKNEE | 亮度曲線與 knee 候選 | 原生參數可設定；輸入域、硬體插值和裁切公式未驗。 |
| 顯示端 CSC＋RGB gamma | LCD／輸出監看轉換候選 | 三矩陣 bank、兩 gamma bank，gamma 資料為 3×16 bytes；LCD/HDMI/EVF 路由各別待驗，不能固定命名 bank。 |
| SIGPRO RawMakePreview、FillLight、RawMix、MBlender | RAW 預覽、顯影、合成；STILL/JPG 介入入口候選 | 原生 jobs／buffer 描述子確認；不證明獨立可編程 DSP 或可上傳自訂 LUT kernel，也未確認連續 LV 路由。 |
| 主 ARM CPU | 軟體完整 3D LUT／四面體內插 | 桌面 reference 已有；機內 buffer ownership、輸入色域、呈現介面和吞吐未測。NEON 加速須另驗。 |
| CRCT、RAW_CORR、WHITE BALANCE、前段增益 | LUT 輸入校準與 headroom 研究 | 有原生路徑；校準不等於 look，與 RAW sink 共享程度待驗，不能作 RAW 不變的效果保證。 |
| DHAZ、TNCR、TMAP | 保留研究項目 | 名稱、MMIO／setter 確認，像素語意未知；TMAP 的尺寸／格點／座標運算不足以證明 tone mapping。 |
| ARM926_1、ARM926_2、ARM9 | 協處理器研究 | 確認分割區名稱，不能據此保證兩個可自由使用的色彩核心；角色和工作介面未知。 |
| GPU、任意硬體 3D LUT、可編程影像 DSP | 保留研究可能 | 尚未找到供目前 sup 呼叫的程式／資料介面；不能因缺少名字便說硬體不存在。 |
| OSD palette、面板校色、JPEG/MOV 編碼器 | OSD、呈現和壓縮 | 256 色 palette 不能當完整 RGB LUT；壓縮／編碼能力亦不證明能執行自訂色彩轉換。 |

可採用的方法分為以下八項，全部交由單一 color sup 管理：

| 方法 | 適用目標 | 現況與還原界線 |
|---|---|---|
| 原生 ISP 多區塊組合 | LV；MOV/JPG 待路由驗證 | 有 native 配置基準，尚未做自訂 cube 擬合；還原度依 LUT 與實測誤差。 |
| 顯示端矩陣＋gamma | LCD；HDMI/EVF 各別驗 | 適合矩陣／曲線類外觀，不能等價任意跨通道非線性 3D LUT。 |
| 主 CPU 完整 3D LUT | 離線對照、低解析度機內驗證與備用方案 | 保留全部 RGB 節點；機內 runtime 未實作，效能與量化／輸入轉換仍待測。 |
| 原生處理＋軟體殘差 | 使用者選定主要架構；監看優先 | 硬體負責主要轉換、CPU 少量補正；要驗證裁切、色差與實際運算／記憶體成本。 |
| 接入原生 RAW 顯影，在 JPEG 編碼前處理 | STILL JPG／DNG 回放顯影 | 原生 job 入口已辨識，尚未接入。單張可放寬延遲，不等於已可即時 MOV。 |
| CDNG／STILL DNG 保存完整 cube＋設定 | RAW 後製 | 離線實檔精確回存及 RAW 不變已驗；機內 writer 未接入。保存不等於 reader 自動套用。 |
| DNG RGBTables／ProfileLookTable／HueSatMap＋ToneCurve | 支援的後製 reader | RGBTables 離線 writer 已有；LookTable 轉換未實作。原生 HSM/TC 曾做 Resolve A/B，不能推成 RGBTables／LookTable 相容性。 |
| 後製軟體直接載入原始 cube | CDNG 解碼後／MOV／JPG | 須對應 LUT 輸入色域、gamma、曝光與插值；與機內 Live View 分開。 |

優先驗證原生三通道 tone／CEQ／CUV 的像素功能，以及硬體主要轉換後的 CPU 少量補正。
完整 CPU LUT 保留作離線真值與低解析度機內比較候選；各路徑皆不先承諾 FPS 或還原百分比。
MOV/JPG 要在編碼前真正轉換像素；CDNG 維持 RAW，以獨立 metadata 保存 look。

公開資料亦核對了 [SIGMA fp 規格](https://www.sigma-global.com/en/cameras/fp/)與
[Socionext Milbeaut 平台介紹](https://www.eu.socionext.com/solutions/visual-solutions/)。
後者沒有建立 fp XZ01 與 SC2000／SC2002／MB86S27 的型號對應；不能借用它們的 DSP、核心數或時脈規格作 fp 證據。
[Adobe DNG 1.7.1](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf)
規定 RGBTables 與 HSV 形式的 ProfileLookTable，兩者都不是把任意 cube bytes 寫進去就會自動套用。
現有 RGBTables 輸出最多 32³，33/65³ 需重採樣且有輸入／輸出限制；完整來源仍獨立保存。

可查核清單：[16 組資源、8 種方法、37 筆具名路由、27 個函式落點及來源 SHA-256](validation/20261009-colour-resource-inventory.json)。
原始 MMIO/descriptor 已與地圖核對，函式落點已與現存反編譯標頭核對，所有來源檔案存在並保存 hash。
這是證據一致性檢查，不是新增像素／效能上機測試。

## 使用者選定架構：原生硬體主要處理＋CPU 少量補正

2026-10-09 使用者提出最終方向：「原生硬體晶片處理＋CPU 輕微調整」。
將此設為統一 color sup 的主要架構方向，尚未視為實機效能或還原度已驗收。

1. **載入／切換 LUT。** 保留完整來源、輸入色域／gamma 與強度；建立原生矩陣、曲線、
   色度區域等配置。CPU 的解析、建表和參數擬合盡量在載入／設定改變時完成。
   硬體像素算式確認後才能建立可信的擬合模型，不能只按區塊名字拼接。
2. **每幀主要處理。** 由原生硬體承擔能表示的轉換；CPU 視實測殘差選用小曲線、
   簡單通道運算或小型補正表。CPU 介入位置依實際影像 job／buffer 路由決定，
   不先假定能在硬體輸出後直接取得可寫的線性 RGB frame。
3. **驗證。** 相同輸入比較完整 cube、硬體單獨結果與硬體＋CPU 結果；
   分別量色差、飽和色／高光、幀率、延遲、CPU 時間與每幀記憶體讀寫量。
   「補正幅度小」不代表計算便宜：若仍須逐像素查表與讀寫整幀，成本可能仍高。
   硬體若先裁切或把不同輸入合成相同輸出，僅看該輸出的 CPU 補正無法恢復已丟失的資訊。
4. **保存／輸出。** CDNG 保留完整原始 cube 和設定，並記錄 backend 版本與必要校準，
   不用硬體近似取代原檔。MOV/JPG 要另驗編碼前可用的硬體／CPU 組合。

CPU 完整 3D LUT 保留為比較及備用路徑；主要產品目標以硬體承擔每幀大部分工作。
對無法由此組合可靠還原的 LUT，顯示實測限制，不把近似結果宣稱為精確套用。

## 2026-10-09 多區塊與補正確認

使用者要求開始確認、充分利用機內已有資源以盡可能還原 `.cube`。
完成原生參數的 14 個條件，各讀三份；涵蓋兩個 ISP context、顯示 CSC/gamma、
CEQ/CEQ24 完整 anchor、DHAZ/TNCR 與原生 tone／develop 描述。
試驗使用 stock menu setter，最後逐 mode 恢復原有參數，再恢復 OFF；未注入、拍攝、錄影或寫卡。
穩定效果必須在前後基準及三份條件讀值均一致；逐筆讀取仍不是原子影像。

| 控制／資源 | 新增確認 |
|---|---|
| TealOrange effect ±5 | RGBLMAT、YCMAT、CEQ 與 CEQ24 的 ORG/TGT anchor，以及 tone 指標共同改變。 |
| PowderBlue effect ±5 | RGBLMAT、YCMAT、CEQ 與 CEQ24 的 TGT anchor，以及 tone 指標共同改變。 |
| Manual highlight／shadow ±5 | CEQ_YGAM 各有 10 個可靠變動 word。 |
| Standard contrast／saturation ±5、Auto tone | getter 接受參數，但本次取樣區沒有可靠差異；尚不能定義這些參數的 CINE pixel 路徑。 |
| CEQ＋CEQ24 anchor 格式 | 六平面 × 24 u16，前 16／後 8 分送兩組 shadow，B 平面倍率 ×4；原廠 Thumb-2 函式逐值核對成功。 |
| bank 1、CUV、顯示端 | 此輪控制未見可靠耦合；保留研究，不認定不能使用，也不強行打開未知功能。 |

原廠 CEQ anchor 的圓周數值排列提示 hue 相關用途，但平面語意、像素插值、工作順序與 clamp 尚未量測。
新增 codec 僅保存 anchor，不包含整個 ISP job 的 enable／clip 等控制。
83 份可表示的 CEQ 觀測都已交原廠函式重新編碼核對；另一份讀到暫態超界 word，明確拒絕轉成可部署資料。
原生 tone 切到 `C3419DA8`／`C341ADA8` 的 RAM 由韌體管理，不能借作本 sup 的 LUT scratch。

`fpSup/lut/residual.py` 已建立 CPU 補正離線基準，接受硬體輸出／完整 cube 目標配對。
先比較 48-byte affine 係數，再比較 5³、9³、17³ 殘差表；完整 cube 仍是目標真值。
domain 超界、未收斂、硬體輸出碰撞都會明列；不以剪裁掩蓋誤差。
七項合成測試核對四面體取樣、獨立樣本擬合、資訊損失、表格大小和求解失敗；不代表機內像素或效能已驗收。

影像路由追查：試驗中的 `C375C05C` 全彩候選 base/W/H 皆為 0。
追加只讀追查找到 `C30255B4` 的 1620×911、四個原生 handle 與另一個 develop 指標，
地址落在已知 scanout ring；當時尚不能由 descriptor 推定 pixel packing。
第一次追加讀值 app_current=5，與試驗中的 CINE=2 不同；只讀保留該狀態。
使用者切回 CINE 後，第三輪確認 app_current=2，同 boot／OFF／原參數，另一個 develop 指標在 ring 中輪替。
舊線性描述仍為 0；輪替指標證明有原生預覽來源。後續授權讀值的格式確認見下節；
有效幀 ownership、色彩編碼與同輸入／輸出配對仍需確認，才可擬合 CPU 補正與報 LUT 還原度。

證據與程式：

- [原生參數試驗與逐筆紀錄](validation/20261009-native-controls-trial-01/report.json)
- [重算穩定差異、CEQ 資料與拒絕原因](validation/20261009-native-controls-summary.json)
- [CINE 只讀輸出描述與最後獨立狀態](validation/20261009-native-output-descriptors-03/report.json)
- [參數 runner 與復原防護](probes/native_controls_trial.py)，8 項新增防護測試，另有既有 8 項 mode 防護
- [CEQ 原生編碼](../../fpSup/lut/native_ceq.py)與 [原廠函式離線核對](../../fpSup/lut/test_native_ceq.py)
- [CPU 殘差基準](../../fpSup/lut/residual.py)
- [完整離線驗證](validation/20261009-hybrid-validation-03.json)，55 項通過、無跳過，含 [預覽讀取及錯誤變體防護](probes/test_native_preview_bytes.py)與線性 YUYV 解碼驗證

預覽診斷 reader 已具體完成與驗證；只使用現有 MEM1，先查 window 7 未被占用，
限定已核對 ring 的一份 0x3FC000 bytes、唯讀 permission、關閉 CPU cache flush，最後核對 window 撤銷及狀態。
不借 echo、不 claim camera scratch、不注入程式或寫影像／卡片；生產者繼續運作，因此讀值可能撕裂，不能作 frame-atomic 色差驗收。
2026-10-09 自動核准審查初次要求明確資料傳輸授權；使用者回覆「可以啊」，授權一份約 4 MB
預覽診斷保存到本機專案。重新審查通過，讀取成功且 window 撤銷及最後狀態核對完成。
[核准審查與授權結果](validation/20261009-native-preview-approval.json)。

## 2026-10-09 授權預覽讀值與格式確認

取得一份 4,177,920-byte 原生 ring 診斷；只使用既有 MEM1 和暫時唯讀 window，
未注入、寫回 frame、錄影或拍照。最後 CINE／OFF／原參數與 boot 相同。
生產者未暫停、未取得 frame lease，這不是可作色差驗收的原子幀。

此 CINE MONIT1 條件可按 **1620×911、每行 3240 bytes 的線性 YUYV8** 解出完整場景。
有效影像 2,951,640 bytes；其後 1,226,280 bytes 是 ring 未使用尾段，不能當像素或高光裁切。
1620 stride 的相鄰行亮度差最小，其他候選 stride 出現條紋，與原生 descriptor 尺寸一致。
這修正舊筆記「scanout ring 必然為 tiled」的推論；**不代表其他模式也已確認此格式**。

目前 Cb／Cr 解碼方向與場景相符，但精確 chroma siting、601／709、full／limited、
色域及 transfer function 尚未校準。已保存四種 RGB 解碼假說供後續核對，未把其中一種當成 sRGB 或 LogC3。
讀取耗時是 USB 診斷傳輸，不是機內 CPU LUT 的幀率。
8-bit 量化與 4:2:2 共用色度會丟失資訊；主硬體轉換應優先研究在這些步驟之前介入，
不能期待只看最後輸出的 CPU 補正恢復全部原始色彩。

- [實際讀取、狀態與 window 撤銷紀錄](validation/20261009-native-preview-bytes-01/report.json)
- [原始資料、stride、範圍與限制分析](validation/20261009-native-preview-bytes-01/analysis.json)
- [四種 RGB 解碼假說圖](validation/20261009-native-preview-bytes-01/colour-decode-candidates.png)
- [離線分析器](probes/analyse_native_preview.py)與 [嚴格 YUYV 解碼](../../fpSup/lut/preview.py)

## 2026-10-09 ARRI 官方 LUT 候選

使用者詢問 ARRI LUT。從 [ARRI 官方 LUT Generator](https://www.arri.com/en/learn/camera-systems/tools/lut-generator)
取得 LogC3 LUT package，保存原始 ZIP、下載來源與 SHA-256；完整解出並驗證兩份 **33³ `.cube`**：

| 候選 | 原始檔與用途 |
|---|---|
| ALEXA Classic 709（K1S1） | [Classic 33³](assets/arri/official-20261009/ARRI_LogC3-to-Gamma24_Rec709_D65-Classic_33.cube)，選為第一個 ARRI 驗證目標。 |
| LogC3 Rec.709 v1 | [v1 33³](assets/arri/official-20261009/ARRI_LogC3-to-Gamma24_Rec709_D65-v1_33.cube)，作官方另一種 rendering 的比較目標。 |

兩者要求 **ARRI Wide Gamut 3／LogC3 輸入，Rec.709 D65／Gamma 2.4 輸出；輸入與輸出皆 full range**。
依據 [ARRI LUT naming convention](https://www.arri.com/resource/blob/294602/1159ce14a38f570431b7eb3cf30947eb/2022-09-arri-lut-naming-convention-logc4-and-logc3-data.pdf)。
fp 的 OFF 預覽尚不能當成 LogC3；須先確認 fp 輸入色域與 transfer function，建立相符轉換，
再比較完整 cube reference、原生處理與 CPU 殘差。LogC4／Wide Gamut 4 是另一套輸入，不能互換。

已準備保留原檔的 float32 完整表與設定於 [Classic 素材](assets/arri/official-20261009/prepared-classic/settings.json)
及 [v1 素材](assets/arri/official-20261009/prepared-v1/settings.json)，都標記 `on_camera_ready=false`。
[原檔來源與候選摘要](assets/arri/official-20261009/selected-cubes.json)。
兩份原檔均逐 byte 吻合官方 ZIP，完整 35,937 節點 float32 素材與 hash 已核對；
[素材驗證](assets/arri/official-20261009/prepared-assets-validation.json)只量格式轉換，並非相機色差。
沒有把未校準的取景 RGB 直接套 ARRI cube 作示意，也沒有部署到相機或宣稱已量到 ARRI 還原度。
官方另有 [Look Library](https://www.arri.com/en/learn/camera-systems/image-science/look-files) creative looks；
後續依真正輸入編碼選擇 `.cube`，ALF／AML 不是本匯入器的 cube 素材。

## 2026-10-09 續查：如何確認色彩與 frame 交接

使用者要求實際確認並說明方法。沿用已核對的現有 fpshd 3.2.0，完成三份固定範圍的
只讀路由診斷；未讀新影像 payload、呼叫原生 job、改參數、注入或寫卡。
本輪 boot 為 5345245，前後均 CINE 待機、OFF、gain 1170、六項調整為零；所有核對的原廠 code/hook 一致。

新增可靠結果：

- 三組 display CSC 的九個係數，三份讀值均逐 word 吻合原生 LCD cache B。
  `C00DD520` 在第二個原始 selector=2 時選 cache B；`C00DD6C8` 的當前 route IDs=1/1
  推得 pending LCD matrix update 走 bank 0。這定位實際配置，不直接命名為已校準的 709/full-range。
- 當前 descriptor 為 **1620×1080、四個 ring handle**，與前次 pixel capture 的 1620×911、boot 4040737 不同。
  本輪沒有 pixel read，不能把前次已驗的 packing 當作此新幾何的實測結果；不能沿用固定 911 高度。
- 生產端 engine 2／8 index、scanout index 與第二 develop 指標都有輪替。
  native `C01D7638` 還會更新 context 1／2 的 index，再 copy descriptor，不能當作純 getter 或 buffer lease。
  這些值是依序讀取；不能用「某筆 index 看似沒在用」推成該 buffer 可寫。
- `XC_SigproRawMakePreview::v0` 是 destructor，不是影像處理入口。
  實際 `C04321A0` 會配置輸出 handle 並呼叫 native jobs；須追完格式、完成通知、釋放與兩個 context 的隔離，
  才能用來重播相同輸入，不直接在 shell dispatcher 呼叫或借用 stock ring。

[新上機紀錄與逐筆 transcript](validation/20261009-native-live-route-01/report.json)、
[實測／原廠函式對照與來源 hash](validation/20261009-native-live-route-01/analysis.json)、
[目前只讀 runner](probes/native_live_route.py)。五項新增測試核對 CINE／錄影／boot／未知 hook／參數變更拒絕。
執行版本保存於 report 旁；目前 runner 將 selector 標籤修正為 `DISPLAY_PARAMETER_SELECTORS`，
不藉原始數值推斷 full／legal range。

像素確認採同一份已知輸入重播：stock、原生矩陣／tone 擬合、原生＋CPU 補正，與完整 cube reference 比較。
先量灰階與六色漸層，定位曲線、跨通道混合和裁切；再逐項加入 CEQ／CUV，避免同時改多區塊而無法定位誤差。
固定 WB／曝光及輸入轉換，以獨立樣本檢驗擬合外的色差，再量每幀耗時、丟幀與設定復原。

已建立 [ARRI Classic 已知輸入試驗素材](validation/20261009-arri-classic-known-inputs-01/manifest.json)：
14,648 筆 float64 RGB 與完整 cube 目標，含 4,913 筆 17³ 擬合色格、6,144 筆不與擬合色格重複的驗證資料，
以及灰階／R、G、B、C、M、Y 各 513 級診斷漸層。原檔、產生器與資料 hash 全部保存。
**這是 LogC3／AWG3 域的數值基準，不是相機 Bayer／YUYV 格式，也尚未送進相機。**
要實測還原度，仍須完成 fp→LUT 輸入校準和 owned native job；不把參考輸出當成硬體結果。
[本輪完整離線驗證](validation/20261009-hybrid-validation-04.json)為 60 項通過、無跳過；
另已核對試驗素材的 hash、原檔逐 byte 保留、資料形狀與 holdout 不重複。

## 機內產品行為（目標，尚未實作）

LUT 選單：開關、檔案、強度、輸入色域／gamma、監看套用、CDNG 保存。
每份 LUT 分別保存輸入設定；輸出固定 Rec.709，不提供輸出色域／gamma 選單。
監看實作基線採 Rec.709 D65／Gamma 2.4，內部 RGB 以 full-range 正規化值表示，
顯示介面的量化及 range 轉換放在最後。輸入預設須明訂原色、白點、gamma、曝光尺度，
以及是否含場景到顯示的轉換；不能只更換 gamma 名稱。

```text
fp 線性影像 → fp 校準／白平衡／曝光尺度
  → 所選 LUT 輸入色域及 gamma → 原始 .cube
  → Rec.709 監看 RGB → LCD 適配
```

強度在共同的 Rec.709 監看空間混合：0% 為基準監看畫面，100% 為完整 LUT 結果。
跨編碼 LUT 不直接混合輸入 Log 與輸出 Rec.709 數值。
離線 `Cube.apply` 的既有數值混合不代替這層監看強度處理。

MOV／JPG 套用另有控制，允許監看外觀與寫檔各自設定。
選錯 domain／不支援的 LUT 必須明示，不能顯示「已套用」卻退化成另一個 look。

每次拍攝開始固定選中 LUT 與設定；錄影中更換設定不能讓同一 clip 混用兩套 metadata。
CDNG 保留原始 Bayer 與校準，另存 LUT／外觀設定；MOV／JPG 的套用則必須在編碼前完成像素轉換。
RAW View 的「輸入校準」與本產品的「使用者 look」分開；不以任意修改 CM／AsShotNeutral 冒充 LUT。

## 尚待完成

1. **原生 pixel backend。** 追 CUVAREA resource 0x17/0x18、RGBMAT_PL resource 0x3E 的呼叫與實際像素算式。
   驗證矩陣／gamma／色度區域組合後的順序、符號、clamp、精度及 full LUT 的誤差；
   若只能近似，保留完整 LUT，顯示其實測誤差，不將近似宣稱為精確 `.cube` 支援。
2. **Live View 路由。** 確認 LV／MOV／STILL context；比較 LCD-only、HDMI、待機、REC、回放。
   監看開關不能改到 RAW，且要釐清 OSD／AF／曝光統計是否被影響。
3. **讀檔與 UI 上機驗收。** 獨立素材讀入、owned resident heap、失敗狀態及共用 v4 UI 已通過離線驗證。
   接續驗收實卡讀檔、LUT 設定畫面與原廠 GUI 互動；加入多檔選擇與設定寫回。
   失敗時保持原廠路徑並顯示狀態，不在 entry 內永久工作。
4. **相機 DNG writer。** 把選中 LUT／設定快照接到 header writer；本次 append-IFD 工具是離線格式基準，
   不是每幀存完再讀回重寫的機內方案。驗證 8/10/12-bit、lossless、STILL DNG、檔案長度與回放。
   [既有 FHD writer 證據](../../research/imaging-hw/native-calibration-20260924/cinemadng-raw-sink-audit.md)
   為 RAW 前 `0x13400` bytes 標頭；本次 33³ 原檔的壓縮 XMP／新 IFD 增加 182,406 bytes。
   不能把離線 payload 直接塞入這個原生前綴；需要另行規劃標頭配置、owned metadata 與區段登記，
   並量錄影每幀增加的寫入量。`C069AC88` 最多 8 個區段是研究入口，不是已驗證的 LUT hook。
5. **後製 A/B。** Resolve 與 Adobe 分別測自訂保存設定、RGBTables、原生 profile tags 的組合與優先序。
   先前 Resolve 吃 HueSatMap／ToneCurve 的證據不能推成它也吃 RGBTables。
6. **MOV／JPG。** 接入編碼前的原生影像 job，量測幀率、丟幀、記憶體與原生噪聲／銳化副作用。
   完整 3D 每像素 reference 不證明主 CPU 能即時跑 UHD；不先承諾吞吐。

驗收需對相同輸入比較：LUT 關閉、完整 `.cube` reference、native backend、CDNG 解碼、MOV／JPG。
同一 LUT 的輸入校準、曝光尺度、gamma、range 必須一致，才能量色差。
上機和卡片建置沿用 [SUP_BUILD_RULES](../../fpSup/SUP_BUILD_RULES.md)；現有其他產品測試不代替本產品驗收。
