# rawview 使用者自訂 LUT — 設計

> **2026-10-09 接續需求**：使用者要求完整 `.cube` 匯入、Live View、CDNG 內存 LUT／設定，
> 並希望擴充 MOV／STILL／JPG。維護開發入口移到 [LUT sup](../lut-sup/README.md)。
> 本文保留 9 月 28 日的顯示端近似設計；它不是整顆 ISP 的能力上限或新版完整需求。
> CUVAREA／RGBMAT_PL 的 MMIO、shadow 與部分 native resource 路徑已由
> [10 月 9 日補查](../../research/imaging-hw/isp-colour-blocks-20260927/LUT_BLOCKS_2026-10-09.md) 離線定位。
> 輸入 CM／WB 與使用者 look 仍分離；新增 LUT metadata 不等同更改相機校準。

2026-09-28。離線設計,**未上機**。基於 rawview 既有架構與
[`research/imaging-hw/isp-colour-blocks-20260927`](../../research/imaging-hw/isp-colour-blocks-20260927/README.md)
的 ISP 色彩地圖。

## 核心決定:放顯示端,與輸入 profile 完全分離

rawview 目前把 **DNG ColorMatrix 綁在 LCD 矩陣上**(`rv_dngcm.py` 依同一個 `sat` 抄 `cm_tab`),
所以螢幕等於檔案。那對「監看」是對的。

但 [`FP_CDNG_RESOLVE_LUT_WORKFLOW`](../../research/imaging-hw/notes/FP_CDNG_RESOLVE_LUT_WORKFLOW_2026-09-27.md)
第 66 行明確要求:

> 新設計必須把「輸入 profile」與「監看 look」拆成獨立狀態:**切監看 LUT 不得順便換 DNG CM**。

兩者不衝突,只要分成兩級:

```
              ┌─ 輸入 profile(既有,不動)──────────────────┐
感光元件 → ISP │ RGBLMAT/tone …  sat k=0/1 → LCD 矩陣 + DNG CM │
              └───────────────────────────────────────────┘
                                   ↓ 錄下來的 CinemaDNG 到此為止
              ┌─ 使用者 look(新增,只到螢幕)───────────────┐
              │ 顯示端 3×3  +  顯示端 RGB gamma            │
              └───────────────────────────────────────────┘
                                   ↓
                                  LCD / HDMI
```

**使用者 LUT 永遠不碰 `cm_buf`**,所以錄出來的檔案永遠是可追溯的原廠 profile(k=0 或 k=1)。
這同時解掉那份筆記指出的可追溯性缺口。

## 為什麼是顯示端

| | |
|---|---|
| 位置 | 在 ISP 之後,**不影響 CinemaDNG、H.264、JPEG** |
| 硬體 | 3×3 矩陣 bank ×3(`0x30190800` / `0x30190860` / `0x30190C70`)+ gamma ×2(`0x30190940` / `0x30190CB0`) |
| 佔用 | **rawview 目前只讀不寫**(`tools/rv_snapshot.py` 已有五個快照點),沒人佔用 |
| 能力 | 3×3 + 每通道曲線 = 矩陣 + split toning,足以涵蓋大部分膠片風格 look |
| 做不到 | per-hue 選擇性(只改天空不動膚色)——那需要 `CUVAREA CARE_SEL`,尚未定位 |

ISP 端(RGBLMAT + 88 條 tone)不適合放 look:tone 只有亮度一條,做不了 split toning,
而且會烘進 H.264/JPEG。

## 主機端:沿用既有工具鏈

[`cube2fp.py`](../../research/imaging-hw/isp-colour-blocks-20260927/cube2fp.py) 已經把 `.cube`
擬合成 **3×3(列和=1)+ 每通道 1D 曲線**,並給出按飽和度分層的誤差報告與「適合轉/不建議轉」判定。
實測膠片 LUT 在低飽和區 ΔE 0.6–0.7、16 點與 2048 點無差別。

這個模型**正好就是顯示端硬體的形狀**,不需要新設計,只要加一個輸出格式:

```
look.fplut        magic + version + 韌體指紋 + 3×3(定點) + 3 條曲線 + 名稱 + CRC
```

矩陣定點尺度沿用 rawview 既有慣例:**9 × int16,列和 512**(`rv_color.py` 的
`struct.pack('<I9hH', ...)`,identity = `(512,0,0)*3`)。顯示端的實際尺度待量(見下)。

## 上機前必須先做的一件事

**顯示端暫存器的編碼沒有量過。** `research/liveview/display-route-audit.md` 只確定了位址與路由是
條件式的,沒有確定:

- gamma 表 `0x30190940` 是 0x30 = 48 bytes → 16 點 × 3 通道 × 8-bit?還是 12 個 word 各自打包?
- 3×3 bank 的係數位元寬、符號、有沒有 offset 欄位
- LCD-only / HDMI / OSD 各走哪個 bank(稽核明說**不能想當然**)

**`tools/rv_snapshot.py` 已經有這五個快照點,跑一次就知道。**

```
1. 原樣快照                     → 得到原廠值,當還原基準
2. 從選單改一次 LCD 亮度/對比   → 看哪個 bank 的值跟著動 = LCD 實際走哪個
3. 接 HDMI 再快照一次           → 分辨 LCD / HDMI 的 bank
4. 寫 identity 回去             → 畫面不變 = 寫入路徑通
```

**在這四步完成前不要寫任何係數。**寫進未驗證編碼的暫存器,是這個專案最容易白費一天的地方。

## 整合點

| 項目 | 做法 |
|---|---|
| 資料來源 | 卡片上的 `.fplut`;rawview 的表格已經是**在相機上產生**(`rv_tables.py`,卡片 8,440 bytes),沿用同一條路 |
| 常駐緩衝 | 比照 `cm_buf`:cave 放 3×3 + 3 條曲線,開機填 identity |
| 套用時機 | 比照 `stub_gs`——只在待機更新,**錄影中不變** |
| 開關 | 比照 `rv_on` / `rv_off`;預設 off = identity = 完全無作用 |
| 主機工具 | 比照 `tools/rv_card.py`(site A → veneer 找參數區),加 `lut load/status/off` |
| 驗證 | 寫入後用 `rv_snapshot.py` 回讀比對,再啟用 |

## 界線

- **未上機。** 顯示端編碼、bank 路由、寫入時機全部未驗證。
- 使用者 LUT **不改變**錄製色彩,這是設計目標也是驗收條件:開關 LUT 前後,
  CinemaDNG 的 `ColorMatrix1/2`、`HueSatMap`、`ToneCurve` 必須逐位元組相同。
- per-hue 做不到。`CUVAREA CARE_SEL` 只有名稱,沒有暫存器,需要實機 diff 才能用。
- `cube2fp.py` 的定點輸出是**依指定尺度換算**的,顯示端真實尺度量到之前不能直接寫。
- 3×3 + 1D 對高飽和色的擬合誤差是 ΔE 10–19(實測),不是缺陷而是硬體上限。
