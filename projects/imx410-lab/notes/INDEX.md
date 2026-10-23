# imx410-lab 筆記索引（先讀這份；2026-10-22 整理）

## 現行（從這裡開始）
| 文件 | 內容 |
|---|---|
| **GENERATOR.md** | 生成器（sensor mode creator）的全部參數、24 種讀出類別、規劃與產生表的規則、驗證狀態 |
| **SMC_VERIFY.md** | 生成器驗證循環的每一輪紀錄與待做 |
| **DEV_PLAN.md** | 開發計畫；D1（自訂讀出）的狀態只維護在這裡 |
| **ARCHITECTURE.md** | 四模組分工：1 sensor mode 生產器、2 ISP profile（res-lab）、3 res-custom、4 UI |
| **CAPABILITY_MAP.md** | 每項能力的證據等級與下一步（PDAF 結案、ISO 暫停等） |
| **ISP_SIZE_RULES.md** | 錄影/預覽/RWZM 尺寸規則（含 TIM x 窗補充） |
| **SUMMARY_2026-10-21.md** | 10-21 成果與推翻的舊結論、量幀率的標準方法 |
| **RESEARCH_DIRECTION.md** | 研究方向 1–7 的完成狀態 |
| **IMX410_RULES.md** | 全部實測紀錄（§1–§67，依時間追加）；舊節已在原處標 ⚠ 訂正 |

## 規則的程式版本（唯一來源）
`readout_cfg.py`（讀出規則）→ `readout_plan.py`（UI 規劃）→ `readout_export.py`（res-custom 覆寫）→ `readout_validate.py` / `readout_batch.py`（上機驗證）。

## 專題
HDR_RESEARCH.md、THERMAL.md(溫度 ADC→°C 表與過熱門檻)、HDR_RECON_REFS.md、L7_14BIT.md、ISO_MODE_SWITCH.md、AE_FLICKER_STOCK.md、PDAF_A7III_DIFF.md、VMAX_SOURCE.md、
MODE_TABLES.md、MODE_TABLES_CONSUMERS.md、MODE_TABLE_RULES.md(逐欄位重建規則)、BUFA_FRONT_TAP.md、SENSOR_BUS_READ.md、ZCAM_COMPARE.md、ASTRO_IMX410.md、WEB_IMX410.md。

## 已過時（保留歷史，檔頭有標示）
CYCLE_PLAN.md、PARAM_STATUS.md、RESWEEP_DESIGN.md（方法仍有效）、READOUT_SOLVER.md、PROJECT_FEASIBILITY.md。

## IMX410_RULES 裡被訂正的節（原處已標註）
§14（0007/0008）→ §44/§53；§15（幀率）→ §46/§48；§20（0003）→ §58；§31（L2b 96 fps）→ §49；§34 → §35/§40；§35 暗部數字 → §40；§46 初版 → 已改寫；§49 的「TIM 行長」= 接收端 x 終點。

## 2026-10-22 磁碟：captures 的原始幀已壓縮
- `captures/**/frame*.raw` 全部改成 `*.raw.zst`（zstd -19，約剩 60%；硬碟只剩 668 MB 時做的）。`resweep.decode` 會自動讀 .zst；其他舊分析腳本直接讀 `.raw`，要重跑先 `zstd -d --rm <檔>` 或整目錄 `find DIR -name '*.raw.zst' -exec zstd -dq --rm {} +`。
- `smc_validate.py` 從此只留**失敗組**的原始幀；通過的組只留 result.json / frame.json / summary。
