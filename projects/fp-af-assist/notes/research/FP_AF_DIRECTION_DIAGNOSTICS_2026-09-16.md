# fp AF：H/L 方向診斷與訊號語義更正

2026-09-16；fp 5.02。分析四輪已存的原廠 Near 掃焦；本輪沒有新的鏡頭移動、拍照或錄影。

## 結論

**不能只看單次 H/L 比值，就決定往近或往遠對焦。** 現有四輪、24 個有效點，在原廠 H 峰
兩側的 ratio 範圍都重疊；L 在這段已拍到的曲線中始終上升，沒有被包住的峰。
這不是宣稱任何鏡頭／場景的單張判向必然不可能，而是這批資料不足以批准那種控制器。

較可行的下一步仍是「幾何先給方向，已知位置變化後觀察 H/L 的變化」，並處理曝光與濾波狀態。
這只是工程方向；本輪沒有訓練 DFD、估深度或部署自製閉環。

## 1. 可重現的離線結果

輸入為 s1-right-b、repeat-a/b/c，每輪六筆結構驗證通過的完成 Near 歷史。
repeat-a 使用只讀重查版本；不把兩份 reread 當兩次試驗。
新工具 [af_fusion_direction_replay.py](../../../../research/autofocus/af_fusion_direction_replay.py) 會先重跑 history analyzer，
並要求 DMA-copy 原廠 trial／釋放證據；不修改來源，也不接相機。

| 輪次 | 原廠 H 峰 | H/L=0.19 的較大位置解 | 較小位置解 |
|---|---:|---:|---:|
| s1-right-b | 10013 | 10120.39 | 9896.15 |
| repeat-a | 9996 | 10108.88 | 9890.93 |
| repeat-b | 10011 | 10111.95 | 9902.65 |
| repeat-c | 10013 | 10115.12 | 9901.71 |

表中的兩解是相鄰實測點的**分段線性內插示例**，不是額外實測點或獨立深度真值。
0.19 是檢視資料後選的示例水平，不是可部署的分類門檻；沒有向採樣範圍外延伸。
就這些曲線而言，同一 ratio 可落在 H 峰兩側約相差 200 多個位置單位的點。

每輪五個相鄰配對中，有一個跨越原廠 H 峰，先排除，剩下合計 16 個同側配對：

| 指標 | 已知 Δposition 下，斜率方向與原廠 H 峰方向一致 |
|---|---:|
| H | 16 / 16 |
| H/L | 16 / 16 |
| L | 12 / 16 |

**這不是 100% 對焦準確率。** 峰標籤本來就由同一條 H 曲線產生，H 一致性存在循環性；
這只是 in-sample sanity check，沒有 held-out 場景、獨立光學真值、反方向掃描或 exposure alignment。
四個跨峰配對未被計入；不能把結果外推到未知移動方向、主體運動或越峰後如何停止。

特別是 repeat-a：H 的離散最高點在 9940，而 H/L 最高點在 10074，差一個 134-unit 採樣步距。
因此 ratio 不能直接取代 H 當原廠峰位；用相同資料自我校正後再報準確率也不成立。

## 2. H/L 不是「帶通值減 scanmin」

來源均為 `out/decomp/full/blk_c02.c`：

1. `C023E1A0` 取得 DMA 統計並按 ROI 累加（44014–44028、44053–44064）。
2. `C023E6F8` 呼叫分帶縮放、條件式 H 修正與 32-bit 飽和（44244–44253）。
3. mode==1 時 offset=256，其他 mode=0（44236–44240）；輸出 area H/L 加入該 offset（44269–44271）。
4. `C023E9D0` 原樣複製至 `C32985E8[]/C32986B4[]`（44363–44374）。
5. `C023EC28` 的第二參數來自該 offset，減法只寫 context `+21C0/+21C4` 和 `C32914FC`
   （44393、44422–44448），不是從兩個 area array 扣除掃描最小值或物理雜訊。

H/L 的 scaling factors 分開（44512–44515、44544–44597）；H-only correction 是條件分支
（44658–44685、44916–45001）；飽和可到 `0xFFFFFFFF`（45140–45157）。
因此 `H/L` 能消掉增益，僅在共享乘法因子、比例固定、沒有 offset／clipping 等假設成立時才是代數事實。
不能把這些假設當作相機已保證的性質。

固定 256、掃描最小值與 physical noise floor 必須分開；也不能因已知道某分支有 256，
就對本批每點一律扣 256——原生六點歷史尚未附逐點 processing-mode／filter／gain 標記。

## 3. 即時與原生歷史是不同讀取時點

Near `C026AE50` 初次存 H/L history（67168–67169），`C023C760` 複製至工作陣列
`C3297F88/C3298054`（42725–42729），`C0255A68` 再從工作陣列覆寫本次 history（56816–56817）。
不能用較晚的一次 live peek 當作同一個原生歷史 sample。
完成後的同索引消費仍如既有 analyzer 所驗證；本輪沒有推翻或自行移位那些 H/L–position 配對。

另修正三個常被誤用的名稱：

| 位址 | 本輪核對的含義 |
|---|---|
| C32915B0 | route／策略狀態，不是 focus target |
| C3291958[] | sweep 位置歷史，不是每幀目前位置 |
| C32915C4/C8/CC/D0 | small H / main H / small L / main L，不是 now/max/min |

四個 aggregate 的 writer／診斷字串在 44278–44281、44388–44399。
現行 collector 的 `peak_now/peak_max/peak_min` JSON 欄名是**舊別名**，原 binary/JSON 均保留，
本輪不為改名改動資料或 RAM layout。不能從這三個數值推導峰值進度或歷史極值。

## 4. 控制路徑與現況

[驅動 gate 審核與唯讀鏡頭查詢](FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md) 發現，
`C04EF7D0` 不含舊筆記聲稱的完整 capture/recording gate，成功碼亦非合焦完成。
本輪只做既存 native getter／cached conversion，未做位移；對稱 ±100 查詢被近端邊界檢查中止。

下一輪位移試验前仍需：支援的 completion/abort、當前鏡頭的真實可用範圍、AF／capture idle、
cache/table 位置與運動時位置回讀的差別，以及逐點曝光／filter 標記。不能以 host timeout 當鏡頭停止。

## 5. 證據與驗證

- [方向重播 JSON](../../../../research/autofocus/captures/af-fusion/2026-09-16-direction-study/direction-analysis.json)：逐點／逐 pair 數值、來源 SHA-256、限制。
- [唯讀查詢及拒絕原因](../../../../research/autofocus/captures/af-fusion/2026-09-16-direction-study/lens-readout.json)：保留原始回覆與錯誤，未美化成成功。
- [方向測試](../../../../research/autofocus/test_af_fusion_direction_replay.py)：31 項。
- [唯讀命令 mock 測試](../../../../research/autofocus/test_af_fusion_lens_readout.py)：8 項，沒有接相機。

加上既有 collector 21 項、history analyzer 40 項，共 100 項測試；科學有效性不由測試數量保證。
分類仍遵守 research/autofocus：工具為散檔、筆記在 notes、證據在 captures；不改 fpSup 产品工作樹。
