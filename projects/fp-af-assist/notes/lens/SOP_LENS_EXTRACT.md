# SOP — 任意鏡頭資料擷取(給 AI 對焦程式用)

原程式／證據目錄：[research/lens/notes](../../../../research/lens/notes/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

**流程:插鏡頭 → 插卡跑 AutoRun → dump 檔丟 parser → 輸出 JSON → 對焦程式讀。**
不需 UART、不需 debug 模式、不需改韌體。對每顆鏡頭都一樣。

## 為什麼可靠(不再靠猜位址)
鏡頭資料塊在 RAM 裡帶一個 magic 標記 **`_LENS_DATA_:`**(韌體 `createBinIndexImpl` 用它定位)。
parser 掃 dump 找這個 magic → 以**鏡頭名字串**為錨點抽欄位(韌體結構佈局跨鏡頭一致)。
所以位址每次不同也沒差,自動定位。

---

## 步驟 1:AutoRun.txt(固定,所有鏡頭共用)
放 SD 卡根目錄:
```
mem save \CANARY.bin 0xC0000600,,0x100
mem save \HEAP34.bin 0xC3400000,,0x100000
mem save \HEAP35.bin 0xC3500000,,0x100000
mem save \HEAP37.bin 0xC3700000,,0x100000
mem save \HEAP38.bin 0xC3800000,,0x100000
```
- 4 個 1MB 堆群,**跳過 0xC36 未映射空洞**(連續讀會當機)。鏡頭資料一定落在這 4MB 內。
- `CANARY.bin`(256B)= 驗證用,對得上韌體進入點就代表機制正常。

### 執行要點
1. **乾淨環境**:先關機、拔 USB、重開機(別進 PTP/USB session ── 殘留狀態會害它失敗)。
2. 裝**要讀的鏡頭**(要能通訊/對焦的 L-mount 鏡頭)。
3. 插卡觸發,等卡燈跑完(4MB 幾秒)。
4. 檔名衝突時相機會加序號(CANARY000.bin…),parser 不受影響。

## 步驟 2:三支腳本(身份 + 對焦距離表 + 每脈衝離焦量)
```
python3 tools/parse_lens.py            HEAP34.bin HEAP35.bin HEAP37.bin HEAP38.bin  # 身份
python3 tools/extract_focus_table.py   HEAP34.bin HEAP35.bin HEAP37.bin HEAP38.bin  # 位置↔距離表
python3 tools/extract_defocus_table.py HEAP34.bin HEAP35.bin HEAP37.bin HEAP38.bin  # DefocusPerPulse
```
- `parse_lens.py` → `lens_<名稱>.json`(身份:name/type_code/serial/maker)。
- `extract_focus_table.py` → `focus_table_<名稱>.json`(位置↔距離,倒數空間內插)。
- `extract_defocus_table.py` → `defocus_table_<名稱>.json`(每對焦步位的每脈衝離焦量 µm,一步到位驅動用)。
  - 來源 `lens_data+0x10c58`(展開後的表,已在四段 dump 內);`dpp_um = defocus_raw/65536`。
  - ⚠️ 鏡頭 ROM 原始 wire(`lens_data+0x2268`→ 0x356BB/136B)在**鏡頭內部**,mem save 抓不到;用展開後的表即可。
- 三支都在尾巴印可貼進 Swift 的片段。

## 步驟 3:JSON 格式(對焦程式讀這個)
**身份**(`lens_*.json`):
```json
{ "name":"28mm F1.4 DG HSM | Art 019", "type_code":"0x6010", "serial":4460197, "maker":"SIGMA" }
```
**對焦距離表**(`focus_table_*.json`,對焦最關鍵):
```json
{ "name":"28mm F1.4 DG HSM | Art 019", "mode":"prime", "n":19,
  "distances_mm":[1000000,3232,...,278],       // 距離(mm),遞減,首值=無限遠
  "positions":  [4096,4559,...,13369] }         // 鏡頭內部對焦位置,遞增,與距離同 index 配對
```

### 對焦表的意義與用法
- `distances_mm[i]` ↔ `positions[i]` 同 index 配對 = 這顆鏡頭的**位置↔距離校正曲線**。
- 換算法 = **在「1/距離(倒數/屈光度)空間」做分段線性內插**(韌體 `XC_Linear`)。
  ⚠️ 不能在距離上直接線性內插(近攝端會嚴重偏差)。詳見 **`FOCUS_DISTANCE_PRINCIPLE.md`**。
- 參考實作:`tools/lens_interp.py`(Python)/ `tools/LensFocusTable.swift`(Swift)。
- 相鄰點斜率 = 每單位位置的屈光度變化 → 離焦量預測先驗(見 `AF_DESIGN_REFERENCE.md`)。
- ⚠️ 表裡的「位置」是**鏡頭內部域**(28mm 約 4096–13369),**非 PTP focus_pos**(約 3168–14296);
  兩者差一層線性換刻度,見 `FOCUS_DISTANCE_PRINCIPLE.md` §6。

---

## ★ 跨鏡頭:兩家都給完整距離校正曲線
| 鏡頭 | 身份 | 對焦表(正確來源 +0x348c/+0x3564) |
|---|---|---|
| SIGMA 28mm F1.4 DG HSM Art (0x6010) | ✅ | ✅ 19 點,距離 ∞→278mm,位置 4096→13369 |
| Panasonic LUMIX S 40/F2 (0x4027) | ✅ | ✅ 10 點,距離 ∞→300mm,位置 6276→10706 |

- **兩家(含第三方)都提供真實的距離↔位置校正曲線**,只是支撐點數不同(SIGMA 19、Panasonic 10)。
- 兩顆 lens data 都落在**同一位址**(magic @0xC34645F4)→ 同韌體配置確定性高,利於重現。
- ⚠️ 舊版本這裡曾寫「SIGMA 非線性、Panasonic 只給線性」——那是 **parse_lens 抽到「中間域」錯表**造成的
  誤判,已更正:正確表在 `+0x348c/+0x3564`,由 `extract_focus_table.py` 抽。

## 已驗證 / 界線
- ✅ **機制**:CANARY 逐位元組對上韌體 → 量產機任意記憶體讀出,已實證。
- ✅ **parser 跨鏡頭/跨廠牌**:SIGMA(Art)+ Panasonic(LUMIX)都正確抽出身份;
  focus curve 有/無都正確回報。
- ✅ **通用錨點**:magic + 名字相對 offset(type_code=name−0x48, serial=name−0x44, maker=name+0x13A)
  兩廠牌一致;表用**訊號特徵**偵測(等差 / 遞增差)故長度可變。
- 位址(0xC34–0xC38)是 fp Ver.5.02 的堆佈局;換韌體版本要重新確認堆群範圍。
- 換更多鏡頭若遇到 name/table 沒抓好,回報我微調 offset/特徵即可。

## 檔案(整理後)
- `AutoRun.txt`(專案根)— 固定 SOP AutoRun
- `tools/parse_lens.py` — dump → JSON parser
- `tools/lens_interp.py` — JSON → 位置↔距離內插
- `dumps/28mm_sigma/` — SIGMA 28mm Art:HEAP*.bin + lens_28mm_*.json + focus_table_28mm_*.json(距離 19點)+ defocus_table_28mm_*.json(dpp 22步, 0→6.43µm)
- `dumps/40mm_lumix/` — Panasonic 40mm:HEAP*.bin + lens_LUMIX_*.json + focus_table_LUMIX_*.json(距離 10點)+ defocus_table_LUMIX_*.json(dpp 12步, 0→7.74µm)
- `tools/extract_focus_table.py` — 距離表;`tools/extract_defocus_table.py` — DefocusPerPulse;`tools/lens_interp.py` / `LensFocusTable.swift` — 內插(倒數空間)
- `dumps/_intermediate/` — 早期探索用的中間 dump(CANARY/H*/LENSDAT/LENSOPT/MGR,可留可刪)
