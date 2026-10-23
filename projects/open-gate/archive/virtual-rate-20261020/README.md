# res-custom 的虛擬格率（2026-10-20 移出核心）

> **同日更新（使用者）：核心要能錄所有格率，只是不負責原生介面。** 錄影那一側已經以泛化的形式
> 加回核心：格率改由 RCD 宣告（`SEC_RATES`，`ogc_layout.DEFAULT_RATES` = 原本的 239.76／279.72／17.98），
> 由服務 API（`VRC_RATES`／`VRC_RATE_SET`，`virtual_rcd.h`）選擇、記在 BIN；`SEC_CAPTURE_TIMING`、
> `SEC_WRITER`、DNG FrameRate、最慢快門與角度換算、寫檔策略、Res Lab 的 240/280 畫布、M12 240p 配方都回來了。
> **仍留在封存的是介面部分**：格率選單第 9–12 列、B2_5 頁面複本、LV 格率文字、格率 commit hook
> （rcmt1/2）、快門清單顯示 hook（tvmin2 / tvdisp / anglist）、轉換器 movw/movt 改寫。
> 下表「移除了什麼」描述的是當時的移除，以這段為準。

程式碼另存在這裡，日後要做成介面 sup 時參考。
這個目錄是**移除前一刻**的完整快照（包含同日新增、隨後也一併移除的 `SEC_WRITER`）。

## 內容

| 路徑 | 是什麼 |
|---|---|
| `res-custom/` | 移除前的整個 `build/res-custom/`（`ogc.c`、`ogc_shims.S`、`ogc_layout.py`、`rcd.py`、`vr_ui.py`、`m12_240.py`、`test_lv_text_style.py`、`test_v3_rescustom.py` …） |
| `build/rl_v3.c`、`build/build_v3_reslab.py` | Res Lab 產生器：239.76/279.72 的 20 欄高格率畫布、`SEC_WRITER` 宣告 |
| `build/build_m12_240.py`、`build/test_m12_240.py` | M12 239.76p 開發配方與其測試 |
| `build/test_virtual_rcd_rates.py`、`test_reslab_rate_commit.py`、`test_reslab_record_rate.py`、`test_reslab_hirate_canvas.py`、`test_reslab_header_copy.py` | 只測虛擬格率的測試 |
| `build/test_reslab_preview_route.py` | 移除前的版本（現行版本已刪掉 240/280 那個測試，其餘保留） |
| `build/test_virtual_rcd.py`、`build/imx410_rate_lv.py` | 參考用副本（現行版本未改） |

## 移除了什麼

**格率**：239.76、279.72（載在 119.88 上）、17.98、8.99（載在 23.98 上）。核心現在只產生原廠 9 個格率的 picker entry。

**hook（10 個）**

| 名稱 | 位址 | 作用 |
|---|---|---|
| rcmt1 / rcmt2 | C057A6F8 / C05821B8 | MV_FrameRate commit：記 S.VRATE、同載體換格率時重載 LV |
| recrate | C00C9BD0 | CinemaDNG FrameRate 有理數 |
| tvmin / tvmin2 / tvdisp | C007F5B4 / C0553CDC / C00A075C | 最慢快門的下限與顯示 |
| anglist / angtv | C0554768 / C052DCFC | 快門角度清單與角度→Tv |
| hdrcopy / bulk | C00FBB90 / C03A5144 | 279.72p 的 DNG 標頭 CPU 複製、4 MiB 寫入批次 |

**其他**

- 格率轉換器與摘要轉換器的 movw/movt 改寫（C06BDB0C/10/18、C06CB6DC/E0/E8）。
- B2_5 頁面複本（加第 9–12 列的摘要、游標、ListItem）。
- 六份格率 CSV 複本裡**新增的**第 9–12 列。
- LV 待機文字（vrlv）與 16 筆 LV 文字紀錄替換（`lv_text_record`）。
- 存檔紀錄裡的 VRATE（`CFG_FLAGS`）與開機還原。
- `SEC_CAPTURE_TIMING`（12）：讓載體格率以另一個感光元件格率錄（H2S240 / native30 實驗）。
- `SEC_WRITER`（14）：279.72p 的寫檔策略。
- 這兩個 section 號碼**不再使用**；要求它們的檔案會以 `UNKNOWN` 被拒絕，不會默默錄錯。

## 留下來的（不是虛擬格率專用）

- 六份格率 CSV 的**原樣**複本與「依 entry 反灰原生格率」（`rate_install` / `rate_follow`，跟位深 CSV 同一種做法）。
- `FR_GET`、`rank_of`、反灰的 gate（frmax / frclass）。
- 時脈閘 `0xC0189440`：只在有格式快於 99.99 fps（或有 Virtual RCD 動態列）時改。

## 已知的相容性影響

- 存了虛擬格率的舊存檔（v21 核心）：開機只還原格式，格率回到相機設定裡的原廠格率（119.88 或 23.98）。
- 要求 section 12/14 的 RCD（例如 Res Lab 舊版 SAVE 出來、帶 280p 寫檔策略的檔）會被拒絕，要用新的 Res Lab 重新存。
- Res Lab 計算機頁面的頻寬估算選項（`SL_O_RFps`，含 239.76/279.72）屬於 Res Lab 自己的 UI，這次沒有動。
