# Tone 之前還有沒有截斷？上游追查報告

2026-09-24；SIGMA fp 5.02。使用本地韌體、反編譯、既有實機紀錄與歷史實驗檔案；本輪未操作相機。

## 本輪結論

**上游仍不能排除截斷；但目前的離線證據不足以證明「哪一級正在把像素剪平」。** 已能把追查範圍從泛稱 ISP，收斂到 preview／small_raw 的 CRCT reduction 分支、gain／WB、RGBLMAT 與 IGAMMA／PSTIGAM 的實際活動設定。

使用者提出的 **bin／vbin 是正確的追查方向**：韌體有明確的 `liveview hbin/vbin`，與 `rec hbin/vbin` 分開；原廠部分配置確實預覽 3×3、錄製 1×1。但 LCD 來源不可直接等同錄影 `CrctVbinToBufA` 抽頭，待機也不一定開 CRCT bin。

本輪沒有找到能保證「只換 linear tone 就修好」的依據。若來源、WB 或矩陣後已出現平台，tone 的直線無法恢復像素差異；反過來說，僅看見 `0xFFF`、`0x1FFF`、11-bit mask 或名稱帶 CLIP，也不能就宣布那裡是根因。

## 已確認與仍未知

| 區段 | 本輪確認 | 對截斷問題的判斷 |
|---|---|---|
| Sensor → preview source | 歷史待機紀錄存在 MONIT1_60／enum8／12bit／2016×1344，small_raw hvbin1×1、zoom1024 | 錄製 RAW 未爆，不能推論不同 readout 的 preview 未爆；沒有同場景上游像素配對 |
| CRCT bin／vbin | 306 列 ROM template 中 17 列指定 preview3×3、record1×1；两筆原生核按現有無符號解讀皆非負、每組係數和固定 | 正常歸一化不應自行產生 overshoot；實際累加位寬、shift、輸出 range 尚未證明 |
| Gain／WB | 原生增益拆分與 Bayer/WB gain 參數限幅存在；更正 `30112740/44` 為 **SIG0_TBLSD**，不是 RAWBLT | gain 參數到頂與像素到頂是不同事件；需要當前增益與該級輸出資料 |
| RAW knee | 已追到的 default／common builder 關閉 enable | 不可因存在 knee 表就稱它正在壓掉高光；其他活動狀態仍需快照 |
| RGBLMAT | 兩組係數有尺度處理；`30115134` 與超界係數除2的 flag 連動 | 係數重編碼不是像素 clipping 證據；硬體負像素與累加結果如何處理仍未知 |
| 原生矩陣降增益 | 第一組只縮放 indices0/3/6，第二組才全九項縮放 | 不能未驗證便把它當成所有顏色共同縮小的 headroom 修復 |
| IGAMMA／PSTIGAM | 各27個 default knot 嚴格遞增，末值分別5120／8192；可追到原生 PQ setter | 未找到能直接等同亮部平台的 default；knot值與控制欄不能代替活動像素量測 |
| Tone 與 LCD 末端 | 前輪已追到曲線、descriptor、SIGSEQ、display CSC／gamma | 可調整不等於上游無截斷；末端仍需 range／gamut 校正 |

詳細證據：[預覽 reduction](preview-reduction-audit.md)、[RAW 前端](raw-front-audit.md)、[矩陣與 gamma](matrix-gamma-audit.md)、[歷史擷取證據](capture-evidence.md)。

## bin／vbin 線索如何改變判斷

設定鏈已核實到：

```text
preview／record 各自的 profile 參數
 → XC_LiveViewDispParamWithRaw（C0438018）
 → C031D988 的 liveview／rec 幾何與位深
 → imager0 selector C0325228
 → C032D9A0 reduction builder
 → C0633B30 main、C0633DA0 sub
```

它建立了值得優先追的預覽分支，但不是整條 ISP 像素先後的完整證明。

例如 profile429 的 template 是 preview 3×3、zoom1024；record 1×1、zoom1600。CRCT 的錄製 mux 另選 writeout，不能用「VbinToBufA 沒開」否定預覽經過 bin。另一方面，既有待機紀錄明確是 small_raw 1×1，因此需把待機與錄影分開。

兩組 reduction 核可寫成候選歸一化權重 `[1,2,1]/4` 與 `[1,14,1]/16`；這是從 ROM 係數比例得到的數學表示，尚非完整 ASIC 運算規格。若 ASIC 的係數 signedness／歸一化與此解讀一致，充分精度的非負加權平均不會大於所有輸入；真正要追的是 bin 前是否已飽和、歸一化／位寬是否正確，以及輸出之後是否有放大或限幅。

## 本輪排除的誤判

1. **`RAWOUT 1FFF0000` 不是已證實的 8191 像素上限。** 追到 callers 後可見 width／offset／height 等幾何資料餵入，應按空間 window／crop 理解；不能當作解除色彩 clipping 的 register 修改。
2. **Bayer/WB 的 `0xFFF` clamp 限制的是 gain 參數。** 四通道增益上限不等於像素 clamp threshold。
3. **11-bit 矩陣係數／2048 點 tone LUT 不等於畫素僅剩11bit或在2047剪掉。** 定點係數、查表座標、內部像素刻度是不同數值域。
4. **`RGBLMAT+34` 不是可任意當成 disable-clip 的未知 bit。** 它與原生矩陣超界時全18係數除2的處理相連；硬體補償的完整語意仍待驗證。
5. **有實驗腳本不等於有實驗結果。** 舊 GAM158／PST15E／CEQ1D0／YUV1E0 dump payload 在核查根目錄中未找到；OFF／T&O 的 PQ dump 相同、tone slices 為零，不能拿來證明模式曲線或上游沒有截斷。
6. **Unicorn native trace 不是色彩實拍。** 它能確認韌體選了哪些路由及 register writes，不能模擬未知 ASIC 算術或提供 pixel saturation 證據。

## 下一步應量什麼，才真的回答「截在哪裡」

先挑一個能重現現象的固定模式；待機、錄影分開記錄。建立以下三個比較位置，位置未能取得時不得用其他模式的資料冒充：

| 位置 | 必要資料 | 可回答的問題 |
|---|---|---|
| A：實際預覽 RAW／small_raw 來源 | 當幀 buffer、格式／packing／有效位深、黑白位、sensor enum、profile、曝光與gain、bin／zoom狀態 | tone 前就已平台嗎？是否使用不同於錄製 RAW 的採集？ |
| B：進入 tone 前可確認的資料點 | 當幀 gain／WB／matrix／IGAMMA／PSTIGAM 參數與可取得的對應像素 | A 有梯度、B 無梯度，便可收斂到這段處理；要再找相鄰可觀測點 |
| C：ISP輸出與LCD輸入 | 已確認取樣點的RGB／YUV畫面、tone活動表、CSC與range | B 有差異而C剪平，是tone／gamut／range或後級問題 |

不是每一级都有可用的記憶體 tap。若無法直接取 B，使用受控的一項變因測試：固定 sensor 曝光与 record 設定，在**已證明位於疑似限制之前**的監看節點衰減，再看平台起點是否按比例後移。若衰減只讓平台變暗，不能直接斷定 sensor 已爆；也可能修改點太晚、負通道已裁切或來源點配錯。

輸出至少保留逐 Bayer 通道／RGB 通道的 response-vs-exposure、平台起點、近最大值像素比例、ROI min/max／可區分階梯數及樣本序號。均勻白牆只能測亮部，還需紅／藍／洋紅漸層測單通道與負值色域問題；場景與光源必須固定。

「RAW還有細節」只應在證實 A 与錄製 RAW 的 readout／曝光／幾何配對後作判準。LCD 照片或 OSD capture 也不能替代 A／B 的數值。

## rawlive 的實作優先順序

1. **先證明 preview／small_raw 來源。** 優先沿本輪確認的 bin／vbin 分支找有效且可同步取得的資料，建立其格式、所有權、更新時機及與錄製 RAW 的關係。
2. **在第一個實際 pixel clamp 之前保留餘量。** 不沿用未驗證的原生矩陣降增益當作 uniform attenuation；先離線驗證實際矩陣及中間值域。
3. **再做可比較的 RAW 還原與顯示映射。** 將黑位、WB、色彩矩陣、平滑高光／色域壓縮與 LCD transfer 分段保留數值；linear tone 作診斷，不能當成色準保證。

本輪交付的是路徑定位、錯誤候選排除與可重算 ROM 證據，沒有把尚未量到的上游 pixel clipping 寫成定案，也没有產生可部署的相機 patch。

## 重算與來源

- [preview-reduction-audit.json](preview-reduction-audit.json)：兩段韌體 SHA256、19,890個profile欄位＋500個mapping逐值核對、兩組核與控制字條件式重算。
- [capture-evidence-audit.json](capture-evidence-audit.json)：歷史檔案 hash、PQ／tone payload 結果與既有 AF紀錄範圍。
- [matrix-gamma-static-data.json](matrix-gamma-static-data.json)：上游 gamma／matrix 靜態資源。
- 詳細報告內引用原始 C 檔、ROM 位址與既有 capture；本輪沒有借用外部 ASIC 規格猜寄存器語意。
