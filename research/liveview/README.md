# SIGMA fp LCD：避免色彩提前截斷的研究結論

2026-09-24；SIGMA fp 5.02；本輪為離線韌體、原始曲線與既有實驗檔案稽核，沒有操作相機。

正式研究目錄：`research/liveview/`。整體規劃：[rawlive — RAW 即時還原](../../projects/rawlive/README.md)；相機端實作與 fp 快照：[rawview](../../projects/rawview/README.md)。本目錄維護相機處理路徑、實驗證據與跨機型對照。

## 上游追查更新（2026-09-24）

新報告：[Tone 之前的上游截斷追查](upstream-clip-audit.md)。使用者提出的 bin／vbin 線索已核到 preview／record 分開的設定鏈；19,890 個 profile 欄位與 500 個 mapping 均與 ROM 相符。17 列原廠 template 設 preview 3×3、record 1×1，既有待機紀錄則是 small_raw 1×1。

兩組原生 bin 核按無符號欄位解讀皆非負、係數和固定；若硬體採同樣解讀並正常歸一化，不應自行產生 overshoot，但 ASIC 位寬／shift 與活動像素尚未量到。已排除把 RAWOUT 的 `1FFF0000` 空間裁切欄位誤當亮度上限；另訂正 `30112740/44` 為 TBLSD gain，並發現原生矩陣降增益不是全部係數等比縮放。**目前仍不能證明或排除 tone 前已發生 pixel clipping，來源驗證須優先於換 tone。**

詳細：[bin／vbin 與 preview](preview-reduction-audit.md)、[RAW 前端](raw-front-audit.md)、[matrix／gamma](matrix-gamma-audit.md)、[既有擷取證據](capture-evidence.md)。

## 對照組：BMCC 6K／Rec.709（2026-09-24）

新整合 [BMCC 6K 對照研究](../../bmcc6k/notes/FP_LIVEVIEW_COMPARISON.md)：已解開外層韌體與 colour-science datapack，恢復相機專屬 Rec.709 設定、91 條 ISO 曲線、校準矩陣和 33³ 監看 LUT。mode 2 的 Film 曲線與官方 Gen 5 公式高度吻合，但核心程式未解開，執行順序仍未知。

這組資料補上可重現的高光肩部與跨通道轉換對照。**BMCC 校準、ISO 表及 Film LUT 不能直接套在 fp 的 Bayer／線性 RGB／已處理預覽上**；來源、色域、編碼與範圍須先確認。完整資料與重現工具已歸入 [bmcc6k](../../bmcc6k/README.md)，BRAW／CDNG 結果也一併收錄。

## 對照組：Z CAM E2-F6（2026-09-24）

同樣用 IMX410 的 Z CAM，監看轉換是明文 GLSL：ZLog2 解碼 → ×12.8 → 單一 3×3 → 1024 點顯示表（每台機器有面板校正檔），**+3.65 檔硬切、沒有色域壓縮**。詳見 [zcam-e2f6-reference.md](../../zcam_e2f6/notes/FP_LIVEVIEW_COMPARISON.md)。

## 結論

**合理的目標是：RAW 尚有差異的高光與飽和色，不要在監看處理中過早變成一整片相同顏色；正常範圍內的色彩則有可驗證的顯示轉換。**

最有依據的方向是 **在第一個不可逆限幅之前保留監看訊號餘量，再做平滑高光壓縮與色域壓縮，最後校正 LCD 的矩陣、訊號範圍與顯示曲線**。單獨把某條 tone 換成直線、換成 Log，或降低 LCD 背光，都不足以保證達成。

本輪已找到可以追查的原生處理入口，但**還沒有量到第一個實際丟失像素差異的位置，也沒有可宣稱修好的相機 patch**。靜態反編譯中的控制參數範圍，不等於已量到像素 clipping。

## 1. 先前實驗真正改了什麼

原始檔案重新找到於 `/Users/dido/Documents/Codex/2026-08-16/4/`。下述結論只適用於找到的版本，不排除另一個任務還做過其他 linear 實驗。

| 找到的版本 | 實際內容 | 本輪核實結果 |
|---|---|---|
| `AutoRun_NoClipTone_Test.txt` | 兩個 tone descriptor 指標改指 ROM `C09A2F34`，ID50／family 5 中心 | **並非沒有平台**。index 1919…2046 全是 8190，只有最後 index2047 變8191。舊 README「一路遞增到100%」不成立。 |
| `AutoRun_Stretched_ID83_Test.txt` | 將 ID83 的有效輸入 0…1918 插值拉伸到 0…2047 | **不是 identity / y=x**。是 `T83(x × 1918/2047)`，保留原曲線的非線性外觀。已從腳本解析全部2048點，與公式完全一致。 |
| 多版 `ClipToBlack`、`OnlyCode2047Black` | 將特定 LUT 輸入範圍輸出黑色，作可見警示 | 可研究該級輸入何時到頂；不能直接當成感光元件 RAW clipping 的證據。 |

例：拉伸版在輸入 index1024 輸出 **6024**；同刻度 identity 約 **4097**。兩者差很多。

ID83 (`C09C3F34`，zero-based index82，ROM編號83) 原曲線在1918後到頂。把這段延長到2047，在**曲線輸入座標假設線性**時只多出 `log2(2047/1918) = 0.0939 stop`。這不等於實測 LCD 比 RAW 多了0.0939 stop，更不能解釋或修復數檔監看餘量差異。

原廠88條表全部重讀並驗證 index 指標、編號、長度、單調性與範圍；MAIN與seg0的整段表hash相同。特別避免只檢查「最後一點是否8191」：ID50正是會因此被誤判的例子。

來源與重算資料：

- [原始拉伸曲線產生器](/Users/dido/Documents/Codex/2026-08-16/4/work/generate_stretched_curve_autorun.py:13)
- [原始 NoClip 說明](/Users/dido/Documents/Codex/2026-08-16/4/outputs/NoClipTone_Test_README.md:3)
- [本輪歷史實驗稽核](historical-curve-audit.json)
- [88條曲線稽核](tone-audit.csv)、[完整歷史證據](prior-evidence.md)

## 2. 舊研究中需要修正的部分

舊 `COLOR_SCIENCE.md` 的部分硬體命名錯置。重新核對韌體自身的dump字串與shadow-register mapping：

| 區塊 | 本輪確認的位址 |
|---|---|
| IGAMMA | `30115000` |
| RGBLMAT | `30115100` |
| YCMAT | `30115A00` |
| GAMMA_TABLE 控制區塊 | `30115B00` |
| C_SAT_C | `30117B00` |

`C0107250` 是IGAMMA分段參數處理；真正兩組矩陣係數處理在 `C01073A0/C0107548`。所以原總圖的精確先後與「主tone一定在YUV域」不能只靠舊摘要認定；位址排列也不自動等於像素處理順序。

另外，9月24日的色彩研究已找到多組原生創意RGB矩陣；舊文「矩陣不隨mode變、沒有相關色彩資源」等過強描述不能繼續當前提。DNG metadata 中的 normal ColorMatrix 與 ISP 的RGBLMAT是不同層；修DNG標籤不會自動修LCD。

直接來源：[韌體區塊名](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:50117)、[原生矩陣路徑](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/native-calibration-20260924/normal-cm-consumers-and-render-base.md:32)。本輪細節見 [ISP稽核](isp-path-audit.md)。

## 3. 現在真正找到的兩組入口

### A. 影像處理端：tone與矩陣／增益

`C02D29E0` 已追到真正的曲線選擇、暫存、descriptor與SIGSEQ排程。它由多個PictureQuality入口共用，分兩個context，依mode與其他設定使用一條或三條表。

這帶出三件實作上的重要事：

1. 改了記憶體指標，不代表硬體正在用它。必須驗證當幀descriptor、實際表內容及排程更新。
2. 舊拉伸版寫入的 `C3414DA8` 是原廠另一context的tone暫存路徑會用的地方，不能因舊註解稱它空閒／non-cache就直接重用；還要處理表更新與cache發布。
3. 尚未把兩context完整對應到LCD、MOV、待機、錄影。不能把共用tone資源或descriptor修改稱為「只改監看」。

原生 `C032EC70→C032EFA8` 存在將增益分配到 **TBLSD** 與矩陣係數的邏輯；可作追查監看前級餘量的入口。後續核實第一組矩陣只縮放三項、第二組才全部縮放，不能直接當成所有顏色共同衰減。它是否改到錄製資料、何時被覆寫，也仍需依當前模式確認。見 [上游矩陣稽核](matrix-gamma-audit.md)。

### B. LCD末端：有獨立的矩陣與三通道gamma

已找到明確的LCD driver路徑：

`LCD JDI driver C0308658 → C0625F68 → matrix state → active-output bank → display CSC`

以及另一條RGB gamma路徑：

`C00DDA20 → C00DDB50 → C00E3AF0`

預設資料為三組相同的16個值 `16,32,…,240,255`，符合identity型末端校正表。確切節點位置與插值仍需驗證，不能當成任意3D LUT。

CSC可見601-like與709-like兩組係數，依輸出路由選bank。**這證明有可校正的末端，不證明LCD正在用錯範圍或矩陣。** 必須確認來源YUV定義、active bank、chroma offset、full/limited levels，才能判斷有沒有範圍轉換造成的額外截斷。

這一段適合做螢幕白點、灰階與矩陣校正；如果輸入影像已經剪平，末端gamma只會把同一塊白變成同一塊灰，無法恢復細節。

詳細位址與證據見 [LCD末端稽核](display-route-audit.md)。

## 4. 解法必須依截斷位置決定

| 實測現象 | 支持的方向 | 應修哪裡 |
|---|---|---|
| RAW本身某通道已飽和 | 拍攝訊號已丟失；不能靠LCD恢復正確色彩 | 曝光／採集；監看另標示RAW通道飽和 |
| RAW保留差異，tone輸入已到頂 | 白平衡、增益、矩陣或更早的preview處理可能先限幅 | 第一個clip之前保留headroom；也檢查preview與record採集是否不同 |
| tone輸入仍有差異，tone輸出合併 | 活動曲線／曲線輸出量化造成 | 改活動context的tone映射，保留灰階及彩色階調 |
| LCD輸入仍有差異，CSC後通道剪平 | matrix/range不匹配或輸出色域不足 | 正確轉換範圍，再於限幅前壓縮色域 |
| 數位LCD輸出有差異，實體面板卻分不開或偏色 | 面板transfer/gamut/亮度與觀看環境 | 面板量測與末端校正 |

以上是可被測試否證的分支，並非本輪已判定的根因。

## 5. 我建議的監看設計

下面是設計需求，不是已證實能直接對應fp硬體的現成處理順序：

```text
仍保留差異的監看來源
 → 黑位、白平衡與正確的色彩轉換（中間值要容得下）
 → 高光柔和壓縮 + 針對顯示色域的色彩壓縮
 → LCD目標transfer與正確code range
 → LCD白點／灰階校正
 → 實體面板
```

- **保留headroom**：若限制是正通道到頂，可在該限制之前共同縮小三通道，保留比例，再用較合適的曲線呈現中間調。若矩陣後負值已被截到0，單純縮小正值不會解決，還需要處理色域邊界／矩陣基底。
- **柔和高光**：不要把還有差異的一段輸入全部指定成同一個白。以平滑肩部保留可辨的階調；並接受有限顯示碼值必有量化。
- **色域壓縮**：亮紅、藍、洋紅等不能只靠一條亮度曲線。應在出界前平滑調整色度，盡量保色相，避免某一通道先硬剪而轉色。
- **正常顯示曲線**：identity有診斷价值，但「保持RAW線性」不代表應把線性數值直接送LCD。Log同樣只是編碼的一部分，不會自行提供正確色域或還原上游clipping。
- **面板校正**：最後才處理LCD白點、灰階、matrix/range。需量實體面板；電腦打開相機截圖無法證明LCD色準。
- **錄製隔離**：第一版應限定已確認的RAW監看模式與context，逐一證實原始影像／metadata與錄影行為未被意外更動，再擴到MOV及其他輸出。

超出LCD實際色域的光源無法同時保持其原始色度、亮度與完整對比；目標應是可控的平滑映射。8-bit畫面也無法逐一保留所有RAW code，但這和不必要地把大片有效訊號硬剪掉是不同問題。面板實際位深及色域本輪沒有量測。

這個設計原則可參照 [ACES Output Transform架構](https://docs.acescentral.com/system-components/output-transforms/technical-details/rendering-overview/)：tone、色度／色域處理及display encoding各有作用。這裡參考其處理原則，不宣稱fp能即時執行完整ACES。

## 6. 最小、可判斷原因的後續實機驗證

本輪未執行。先做小範圍定位，證明headroom與context，再做完整外觀調校。

### 固定條件與觀測

固定光源、快門、光圈、ISO、手動WB與場景；先選一種目前使用的RAW模式，再分別測OFF與Standard。場景包含灰階、高光漸層、普通色卡，以及紅／藍／洋紅LED或高飽和物件。後續擴到其他ISO、WB、待機／半按／錄影、LCD-only／HDMI等狀態。

每個狀態記錄：實際模式與gain state、曝光、RAW黑白位準與逐通道值、活動tone指標與完整表、matrix/gain context、display output route與CSC/gamma。需要比較的動態指標必須在一致快照取到，不能用數次不同时的host read拼成同一幀。

RAW與預覽未必是同一個readout或相同幾何，先確立配對關係；靜態場景比較可降低風險，但不能憑RAW尚未爆就假定預覽ADC也未爆。

### A/B順序

| 實驗 | 只變一件事 | 可回答的問題 |
|---|---|---|
| A 原廠 | 建立完整baseline | 截斷隨曝光與色彩如何出現？ |
| B 找到的stretched ID83 | 確認活動表已換成相同2048點 | 原先拉伸到底改善了多少？ |
| C 真正identity診斷 | 使用同刻度、單調直線表，驗證active context | 去掉原tone後，平台是否仍在？不是最終觀看外觀。 |
| D 已確認監看前級的共同衰減 | 分別減1、2 stop；保持sensor/record設定固定 | 截斷起點是否相應後移？若僅變暗而細節未恢復，可能修改點太晚，也可能是負值裁切、色域邊界或來源已飽和，需再區分。 |
| E 校正range/CSC或加入色域處理 | 根據A–D證據選擇，不同時改所有參數 | 彩色截斷是否來自YUV轉RGB或色域邊界？ |

**D要成立，必須先證明衰減發生在疑似clip之前，且不改RAW採集。** 否則不能把「變暗後好了」解讀成監看修復。

### 通過條件

1. RAW／預覽來源仍有差異的測試階梯，在最終監看可辨；允許正常量化，不容許無必要的大段平台。
2. 飽和色隨曝光增加平滑過渡，沒有單通道硬剪造成的突然轉色。色相誤差用受控參考量測，不只靠肉眼喜好。
3. 中性灰不偏色，正常曝光色卡與事先選定的參考顯影流程一致到可接受的量測誤差；不將「OFF外觀」直接當絕對色準。
4. RAW／錄製資料、metadata、對焦／測光、overlay與播放没有未預期變化；需驗證切mode後仍套用且能恢復。
5. 面板色準以實體量測完成。截圖／HDMI各自先確認它們的處理與取樣位置。

不要用 `display capture` 當作完整live image：既有工具抓到的是OSD。也不要把改tone後的斑馬／直方圖當獨立RAW飽和證據。SIGMA手冊有描述waveform的0…255亮度與EL ZONE受模式／ISO影響，並未建立它們等同逐RAW通道clip的保證。[官方手冊，頁49–51](https://www.sigma-global.com/en/support/download/fp_Manual_FW_Ver.5.0_EN_2.pdf)

## 7. 本輪交付與仍缺的證據

已完成：歷史AutoRun內容還原、2048點逐點驗證、88條原廠曲線獨立重算、舊地址訂正、原生tone排程與LCD末端路徑定位，以及上述可區分原因的實驗方案。

仍缺：使用者實際看到截斷時的同場景來源／輸出配對、當前活動context與完整表、第一個pixel clip位置、面板校準量測。不能因此宣稱是哪一個register造成，也不能交付可安全部署的修復版。

離線重算方式：執行本目錄 `audit_tone_curves.py`；它只讀ROM與歷史腳本文字並寫本目錄報告，不執行AutoRun、不連相機。原始檔案皆未修改。

相關詳細報告：[歷史證據](prior-evidence.md)、[ISP路径](isp-path-audit.md)、[LCD末端](display-route-audit.md)。
