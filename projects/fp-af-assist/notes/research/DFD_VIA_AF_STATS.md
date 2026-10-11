# SIGMA fp Ver 5.02 — DFD via the hardware AF-statistics engine (Bayer-green HF energy)

> 目標:評估用 AF 雙頻帶統計做 DFD，避免先抽取完整 Bayer 幀。
> **2026-09-16 更正：** 訊號可以讀取，不等於可任意配對。mposm 是 sweep 歷史，idle 不更新；
> Near 甚至會先發布未填槽。應驗證完成的原生 H/L–position 歷史，不把一般 peek 宣稱為曝光對齊。
> USB/RAM 操作仍需依現行工具的所有權與傳輸規則，沒有「無凍結風險」保證。
> 已量測結果與本頁更正依據見 [H/L 方向診斷](FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md)。
>
> EA = ARM 位址(base 0xC0000000),file_off = EA − 0xC0000000。信心:**[C]** 反編確認 · **[I]** 推論 · **[P]** 需上機。
> 姊妹:`AF_AE_INTERNALS.md`(濾波鏈)、`AF_LIVE_STATE_MAP.md`(live cells)、`AF_COMPLETE.md`(原理)、
> `bayer-not-in-dram-liveview`(為何抽 Bayer 幀難)。gimbal-ai 的 DFD 科學在其 `AI_AF.md`(Lorentzian 等)。

---

## 0. 一句話結論
**AF-C 在 CINE live 吃的是 Bayer(綠通道),不是 developed YUV。** 由專用 SIG 硬體統計引擎
`0x30050000`(`src/driver/AF/src/af_common.cpp`)在 **CSEP(debayer)之前** tap raw 流、挑綠通道、
過 IIR 高通濾波鏈算出 **HIGH/LOW 雙頻帶高頻能量 per-ROI**。這正是 DFD 需要的「對焦-銳度曲線」訊號,
而且結果 cell 可讀。**→ 優先研究「已驗證的原生掃焦歷史」，不需先抽完整 Bayer 幀。**
這些是經韌體縮放、校正、飽和處理的統計，不能稱為未處理的 raw 振幅；DFD 尚未驗證。

---

## 1. 為什麼確定是 Bayer(不是 YUV)[C]
統計塊 MMIO `0x30050000`,其設定暫存器只在 debayer 前才有意義。C5 telemetry 欄位
(`blk_c02.c:98309`,字串 @0xC0926940):`AF_Y_SEL, TG_SEL, MEDEN, GAFPICK, GAF_ID, BITMSK, SFT_SEL, LPF_SEL`。
- **`GAF_ID` / `GAFPICK` = 「Green-AF pick」**:`0x30050440` 有 **2-bit CFA 位置欄位**(mask 3,setter `FUN_c0636ff8`@`blk_c06.c:47905`)+ pick 欄位(bits 6:4,`FUN_c06370a0`)。**2-bit「4 個 mosaic 位置挑一」是純 CFA 概念,debayer 後不存在。**
- **`gain_af_RGB=%d`**:AF 數位增益 `0x30050464`(setter `FUN_c0637138`)**per-Bayer-channel(RGB)** 施加 → mosaic 資料。
- **`AF_Y_SEL`**(`0x30050450` bit0,`FUN_c0637020`)選塊內 luma vs 綠通道 pick;那個「Y」是**raw-domain 從 CFA 算的 luma**,同一個 Bayer tap,**不是 CSEP 輸出的 YUV**。此塊從不讀 developed YUV frame buffer。
- pipeline:`SIG0 → SIG1 RAWOUT → PRE_TOP CSEP`(debayer);AF/AE 統計 tap 在 **SIG raw cluster、CSEP 之前**。AE metering 塊 `0x30058000` 是它的姊妹(同為 raw-domain 統計引擎)。

---

## 2. 每幀讀取路徑(DMA-buffer 讀,非軟體 pixel loop)[C]
- **`FUN_c023e1a0`@`blk_c02.c:43977`** = 硬體讀。透過 `FUN_c02aa930(handle, slot)` 取 slot **0/1/5** 三個
  source-plane DRAM buffer,各 `memcpy` 0x400 bytes(256×u32)進 stack,再**沿 AF ROI 窗口 per-line 累加**
  (44053–44064, 44130–44159)。三通道 = HIGH band / LOW band / 第三統計。
- 描述子表 **`0xC340474C`**(`FUN_c02aa808`@`blk_c02.c:105815`,tag `af_common.cpp`);每 slot 0x10 bytes,
  **DRAM buffer 指標在 +0xC**。
- 上傳鏈:`FUN_c023e6f8`@44208 → `FUN_c023e9d0`@44329(寫 band 陣列)→ `FUN_c023ec28`@44406。
  e6f8 做 H/L 分別縮放、條件式 H 校正、32-bit 飽和，mode 1 再加 256、其他 mode 加 0；
  ec28 只在 context copies 與 C32914FC 減去該固定 offset，**不是減 scanmin 或量測噪聲**。
- 濾波鏈(`AF_AE_INTERNALS §2`):IIR biquad HPF banks **HIGH `0x30050220-238` / LOW `0x30050260-278`**
  (`FUN_c06371e0`/`c0637290`@`blk_c06.c:48047/48065`),median(`MEDEN`),per-line 累加。enable `FUN_c0636310`@`blk_c06.c:47039`。
  config 由 sensor-mode 表施加(`FUN_c0240xxx`@`blk_c02.c:45426-45429`:TG_SEL/GAF_ID/GAFPICK/AF_Y_SEL)+ 工廠 dispatcher `FUN_c0236608`@39120。

---

## 3. ⭐ 可 peek 的 DFD 訊號(核心產物)
### 成品指標(直接可讀,無需 firmware call、在 `AF_LIVE_STATE_MAP` 讀表內)[C]
| 值 | 位址 | 意義 |
|---|---|---|
| **saf_jdat_h[]** | **0xC32985E8** | 每 ROI HIGH，u32 processed accumulator；非 bandval−scanmin |
| **saf_jdat_l[]** | **0xC32986B4** | 每 ROI LOW，同樣保留 mode-dependent offset |
| aggregate band/window values | 0xC32915C4 / C8 / CC / D0 | small H / main H / small L / main L，**不是 now/max/min** |
| route / g_afpos | 0xC32915B0 / **0xC32914E0** | 策略狀態 / 目標與峰位累加域，非實測鏡頭位置 |
| **mposm[]** | **0xC3291958** | i32 sweep 位置歷史；需正確索引及完成性驗證，非即時位置 |
| area0 strong-judge ref | 0xC32914FC | (44448) |

寫入處:`saf_jdat_h/l` @`blk_c02.c:44368-44369`;aggregate bands @44388-44391。

### 前累加的 per-line band buffer(進階,可選)[C 位置 / P live 指標]
描述子表 `0xC340474C` slot 0/1/5,指標 +0xC。deref 一次即得 per-line 綠頻帶能量(窗口內)。用 peek-via-inject 原語可讀。

### 解析度 / 範圍
**ROI 窗口,非全幀。** 窗口幾何 `0x30050010`(0x3ff mask,≤1023)→ 在**降採樣/binned Bayer-綠格**上,
每區最多 256 累加線。AF 區框:single 32/64/128、region 119×73…833×511(`AF_LIVE_STATE_MAP §Q15`)。
更新頻率:每 CAF eval 幀(divisor 1≈17ms / 2≈33ms,`AF_AE_INTERNALS §⑨`)。

---

## 4. DFD 採集流程(新路徑,取代抽 Bayer 幀)
```
授權原廠 AF，記錄事件與曝光 → 釋放並核對 idle / 設定 / echo
→ 兩次讀取 Near metadata、descriptor、area-0 H/L 與 mposm 歷史
→ af_fusion_history_analyze.py 驗證支援的完成前綴、同索引配對
→ 記錄未知的逐點曝光／filter；不先宣稱 DFD 可用
→ 以跨場景、光圈、鏡頭與雙方向留出資料驗證模型
```
純離線分析不接相機；history probe 只讀固定 RAM 與 getter。即時 collector 仍會暫寫 RAM、借用 echo。
原生 Near 寫入後还會經工作陣列覆寫 H/L，同索引消費不等於任意時刻 live H/L 已與 mposm 對齊。
任何未經驗證的自製 drive 路線都不得沿用此配對假設。

---

## 5. 對接 gimbal-ai 的 DFD 科學(其 `AI_AF.md`)
- 舊 HDMI/YUV 資料曾以 Lorentzian 模型得到特定擬合結果；**未證明其形狀、寬度不變性或誤差能轉移到此處**。
- 同一個 H/L 比值可落在峰位兩側；即使幅度正規化也不會自動得到失焦符號。現有四次同場景掃描已出現這種歧義。
- 固定 firmware offset、掃描最小值與物理 noise floor 是三件不同的事。不可任意扣 256 或 scanmin 當通用降噪。
- H/L 消增益只在兩帶共享乘法增益、比例固定、沒有 offset／飽和等條件下成立。此處有分帶縮放與條件修正，必須實測。
- 尚需獨立曝光／運動對齊、noise/filter metadata 與跨場景校正；先保留 H、L 原值，不以 ratio 取代兩個通道。

---

## 6. 關鍵 EA 索引
| 項目 | EA / 位址 |
|---|---|
| AF 統計引擎 MMIO base | `0x30050000`(af_common.cpp)|
| GAFPICK/GAF_ID(CFA 綠 pick,2-bit) | `0x30050440`(setter `FUN_c0636ff8`@blk_c06:47905)|
| gain_af_RGB(per-Bayer 增益) | `0x30050464`(`FUN_c0637138`)|
| AF_Y_SEL | `0x30050450` bit0(`FUN_c0637020`)|
| HPF HIGH / LOW banks | `0x30050220-238` / `0x30050260-278`(`FUN_c06371e0`/`c0637290`)|
| 每幀讀 | `FUN_c023e1a0`@blk_c02:43977(slot 0/1/5,memcpy 0x400)|
| 描述子表(buffer ptr +0xC) | `0xC340474C`(`FUN_c02aa808`@105815;`FUN_c02aa930`@105866)|
| band 寫入 / span | `FUN_c023e9d0`@44329 / `FUN_c023ec28`@44406 |
| **saf_jdat_h / saf_jdat_l** | **0xC32985E8 / 0xC32986B4** |
| aggregate small-H/main-H/small-L/main-L | 0xC32915C4/C8/CC/D0 |
| g_afpos / mposm[] / route | 0xC32914E0 / 0xC3291958 / 0xC32915B0 |
| AE metering 姊妹塊 | `0x30058000` |

**注意**:此塊給的是**濾波後 HF 能量(邊緣/對比)**,不是 raw Bayer 影像。若要真 Bayer 像素做自訂 DFD kernel,那是另一條 `0x50000000` Bayer DMA(見 `raw-bayer-capture.md`,難)。但 DFD 要的若是 **Bayer-domain 銳度訊號**,AF 引擎已經算好了。
