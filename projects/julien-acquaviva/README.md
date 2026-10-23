# Julien R168 → res-custom

2026-10-23 重新核對上游：main 仍為 `3d60d0f7d3ecbc09843d87a80e35e6adf735abe2`，
本地 `upstream/` 的 35 個檔案均與 GitHub tree 相同，沒有新內容需要覆寫。
最新測試版仍為 R181，推薦正式版仍為 R168；沒有新增公開的 QS 實作原始碼。
詳見 [upstream-status.json](upstream-status.json) 與 [完整自製瓷磚方向](../../research/ui/CUSTOM_QS.md#14-完整自製瓷磚與上游更新核對2026-10-23)。

已提取 **1,552 個有效設定**（4 種 DATA 目標 × 3 比例 × 19 個 crop × 可用幀率），
轉為 **984 個固定畫幅 RCD3 資料檔**。來源是 Julien 的 R168；R181 是測試版，未作為此次來源。
產物屬於離線開發版，尚未上機驗證。

## 他自己的計算公式

有。上游 BIN 內有獨立的 ARM/Thumb 解析度規劃器，結合查表與整數運算。
公開 repository 提供 BIN 和 `modes_v45.json` 結果表，未找到該規劃器的原始碼。
本次直接在 Unicorn 執行他自己的規劃器，禁止執行原廠韌體；只有設定物件 getter
`C0732FCE` 被明確替代，回傳已初始化的 DATA 目標設定。

對公開的有效設定，輸出尺寸與 RWZM 可以由下列規則完整重現：

```text
W, H = 該 crop / fps 的 nominal window
L    = 該 DATA 目標 / 比例 / fps / crop 的輸出寬度上限
a:b  = 3:2、16:9 或 2:1

若 W <= L:
    output = W × H
    RWZM 寫入值 = 1023（韌體實際下夾為 1024，即 1:1）
否則:
    output_width  = L
    output_height = floor(L × b / a)
    RWZM          = ceil(1024 × W / L)
```

例如 SSD、3:2、crop 1.0、24p：`W=6048, H=4032, L=4488`，
輸出 `4488×2992`，RWZM 為 `1380`。
同一個感測範圍在 v90 / v60 / v30 下分別得到
`3576×2384` / `3120×2080` / `2832×1888`。

上限 L 與有效設定範圍是上游規則資料，不是任意 MB/s 代入一條公式就能得到的連續函數。
BIN 還有預覽、光柵對齊、緩衝區、讀出高度及最大幀率限制；上述公式是**有效設定的
輸出尺寸／縮放計算**，不能用它直接產生任意新幀率或感測器暫存器。

純 Python 計算器：[tools/planner.py](tools/planner.py)；規則資料：
[extracted/planner-data.json](extracted/planner-data.json)。兩者不需要韌體映像、Unicorn 或相機。

```sh
python3 projects/julien-acquaviva/tools/planner.py --media SSD --ratio 3:2 --crop 1.0 --fps 24
```

上游函式位置（R168）：`C07945C2` 規劃器、`C079453E` nominal window、
`C079569E` 寬度上限、`C07946B0` 比例／RWZM 計算、`C0794AE2` 光柵／預覽／限制，
`C0734838` 錄影 canvas。這些地址只用於離線解析，沒有安裝上游 hooks。

## 成品

- `build/r168-rescustom/32RESCUS.BIN`：現行 res-custom 核心，新增 2:1 支援。
- `build/r168-rescustom/RESCUS/`：預設六格式；一次最多使用六個 RCD。
- `build/r168-rescustom/catalogue/{SSD,v90,v60,v30}/`：完整 984 格式，供挑選。
- `build/r168-rescustom/index.json`：每檔的 crop、比例、尺寸、來源幀率、額外幀率與雜湊。
- `extracted/r168.json`：1,552 個 native 設定、完整錄影 canvas、donor、原生時序與轉換參數。
- `build/julien-r168-rescustom.zip`：核心、全部 RCD、六個範例、公式計算器及來源對照。

預設六檔都對應 crop 1.0、23.976 / 24 / 25p：

| RCD | DATA | 比例 | 輸出 |
|---|---|---|---|
| JFA10A | FAST / SSD | 3:2 | 4488×2992 |
| JRA10A | REGULAR / v90 | 3:2 | 3576×2384 |
| JMA10A | MEDIUM / v60 | 3:2 | 3120×2080 |
| JSA10A | SLOW / v30 | 3:2 | 2832×1888 |
| JFB10A | FAST / SSD | 16:9 | 4864×2736 |
| JFC10A | FAST / SSD | 2:1 | 5184×2592 |

檔名規則：`J` + DATA（F/R/M/S）+ 比例（A/B/C）+ crop×10（10..28）+ 畫幅組序號。
例如 JFA10B 是同一 DATA／比例／crop 下的另一個固定畫幅，並非 A 檔的更新版。

完整 catalogue **不能整份當作核心的 RESCUS 目錄**：核心最多掃描 16 檔、啟用 6 檔。
請使用範例目錄，或從 catalogue 選擇最多六檔。

## 轉換邊界

R168 的畫幅隨 DATA 與 fps 自適應；RCD3 每檔固定輸出尺寸與錄影 canvas。
因此相同幾何的 native 設定合併為一檔，其他幾何拆開。來源幀率列在 `source_fps`；
res-custom 依 mode ceiling 自動提供的較低／虛擬幀率另外列在 `extra_rate_ranks`。
後者仍使用該檔固定畫幅，不能當成 R168 在該幀率的自適應結果。

錄影 canvas 的 66 欄（除 fps 與兩個平面碼由核心處理）逐欄保存。
原生 `+0x108` 為 4042，與 p83 的原值相同；RCD 的 canvas 區域結束於 `+0x104`。
META、R28、R38、R14、R68、REG 及必要的 TIM/R10 差異轉成虛擬 donor overrides，
不改寫原廠模式表。錄影 physical readout window 與 `nominal_window` 不同；
`quantized_window` 則包含 RWZM 整數量化的數像素差異，三者分開保存。

時序由現行 res-custom 求解。所有正式幀率的
`hmax × (vmax − 1) + tail` 週期與 native 表一致；24p 與 59.94p 的
vmax/tail 分配不同，受核心現有最低 tail 和取整規則影響。它們仍需實機驗證曝光與畫面。

2:1 使用 aspect 9，新核心 version 2 增加有界、具所有權檢查的比例 getter，回傳 `2,1`。
原廠 1..8 比例仍走原廠函式。2:1 RCD 宣告 MINCORE=2，舊核心會拒絕；
3:2／16:9 檔仍是 MINCORE=1，舊資料維持相容。

UI 使用 res-custom 的固定格式選單／QS／standby 慣例，沒有移植上游的動態 crop／DATA UI。
尚未在相機上確認全部 crop 的 standby 視野、放大檢視、錄影、曝光或回放。
尺寸比對的條件是 12-bit CinemaDNG；上游的 lossless 壓縮器和 gyro hooks 不在這次解析度轉換內。
FAST／REGULAR 等名稱表示來源 DATA 目標，不能當作儲存裝置速度保證。

## 重建及驗證

```sh
python3 -B projects/julien-acquaviva/tools/extract_r168.py
python3 -B projects/julien-acquaviva/tools/build_rescustom.py
```

另選六檔時使用新的本機輸出目錄：

```sh
python3 -B projects/julien-acquaviva/tools/build_rescustom.py --out /tmp/julien-selected --select JFA10A,JFB10A,JFC10A
```

離線驗證：

```sh
cd projects/open-gate/build/res-custom
python3 -B -m unittest test_v3_rescustom
cd ../../../julien-acquaviva/tools
python3 -B -m unittest test_conversion
```

既有回歸 65 項；本次驗證涵蓋全部公開設定、RCD round trip、純 Python 公式、六檔載入／canvas、
六種 donor 的實際原廠 readers／sensor register writer 比對、2:1 回放與 ABI、版本拒絕，
以及比例 pair 和所有權 guard 的破壞測試。設定、UI、I/O 與 sensor writer 的硬體邊界由既有
camera harness 替代；離線成功不代表實際感測器或 GUI 已驗證。

本次只在新的本機輸出目錄建置。共用 loader／AutoRun 未修改；沒有寫卡、操作相機或發布。
成品 SHA-256：`build/r168-rescustom/SHA256SUMS.txt`；用於追溯，不是執行期版本綁定。

## 上游來源

[sigma-fp-supmod](https://github.com/julienacquaviva/sigma-fp-supmod)，固定 commit
[`3d60d0f7d3ecbc09843d87a80e35e6adf735abe2`](https://github.com/julienacquaviva/sigma-fp-supmod/tree/3d60d0f7d3ecbc09843d87a80e35e6adf735abe2)。

- [R168 FPOG.BIN](https://github.com/julienacquaviva/sigma-fp-supmod/blob/3d60d0f7d3ecbc09843d87a80e35e6adf735abe2/release/R168/FPOG.BIN)
  SHA-256 `f4cddac261c47021ce666449cdab3deb6c12f1467b019113b6d70909b854fd98`
- [modes_v45.json](https://github.com/julienacquaviva/sigma-fp-supmod/blob/3d60d0f7d3ecbc09843d87a80e35e6adf735abe2/tools/modes_v45.json)
  SHA-256 `55490af681ffb6b530e4085be62255c251b1fafeb2c328255ba626fa71cbb98b`

原始上游檔案保存在 `upstream/`，沒有改動。
