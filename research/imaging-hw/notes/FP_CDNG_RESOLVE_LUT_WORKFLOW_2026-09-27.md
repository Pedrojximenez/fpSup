# SIGMA fp CinemaDNG → Resolve → 機身 LUT：證據整理與實作流程

2026-09-27。範圍是 fp Ver.5.02 與本地既有研究；不是 fp L。此次只讀取筆記、程式、既有實驗與官方／作者文件，未操作相機、未改原始素材或 Resolve 專案。此文件是研究與設計，尚未產生或部署可用的機身 `.cube` 引擎。

**建議主線：辨識 DNG profile → 統一原廠 normal 輸入矩陣與機身校準 → Resolve 明確管理工作空間 → 獨立 look → 顯示轉換。機身 LUT 第一階段以 LCD 監看為目標，HDMI 另驗；先建立桌面參考，再選擇完整 3D LUT 或原生 ISP 近似。**

**同日補充新來源：**使用者提供 Ole Berek 2026 年 3 月的 Facebook BMD Gen5 流程，與下文 2023 年 V-Log 指南不同。已核對兩張流程圖及關鍵作者回覆，新增[獨立稽核與 2×2 驗證設計](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/notes/FP_OLE_BEREK_GEN5_WORKFLOW_AUDIT_2026-09-27.md)。它在 Film5 編碼數值上插入 Gen1/sRGB 變換，可作配色候選，但尚不足以證明通用 IDT 或 98% 色準；不能直接疊到 patched OFF 而省略比較。

「正確還原」至少有三個不同目標：

| 目標 | 驗收依據 | 現況 |
|---|---|---|
| 正確解讀 fp 輸入描述 | writer、metadata、同 RAW A/B、浮點資料 | normal CM 的來源與 Resolve 反應已驗證；完整浮點解碼仍待補 |
| 實際場景色準 | 已知光源、灰卡／色卡、獨立實景 | 尚未完成，不能把原廠矩陣直接稱為色度學真值 |
| 重現 SIGMA／某種創意外觀 | 指定 reference render 與固定顯示條件 | 屬於 look；不應偷偷混入輸入校準 |

## 1. 已有證據足以排除什麼

### 1.1 OFF、normal 與 Standard 不是同一個終點

現有 writer 與實拍檔顯示，五個標準 profile tag 分 OFF／非 OFF 兩組：

| 素材狀態 | ColorMatrix1/2 | HueSatMap1/2 | ToneCurve | 用途 |
|---|---|---|---|---|
| 原廠 OFF | OFF 專用 | identity | identity | 保留原始外觀，但輸入描述有待校準的問題 |
| 修正 OFF／C 候選 | normal | identity | identity | 本設計採用的低風格干預基線 |
| Standard 等非 OFF | normal | normal | normal | SIGMA 標準 DNG profile 渲染基線 |

normal CM + identity look **不是**「Standard 沒修完」。前者用於分離輸入描述與創意處理，後者包含非線性色彩與明暗處理。HueSatMap 也可能承擔廠商的顯色修正；拿掉它不自動等於更準，仍需色卡驗證。

非 OFF 的五個標準 tag 相同，不代表 PowderBlue、Teal & Orange、Standard 的機內畫面相同；創作模式另有私有資料與渲染路徑。查過的多模式樣本主要是 still DNG，共用 writer 提供與 cDNG 的關聯，不能寫成已完成每個 cDNG 模式的全面實拍。

來源：[模式與 writer](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/colormatrix-ab-20260923/non-off-modes-and-workflow.md)、[OFF 設計與矩陣推導](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/colormatrix-ab-20260923/off-design-assessment.md)。SIGMA 官方把 OFF 定位為供調色使用的低處理模式，這證明產品意圖，不能證明絕對色準。[官方說明](https://www.sigma-global.com/en/shooting-with-sigma/sigma_color_mode_library/)

### 1.2 Resolve 並非忽略 fp metadata

- 9/23–24：同 RAW 只改 CM1/CM2，Resolve 輸出確實改變。
- 9/25：同 RAW 的單 tag／多 tag 變體，在兩組專案設定中證明 ToneCurve、HueSatMap 也會影響 Resolve。
- 「只換矩陣佔約 4%」是某張低飽和畫面中，兩種最終 RGB 平均差的比值，**不是色準完成率**。本次相同 As Shot 解碼中，中性方向大致維持，整幀平均會稀釋飽和色變化。
- 五 tag 移植接近兩次錄影的差異量級，支持 profile 組合的解釋；不代表不同 take 逐像素等同。
- TIFF 顯示域擬合出的 3×3，不是可直接拿來製作通用 IDT／LUT 的場景線性矩陣。

9/25 的實際來源是兩 take 的 `000001.DNG`；README 所述「第 49 幀」是該靜幀在測試時間軸展開後的輸出位置，不是來源影片第 49 張。

來源：[profile A/B](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/profile-tags-ab-20260925/README.md)、[建檔來源](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/profile-tags-ab-20260925/build_variants.py:9)、[TIFF 解讀界線](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/resolve-ac-observation.md)。這些結果針對當時 Resolve 21.0.4.5／macOS 設定，不擴張成所有版本、所有 checkbox 的保證。

### 1.3 機身校準已經算進矩陣

本地 writer 稽核確認：

```text
D_body = diag(calR / 323, calG / 511, calB / 672)
CM_stored = inverse(D_body) × CM_ROM
```

`D_body` 是 Sigma 私有 CameraCalibration，不是當次白平衡；AsShotNeutral 來自另一組狀態。重建以檔內儲存的 float32 私有校準值為準；若從 calR/G/B 重算，先按 writer 量化為 float32。儲存 CM 取 SRATIONAL，分母 10000、分子向零截斷。解碼 CM 時已帶入該機身修正，不能再補一次，也不能將私有欄位盲目複製到標準 CameraCalibration1/2。

既有 A／C／297／298 樣本沒有標準 CameraCalibration1/2、AnalogBalance 或 ForwardMatrix1/2。這是樣本結果，不能推論其他 DNG 永遠沒有。BaselineExposure 也非固定：A/C 為 0，297/298 為 3；不得一律加三檔。

來源：[機身校準來源鏈與 byte 驗證](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/body-calibration-audit.md)。DNG 規格的 ColorMatrix 方向是校準光源下 **XYZ → reference camera native**；反向顯影還涉及白平衡、插值與色適應，不能只把 tag 當 camera→XYZ 直接乘。[Adobe DNG 1.7.1，頁 32–36、100 起](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf)

### 1.4 你已有的補丁必須納入流程

9/26 使用者自行修改的 OFF writer，已讓 `A001_075` 寫出 normal CM，並保留 identity HSM／ToneCurve。它不會因此改變 LCD 的顯示矩陣或建立 `.cube` 功能。

另外，現有 rawview 的 `rv_dngcm.py` 會依設定改 DNG 矩陣，README 最初的「metadata 不變」已不能概括後續所有版本。新設計必須把「輸入 profile」與「監看 look」拆成獨立狀態：切監看 LUT 不得順便換 DNG CM。

讀檔時按 tag 內容判定原廠 OFF／normal／未知變體；不能只憑 ColorMode 名稱、韌體字串或檔案日期。已為 normal 的檔案不再套 OFF 修正。

來源：[OFF 補丁及樣本](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/off-matrix-firmware-patch-20260926/README.md)、[rawview DNG writer](/Users/dido/Developer.localized/SIGMAfp_re/projects/rawview/build/rv_dngcm.py:2)。LED 實驗證明變換有作用與兩種補丁方式相容；沒有光譜量測，不能說往紫移就是更接近真實。

## 2. 歷史說法如何處理

| 說法 | 判斷與替代做法 |
|---|---|
| fp RAW 就是 sRGB／P3／BMD gamut | 不成立。RAW 感光元件座標、metadata 描述、解碼輸出空間是不同層。P3-D60/Linear 可是 decoder 輸出，不代表 sensor 原生色域 |
| 選 BMD Film，再掛 ARRI LUT，顏色就正確 | 可以產生喜歡的 look；不能据此證明輸入校準。gamut 與 gamma 要各自正確對應；BMD Gen1、4.6K、Gen5 不能混用 |
| Resolve 只吃 CM，或完全不吃 CM | 都被本地 A/B 否定；TC/HSM 行為還要記錄 RAW 面板設定 |
| OFF 必須把五 tag 都換掉 | 只有想重現完整 normal profile 才如此。低風格基線採 normal CM + identity HSM/TC，再另量色準 |
| 一張 DCTL 矩陣能修所有 OFF／白平衡 | A 與 D65 端點不同，且 decoder 的光源推算／插值會參與；優先在 metadata 層修描述 |
| 複製 BMD／Sony／Z CAM 的 sensor matrix 更好 | 即使感光元件相近，也沒有本機校準證據；只借演算法、工作色域或顯示曲線 |
| LCD 白掉就是 RAW 白掉 | 不成立；preview readout、gain、矩陣、tone、顯示 range 都可能先到頂 |
| 16-bit TIFF 足以證明未裁切 | 不成立；unsigned TIFF 不保留負值，既有樣本還有約 10-bit 量化網格。用浮點 EXR 檢查上游數值 |
| RAW 解成 Rec.709 就立即失去寬色域 | 不一定；浮點 RGB 可保留負值／超 1。真正要驗的是各階段是否 clamp，而不是只看色域名稱 |
| 拿不到 GPU/3DLUT 字串，就證明硬體沒有 | 只能說尚未找到可用路徑；不能以字串缺席作硬體不存在的證明 |

**BMD 工程師 CaptainHook（2019-10-24）**：原帖明確說非 BMD DNG 選 BMD Film Gen1 時，gamut 部分不做轉換，不能把 BMCC／Pocket 的 LUT 當 fp 校正；Rec.709 decode 則利用 DNG 兩組矩陣和 AsShotNeutral。他並說該 RAW decode／CST 的浮點路徑不會只因選 Rec.709 就裁切。這是歷史版本的一手說明，不保證目前每條 decoder 分支完全不變，但足以否定「BMD Film 名字代表已套 BMD 校準」的推理。[工程師原帖](https://www.eoshd.com/comments/topic/38460-sigma-fp-review-and-interview-cinema-dng-raw/?comment=324559&do=findComment)

**Michael Garrett（2023）**：正確指出 OFF metadata 與監看不一致的問題，也明說 Adobe Standard 是暫時繞道。其「未特徵化／忘記更新 tag」屬當時推測；後續本地研究已找到 OFF／normal 明確分支與 normal 常數。文件把 CM 方向簡寫反了，並把 Resolve 使用 LibRaw 當成前提，後者本輪未確認，不能沿用。他的色卡也明載非受控光源。來源：[原始 PDF，頁 2、4、5、11、12](</Users/dido/Downloads/954594137-SIGMA-Fp-Color-Workflow-Feedback-sm.pdf>)。

**Ole Berek v3（2023）**：曝光分配、高光曲線、四面體插值可作工作流參考。其 v3「超過 Rec.2020 的 fp gamut」不是本地已驗證的 sensor 特徵化。文件第 7 頁實際是 P3-D60/Linear → Panasonic V-Gamut/V-Log → 對應 LUT；這是一套有指定輸入的 recipe，不能省掉前轉換，也不能拿 Atomos 監看 LUT 直接套 LCD 的 OFF 訊號。文件第 6 頁「FCP 加 analogue gain」用語不精確：已錄檔案的軟體操作不會改變當初感光元件的類比增益。來源：[原始 PDF，頁 2、4–8](</Users/dido/Downloads/SIGMA fp Rec709 LUT & Operations Guide v3.pdf>)。

**Ole Berek（2026-03，新方案）**：P3-D60/Linear → BWG/Film5 → 刻意按 Gen1/sRGB 重新解讀與變換 → 按 BWG/Film5 轉到 DWG/DI。中間兩側 gamma 相同不代表有色像素的非線性處理消失；中性灰可能近似直通，整鏈仍非普通連續 CST。保留為可驗證的相機配色方案，另外比較原廠 OFF 與 normal CM；沒有將其「98%」視為有定義的量測數字。[原文](https://www.facebook.com/groups/1124721801045663/permalink/3067172403467250/)、[完整參數、限制與 LUT 分支](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/notes/FP_OLE_BEREK_GEN5_WORKFLOW_AUDIT_2026-09-27.md)。

**SIGMA 的 Dual Base ISO 白皮書（2020）**：12-bit CinemaDNG／HDMI RAW 基準是 ISO 100／3200，8/10-bit CDNG 與 MOV 為 100／640。ISO 800 的曝光分配有官方建議，但不是新 sensor base，也不能由 post 的 ISO 滑桿重現硬體切換。白皮書未直接建立 Ole 文件中每個 1/3 檔的完整實測表。來源：[若松原始白皮書，頁 2–4](</Users/dido/Downloads/SIGMA fp Dual Base ISO technology (EN).pdf>)、[SIGMA fp 手冊頁 170](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN_2.pdf)。

## 3. Resolve 主流程：先得到穩定的輸入

### A. 整理素材與 profile

1. 原片保留；記錄相機／韌體、錄影格式、真正位深、ISO、AsShotNeutral、BaselineExposure、BlackLevel、WhiteLevel、CM/HSM/TC 及 RAW payload hash。
2. 原廠 OFF：在工作副本用該檔的機身校準與 normal ROM 常數重建 CM1/2；HSM/TC 保留 identity。缺少或未知校準資料就標記未支援，不借另一機身數字代入。
3. patched OFF：驗證已是 normal CM 後直接使用。
4. Standard／其他非 OFF：保留原 profile 可作 Standard 外觀參考；若要與 corrected OFF 共用低風格基線，另建副本只將 HSM/TC 正規化為 identity。這是選擇渲染基線，不是聲稱刪掉 profile 後必定更準。
5. 正規化須冪等；第二次執行不再變更。驗證所有 RAW strip/tile hash，僅允許預定 tag 改變，記錄完整 manifest。縮圖可能仍呈舊外觀，不能用縮圖判斷 RAW 解碼。

### B. 保留你現在的 RCM 工作流

- Color science：DaVinci YRGB Color Managed，固定自訂設定，不讓不同專案自動換一套預設。
- Timeline：DaVinci Wide Gamut / DaVinci Intermediate。
- Input DRT：None，避免輸入階段先做 tone mapping；這不會停止色彩空間轉換。
- SDR 參考輸出：Rec.709 / Gamma 2.4，固定顯示／輸出映射與亮度條件。Mac/QuickTime 顯示管理另核對，不把 Rec.709-A 當 sensor 校正。
- RAW：保留當前可驗證的 CinemaDNG 解碼基線，WB 從 As Shot 起步；對照時固定曝光、Highlight Recovery、預製曲線／embedded profile 狀態、其他 RAW 調整。
- **RCM 會根據 RAW 路徑自動管理輸入，不要因專案寫 P3 就再加 P3→DWG 的 CST。** 直接置於此工作域的 LUT 須吃 DWG/Intermediate；其他輸入契約需成對轉換。
- 基線驗證時先關 Highlight Recovery；需要時逐鏡頭加回，它可能重建缺失通道而改變顏色，不能算作真實色彩量測。
- 已正規化 TC/HSM 的素材可減少對不明勾選框行為的依賴；仍以同 RAW tag 對照確認 TC/HSM 在目前設定中的作用。是否另有共同非線性處理，另以浮點線性參考、曝光比例及灰階測試核對。

Resolve 21 官方手冊頁 235 說明 RAW 自動輸入管理；頁 181 列 CinemaDNG 解碼選項。[本機官方手冊](</Applications/DaVinci Resolve/DaVinci Resolve Manual.pdf>)。本輪未操作 UI；不把網友提到的 ACES/Linear 新選項當成已確認的本機設定，改選 ACES 也不會修復錯誤 CM。

### C. 明確節點鏈與烘焙用分支

日常 RCM：

```text
已識別／正規化 DNG
  → RAW 解碼與 RCM 輸入轉換
  → DWG/Intermediate：曝光、WB 微調 → creative look
  → RCM 顯示轉換 → Rec.709 Gamma 2.4
```

為了逐值驗證及製作 LUT，另開 **非管理 DaVinci YRGB** 測試專案：

```text
Camera RAW：P3-D60 / Linear
  → CST：P3-D60/Linear → DWG/Intermediate（Tone/Gamut Mapping=None）
  → 每鏡頭曝光／WB（不併入通用 look LUT）
  → look
  → 一個明確的 display transform（含所需 tone/gamut mapping）
  → Rec.709 Gamma 2.4
```

這兩套是不同專案模板，不能同時開 RCM 又照抄整條手動 CST。若把已映射為 709 的監看 LUT 放在 RCM 的 DWG 節點，還讓 RCM 再輸出一次，會重複轉換。

「LogC／V-Log 比較好看」可以在已知工作空間後加入正確的轉換，再使用要求該輸入的 look。只選 gamma、不核對 gamut，或把平淡影像重新指定為更寬 gamut，都不算輸入校準。

## 4. 把數學正確與畫面好看分開驗收

建立三組測試，每組只回答自己的問題：

| 測試 | 方法 | 成功條件 |
|---|---|---|
| metadata／decoder | 同一 RAW 的 CM、HSM、TC 單變因；另測 A/D65 端點及中間 WB | 讀取與作用可重現；不以不同 take 當零誤差對照 |
| 場景還原 | 已知穩定寬頻日光／鎢絲光，灰階、色卡、膚色；不同曝光；另測獨立 LED 場景 | 相同 XYZ／白點下比較；報 ΔE00 分佈、灰階中性、曝光穩定與飽和色異常 |
| 輸出顯示 | 固定 DRT，浮點 reference、LUT、機身 digital capture、實體 LCD 分別比較 | 區分 decoder 誤差、LUT 插值誤差、硬體量化、面板誤差 |

色卡目標須匹配實際光源與色適應；不能在未知室內光下與網路色塊比一次，就稱絕對準確。矩陣拟合用一組樣本，驗收用未參與擬合的樣本。窄頻光源是壓力測試，不能保證雙光源 3×3 能消除所有同色異譜問題。

數學驗證輸出選浮點 linear EXR、保留負值與 >1，不套 display transform；回讀檢查灰階與飽和 RGB 的完整範圍。EXR 容器本身不保證上游未裁切，所以還要測在顯示轉換前降低曝光，能否恢復原本不同的亮部值。不要用已經 tone-mapped 的 TIFF 反解一條 gamma，冒充原始 scene-linear。

## 5. `.cube` 的契約先固定

### 5.1 桌面標準交付兩種，不混用

| 檔案類別 | 輸入 | 輸出 | 包含內容 |
|---|---|---|---|
| `Look_DWGDI_to_DWGDI_v001.cube` | DWG / Intermediate | DWG / Intermediate | 只有創意調色，適合 RCM 節點 |
| `Monitor_DWGDI_to_709g24_v001.cube` | DWG / Intermediate | Rec.709 / Gamma 2.4 | look + 指定顯示轉換，適合可提供該輸入的監看管線 |

以上是**預定名稱與契約**，尚未生成。sensor→工作空間、per-body 校準、雙光源白平衡、黑白位準和 ISO 正規化由上游處理，不烘成一張假定固定光源的通用 LUT。

每個 LUT 附 manifest：版本／hash、input/output primaries/white/transfer、domain、格點、插值、profile 基線、DRT 版本、是否含 display transform、支援曝光範圍、來源專案。`.cube` 本身不能可靠傳達完整色彩管理語意，檔名與註解也不能讓播放器自動猜對。

### 5.2 Resolve 製作

1. 先把校準與正常曝光做在 LUT 外，固定工作空間。以灰階、膚色、飽和漸層與實景設計 look。
2. look-only 匯出時只保留創意節點；monitor 匯出另包含一次顯示轉換。別把所有 clip correction 不加區分烘进去。
3. Resolve 官方匯出支援 Primaries、Custom Curves 及相容 ResolveFX，例如 CST、ACES Transform、Gamut Mapping。含 qualifier／window／銳化模糊或不相容 FX 的節點可能整節點被忽略；DCTL 不能概括保證可由 Generate LUT 完整匯出。
4. 降噪、grain、halation、時域／空間效果不能由單純 RGB→RGB LUT 表達。要保留這些就另交 PowerGrade；可逐像素表達的 DCTL／DRT 則由明確的數學 evaluator 取樣，或驗證實際 exporter 支援後再使用。
5. 先以 65³ 作離線高密度參考，再比較 33³／17³；插值採四面體作起點，但仍量測誤差。不要把 scene-linear 的 0…1 均勻格點直接當完整動態範圍容器。
6. LUT 重新匯回空白驗證專案，對同一批 test vectors／影像比對原節點輸出。檢查輸入 domain、超界行為、黑位、中性軸、飽和高光與格點間中點；不是只看一張人物照片。

來源：Resolve 21 Reference Manual 頁 3551–3552。[本機官方手冊](</Applications/DaVinci Resolve/DaVinci Resolve Manual.pdf>)。這裡的 bake 僅代表已知 RGB 域內的映射；不包含 RAW 解碼、demosaic 或可依鏡頭改動的 metadata。

### 5.3 接入 Ole 2026：可選的 profile 配色模組

**可以納入同一套 LUT 架構。** 已知 CST 子鏈是固定的逐像素 RGB→RGB 變換，在約定的數值域及誤差範圍內可取樣成 3D LUT。先把它當作依輸入 profile 驗證的配色模組，與一般創意 look 分開管理。對 corrected OFF 的預設仍 bypass，待 2×2 驗證後才決定是否啟用。

共用處理順序：

```text
輸入與動態前處理：黑位、WB、曝光／ISO 正規化、相機校準
  → 已驗證的 DWG/Intermediate
  → Ole 2026 配色模組（可選；綁定輸入 profile）
  → 個人 creative look（可選）
  → 一次 display transform
  → LCD／HDMI 各自的輸出編碼與校正
```

Ole 模組內部固定為：

```text
CST：DWG/Intermediate → BMD Wide Gamut Gen4/5 / Film Gen5
  → Q：Input Gen1/sRGB → Output sRGB/sRGB（刻意重新解讀數值）
  → CST：按 BMD Wide Gamut Gen4/5 / Film Gen5 → DWG/Intermediate
```

兩端 CST 不加 tone/gamut mapping 或 OOTF；前端必須是原 Node03 的逆，此例兩端 White Point Adaptation 關。上游需對應原方案的同一 RAW/profile/WB/曝光及純工作空間轉換，才可談等價；經過另一套 input tone mapping 的 DWG 值不能直接假定相同。完整設定與原圖見 [Ole 2026 稽核](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/notes/FP_OLE_BEREK_GEN5_WORKFLOW_AUDIT_2026-09-27.md)。

| 交付 | 輸入／輸出 | 放置位置 |
|---|---|---|
| 桌面 recipe cube | DWG/DI → DWG/DI；只含上述 Ole 子鏈 | RCM 工作節點，後面仍由 RCM 做一次顯示轉換 |
| 通用監看 cube | DWG/DI → 指定顯示輸出；Ole + 選定 look + DRT | 確認能提供 DWG/DI 的監看路徑，後面不再加 DRT |
| 機身編譯產物 | 實際 body tap → 指定 LCD／HDMI 輸出 | compiler 合成輸入 adapter、Ole、look、DRT 與必要輸出 adapter；依模式驗證 |

這三類是設計中的產物，尚未生成。若 LCD／HDMI 需要不同 adapter 或顯示目標，產生不同版本，不能共用一張表後只改 range 標籤。忠實重現作者 DRT 的 Rec.709/Rec.709 版本，與本設計的 Gamma 2.4 版本另名，不能混稱相同。

主機端保留高精度函數／節點 reference，把可固定的各階段先合成，再一次取樣目標 cube；機身不需要真的連跑數個 CST，也避免多張低密度 cube 串接累積插值誤差。若以已匯出的 cube 作為中間來源，須另記錄其密度、插值與累積誤差，不能稱為直接從高精度函數取樣。動態 WB、黑位與曝光處理仍在 LUT 外，依既定次序放在 Q 前，不能移到 Q 後假定等價；若 adapter 必須依模式或其他狀態更換，runtime 明確選擇對應產物，不用一張表掩蓋差異。

「Ole 開／關」以同 adapter、同 look、同 DRT 的成對產物切換，只變 Q。不能用 bypass 整張 monitor cube 來冒充只關 Q，否則必要的輸入／顯示轉換也一起消失。「回原生監看」是另一個獨立狀態。

manifest 另外標記 `recipe_id`、`recipe_version`、`input_profile_id`、`adapter_id`、`display_transform_id` 與驗證狀態。至少區分 original OFF、normal CM + identity HSM/TC、完整 normal profile；Q 不因選單寫 OFF 就自動啟用。機身監看模組切換不修改錄影 DNG 的 CM/HSM/TC，也不把 profile 正規化功能綁到 look 開關。

`input_profile_id` 須能追溯 CM/HSM/TC、BaselineExposure、RAW 解碼版本與設定、曝光正規化位置及已驗證 WB／曝光範圍。Q 的邊界測試涵蓋負值、超 1、跨通道矩陣產生的出界與飽和漸層；中間 DWG/DI→DWG/DI 表不能預設輸出全部在 0..1，只有已確認有界的最終監看表才量化成相應 uint16 格式。

實作沿用 §6.2 的兩條路：軟體 3D LUT 可重現取樣後的函數；原生 ISP 的 matrix／tone 路線只能先擬合並報殘差，未達門檻就不能標為 Ole 等效。若可取得的 body tap 已做不可逆裁切或其他未知處理，須找更上游來源，不能假設 adapter 能完整還原。

接入驗收按順序做：① 同 RAW 的原廠 OFF／normal CM × Q 開／關；② 原節點對桌面 cube 回讀；③ body adapter + cube 對桌面 reference；④ 實際 LCD／HDMI 顯示與錄影共存。Highlight Recovery、RAW 解碼、未知的 FILM GEN/FPE 節點不自動包含在這個已知子鏈中。

## 6. 機身端目前實際能做什麼

官方 fp FW5 手冊／選單未列使用者 `.cube` 匯入；本地也尚未建立可直接執行任意 `.cube` 的引擎。因此這是 fpSup 功能開發，而非把檔案複製到卡片即可使用。[官方手冊](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN_2.pdf)

rawview 已有原生 tone／matrix 路徑和選單整合，能作為開發基礎，但需先解決三項前提：

1. **活動模式／位深**：已有 UHD 實際為 8-bit、設定欄位仍像 12-bit 的紀錄；不能只看設定 `+0x788` 啟用 12-bit 增益及曲線。待機、錄影、解析度切換各自核對真正狀態。
2. **色溫與機身適用性**：`rv_color.py` 現有矩陣使用固定 CM2 樣本；不能直接當成跨 WB、跨機身通用校準，須改為已驗證的本機資料與雙光源模型。
3. **上游截斷**：先確認實際 preview source、gain、WB、matrix 後的範圍。上游已剪成平台，後面再套 cube 也無法救回。

來源：[rawview 進展](/Users/dido/Developer.localized/SIGMAfp_re/projects/rawview/README.md)、[固定 CM2 實作](/Users/dido/Developer.localized/SIGMAfp_re/projects/rawview/build/rv_color.py)、[上游截斷稽核](/Users/dido/Developer.localized/SIGMAfp_re/research/liveview/upstream-clip-audit.md)。

目前 rawview 的 SA／GA 是本專案定義的顯示映射，不能當作 V-Log／LogC 的別名。現行 matrix 控制只剩 0／1 兩級，也不應沿用 README 舊版的多級設定。詳見 [rv_tables.py](/Users/dido/Developer.localized/SIGMAfp_re/projects/rawview/build/rv_tables.py:4)、[rv_color.py](/Users/dido/Developer.localized/SIGMAfp_re/projects/rawview/build/rv_color.py:69)。

### 6.1 理想的共用色彩契約

```text
preview RAW（確認與錄影的模式、黑白位和增益關係）
  → 黑位／線性化／WB／demosaic
  → 本機校準與相機色彩轉換
  → 已定義的工作 RGB，曝光正規化
  → 適當 shaper／log encoding
  → look + display transform
  → 分支：LCD 校正／編碼；HDMI RGB↔YCbCr／range
```

這是**設計契約**，不是已證明 fp 的硬體逐級順序。若 native 管線無法產生 DWG/Intermediate，就由 host compiler 把「实际輸入座標→工作空間→look→目標顯示」合成 body 專用表／參數；不能只改檔名說它是 DWG。

WB、黑位與 ISO 增益在 LUT 前；如果實際機身 tap 必須依 ISO/模式換表，交由 compiler/runtime 產生並標記。已做統一曝光座標的創意 look，不必因 ISO 數字改變就換一種色彩風格。

LCD 與 HDMI 的 transfer/range 分別量測。內部 YCbCr 權重、HDMI 訊號標記與 display primaries 不是同一件事；不能看到 Rec.601 係數就認定 sensor gamut 為 601，也不能只貼 Rec.709 標籤便稱完成。

### 6.2 路線選擇

| 路線 | 能力 | 開發判準 |
|---|---|---|
| 原生 ISP 擬合 | 用已確認的 matrix／tone 等區塊近似 look，對現有 rawview 改動較小 | 每個 LUT 都要評估殘差；只能把驗收通過的 look 標為支援 |
| 軟體 3D LUT | 可忠實實作取樣後的任意 RGB→RGB cube | 先找可靠 RGB/YUV tap、buffer 所有權與顯示輸入；量測 CPU／頻寬／錄影共存，不能預先承諾幀率 |
| 外接監看器 | 設備若支援自訂 LUT，可先驗證完整 look | 必須先確認 HDMI 實際輸入編碼；不是把 body 問題自動解決 |

建議先做 host 的正確 cube evaluator 與 native ISP fit feasibility，並行做小解析度軟體 3D LUT benchmark。若必須支援任意 `.cube`，而 ISP 擬合未達門檻，就進軟體路線；不把近似當成完整支援。

軟體原型可從 320×180、5 fps 開始量測再逐步提高，這是測試設定，不是已達效能。現有 RAW false-color 的 completed-frame callback／worker 可供參考，但 palette overlay 與約 21.7 次/秒 drawer cadence 不證明真彩 LUT 可同速運行；還須找到適當精度的 RGB/YUV 呈現面。舊 host rawview 的 percentile stretch／以 frame max 正規化會讓 LUT 輸入隨畫面改變，不能作色準 reference。[假色原型界線](/Users/dido/Developer.localized/SIGMAfp_re/research/display/RAW_FALSE_COLOR_IMPLEMENTATION.md)、[舊 host renderer](/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/fpshell_tool/monitor/rawview.py)

CUVAREA／RGBMAT_PL 的名稱提供研究線索，尚無完整參數與輸入輸出語意；只有實際證明其作用後才能加入擬合器。尤其不能因兩組 9 係數便直接假設它們是兩個串聯 3×3。

## 7. 機身 `.cube` loader／compiler 設計

### 主機工具

1. 讀 `.cube`：支援明定的純 1D 或純 3D 格式、TITLE、DOMAIN_MIN/MAX；對未知混合 1D+3D／擴充語法明確拒絕或先由 host 轉換，不靜默猜測。
2. 驗证 N³ 筆資料、有限值、domain 大小、R/G/B 順序、檔案上限；用 identity、channel permutation、非对称診斷 LUT 驗證 R 最快索引。
3. 同時保留 floating reference；不能在 parser 把所有負值／>1 輸出直接夾掉。只有確定目標輸出契約有界，才轉成相應 fixed-point。
4. 以實際 body tap 的 adapter 合成 LUT 或擬合 ISP 參數；受硬體係數範圍、表長與量化約束。
5. 產生二進位、manifest、支援模式、reference vectors、誤差熱圖。硬體近似要報 mean/p95/max 與最差色塊，不能只報平均。

### 記憶體與算力預算

下表只算 RGB 三通道 uint16 表值，尚不含 shaper、padding、manifest 或 framebuffer：

| 格點 | 格數 | 單表大小 |
|---|---:|---:|
| 17³ | 4,913 | 29,478 bytes，約 28.8 KiB |
| 33³ | 35,937 | 215,622 bytes，約 210.6 KiB |
| 65³ | 274,625 | 1,647,750 bytes，約 1.57 MiB |

33³ 雙表約 421 KiB。現有 boot BIN 的 61,440-byte 限額不是全部可用 RAM；不要把 33³ 表硬塞其中。loader/runtime 放 boot 模組，LUT 作獨立檔，在初始化或安全時點載入自有緩衝。

720×480×30 約 10.4 Mpixel/s，1080p30 約 62.2 Mpixel/s，只是需處理的像素量，不是實測效能。還需計算 YUV/RGB 轉換、插值、cache miss、讀寫與拷貝；先從 LCD 所需解析度量測。

### Runtime

- 在 worker／安全載入階段讀檔、解析／驗證；逐幀 callback 不做檔案 I/O、不做大配置。
- active/inactive 雙表或等效原子切換；確認完整載入、版本、尺寸與校驗後，於幀邊界切換。解析失敗保留舊表或 bypass。
- 只使用確認可擁有的緩衝與 display 路徑；DMA/cache/對齊按已知平台規範處理，不能拿錄影 buffer 原地改色。
- look toggle 不更動 Bayer 或 DNG CM/HSM/TC；profile 校正是另一個有版本的固定功能。
- 切模式、錄影開始／停止、重開機、錯誤狀態都可回原生顯示。未驗證模式顯示「未支援」並 bypass。
- 第一階段先驗 LCD；HDMI 非 RAW 監看另驗。HDMI RAW 是不同協定／路徑，不能將它視為已烘 LUT 的 RGB 影片。
- 波形／false color 明確標示讀 LUT 前或後；sensor clipping／RAW 曝光工具應來自 LUT 前的有效來源，避免 look 肩部讓曝光警示失真。

## 8. 實作順序與完成門檻

| 階段 | 交付 | 通過條件 |
|---|---|---|
| P0 基線 | profile 檢查／正規化規格、Resolve 模板、素材 manifest | 識別原廠／patched OFF、處理冪等、RAW hash 不變，固定解碼可重現 |
| P1 桌面 reference | look-only 與 monitor cube、source node graph、測試圖 | 匯出再匯入與 evaluator 相符，無漏節點／重複 DRT |
| P2 機身 feasibility | tap/encoding 測試、模式 gating、ISP 擬合結果與軟體 benchmark | 確認活動模式、範圍、buffer 所有權；量化色差與幀時間，有足夠錄影餘裕 |
| P3 LCD MVP | 一個 verified profile + 一個 supported look + bypass | LUT on/off 不改錄影色彩 tag；參考圖一致，連續錄影與切模式無回歸 |
| P4 擴充 | HDMI、其他 ISO/位深／解析度、任意 cube 相容性 | 每條輸出各自通過 range、色彩、效能測試，不以 LCD 成功代替 HDMI 成功 |

暫定工程門檻可先訂「無明顯 banding／中性偏色、灰階連續、95% SDR 測試樣本 ΔE00 <2、最差樣本另列、長時間錄影零新增掉幀」。這只是**待確認的驗收規格，不是目前成績**；最差飽和色若失敗就不能藏在平均值裡。軟體／ISP 跟 reference 的誤差和相機對真實場景的色準要分開報。

測试最少覆蓋日光／鎢絲光／窄頻 LED、低／高 gain 分支、ISO 100/800/3200、灰階与 RGB/CMY 漸層、過曝階梯、待機／錄影切換，以及支援的實際位深。10/8-bit 未完成自己的量測前，不沿用 12-bit 的曝光規則。

## 9. 筆記衝突索引：實作時不可照抄

本輪保留歷史筆記原文，用這份索引標記限制，避免抹去研究脈絡。

| 舊筆記說法 | 應採取的解讀 |
|---|---|
| `COLOR_SCIENCE.md` 把 private calibration 寫成 as-shot WB | 依 9/24 body-calibration audit 更正，見 §1.3 |
| 同檔「無 HSV LUT／無 hue rotation」、profile resource 全在 runtime | 不能泛指 DNG：後續已找到 ROM HSM/TC 與 non-OFF 標準 profile；native ISP look 另待證 |
| 9/25 README「4%」「純線性」「等同 Standard」 | 依 §1.2 限縮為指定場景／輸出域的反應，不等於色準或精確 IDT |
| 9/27 ISP 表將 `C0107250 / 30210C78` 寫成 RGBLMAT | descriptor 稽核指它屬 IGAMMA；RGBLMAT 主區在 shadow `30210CB0..CE4`。不能按最新日期直接採信 |
| 名稱表直接推定 CUVAREA 就是 FCBlue | 沒有控制變因與像素證據，僅保留為候選 |
| rawview 開頭「metadata 不變」 | 後續 `rv_dngcm.py` 已有 CM 更新；以實際版本／讀回 tag 為準 |

地址來源：[descriptor 與矩陣稽核](/Users/dido/Developer.localized/SIGMAfp_re/research/liveview/matrix-gamma-audit.md:16)、[存在衝突的 ISP 名稱清單](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/isp-colour-blocks-20260927/README.md)。本設計不根據未證映射提出寄存器寫入值。

下一個最有價值的產物是 **profile 檢查器＋固定 Resolve 基線＋一組有明確 I/O 的 LUT reference**。這三項建立後，機身工作的問題才可量化為「在哪個輸入域、以多少誤差、多少時間重現這個已知函數」。
