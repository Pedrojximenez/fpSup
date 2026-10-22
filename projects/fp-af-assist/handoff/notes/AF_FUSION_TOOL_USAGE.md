# SIGMA fp AF-fusion 工具使用方式

更新：2026-09-16。適用 **SIGMA fp Ver.5.02**、已正常運作的本地 fp USB shell。
這份是操作教學；實測證據與位址推導見 [原廠 AF 實測紀錄](FP_ORIGINAL_AF_TRIAL_2026-09-16.md)。

**重要更正（同日後續稽核）：** 舊 binary v1/v2 的 capture 欄位不能證明未錄影。
新版 v3 / JSON v6 讀取真正 MovieRecording `C30338D0`、四個 busy bytes `C30338C8..CB`，
以及 full-u32 shutter gate `C3033A6C`；舊資料保留 raw 值、recording 解為 unknown。
詳見 [capture 位址與安裝修正](FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md)。新版 handler／安裝流程
已通過離線測試，但尚未完成 v3 collector 的實機驗證；舊 v2 的 100 Hz 結果不自動轉移成 v3 成績。

## 1. 工具與操作邊界

| 工具／動作 | 相機端作用 | 用途 |
|---|---|---|
| collector `inspect` | 無 | 離線組譯、尺寸與 SHA-256 |
| collector `mock` / `decode` | 無 | 測試資料／重播既存二進位 |
| collector `collect` | 暫寫 RAM、借用／還原 echo；不主動對焦或改曝光 | 即時 H/L、位置索引、gain、ROI 與 AF 狀態 |
| `collect --half-press-after ...` | 上述作用，加原廠 S1ON/S1OFF，可能移動鏡頭與改變 AF 期間曝光 | 已獲授權的一次原廠 AF 實驗 |
| history probe | RAM 讀取與設定 getter，不安裝 handler | AF 完成後的原生掃焦歷史 |
| history analyze | 無，僅讀既有 JSON | 完成 Near / area-0 歷史的結構檢查與候選峰值重算 |
| direction replay | 無，僅讀既有 history／manifest | H、L、H/L 同側梯度與跨峰歧義診斷，不是 DFD 準確率 |
| lens readout | native cached getters／conversion；不寫注入 RAM、不驅動 | 查端點與局部距離換算，非光學位置／停止證明 |

manifest 的 `live-read-only` 是「不下鏡頭／曝光控制」，**不是相機 RAM 零寫入**。
安裝這份 skill 不代表授權對焦；只要求寫文件或分析資料時，不連相機、不做測試動作。
這套流程不拍照、不錄影、不刷新韌體，不應為了取得曲線自行擴大到上述操作。

## 2. 路徑與前置檢查

工具保留在研究目錄，不搬到 skill 裡另養一份副本：

```sh
fp_re_root=/Users/dido/Developer.localized/SIGMAfp_re
af_root="$fp_re_root/research/autofocus"
shell_root="$fp_re_root/fpSup/fp_usb_shell"
```

需保留相鄰檔案：`af_fusion_collector.py`、`af_fusion_snapshot.S`、`af_fusion_history_probe.py`、
`test_af_fusion_collector.py`。另有獨立、僅用標準函式庫的 `af_fusion_history_analyze.py` 與
`test_af_fusion_history_analyze.py`，不需 shell 模組。collector 使用 shell 目錄的 `putfile.py` / `armasm.py` 及其組譯依賴。
若專案搬家，改上述根路徑，不更改相機硬編碼位址來猜測相容性。

先離線驗證：

```sh
python3 "$af_root/af_fusion_collector.py" inspect
(cd "$af_root" && python3 -B -m unittest -v test_af_fusion_collector.py)
```

2026-09-16 更正版通過 50 項測試；當前 inspect 為 record 212 bytes、handler 1000 bytes、
SHA-256 `38d121bdf2fdd0653a779070a09fb1c3b93e9594719895a2ffe4e4b98eb757c0`。
nonce seed 為 `C072F7D4`。安裝改為逐字讀回驗證，先透過 ROM 做 D-cache／I-cache publication，
才啟用 RAM handler；不再依賴未發布指令快取的臨時 bulk loader。
inspect 不會檢測 USB、型號、版本或 RAM 位址是否適用。

Live 前確認是支援的機身／韌體，且原有 shell daemon 正常；預設 socket `/tmp/fpshd.sock`。
若需確認 daemon，可用 `"$shell_root/host/fpsh" ping`，這是**主機 daemon ping**，不是 firmware 的 `ping` 指令。
ping 不能證明機身／韌體身分。沒有現成 shell 時停止 live 步驟，另行處理連線，不自行改卡片或刷機。

保留當前 focus rectangle、mode、area mode、size。這四個 no-arg 命令已核對為 getter：

```sh
"$shell_root/host/fpsh" menu SetFocusPosition
"$shell_root/host/fpsh" menu SetFocusMode
"$shell_root/host/fpsh" menu SetFocusArea
"$shell_root/host/fpsh" menu SetFocusAreaSize
```

在 collector 不在執行時讀取並保存回覆；不要與記錄器並行搶 shell。
SetFocusPosition 回 `x y width height`，工作域 1024×682，**不是鏡頭焦點位置**。
本教學不需要 setter，也不要求把設定改成上次實驗的數字。

## 3. 不觸發對焦的即時收集

```sh
python3 "$af_root/af_fusion_collector.py" collect \
  --duration 3 --hz 100 --retries 0
```

省略 `--output` 會在 `captures/af-fusion/` 建新時間戳目錄，完成後印出完整路徑。
要指定可辨識名稱時，`--output` 必須是**不存在的新目錄**；同名重跑會拒絕，不要刪舊資料求方便。
100 Hz 是已通過的一組測試條件，不是所有設定下保證每 10 ms 都取得一筆。

常用參數：

| 參數 | 預設／限制 | 語義 |
|---|---|---|
| `--duration` | 10 秒，必須 >0 | 收集階段時長；不含安裝／驗證 handler 的時間 |
| `--hz` | 20，必須 >0 | 主機排程頻率，不是感測器 fps |
| `--samples` | 無，必須 >0 | 另一個停止條件；**仍受 duration 限制**，非一直等到湊滿 |
| `--retries` | 3 | 一般 collect 的 raw 重試；半按模式的 raw 路徑不使用此重試值 |
| `--timeout-ms` | 200 | USB 交換等待；一般 collect 的本地 socket 仍非獨立硬截止 |
| `--usb-shell` | 由工具路徑推導 | 只在 host 模組位址不同時指定 |
| `--socket` | `/tmp/fpshd.sock` | 只在 daemon 使用其他位址時指定 |

目前 CLI 沒有完整拒絕 NaN／無限大的數值；只用有限、正值和經過驗證的短測試參數。
不要以 `--retries` 或 timeout 的極端值試探硬體。

## 4. 已授權的一次原廠半按 AF

在使用者允許鏡頭動作的範圍內，先說明這次只半按、不拍照，然後：

```sh
python3 "$af_root/af_fusion_collector.py" collect \
  --duration 6 --hz 100 --retries 0 \
  --half-press-after 1.5 --half-press-hold 2
```

開始記錄後至少等待指定時間、10 筆完整記錄及新鮮 snapshot 才嘗試 S1ON。
半按不能搭配 `--samples`；after 允許 0.2–10 秒、hold 允許 0.1–5 秒，
duration 至少要包含 after + hold + 0.5 秒。若資料不合條件或剩餘時間不足，可能整輪不觸發。

S1ON 不重送。finally 會嘗試 S1OFF，然後才還原 echo。控制回覆須為完整 `OK \n` 封套；
空 EOF 不是成功。半按模式的 host 交換另有有限等待，但不等於相機端 watchdog：
斷線、daemon 故障、主機被強制終止仍可能妨礙釋放。
工具只接受新鮮 v3 記錄；真正錄影旗標、四個 capture busy flags 或完整 shutter gate 任一非零
都拒絕 S1ON。這些是取樣條件，**不是與使用者操作互斥的硬體 interlock**。

正常中止使用一次 Ctrl-C，讓它跑 finally；不要用強制終止作為正常停機方式。
看見 cleanup 失敗／無法確認釋放時停止所有後續鏡頭動作，保存事件和錯誤，先處理釋放／恢復。
不要為救一輪資料繼續重送 AF 或強寫未知 handler。

## 5. 讀取原廠完成後的掃焦歷史

等 AF 已停止、collector 已結束並完成清理，再把其印出的**實際目錄**設為 `capture_dir`：

```sh
# 請填剛才工具印出的路徑，不要照用舊實驗目錄。
capture_dir=/absolute/path/from/the/completed/collector
python3 "$af_root/af_fusion_history_probe.py" \
  --output "$capture_dir/native-history.json" --count 32
```

`--count` 允許 1–128；預設 32。输出檔不可已存在。
probe 取兩輪 Near metadata、descriptor、globals、位置與 **area 0** H/L 前綴，並保存四個 getter、
echo readback。它只讀固定範圍，不會依當前 AF area 切到其他區域，也不會觸發新的掃焦。

必須人工／分析程式另外驗證：

1. AF 在讀取期間確實停止；兩輪內容相同只證明未觀察到變動，不能單獨證明是新的完成曲線。
2. 核對原始兩次讀回的差異、Near vtable C091F134、completion byte +28=1，descriptor pointers 正確。
   完整相同最容易核對；唯一已查明可變例外是 `C32914FC`，見下節，不可泛化為忽略 globals。
3. Near state 4 可以同步完成；不可一律要求 state 6，也不可任意 state 都接受。
4. 核對 raw n、delay d、descriptor count、有效前綴，並確認 area 0 正是本次分析的區域。
5. 這條已驗證 Near 路徑中，若 `0≤d≤n<1000` 且完成 metadata 一致，最後已填位置為 n−d；
   必須與 count 等證據一致再配對。不要把此公式直接泛化到所有策略。
6. 完成後配 `H[k]/L[k] ↔ mposm[k]`，不再把 H/L 位移 d 格。
   0 可以是合法位置；非零尾端也可能是舊曲線，不用數值是否為零判斷長度。

原始 words 是 u32，像 position 或 signed flag 需要時按二補數解讀；probe 不會自動轉型。
`two_passes_equal=false` 仍會正常 exit 0，因此「程式成功」不等於資料可用；也不一定是歷史變動，
因為這包資料還包含即時統計。必須辨明是哪個位址有差異。
若 count 超過當次讀到的前綴，不能假裝已讀完；須另一次新的只讀擷取／工具擴充。

### 5.1 離線 Near / area-0 分析

```sh
python3 "$af_root/af_fusion_history_analyze.py" "$capture_dir/native-history.json" \
  --output "$capture_dir/near-history-analysis.json"
(cd "$af_root" && python3 -B -m unittest -v test_af_fusion_history_analyze.py)
```

完全離線，不載入 USB 模組；不指定 `--output` 時印 JSON。輸出必須是新檔，不建立父目錄。
exit 0 只表示支援範圍內的結構檢查通過，exit 2 是輸入／參數被拒絕，不能把 0 當成 DFD 通過。
它會自行比較兩次 words，不信任檔案聲稱的 `two_passes_equal`；原始旗標若與內容矛盾也拒收。

支援範圍刻意保守：固定區塊位址／長度、u32 words、兩次 metadata／所有已讀陣列穩定；
Near vtable、state 4/6 + completion byte 1、非負 d/n、descriptor count=`n-d+1`、delay copy、
四個 pointer、足夠的已讀前綴、Near +10 interpolation offset=0，並要求 chosen area
`C3291514` 與 reference area `C3291534` 都為 0。兩者在一般韌體流程不必相等，
此限制只是工具目前驗證的 area-0 protocol，不是宣稱其他 area 無法對焦。

**唯一可變例外 `C32914FC`：** `C023EC28` 持續把當前 area-0 L 減去一個調整量存於此處，
與 Near completion 無直接相依；它不是歷史元素，也不進入這次峰值插值。
工具保留 `full_dump_stable=false`，另報 `history_stable=true`、差異位址和前後值。
任何其他 word 變化都拒收；不修改 probe 原始 JSON，也不容許「兩次看起來差不多」。

輸出有效前綴，將 position 轉 signed i32；0 可是合法位置，不用非零尾巴延長陣列。
峰值重算只實作**唯一、內部 H 最大值、嚴格單調位置**的原廠加權分支，採最近整數、
半整數向遠離 0 方向捨入，再限制於鄰點半步；另列一般二次曲線頂點，不混成同一演算法。
方向由單調位置推得，未擷取的韌體方向／分支旗標仍是限制，因此命名為 candidate，
不是完整韌體 replay。端點、重複位置、方向反轉、並列峰值等不產生插值候選。

即使得到原廠同值，也保留 `freshness_confirmed=null` 與 `usable_for_dfd=null`：
舊 Near 物件可能仍完整，需以 events／當輪 route／索引重置／新歷史另證明新掃焦；
原生歷史未附逐點 gain，不能直接認定六點曝光一致。設定 getter 或 echo 的驗收仍是獨立步驟。
三次重複實驗及公式來源見 [重複性紀錄](FP_AF_REPEATABILITY_2026-09-16.md)。

### 5.2 離線 H/L 方向診斷

```sh
python3 "$af_root/af_fusion_direction_replay.py" \
  "$af_root/captures/af-fusion/2026-09-16-s1-right-b/native-history.json" \
  "$af_root/captures/af-fusion/2026-09-16-repeat-a/native-history-recheck.json" \
  "$af_root/captures/af-fusion/2026-09-16-repeat-b/native-history.json" \
  "$af_root/captures/af-fusion/2026-09-16-repeat-c/native-history.json"
```

預設只印 JSON；`--output NEW.json` 要求新檔、已存在父目錄。每個 history 旁必須有
manifest，且為已釋放的 DMA-copy 原廠 AF trial；同一 parent 內 reread 不可重複計數。
`--ratio-level` 預設 0.19，必須有限且 >0，只計算分段線性內插交點，不是學好的判向門檻。
來源位址、完成性與峰值先由 history analyzer 驗證；本工具不讀 samples 補出逐點曝光。
傳輸 counters 仍會附上，不把原始 invalid reply 改成 0。

以**同一批 H 算出的原廠峰**作參考，先排除跨峰／碰峰的配對，再列局部斜率方向的一致數。
所以即使 16/16，也不是獨立準確率；不外推到反向運動、其他場景或閉環控制。
zero-L 的 ratio 是 null，pair 棄權，不用除零或任意 epsilon 製造方向。
詳細語義與舊筆記更正見 [方向診斷](FP_AF_DIRECTION_DIAGNOSTICS_2026-09-16.md)。

### 5.3 不移動鏡頭的原廠 getter／換算

這是 **live 操作**，不是離線驗證的必要步驟。使用前讀
[drive-gate 審核](FP_FOCUS_DRIVE_GATE_AUDIT_2026-09-16.md)，並確認使用者範圍允許查詢既有相機。

```sh
python3 "$af_root/af_fusion_lens_readout.py" --output /existing/directory/new-readout.json
```

使用現有 socket（可明確 `--socket`），host lock、bounded exchange、型號／版本驗證，
只送 `lens getfpos/getfedge/cnvfpos/cnvfdist`，沒有 focus drive、wait/abort、setter 或 injection。
距離 edge 先換成 nominal position range；只有 current±100 都在該範圍時才做**數值換算**，
再讀 cached position。無論成功與否都保存已收到的 transcript，輸出不可已存在。
即使 exit 0 也不是鏡頭運動完成或光學測距證明；exit 1 的 guard/transport 例外應檢查保存的 error。
邊界 guard 失敗時停止，不改用 ungated `lens setfpos`，不重試移動來「救資料」。
nominal distance-converted edge 並非含 allowance 的 driver hard limit，不能直接拿來控制。

新工具測試均為離線；lens suite 完全 mock transport：

```sh
(cd "$af_root" && python3 -B -m unittest -v \
  test_af_fusion_direction_replay.py test_af_fusion_lens_readout.py)
```

**欄名警告：** collector 的 `peak_now/peak_max/peak_min` 是既有 schema 的舊名，對應
small H/main H/small L aggregate，不是 now/max/min。H/L 也不是已扣 scanmin 的 raw 值；
固定 mode offset、noise floor、增益校正不得混為一談。本輪不覆寫舊 capture 欄名。

## 6. 保存、重播與驗收

一轮 collector 通常產出：

- `manifest.json`：handler hash、參數、時間、傳輸计數；半按模式另有 release 狀態。
- `samples.bin`：新版 v3 為原始 212-byte records；舊 v1/v2 為 208 bytes，重播自動依 header 辨別。
- `samples.jsonl`：包含 host 時戳的已解析資料；binary 本身沒有 host 時戳。
- `events.jsonl`：僅半按模式；開始／釋放的嘗試、回覆或例外。
- `native-history.json`：需另執行 history probe 才有。

另保存當次 handler 原始碼、前置設定與解讀紀錄；不可把推論寫回原始資料冒充量測。
重播與離線測試不需要接相機：

```sh
python3 "$af_root/af_fusion_collector.py" decode "$capture_dir/samples.bin"
python3 "$af_root/af_fusion_collector.py" decode "$capture_dir/samples.bin" \
  --jsonl "$capture_dir/decoded-offline.jsonl"
```

`decode --jsonl` **會覆寫已存在的目標**；輸出必須用新檔，絕不能指向原始 samples.jsonl，
否則會丟掉 host 時間資料。`mock --output` 則要求不存在的新目錄。

驗收不能只看 exit code：

- collector exit 0：有寫出記錄；不保證零遺失或光學有效。
- collector exit 2：沒有完整記錄；argparse 參數錯誤也可能是 2，需看訊息。
- collector exit 3：半按模式沒有嘗試開始；不代表一般工具錯誤。
- 例外／cleanup 失敗：保留 manifest、events、stderr；不能標成成功完成。
  manifest 沒有獨立 `run_error`／`echo_restored` 欄位，必須一起核對程序退出與實際 readback。
  history probe 是全部讀完才寫檔，途中失敗可能沒有部分 JSON；保留原有錯誤輸出。
- 檢查 invalid、stale nonce、duplicate、out-of-order、sequence gap；再看 camera tick 間距。
  sequence 連續仍可能有主機排程／USB 等待造成的採样空窗。
- `snapshot_coherent=true` 不是曝光對齊證明，`usable_for_dfd=null` 仍待判斷。
  Near 會先發布尚未填好的下一格索引，idle mposm 也不會跟著每張 Live View 更新。
- 半按時查事件、release_transport_completed 與 release_still_required；釋放後核對 AF 回到
  本次基準狀態、echo=C03D99A0、四個 getter 未意外改变。歷史 probe 不會替你作設定前後比較。
- H/L 是 CDAF 高／低頻帶，不是相位像素。UI ISO 固定不代表 AF 的實際 gain 不變。

## 7. 不可誤用的路徑

- 不混跑其他 echo borrower、callfn、dump 工具。使用 `/tmp/fp-af-fusion.lock`，未知擁有者先查清楚。
- 不把無參數 `imager high_gain_off` 當 getter；它會改 force-LCG 狀態。
- 不把帶參數 `imager check_convert_abs_gain` 當純查表；它會改實際增益，未保證恢復原增益。
- 不用 `af msr` 做純 AF 測試；它可能进入 S2 拍攝流程。
- 不把 `menu SetFocusPosition` 當馬達絕對位置；不向 live AF object 直接塞座標。
- 不換回舊 952-byte direct-DMA handler；可快取 code-cave 會混到新舊 cache line。
  目前 1000-byte 版本 CPU-copy 到已配置的 USB capture buffer，無須改 worker/MMU。
- 不把成功重算原廠峰值宣稱為 DFD 或光學真值驗證；須另測不同方向、起點、曝光、光圈與鏡頭。

## 8. 文件與 skill 維護

工具與量測屬於 `research/autofocus/`；教學與研究結論放 `notes/`，證據放 `captures/af-fusion/`。
可重用 skill 名稱為 `sigma-fp-af-research`，安裝於 `/Users/dido/.codex/skills/sigma-fp-af-research/`。
Skill 保留決策與安全門檻，引用本教學；不複製整套工具或維護另一份版本。
CLI、資料格式或安全門檻變更時，同步核對 skill、教學與工具測試。

USB transport、ARM 探針與共享 RAM 的底層知識另有既存 skill：
原始檔在 `fpSup/.claude/skills/fp-usb-shell/SKILL.md`，Codex 版本安裝於
`/Users/dido/.codex/skills/fp-usb-shell/`。安裝版保留原文副本，另訂正暫存區使用、DMA cache、
daemon 正常退出與過期操作規則；原檔未修改。只做 AF 離線重播時不必載入底層 skill。
