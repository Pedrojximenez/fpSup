# 自訂讀出系統的模組分工（使用者 2026-10-22 定）

> **本 session 的範圍：只做模組 1（sensor mode 生產器）**——規則、上機驗證（第 1 層）、輸出給模組 3 的覆寫清單格式。
> ISP（模組 2、3 的 ISP 部分）由其他 agent 負責（使用者 10-22）；第 2、3 層驗證交給他們。

| # | 模組 | 角色 | 現在在哪 | 最終 |
|---|---|---|---|---|
| 1 | **Sensor mode 生產器** | 產生合格的感光元件 mode（讀出等級、合併、格式寬、視窗、消隱、HMAX/VMAX、虛擬表要改的列） | `projects/imx410-lab/readout_cfg.py`（+ `readout_validate.py`、`readout_batch.py`） | 開發工具，不出貨 |
| 2 | **ISP profile 生產器** | 產生錄影/預覽 profile（RWZM Z、rec 矩陣、DefaultCrop、預覽參數、位深、寫檔策略） | `projects/res-lab`（Res Lab producer，RCD 編碼器） | 開發工具，不出貨 |
| 3 | **res-custom** | 在相機上安裝虛擬 mode + 虛擬 profile + ISP 相關設定（RCD consumer） | `projects/open-gate/build/res-custom`（契約：`VIRTUAL_RCD.md`，RCD1 wire v3、Virtual RCD ABI 2） | **出貨** |
| 4 | **新 UI** | 裁切 → 解析度 → fps → 品質（先用 RS 區分）；用 1、2 的實測規則決定可選值並產生配方交給 3 | 規則原型：`projects/imx410-lab/readout_plan.py`（含 `notes/ISP_SIZE_RULES.md`） | **出貨** |

## 資料流
```
(開發期) 1 sensor mode 生產器 ──實測規則──┐
         2 ISP profile 生產器 ──實測規則──┤→ 規則表（讀出等級 × 下限 × 格式寬 × 視窗中心 × 錄影限制）
                                          ↓
(出貨)   4 UI：使用者選裁切/解析度/fps → 依規則表算出「虛擬 mode 列 + 虛擬 profile」（配方）
         3 res-custom：驗證配方 → 安裝虛擬 mode/profile → 韌體自己完成 SetImgMode（ISP、預覽、錄影全對齊）
```
- 出貨時 1、2 不在相機上 → **規則必須濃縮成 4 能在相機上計算的形式**（小表 + 公式），不是一堆預先產生的檔案；
  使用者可自訂長寬，所以配方要在相機上即時算。
- 1 的產出**直接放進 3 現有的虛擬 mode**（訂正：不需要新 section）：res-custom 的 `SEC_VMODES` 已支援以 donor 為底、
  對七張表（TIM、META、R28、R38、R14、R68、**REG**）與放大表做逐字（4 bytes）覆寫 `{donor, kind, offset, value}`，
  最多 256 筆覆寫、16 個虛擬 mode（`ogc_layout.py` TABLES / RCD_MAX_OVR / MAX_VMS，`rcd.py override_ok`）。
  → 模組 1 的輸出格式 = 覆寫清單：REG 列的 0001／0003／0022–0025／0016／快速 AD 組（77 字），TIM +4（HMAX/尾段）、+8（VMAX）、
  +0xC（行長）、+0xE/+0x10（首末列 = 光柵高），R38 +8（DCLP 寬）。覆寫是整字，需以 donor 原字為底合併欄位（離線從 MAIN 映像讀 ROM 表）。

## 驗證分層（每個配方）
1. 感光元件端（模組 1）：接收列數、曝光線性、連拍無掉幀（`readout_validate.py`）。
2. ISP/預覽（模組 2+3）：配方烘進虛擬表後由韌體切換；預覽傳輸計數增加、ISP 偵測影像（0xC375D8C0）與 RAW 相關、ISP 無錯誤旗標。
3. 寫檔（模組 3）：規劃器離線判斷合法性（rec 矩陣、16/10 邊、寬 %16、錄影 fps、資料率），再實錄 3 s 讀回 DNG 檔頭與一幀。
規則：任何會經過模式切換的配方，必須先通過第 1 層（RESWEEP_DESIGN §9）。
