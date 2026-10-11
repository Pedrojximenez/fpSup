# Native subject 輸入契約：第二個離線增量

原程式／證據目錄：[research/autofocus/analysis/native_subject_20260927](../../../../research/autofocus/analysis/native_subject_20260927/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

2026-09-27。完成正確來源的資料解碼及合焦事件接點稽核。相機正在使用，全程未連線、未操作鏡頭、未改卡片或部署韌體。

## 程式變更

1. [af_fusion_collector.py](../../../../research/autofocus/af_fusion_collector.py) 升為 JSON v7。舊 AFF1 所謂 face 實為 AAT 結果，所謂 AAT box 實為計數與單一座標，face ID 讀值亦錯位。新版按已知來源保留 raw 整數與完整 40 bytes，不再從它們輸出幾何尺度／主體 ROI／tracking ID。AF、gain、capture guard 與 wire layout 保持原語意。
2. [af_subject_observation.py](../../../../research/autofocus/af_subject_observation.py) 新增完整 native byte-slice decoder，分開 face group、adopted AAT publication、AAT model；提供原值、offset／型別／來源說明及全長 bytes_hex。未知的來源時間、身份連續性、投影／鏡頭條件仍保持未知，不直接轉成 FgSample。
3. `decode --jsonl` 拒絕覆寫既存檔案，保護原始 JSONL 的 host 時戳與 binary。本輪只改 snapshot 的來源說明註解，組譯結果仍為原本 1000 bytes；未換讀取地址、未安裝 handler。

## 驗證

- AF 工具與新 decoder **149 項測試通過**；其中新 native decoder 13 項，collector 新增 7 項。包括 plausible 框、高 quality、舊 valid flags 全亮時仍不能升格成幾何資格，以及原始型別、位元組與既存檔案的保存。獨立核對另修正 face 兩組座標為 signed i32，避免左上角為負時被解成巨大正值；size／ID 維持 u32。
- 幾何核心 **39 項測試通過**，其程式未改；未恢復電腦即時 AF 控制。
- 15 份既有 binary、3,538 records 均可重新解碼（v1=432、v2=3,106）。每筆 40 bytes subject 片段完整保留，無幾何資格或有效 cue。
- 每份 binary 重解前後 SHA256 相同，詳見 [legacy-redecode.json](../../../../research/autofocus/analysis/native_subject_20260927/legacy-redecode.json)。這是本輪不變性檢查；歷史 manifest 沒有 samples.bin hash，不能聲稱已驗證採集當時完整性。舊 samples.jsonl 沒有改寫。
- `inspect`：record 212 bytes、handler 1000 bytes、SHA256 `38d121bdf2fdd0653a779070a09fb1c3b93e9594719895a2ffe4e4b98eb757c0`，與先前 binary v3 相同。這是離線組譯，不能證明實機已驗收。

由 SIGMAfp_re 根目錄可重現：

```sh
python3 -B -m unittest discover -s research/autofocus -p 'test_af_*.py'
python3 -B -m unittest discover -s fpSup/focus/geometry -p 'test_*.py'
python3 research/autofocus/af_fusion_collector.py inspect
```

新 decoder 使用方式（給後續已擷取的完整區塊，不會自行連相機）：

```python
from pathlib import Path
from af_subject_observation import decode_native_subject

observation = decode_native_subject(
    face_group=Path("face-group.bin").read_bytes(),  # exactly 0x9C bytes
    face_group_index=0,  # native slot, not persistent identity
    aat_publication=Path("aat-publication.bin").read_bytes(),  # 0x28 bytes
    aat_model=Path("aat-model.bin").read_bytes(),  # 0x2C bytes
)
```

缺少來源就省略對應參數，不能補零冒充實際擷取。三塊 bytes 同時存在也不保證相同曝光／來源 epoch，`geometry_eligible` 仍為 false。現有 AFF1 不能提供這三份完整區塊。

## 影響下一步的發現

[確認事件稽核](../geometry/NATIVE_CONFIRMATION_AUDIT.md)已找到 AfMgr terminal result 與 native-L final drive-end 的具體接點。原廠 AF 成功結果可能早於最後一次鏡頭移動完成；Near 函式返回 1 也可能帶失敗旗標，位置 cache 可由其他路徑更新。

接下來先做 episode／result／final-drive-end 的配對與拒絕狀態機，涵蓋取消、重試、backlash 中間完成、跨主體／跨輪事件、掉事件、重送及 no-op。之後才把經驗證的同輪成功、可信位置及新鮮同主體尺度送入 `fg_confirm`。目前只完成來源契約與離線解碼，native hook、資料來源 freshness、光學 settle 與實機幾何方向仍待驗。
