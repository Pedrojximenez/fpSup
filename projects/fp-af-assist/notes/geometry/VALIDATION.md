# 幾何核心離線驗證紀錄

2026-09-27，Apple clang 21.0.0（clang-2100.3.27.1）。這是 M2-G 的離線程式增量，不是實機 AF 驗收。相機正在使用；本輪沒有 USB 連線、鏡頭操作、卡片修改或韌體部署。

## 後續整合：配對、ARM observer 與 raw 解碼

已完成 [上機前離線交接](OFFLINE_INTEGRATION.md)所列程式增量。最後一次整套執行結果：

| 檢查 | 結果 | 能證明的範圍 |
|---|---|---|
| geometry 完整套件 | **125 tests 全過，無跳過**；11.231 s 含 process overhead | 幾何、配對、回放、ROM 指令驗證、ARM build、observer／decoder 整合 |
| autofocus 研究工具回歸 | **149 tests 全過，無跳過**；0.703 s 含 process overhead | 舊採樣器與 native subject 解碼相容性；不包含相機 |
| 配對器 ASan／UBSan | **192,062 API events**、17,296 candidates、36 mutation modes、16,384 長 consumed tails；全過 | 公開 API、一次候選、失效／時間回繞／身份／配對與長期追蹤邊界 |
| ARM objects | geometry `.text` **5,076 bytes**；confirm_join **3,268 bytes**；各自 `.ARM.exidx` 80 bytes；無 undefined symbols／可變全域 | 交叉編譯／ELF 稽核；這兩個 C object 尚未在 ARM 執行 |
| Observer 實際 ARM bytes | **1,020 bytes**；Unicorn **13 tests 全過**，包含在上述 125 項內 | 四 wrapper 原 callee 恰一次、pre/post 時點、r0–r12／SP／APSR、固定返回、buffer 邊界與 commit 順序；native callee 是受控 stub |
| 測試負向對照 | **2 個故意破壞均被抓到** | 把 AF 的 APSR restore 指令改 NOP；故意污染 continuation 的 r4 |
| ROM 接點 | 49,245,696-byte ROM SHA-256 相符；四個 BL／target／continuation／context／callee guards 全符合 | 只核對儲存映像，不證明目前相機 RAM 或 hook 可部署 |
| 串接合成重播 | **80 events、2 candidates、2 simulated attempts／accepted、0 rejected** | 未配齊及中間 backlash 不建基準；取消、换主體、no-op、漏事件、失敗結果拒絕；另測 Geometry 拒絕時不計成接受 |

串接回放中的幾何輸出為 UNKNOWN 29、接近 27、遠離 17；只有呼叫 geometry 的事件才計數，不能以 80 個全部事件當分母，也不是實機準確率。`FjState=116`、`FgState=396` bytes。四個 raw observer 每來源 state 40 bytes、每 record 256 bytes，wrapper 額外 stack 64 bytes；尚未取得原生 task 的 stack 餘量或實機執行成本。

實際證據：[整合摘要](../../../../fpSup/focus/geometry/validation/integration-summary.json)、[配對 ARM manifest](../../../../fpSup/focus/geometry/validation/join-arm-manifest.json)、[串接回放摘要](../../../../fpSup/focus/geometry/validation/join-replay-summary.json)、[observer build manifest](../../../../fpSup/focus/geometry/validation/observer-build-manifest.json)、[sanitizer 摘要](../../../../fpSup/focus/geometry/validation/join-fuzz.json)。完整 log／binary 位於 `artifacts/offline-20260927/integration-final/`。Build manifest 只記建置，因此保留 `arm_emulation_verified=false`；已實際執行的 observer 模擬證據另列整合摘要，不混成 builder 自行驗證。

Unicorn 2.1.4 在這台 Mac 的受限 sandbox 首次 `mem_map` 即 SIGILL，尚未執行 observer。已使用工具正常核准的 JIT 執行環境完成測試，未改 codesign 或安全設定。`test_native_observer.py` 先執行 child probe；不允許 JIT 或缺少 Unicorn 時明確報 ERROR，不 skip、不冒稱通過。正常終端可依 [交接命令](OFFLINE_INTEGRATION.md#可重跑的離線驗證)重跑。

本輪修正的兩個邊界：配對的等待期限不再錯誤截斷已建立基準的幾何追蹤；重播將 simulated confirmation 的嘗試、接受、拒絕分開報。Raw decoder 另拒絕 `count==capacity` 卻 `full=0` 的不自洽停機快照。

**下一步需要相機確認觀測環境與資源；未建立可信 native adapter 或 installer。** 沒有校準新尺度、驗證光學穩定、接入原廠 AF 決策、測量 EP83 實收或證明連續 AF 改善。所有 motion／confirmation authority 仍為 false。

## 較早的單獨幾何核心驗證

| 檢查 | 實際結果 | 證據界線 |
|---|---|---|
| C 行為與工具整合 | 39 項全過，3.452 s | 首焦／失效／時序／尺寸／方向物理／輸入契約／建置 audit，不含相機 |
| ARMv7 Cortex-A9 建置 | `.text` 5076 bytes、`.ARM.exidx` 80 bytes；五個 API，無 undefined symbols／可變全域 | 只交叉編譯 relocatable object，未在 ARM 執行，也未完成 hook ABI 或 CPU 預算測量 |
| 狀態大小 | `FgState` 396 bytes（本機 ABI 測量） | 呼叫端持有；尚未計入 future adapter、buffer、hook stack |
| ASan／UBSan 事件測試 | 788,608 次事件，全過 | 固定種子，合法 config 邊界、尺寸極端值、時間／序號回繞、重播、失效與重建 |
| 擬合 oracle | 362,468 次 long-double 速率／殘差比較，全過，其中 100,000 組直接極限窗口 | 允許 1 Q16 LSB 數值差；驗證數學，不等於光學模型成立 |
| 除法／Q16 oracle | 1,000,000 組 uint64 helper 與 uint128 精確結果比較，全過 | 無 sanitizer 或 assertion 失敗 |

來源與產物雜湊：[ARM manifest](../../../../fpSup/focus/geometry/validation/arm-manifest.json)、[replay summary](../../../../fpSup/focus/geometry/validation/replay-summary.json)。兩份記錄明列 `deployment_ready=false`、`motion_authorized=false`。完整本地輸出在 `artifacts/offline-20260927/`（不納入 Git）；可依下列指令重建。

本輪整合還修正兩個工具缺口：ARM audit 現在拒絕不占 `.bss` 的 COMMON 可變全域；重播另計「標為應 UNKNOWN 卻輸出方向」的違反，不把這類資料從統計完全排除。

## 合成動態重播與已知問題

[synthetic_motion.jsonl](../../../../fpSup/focus/geometry/fixtures/synthetic_motion.jsonl) 含 78 個事件。輸出 UNKNOWN 23、靜止 16、接近 22、遠離 17。已知運動標籤樣本 71 筆中，51 筆相符、4 筆不符、16 筆 UNKNOWN；另有 4 筆應保持 UNKNOWN 的 sample，全部保持 UNKNOWN。其餘 3 筆為確認／失效事件。這些是示範計數，不能稱為相機方向準確率。

四筆不符完整保留：

| 合成時刻 | 指定運動 | 輸出 | 原因 |
|---|---|---|---|
| 640 ms | 接近 | 靜止 | 剛起動，短窗含先前靜止資料 |
| 1440 ms | 遠離 | 接近 | 反向後窗口保留前段趨勢 |
| 1480 ms | 遠離 | 接近 | 同上 |
| 1520 ms | 遠離 | 接近 | 同上 |

1560 ms 首次改判遠離：比第一筆遠離標籤延後 120 ms，比合成軌跡的轉折点 1400 ms 延後 160 ms。這不是實機延遲，不能用來設定鏡頭提前量。尚未實作專用反向偵測／速度預測；目前結果只能供旁路觀測。鏡頭移動期間核心清除窗口，因此連續追焦的可用覆蓋率也仍須實測。

## 重現

在 [fpSup/focus/geometry 程式目錄](../../../../fpSup/focus/geometry/) 執行，選用尚未存在的輸出目錄：

```sh
python3 -B -m unittest discover -s . -p 'test_*.py' -v
python3 replay.py fixtures/synthetic_motion.jsonl --output /private/tmp/fp-geometry-replay-check
python3 build.py --output /private/tmp/fp-geometry-arm-check
clang -std=c11 -O1 -g -Wall -Wextra -Werror -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all fuzz_geometry.c -lm -o /private/tmp/fp-geometry-sanitize
/private/tmp/fp-geometry-sanitize
```

壓力測試是 native-only，直接包含生產 C 以核對 private 算術極限，不能編入機內程式。固定種子 `0xa95031786e42d7fb`，成功摘要：

```text
PASS events=788608 oracle_fits=362468 direct_fit_bounds=100000 helper_cases=1000000 seed=0xa95031786e42d7fb
```

算術界限另經人工核對：`q ≤ 2^27`、`n ≤ 32`、窗口跨度 `≤1000 ms`、OLS 分母 `≤256000000`；速率最大中間分子 `≤4398046511104000000`、殘差有號中間量 `<7×2^60<INT64_MAX`。Q16 小數以逐位除法產生，避免先乘 65536 的溢位。這些界限以 API 驗證過的設定與完整 caller-owned state 為前提。

## 下一驗收缺口

先依 [輸入稽核](NATIVE_INPUT_AUDIT.md)實作可信 face／AAT／合焦事件 adapter；現有 AFF1 欄位不能直接使用。接入後先旁路紀錄，取得固定主體、已知前後移動、反向、转頭、遮擋與鏡頭呼吸對照，分開量錯判及 UNKNOWN 覆蓋率。這些缺口未完成前，不把離線通過稱為 M1／M2-G 實機完成，不宣稱已改善連續 AF。
