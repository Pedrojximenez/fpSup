# Ole Berek 2026-03 fp → BMD Gen5 流程核對

2026-09-27。使用者提供 Facebook 分享連結後，讀取公開貼文、兩張完整流程圖及與 sRGB 節點相關的作者回覆。這是對新來源的補充分析；沒有操作相機或 Resolve，沒有完成色卡／Pyxis 匹配實測，也沒有生成 `.cube`。

**結論：這是一條值得實測的相機配色方案，核心是在 Film Gen5 編碼數值上加入非線性色彩補償。目前的公開證據不足以把它定義成 fp 通用 IDT，或證明 fp 原生色域為 BMD Gen1。它與作者 2023 年的 V-Log LUT 指南不同，必須分開評估。**

## 1. 來源與證據範圍

- [使用者分享連結](https://www.facebook.com/share/p/18XSQ5KQyN/)
- [Ole Berek 原文](https://www.facebook.com/groups/1124721801045663/permalink/3067172403467250/)，頁面日期 3 月 6 日；流程圖明載 March 2026。
- [流程圖一：RAW、Node01、Node02](https://www.facebook.com/photo/?fbid=10243837806707586&set=pcb.3067172403467250)
- [流程圖二：Node03、輸出 CST](https://www.facebook.com/photo/?fbid=10243837806787588&set=pcb.3067172403467250)
- [作者答覆 sRGB／Rec.709 與數學正確性](https://www.facebook.com/groups/1124721801045663/posts/3067172403467250/?comment_id=3067377433446747&reply_comment_id=3067664470084710)；同一串後續回覆把作用描述為修正 gamut，其餘直通。

作者表示此法源於匹配自己的 Pyxis 6K，宣稱匹配到 98%，並認為結果可按 BMD Gen5 繼續轉往其他工作空間。已讀內容未提供「98%」的誤差定義、配對 RAW、測試光源、曝光／WB、獨立驗證樣本。不能把它轉寫成量測色準。兩機採近似感光元件的說法也不是相機光譜響應或校準相同的證據。

閱讀範圍不是全部 73 則留言；不能推論其餘討論不存在補充資料。網頁開頭的概括標題標有 Meta AI 生成，沒有把它當成作者自己的論文標題。

## 2. 從截圖轉錄的設定

縮寫 BWG = Blackmagic Design Wide Gamut Gen 4/5；Film5 = Blackmagic Design Film Gen 5；DWG/DI = DaVinci Wide Gamut / DaVinci Intermediate。下表的箭頭表示介面設定，不能直接視為每一步實際訊號的正確標籤。

| 階段 | 設定 | 可見的附加選項 |
|---|---|---|
| Camera RAW | Decode Using Clip；As Shot；P3-D60 / Linear | Decode Quality 使用 project setting；Highlight Recovery 開啟 |
| Node01「CST IN」 | P3-D60 / Linear → BWG / Film5 | Tone/Gamut Mapping=None；White Point Adaptation 開；Forward/Inverse OOTF 關 |
| Node02「IDT」 | BMD Film Gen1 **色域** / sRGB **gamma** → sRGB 色域 / sRGB gamma | Tone/Gamut Mapping=None；White Point Adaptation 關；Forward/Inverse OOTF 關 |
| Node03「→DWG」 | BWG / Film5 → DWG / DI | Tone/Gamut Mapping=None；White Point Adaptation 關；Forward/Inverse OOTF 關 |
| Node05「→Rec709」 | DWG / DI → Rec.709 / **Rec.709** | DaVinci tone mapping；Custom Max Input=10000 nits；Adaptation=9.00；Saturation Compression，Knee=.900、Max=.902 |

圖二下半標成「4th Node」，實際選中圖中的 **Node05**。輸出 gamma 欄是 Rec.709，不能代換成 Gamma 2.4 後仍聲稱忠實複製。Custom Max Output 未勾；Advanced 被畫面截斷，沒有替作者補填未知值。

另有 Node04「FILM GEN」及 Node06「FPE」，截圖呈暗色，但沒有內容／明確啟停證據。專案 Color Management 設定、Camera RAW 完整面板、來源 ColorMode/profile 也未出現在這兩張圖中。因此已知的是 CST 子鏈，尚不能重現作者完整示範畫面。

## 3. Node02 實際做什麼

以 `E`／`D` 表示編碼／解碼、`M` 表示色域矩陣。忽略尚未核對的 Resolve 負值延伸、裁切與內部精度：

```text
x = P3-D60 linear RGB
z = E_Film5(M_P3→BWG × x)                 # Node01
Q(z) = E_sRGB(M_Gen1→sRGB × D_sRGB(z))   # Node02，無白點適應
y = E_DI(M_BWG→DWG × D_Film5(Q(z)))     # Node03
```

Node01 產出 BWG/Film5 數值；Node02 故意把這些數值當作 Gen1/sRGB；Node03 又把改過的數值當回 BWG/Film5。這是對數值的額外變換，不是普通、前後標籤一致的色彩管理串接。它可以有配色價值；有效性須由結果驗證，不能只靠 CST 名稱或把節點取名 IDT 成立。

**兩側都用 sRGB gamma，不表示 gamma 完全抵消。** 中間隔著跨通道矩陣，通常 `E(M D(z)) ≠ Mz`。在近似保持中性的灰軸上，確實可有 `Q(q,q,q) ≈ (q,q,q)`；因此 Film5 的灰階編碼大致保留。但有色像素的色相、飽和度及亮度仍可能改變，不能概括為只動 primaries、其他全部直通。

Node02 bypass 時，Node01+03 應接近普通 P3-D60/Linear → DWG/DI（仍須確認白點、範圍與實作）。加入 Q 才產生本方案的特殊效果。Tone/Gamut Mapping=None 不會消除 transfer function 的非線性。

本地 [Gen1 常數研究](/Users/dido/Developer.localized/SIGMAfp_re/bmd_gen1/notes/BMD_FILM_GEN1_GAMUT.md) 所記近似矩陣可用於理解方向：無 CAT 的 Gen1→sRGB 矩陣有明顯負的跨通道項與大於 1 的對角項，能拉開通道差異。因此「偏淡畫面變得濃郁」有數學原因，但不能由此推回 fp 真實 sensor gamut。未以這些近似數字冒充實際 Resolve CST 輸出。

sRGB 與 Rec.709 的標準 primaries 相同，不代表兩條 transfer curve 相同。若只改 Node02 的輸出色域名稱而保留 sRGB gamma，結果可相同／接近；若把 gamma 也換掉，則不是普遍相同的函數。作者的「幾乎一樣」宜視為其測試觀察。

## 4. 與本地 DNG 證據如何對接

這條流程先用 P3-D60/Linear 解碼，所以輸入仍可能受到 CM、HSM、ToneCurve、AsShotNeutral、BaselineExposure 等影響。換成 BMD 空間不會抹去解碼前已使用的 metadata。

本地同 RAW A/B 已證明 Resolve 在既有設定中使用 CM/HSM/TC；writer 也找到 OFF／normal 明確分支。因此作者在照片回覆中對 video metadata 的廣泛否定，不能取代逐 tag 的觀察。其「SIGMA 混用 Gen1 與 sRGB」是解釋假說；目前沒有由 sensor／writer 到此 Q 的推導。

2019 年 CaptainHook 對非 BMD DNG 的「BMD Film Gen1 RAW decode 不做 gamut 轉換」說明，與這篇 **P3 RAW 解碼後另加 Gen1 CST** 是不同位置，不能拿前者直接當作後者的證明，也不能只因前者就否定此方案的配色用途。

你的 9/26 OFF 補丁已寫 normal CM、保留 identity HSM/TC。尚未證明這套 recipe 使用哪組原始 profile；若 Q 正好在補償原廠 OFF 偏淡的路徑，直接加到 patched OFF 可能再次改色。這是待測風險，不能先寫成已證實的重複補償。

來源：[profile 同 RAW 實驗](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/profile-tags-ab-20260925/README.md)、[OFF 補丁](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/off-matrix-firmware-patch-20260926/README.md)、[主報告中的工程師原文與版本限制](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/notes/FP_CDNG_RESOLVE_LUT_WORKFLOW_2026-09-27.md)。

## 5. 最小驗證設計

先開獨立的非管理 DaVinci YRGB 測試專案，保證節點收到 P3-D60/Linear；不要把原鏈直接放入已完成 RAW→DWG 轉換的 RCM 節點。這是我們的可控測試設定，不是聲稱作者專案必然如此。

建立同一張 RAW、保留同一 Bayer payload 的 2×2：

| DNG profile | Node02 bypass | Node02 開啟 |
|---|---|---|
| 原廠 OFF CM + identity HSM/TC | A | B |
| normal CM + identity HSM/TC | C | D |

1. CM 依該檔機身校準重建，不借用其他機身矩陣。固定 As Shot 與同一 AsShotNeutral，並固定 BaselineExposure、黑白位準和其他 RAW 控制；不要只輸入相同 Kelvin/Tint 就認為 WB 變因已鎖定。
2. 第一輪關 Highlight Recovery，隔離可量測通道；另做作者 HR 開啟的重現分支。未知的 Node04/06 在受控測試中明確 bypass。
3. Node03 後轉為共同的 DWG linear 或 XYZ、匯出浮點 EXR；不含 Node05 DRT。核對負值／超 1 與裁切。
4. 四組再加同一 DRT 看外觀。作者的 Node05 另列為「原配顯示方案」，不要一組用它、另一組用不同 RCM DRT 卻把差別全歸於輸入色準。
5. 同 RAW 固定 WB，在 Q 之前的場景線性域加 -2、0、+2 EV，輸出轉回線性後撤銷曝光，檢查色度漂移。只使用未裁切有效樣本；這測曝光相依性，不替代實拍跨 ISO 測試。
6. 色卡、灰階、膚色、飽和 LED 分別報結果；量測採匹配光源的 reference，至少日光／鎢絲光及獨立驗證畫面。Pyxis match 必須用配對素材、固定解碼及共同顯示參考，與絕對色準分開報。

若 B 比 A 好而 D 比 C 差，支持 Q 與原廠 OFF 補償有關，但「好」必須以明定 reference 判定，不能只看飽和度變高。如果在多光源與曝光下都改善，才逐步提高其作為校正的可信度。normal CM 亦是來源可追溯的候選基線，不預設為絕對真值。

## 6. 對機身 `.cube` 設計的影響

把它新增為**待驗證的 recipe 分支**，不要直接取代 sensor／DNG profile 校準。主流程仍是「已知輸入 → 校準與工作空間 → recipe／look → 顯示」。

要在 DWG/DI 工作節點使用，可把已知變換改寫成：

```text
DWG/DI
→ 正常 CST：BWG/Film5
→ Q：用 Gen1/sRGB → sRGB/sRGB 的設定處理數值
→ 按 BWG/Film5 解讀，正常 CST 回 DWG/DI
```

此子鏈可候選烘成 `Ole2026_Q_DWGDI_to_DWGDI.cube`，但名稱不表示已生成或已驗收。manifest 必須標示 Q 的確切設定、適用 DNG 基線及驗證範圍；它可能含輸入補償，不能先稱為對所有相機通用的 look。

等價改寫有條件：兩端 CST 的 Tone/Gamut Mapping=None、Forward/Inverse OOTF 關；第一個 DWG/DI→BWG/Film5 必須是原 Node03 的逆，此例 White Point Adaptation 關。進來的 DWG/DI 也須由同一 RAW/profile/WB/曝光經純工作空間轉換得到，未先加另一套 input tone/gamut mapping。不能用 CST 預設值或不同 RCM 輸入處理，便宣稱與原 Node01–03 等價。

若另烘監看版本，顯示轉換需獨立有版本：重現作者版為 Rec.709/Rec.709 與其 tone/gamut mapping；自訂 Gamma 2.4 版則明確另名。兩者輸出後均不再重複套 RCM DRT。

不要將完整 P3-linear 輸入鏈直接匯成預設 0..1 cube 丟上機身：超白線性範圍、負值、RAW 動態 WB、ISO 正規化、Highlight Recovery 均不會自動由一張靜態 cube 解決。優先在已知 log 工作域取樣，以 Resolve reference 檢查邊界與插值。機身還要先量出實際 tap 的編碼，完成 tap→工作域 adapter；LCD OFF 訊號不等於這裡的 P3-D60/Linear 或 Film5。

**本輪完成：來源閱讀、設定轉錄、數學性質分析、A/B 與 LUT 分支設計。仍待完成：真正 Resolve 重現、受控色準與 Pyxis 配對量測、cube 匯出回讀、機身接入驗證。**
