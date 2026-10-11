# fp 機內 DFD／AAT：無 PDAF 與其他機身的參考價值

日期：2026-09-27。範圍：本地公開更新檔、既有反編譯／解包結果與原廠文件；未操作相機，未執行更新程式或未知韌體。本文新增研究排序，不變更既有原始證據。

**最直接的無 PDAF 方法參考是 Panasonic S5／S1H／S1，其次為 Leica SL2-S；目前本地都沒有可讀的 AF 演算法。BMCC 6K 有最完整的可讀 AF 控制契約，但 10.2.2 已有官方 PDAF 支援宣告，不能列為無 PDAF 成功案例。** 對 fp 的實作仍以本機 CDAF 原始程式、H/L 實測及已核對的 lens／scheduler 路徑為準。

標記：**[B]** 本地位元組／程式／包內文件直接支持；**[O]** 原廠公開文件；**[I]** 從資料推導的研究建議；**[U]** 未確認。同樣 24 MP、L-Mount 或疑似同系列感測器，均不代表可搬用 AF 常數、像素排列或 PSF。

## 1. 排序：先分「算法可讀」與「方法可借鏡」

| 優先 | 對象 | 本地真正可讀的證據 | 對 fp 可借鏡 | 邊界 |
|---|---|---|---|---|
| 1 | Panasonic S5；同組 S1H／S1 | 官方 UPD 容器與分區表；原廠 Contrast AF + DFD 說明、AF 行為文件 | DFD 與 CDAF 分工、鏡頭光學模型、轉移速度與重新對焦敏感度分開、目標切換／追蹤策略 | 主程式分區尚未解開，沒有讀到兩幀估距公式或 AF 狀態機實作 |
| 2 | Leica SL2-S | 官方 contrast metering + depth mapping、追蹤改進說明；LFU 容器目錄 | CDAF 加深度估計、iAF／AF-S／AF-C 與目標偵測分工 | 對比＋depth mapping 不等於已證明其與 Panasonic DFD 是同一份演算法；程式未解 |
| 3（旁支） | Blackmagic Cinema Camera 6K／Fulda，10.2.2 | 已解外層 359 檔；LensControl OpenAPI、UI、host RPC symbols、周邊 MCU 偽碼 | ROI 正規化、目標／模式／狀態／能力分離、失去追蹤與手動操作的狀態表達 | 官方已宣告 PDAF；Autofocus／Lens／ImageSensor 主程式仍受保護，不能當無 PDAF DFD 實作 |
| 排除本組 | Panasonic S5II／S5IIX | 官方 Phase Hybrid AF；本地 UPD 容器 | 可作 AF 選擇／介面架構旁證 | 不能把 phase + contrast 結果計為無 PDAF；本地算法仍不可讀 |
| 排除本組 | Sony α7C | 解包成功、IMX410 RTTI／sensor tables 已確認 | 另案可研究可讀控制碼、lens／readout 排程 | 有 PDAF；sensor driver 可讀不等於本輪已讀 AF 算法 |

此順序是**對當前 fp 機內 DFD／AAT 研究的價值**，不是相機性能或 AF 準確率排名。若只按本地可讀的 AF 相關原始契約，BMCC 排在 Panasonic／Leica 前；若要求「可移植的 AF 演算法機器碼」，本節三個無／旁路候選目前均未取得。

## 2. Panasonic：最接近問題，但本地尚停在容器

**[O] AF 身份。** [S1 官方規格](https://www.panasonic.com/in/consumer/cameras-camcorders/camera/s/dc-s1.specs.html)列出 Contrast AF、DFD、AF-S／AF-C、目標追蹤及移動物體預測；[S1H 官方規格](https://www.panasonic.com/th/consumer/cameras-camcorders/lumix-s-cameras/lumix-s-full-frame-camera/dc-s1h.html)也列 Contrast AF + DFD；[S5 官方發表](https://na.panasonic.com/news/new-hybrid-full-frame-mirrorless-camera-the-lumix-s5)明確將 Contrast AF 與 DFD 結合。這支持其作為無 PDAF 設計對照，不需要先把 sensor 硬定名為 IMX410。

**[O] 可借鏡的分工。** 原廠 [LUMIX Video AF Guidebook](https://www.panasonic.com/content/dam/Panasonic/Global/Learn-More/lumix-af-guidebook/LUMIX_Video_AF_Guidebook_211201.pdf)的 DFD 說明（p.26，網頁索引可讀；本次直接 PDF URL 回 404）呈現兩張影像銳度比較、光學特性、DFD 與 contrast calculation 共同供 AF controller。這是方法概要，沒有公式／參數／可重現實作。[S5 手冊 p.258](https://eww.pavc.panasonic.co.jp/dscoi/DC-S5/P_PP/DC-S5_DVQP2197ZD_full_eng.pdf)把 AF Speed 與 AF Sensitivity 分開：前者是移動快慢，後者是主體距離大變時何時重新反應。對 fp 值得借用這種責任分工，不能把「快一點」同時当成追蹤身份、重新對焦判斷與馬達速度的改動。

**[B] 本地樣本。** S1 V2.4、S1H V2.8、S5 V2.9；另有 S5II V3.7／S5IIX V2.7。完整來源／hash／版本及欄位在 [PANASONIC_IMX410.md](../../../../panasonic_imx410/notes/PANASONIC_IMX410.md) 行 15–27，各機 `sections.csv` 與 `out/sections.json`。例如 [S5 分區表](../../../../panasonic_imx410/S5/sections.csv)、[S1H 分區表](../../../../panasonic_imx410/S1H/sections.csv)。

分區表可讀 `program`、`postboot*`、`lens_hist` 等名字，不代表內容已可讀。已記錄 type-3 程式區非零分區參數、明文摘要／密文不相等與高熵；抽出的 `03_program.bin` 仍為受保護資料。沒有 AF 符號、DFD lens profile 或 tracker 邏輯可引用。現有報告「未找到公開解法」是 9/26 調查範圍，不應提升為絕對不可能解開。

**[U] sensor 型號。** 本地無解密 driver／RTTI／register writer 可以確認 S1／S1H／S5 精確為 IMX410；24.2 MP 與規格相似只是線索。S5II／S5IIX 官方已明言新 sensor 支援 [Phase Hybrid AF](https://www.panasonic.com/uk/corporate/news/articles/panasonic-introduces-lumix-s5iix-and-lumix-s5ii-mirrorless-cameras-with-hybrid-phase-detection-af-system-enhanced-active-i-s-and-newly-developed-24-megapixel-full-frame-cmos-sensor.html)，不可混進純 CDAF／DFD 對照。

## 3. Leica SL2-S：第二個無 PDAF 系統參考

**[O]** [SL2-S 官方技術資料](https://leica-camera.com/sites/default/files/pm-54089-201120__SL2-S_technDatas_en_RZ.pdf)第 2 頁將 AF 寫為 contrast metering + depth mapping，支援 iAF／AF-S／AF-C。官方 [2.0 更新公告](https://leica-camera.com/en-int/Company/Press-Centre/Press-Releases/2021/Press-Release-Firmware-version-2.0-for-the-Leica-SL2-S-New-features-and-optimised-video-mode-performance)描述追蹤以及眼、臉、頭、身體偵測的改善。可用來提出 fp AAT 的驗收場景；無法由行銷描述推出 confidence 算法或其與 Panasonic 的程式共用程度。

**[B]** 本地 `SL2S_630.lfu` v6.3.0 經 NOT 可讀 UPD／MC701 與 48 筆目錄。`program` entry 為 type 3、15,138,816 bytes；程式區 NOT 後仍不成可讀 ELF／code，type-2 可讀區為空白填充。證據：[OTHER_IMX410.md](../../../../other_imx410/notes/OTHER_IMX410.md) 行 117–125、[lfu_directory.json](../../../../other_imx410/leica_sl2s/out/lfu_directory.json)。`lens`、`lens_hist` 等名稱不等於拿到鏡頭模型。

**[U]** 本地與這份官方規格尚無精確 Sony part-number 證據。不能因 SL2-S 與 S1 的資料容器相似，就宣稱相同 sensor／AF firmware。

## 4. BMCC 6K：可讀的比「加密」多，但不能分類成無 PDAF

### 4.1 先固定機型和版本

本地是 **Blackmagic Cinema Camera 6K 全片幅 L-Mount／Fulda／PID 0xBEDC**，不是 Pocket Cinema Camera 6K／6K Pro。Camera Setup 安裝包版本 10.3，內層相機版本為 **10.2.2／f17.326200**。身分鏈見 [BMCC6K_FIRMWARE.md](../../../../bmcc6k/notes/BMCC6K_FIRMWARE.md) 行 19–26。

**[O] 2026-09-27 核對官方發布正文：** [Blackmagic 官方 SDK／software 頁](https://www.blackmagicdesign.com/mx/developer/partial/camera/sdk-and-software)的 2026-08-10 Camera 10.2.2 說明明列 Cinema Camera 6K 支援 phase-detection AF；此頁可直接讀到發布正文（行 181–190），不是論壇或二手媒體轉述。現行[官方產品規格](https://www.blackmagicdesign.com/developer/products/camera/techspecs)也列單次、連續、物體與人臉追蹤模式。

因此，BMCC 6K 新版 AF 可以作系統／介面對照，**不能當作「無 PDAF 也已做出相同追蹤表現」的證據**。即使較舊版本只啟用 contrast AF，也不能以軟體未使用相位資料推論硬體沒有 phase pixels。

官方只公開 36×24 mm、6048×4032 等規格；本輪未從可讀 camera driver 確认 IMX410 精確型號。**PDAF 支援是官方功能事實；精確 sensor part number 仍未知**，兩者分開。

### 4.2 真正可讀的 AF 原始資料

9/24 已還原外層旋轉 XOR／tar，359 個檔案驗證通過；舊「整包主機端解不開」結論已失效。[解包及反編譯報告](../../../../bmcc6k/analysis-20260924/bmcc6k-decompile-20260924/README.md)。

直接可讀的 [LensControl.yaml](../../../../bmcc6k/analysis-20260924/bmcc6k-decompile-20260924/payload_audit/extracted/payload/public_html/control/swagger/Camera/LensControl.yaml) v1.2.0 提供以下**介面契約**：

| 行號 | 契約 | 可借鏡的設計方式 |
|---|---|---|
| 136–180 | normalized focus 讀寫；寫入也可帶 focusDistance | 座標正規化與鏡頭能力分開；不把 normalized 位置當公尺或實際到位 |
| 181–213 | doAutoFocus；ROI 點為 0–1，省略時中心 | 明確區分 AF trigger 與 ROI；不由畫面中心推論 fp area 0 |
| 214–250 | supported、enabled、mode、state；Idle／Focusing／Focused／Paused／Error；TooClose／LostTracking／ManualFocus | 是否支援、是否啟動、流程狀態和失敗原因各自獨立 |
| 270–288 | supportedModes，依 product／lens 的 capability | 不以 enum 存在推論所有機型／鏡頭皆支援 |
| 289–342、575–602 | target point／rectangle；normalized x/y/width/height | AAT target 有座標域和大小契約；追蹤窗與量測窗應明確轉換 |
| 343–398 | retrigger 用目前 target；trackFace 用 faceIndex；可回 501 | 追蹤失去、重觸發、臉索引與不支援需分開處理 |
| 504–531 | lens focus controllable／distance adjustable／range | 控制前先確定該 lens route 真有能力 |

這些不是 camera-side handler 偽碼，沒有 sharpness metric、DFD 公式、step scheduler、H/L offset、停止判準或 tracker 更新公式。文件本身也要求 capability 查詢；本次未連機驗證每個 endpoint。

### 4.3 有檔案／符號不等於已解 AF 算法

- **[B] Autofocus app 已抽出，但未解明文。** `payload/apps/Autofocus.elf_encrypted` 為 238,064 bytes，SHA-256 `c49fdaf4231149a87ffc8d77d92f1ef3bd993808459c2bfc4c0ac26756bcd61f`；本次唯讀重算。前 16 bytes 為 `eb8558630b0afc54d5fc37701aba12bb`，不是 ELF magic。此現象配合既有保護層稽核，支持「尚不可當 ELF 反編譯」，單凭高熵不決定加密算法。[實檔](../../../../bmcc6k/analysis-20260924/bmcc6k-decompile-20260924/payload_audit/extracted/payload/apps/Autofocus.elf_encrypted)
- **[B] host 符號可讀。** [libCameraPlugin_symbols.txt](../../../../bmcc6k/analysis-20260924/bmcc6k-decompile-20260924/host_audit/libCameraPlugin_symbols.txt) 行 1916 有 `getILPDData`，1917 有 `Camera::ImageSensor::getPDAFCrop`（0x272B8），1932 有 `getImageSensorModel`。這些是主機 plugin 共用接口名；未核對 camera AF call graph、機型 gate 或返回值，不能據此單獨認定 BMCC sensor 型號／DFD／PDAF 算法。
- **[B] 已匯出的 C 是 Bluetooth 與 USB Power Delivery MCU**，不是 autofocus 主 app；不能把「反編譯 1,837／752 個函數」計為已解主 AF。
- 主應用、Loader／Kernel 的第二層仍待獨立研究；外層 XOR、boot image eFuse 標記都不能直接套為 Autofocus app 的解密方法。host updater 的 memcpy／zlib 路線也不是鏡頭對焦算法。

## 5. 對 fp 的可用結論

**[I] DFD 留在建議層，原廠 CDAF 保持收斂與馬達 owner。** Panasonic 的分工概念支持研究方向，但不提供 fp 所需的數值；先在已知 Δposition、多點 H/L、穩定 ROI 和逐點 exposure/filter 標記上驗證，避免把單筆 ratio 當帶符號 defocus。fp 的四輪完成 history 已證明 ratio 的雙解問題，见 [方向診斷](FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md)。

**[I] AAT 要提供「同一目標且可靠的 ROI」，不是直接提供已驗證深度。** 借 BMCC 的 target/state/capability 分離，對 fp 保存 raw tracker box、AF 實際量測框、confidence、ROI identity／generation、lost/manual/pause 狀態；原廠 AAT resize 與臉／眼優先鏈仍以 fp 程式為準。改善重新對焦敏感度、框擴張、錯追與放棄策略，與 motor 速度分開驗收。

不可跨機直接搬用：Panasonic／Leica 光學 profile，BMCC 的 phase signal／AI model、L-Mount 脈衝尺度，任一家的曝光／readout cadence、sharpness threshold、延遲常數、sensor register、ROI 索引或內存地址。相同接環也不保證同一顆鏡頭在兩機上的 drive timing 一致。

## 6. 有界下一步

1. **先完成一份本機映射表，不擴張到新相機部署。** 把 BMCC 的 target／state／capability 概念對應 fp 已知 AAT box、confidence、area0、route 與 native-L completion；未知欄位保留未知，尤其不把發布序號命名 frame ID。
2. **Panasonic／Leica 只做有限原始文件對照。** 整理 AF Speed／Sensitivity、目標切換／丟失／暫停與 CDAF／DFD 責任分工；如沒有新可讀 code 或已驗證解包方式，不反覆對密文跑 strings／反編譯。
3. **BMCC AF 核心研究限單一依賴鏈。** 若繼續，先限定 Autofocus→Lens／ImageSensor 的容器／載入身份與可核對入口；取得有效 ELF／可識別 code 和完整性證據後，才談算法反編譯。共用 API 和 host symbols 不當替代答案。
4. **研究成果回到 fp 旁路驗證。** 先量 AAT ROI 穩定與失效判定，再對原廠 AF trajectory 離線／機內 shadow 估算方向或搜尋窗；高信心建議才考慮介入原廠 CDAF，低信心保持原廠流程。比較錯誤換目標、反向次數、重新對焦延遲與最終原廠確認，不只比较瞬間速度。

**停止條件。** Panasonic／Leica 若未出現新可驗證的明文／解包入口，完成上述方法文件對照即停止密文分析，回到 fp 資料；BMCC 若無可識別的 camera-side AF code，完成控制契約映射即停止宣称已取得算法。任何外部候選若只得到符號或 metadata，不升格為演算法證據。Z CAM 留給可讀程式結構對照；使用者已指出其連續 AF 體驗不理想，故不以它作連續 AF 性能範本，也不以該經驗推論每個版本或演算法皆無價值。

本次只新增此筆記；沒有取得其他品牌相機的實機資料、破解主 AF app、移植 DFD 或改動 fp 韌體。
