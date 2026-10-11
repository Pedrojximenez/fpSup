# fp 原廠 AF：三輪重複性與完成歷史的離線驗證

2026-09-16；fp Ver.5.02；使用者授權由工具操作相機。

## 結論

三輪同設定原廠 AF 都取得六筆完成 Near 的 H/L–position 歷史，從 H 峰鄰點重算的候選位置
**9996、10011、10013**，全部吻合 Near +64/+7C 保存值。三輪合計 1795 筆新 DMA-copy
snapshot，無 invalid／duplicate／stale／out-of-order／sequence gap；但仍有排程取樣空窗。

這使「讀取完成曲線 → 排除尾巴 → 重現峰值」不再只是單次巧合。
它仍不是 DFD 校正、獨立曝光對齊驗證，或對焦速度／命中率改善。三輪都從相近合焦狀態出發，
沒有刻意改焦距離、光圈、鏡頭、ROI 或曝光；環境／目標的絕對靜止未另以影像量測。

## 實驗邊界與狀態

前置查得 `w71c1 / rel 5.02.0.V91 / xc V91`，firmware git hash
`13aa621060efff11aaba9b21ad925005302605cf`；既有 fpshd 3.0.0 / EP01–EP82。
每輪 6 秒、100 Hz；1.5 秒後送一次 S1ON，約 2 秒後 S1OFF；不重送開始。
未送 S2、未拍照／錄影，未改選單／框／gain，未刷新 firmware、卡片或 shell worker。

所有輪次開始與結束 route 都為 14，中間進入 AF；movie_recording 全程 false。
每輪 events 的 S1ON/S1OFF 都收到完整 `OK \n`；manifest release completed=true、required=false。
歷史讀取後 echo 均為 `C03D99A0`。

前後設定維持：Position=`784 341 128 128`、Mode=`0`、Area=`0`、Size=`3`。
repeat-a 第一次 position getter 出現一次 `moved=12/64` 短回覆，不算成功驗收；
未重送 AF，另存 `native-history-recheck.json` 的只讀核對，四個 getter 全部正確。
repeat-b/c 第一次核對即正確。短回覆與兩次讀回的 live-stat 差異分開記錄，不混成同一失敗。

## 重複性結果

| 輪次 | snapshot 數 | 最大相鄰 camera tick 間距 | 有效歷史 | H 峰 k | 重算＝Near 峰 | 最後命令位置 | AF gain |
|---|---:|---:|---:|---:|---:|---:|---|
| repeat-a | 597 | 39.666 ms | 6 | 4 | 9996 | 10006 | 117→218→117 |
| repeat-b | 599 | 28.903 ms | 6 | 3 | 10011 | 10021 | 117→217→117 |
| repeat-c | 599 | 27.776 ms | 6 | 3 | 10013 | 10023 | 117→218→117 |
| 前次 s1-right-b（對照） | 592 | 82.604 ms | 6 | 3 | 10013 | 10023 | 117→220→117 |

新三輪峰值範圍 17 個鏡頭位置單位；此單位不能直接換成距離、景深或成像清晰度。
最後命令位置都比 Near 峰多 10；它是命令域，不是馬達／光學真值。
新三輪 gain 對應 analog code：基準 985，AF 時 2426/2418/2426，HCG raw 均 0。
gain 脈衝已觀測，但尚未把每一歷史樣本與其實際積分窗口／gain 獨立對齊。

新掃焦證據不只看 Near completion：每輪 events、route 14→AF→14、索引重置、
命令位置變化及新曲線一起支持本輪確有執行。分析器本身仍不把歷史 freshness 自動標 true。
連續 sequence 只是成功呼叫的連續編號，不代表每個預排的 10 ms 時槽都有資料。

## 三輪有效前綴

每輪皆 n=6、d=1、descriptor count=6、state=4、completion byte=1、area/reference=0。
配對 k=0..5；不把 H/L 再偏移 d，不接受尾端額外非零 L 或未填位置。

| k | a position | a H | a L | b position | b H | b L | c position | c H | c L |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 10422 | 2993 | 34756 | 10405 | 3138 | 35060 | 10420 | 2983 | 34841 |
| 1 | 10340 | 4004 | 36544 | 10340 | 3984 | 36574 | 10338 | 4084 | 36740 |
| 2 | 10205 | 6260 | 39465 | 10207 | 6307 | 39560 | 10205 | 6359 | 39492 |
| 3 | 10074 | 8440 | 41909 | 10074 | 8472 | 41898 | 10074 | 8531 | 41971 |
| 4 | 9940 | 8532 | 42855 | 9943 | 8434 | 42740 | 9940 | 8432 | 42922 |
| 5 | 9807 | 7508 | 43038 | 9809 | 7445 | 43039 | 9807 | 7512 | 43161 |

## 為何 full-dump 不相同仍可能有穩定歷史

新三輪的兩次讀回唯一變動 word 是 globals +1C，即 `C32914FC`。
`FUN_C023EC28` 將當前 area-0 L `C32986B4` 減去一個調整值存入此處；
呼叫者 `C023E9D0` 先複製當前 AF 統計，再更新它。
來源 `out/decomp/full/blk_c02.c:44365–44393,44448`；這不是 Near 歷史元素，
也不是 `C025AB90` 插值輸入。不能把那個調整參數任意命名成已知 noise 單位。

因此保留原始 `two_passes_equal=false`，離線輸出分列 `full_dump_stable=false` 與
`history_stable=true`。只豁免這個確定的位址；其餘 metadata、globals 或已讀陣列改變皆拒收。
不重寫證據、不反覆讀到「碰巧完全相同」才當成功。

## 原廠插值與驗證界線

`C025AB90` 的內部峰分支（blk_c02.c:59542–59620）：

```text
a = abs(p[k]-p[k-1]); b = abs(p[k+1]-p[k])
U = (H[k]-H[k-1])*b/a; V = (H[k]-H[k+1])*a/b
T = U-V; delta = round_away((T>=0 ? b : a)*0.5*T/max(U+V,1))
delta 限制在 [-floor(a/2), floor(b/2)]
descending candidate = p[k]-delta
```

韌體用 `C3291605` 決定加減；離線工具僅在嚴格單調位置下推定方向。
尚未捕捉全部分支旗標，因此只是此分支的 candidate，不是完整函式重播。
`C067E2AC → C067F804` 為最近整數、半整數向遠離 0 捨入；不是截斷。
證據：`blk_c06.c:106686–106694,107763–107787`。
一般不等距二次擬合另外輸出，不能說成與原廠公式完全相同。

其他重要 source gates：

- Same-index H/L–position 消費：blk_c02.c:57053–57060、57169–57177。
- 成功 return 在 n 遞增之前：67273–67280；繼續才遞增：67319–67320。
- descriptor count 可暫時預約多一格：67245–67255；工具要求完成 prefix count 一致才接受。
- state 4 或 6 可搭配 completion=1：59156–59184。
- chosen area C3291514，0xFF 是未選；reference area C3291534，兩者一般不必相等。
  工具只支持兩者皆 0 的窄範圍，未宣稱其他 area／aggregate fallback 無效。

## 檔案與下一階段

新工具：[af_fusion_history_analyze.py](../../../../research/autofocus/af_fusion_history_analyze.py)，
[離線測試](../../../../research/autofocus/test_af_fusion_history_analyze.py)，操作例見 [使用說明](AF_FUSION_TOOL_USAGE.md)。
驗證：新分析器 40 項測試、既有 collector 21 項測試全部通過；CLI 已測試拒絕覆寫與來源
SHA-256；1795 筆新 binary 重新解析後，AF／indices／exposure／integrity／nonce 均與原 JSONL 相符。
AF skill 格式驗證也通過。這些測試不等於光學或 DFD 模型驗證。

原始 captures：

- [repeat-a](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-a/manifest.json)、[history](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-a/native-history.json)、[只讀核對](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-a/native-history-recheck.json)
- [repeat-b](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-b/manifest.json)、[history](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-b/native-history.json)
- [repeat-c](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-c/manifest.json)、[history](../../../../research/autofocus/captures/af-fusion/2026-09-16-repeat-c/native-history.json)

各輪另存 handler-source.S 與 near-history-analysis.json；分析輸出記錄來源 SHA-256，
不改 samples、events、manifest 或 history。當前 handler 1000 bytes，SHA-256
`2bcde803e7948b2b0c375147936e37587d5d12960e5036e418c07beed484736d`。

接下來有意義的驗證是受控的近／遠失焦起點、曝光變化標記與 H/L 模型方向判別。
應先審查 gated lens-drive 與 drive-end 量測；本次沒有新增任意馬達命令或部署自製 AF 閉環。
