# fp — 用 AutoRun/mem save 抓 RAW 幀(全幅 / live-view)

## 反編譯結論(still_raw_dump 真相)
- `imager debug_out still_raw_dump` = 設除錯遮罩 **bit 2 @ `0xC343A624`**。
- 拍照時(`FrameExpos_s` @0xC0315C10)它**只把 raw 緩衝位址印到 UART**:
  `"Rec Raw OutPut %02d %08x"`、`"table_num %04d raw_addr %08x"`。**不寫卡。**
- raw 緩衝本身在 **DRAM `0x50000000` 區**(`FUN_c001a048(...,0x1000000,...,0x50000000+off)` = 16MB 塊)。
- → 正解:**mem save 直接抓 `0x50000000` 區。**

## 格式(韌體確認)
- `smallraw_size :%05dx%05d`、`smallraw_bit`(0:12 / 1:14 / 2:16 / 3:10 / 4:8 bit)、`smallraw_endian`(Little/Big/Middle)。
- 全幅靜態:6000×4000(fp)/ 9520×6328(fp L),12/14-bit,Bayer RGGB。
- live-view small raw:降採(由 `XC_LiveViewSmallRawManage` 管),環形 `0x50000000 + idx×0x100000`(1MB/幀)。

## ★ 誠實分岔:兩個目標,難度天差
| 目標 | 方法 | 說明 |
|---|---|---|
| **全幅靜態 RAW(照片)** | **直接拍 DNG** | fp 本來就存 12/14-bit DNG = 全幅 Bayer raw。**不需 hack。** |
| **全幅靜態 RAW(pre-pipeline / 非標準模式)** | 拍照後 mem save `0x50000000` 大塊 | 拿管線前的原始 raw;需緩衝仍在 |
| **live-view 連續 raw(自製錄影機核心)** | live view 中插卡 → mem save `0x50000000` 環 | 相機不存的連續幀;降採、單幀/次 |

## AutoRun 方案

### 方案 1:live-view raw 幀(novel)
相機進 live view(裝鏡頭、顯示影像)→ 插卡觸發 → mem save 當前環幀:
```
mem save \CANARY.bin 0xC0000600,,0x100
mem save \LVRAW0.bin 0x50000000,,0x100000
mem save \LVRAW1.bin 0x50100000,,0x100000
mem save \LVRAW2.bin 0x50200000,,0x100000
```
- 抓環形前幾個 1MB 幀。哪個是當前幀要比對(非全零、有 Bayer 紋理者)。
- ⚠️ live view 持續更新,抓到的是插卡瞬間的幀。

### 方案 2:全幅靜態 raw(pre-pipeline)
1. **先拍一張全幅照片**(RAW/DNG 模式)→ raw 留在 `0x50000000` 大緩衝。
2. **立刻插卡**(趁緩衝未被覆蓋)→ AutoRun 抓大塊:
```
mem save \CANARY.bin 0xC0000600,,0x100
mem save \STILLRAW.bin 0x50000000,,0x03000000
```
- `0x03000000` = 48MB(6000×4000×16bit)。⚠️ 大檔、寫較久;若緩衝在別的 offset 要調整基址。
- 更穩:先小塊探針找到非零 raw 起點,再精準抓。

## Bayer → DNG 解碼(組成可看的檔)
拿到 raw 後(假設 6000×4000、12-bit packed、RGGB):
1. 解 12-bit packing(每 2 pixel = 3 bytes,見 `RECORDER_SPEC.md`)或依 `smallraw_bit` 決定。
2. 包成 minimal DNG:`ImageWidth/Length`、`BitsPerSample`、`PhotometricInterpretation=CFA`、
   `CFAPattern=RGGB`、`Compression=1`、加上你已能抽的鏡頭 metadata(型號、對焦距離)。
3. 用 SIGMA 的白平衡/矩陣(在韌體 SensorAdjustment / DngDevelop)或給 dcraw/RawTherapee 處理。

## 界線 / 待實測
- `0x50000000` 是 raw 區基底(韌體確認),但**當前幀在哪個 offset、全幅緩衝確切起點/大小**需實測
  (先探針 dump 幾塊,看哪塊是非零 Bayer)。
- live view 抓到的是**降採 small raw**,非全感光元件;**全幅只在靜態緩衝**。
- 連續錄影級(每秒數十幀)mem save 做不到(一次一幀、寫卡慢)——這是「單幀/縮時」級,不是即時錄影。
- bit depth/endian 依 `cam_still_raw_bittype`/`cam_still_raw_endian` 設定,解碼前先確認。
