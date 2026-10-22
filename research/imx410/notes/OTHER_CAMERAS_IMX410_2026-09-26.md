# 其他 IMX410 相機韌體 —— 四家彙整(2026-09-26)

> 2026-09-27 AF 分類補充：本表的 IMX410 是研究分類，不代表每機已確認相同 variant。BMCC 6K 外包 10.3 的內層相機版本是 10.2.2，官方已加入 PDAF；不能當無 PDAF 樣本。Panasonic／Leica 主 AF 尚未解。新的比較與邊界見 [跨機型 AF 研究](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/NON_PDAF_CAMERA_REFERENCE_2026-09-27.md) 與 [PDAF 重審](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md)。

靜態分析,未碰任何相機。各家細節:`nikon_imx410/notes/NIKON_IMX410.md`、`panasonic_imx410/notes/PANASONIC_IMX410.md`、
`other_imx410/notes/OTHER_IMX410.md`;先前:`sony_a7m3/`、`zcam_e2f6/`、`bmcc6k/`。[C] 位元組/程式證實 · [?] 推論。

## 取得狀況

| 相機 | 韌體 | 能否解開 | 取得的 IMX410 資料 |
|---|---|---|---|
| Z CAM E2-F6 | 1.0.13 | ✓ | 33 欄暫存器表 + 尺寸/ADC 表(Sony 參考清單 [?])|
| Sony A7 III | 4.04 | ✓ | 19 欄 |
| **Sony α7C** | 2.03 | ✓ | **19 欄 × 349 暫存器**;確認 IMX410 [C] |
| **Nikon Z6 / Z6 II** | C3.80 / C1.70 | ✓(Nikon-Patch XOR)| **找不到 Sony 格式暫存器表** [C 多種搜尋皆 0];只有 Nikon 自己的尺寸表 |
| Nikon Zf | C3.01 | ✗ 新加密,無公開方法 | — |
| Panasonic S1/S1H/S5/S5 II/S5 IIX | V2.4–V3.7 | ✗ UPD 容器,程式分區逐區 IV 加密 | — |
| Leica SL2-S | 6.3.0 | ✗ 整檔 NOT 後同類 UPD,程式分區加密 | — |
| DJI Ronin 4D | — | 官方無下載檔 | — |
| BMCC6K | 10.3 | 主程式加密(先前)| — |

## 跨廠牌一致的否定結果 [C]

五份可讀的 IMX410 設定(fp、Z CAM、A7 III、α7C,加上 Nikon 尺寸表的旁證)都:
- **沒有被使用的垂直三抽頭**(`0737/0738`=4 只出現在 Z CAM 的死欄位 2020×336);
- 合併時 `0734` 只有 1 / 3 / 5(不合併 / ÷3 / ÷2),沒有第四個值;
- 奇數倍率只有 ÷3;沒有 RAW14 + 合併的組合。
與 `REDUCTION_KERNEL_MEASURED.md` §7.63 的幾何模型一致。

## fp 沒有、但別家有的讀出

| 讀出 | 來源 | 可能用途 |
|---|---|---|
| 全像素 1:1 + **fast 類比**(3412 / 2830 列)| α7C | 高格率 16:9 全寬 / 1.2× |
| 專用 4160 寬讀出(43 RAW14 / 44 RAW12 / 44 ADC11)| Z CAM 清單 | 4K 到 72p;ADC11 到 90/120/170p |
| 全幅 ADC11(6064×4040)| Z CAM 清單 | 快速全讀出(推估捲簾 ≈ 18.5 ms)[?] |
| RAW14 專用垂直視窗(2950 列)| α7C | 14-bit 裁高 |
| Sony preset 21(merge 關、RAW14 類比指紋)| α7C | 唯一「14-bit + 縮減」候選 [?] |
| **全寬、只垂直 ÷3(6064×1138)**| Nikon 尺寸表 [?] | 全水平解析度的 ÷3;依 §7.63 應為對齊的幾何 |
| 全高、只水平 ÷2(3032×4040,Sony 59)| Z CAM 清單、Nikon AF 記錄 | — |
| 全寬、只垂直 ÷2(6064×2012)| Z CAM 清單 | — |
| 全寬垂直視窗範本(6064×3260/3132/2700/2592/2560/1728/1188)| Z CAM | 任意高度視窗的 `0022–0025` 值 |

另:α7C 確認 **輸出列數 = 2 × (`0x072A` | `0x072B`<<8)**(見 `SENSOR_MODE_METADATA.md` §8.1)。
Nikon 的尺寸表不一定是感測器讀出尺寸(可能是 ISP 輸出),以上 Nikon 行都只能標 [?]。
