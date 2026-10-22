# 合焦配對與 raw observer：上機前離線交接

2026-09-27。本輪依「上機测试前自動繼續」完成離線程式與验证；相機正在使用，沒有相機連線、鏡頭動作、daemon 切換、卡片寫入或部署。這不是可直接裝卡的 AF 測試版。

同日後續：使用者接上 USB 後已完成 [原生唯讀 preflight](../evidence/capture-native-preflight-20260927-121028.md)。實機接點相符、取得 stack 基線；沒有安裝本文件的 observer。發現現 worker 獨立 pool 與舊 collector 不相容，已阻擋舊 live installer。以下保留離線階段的交接；最新實機已知條件與剩餘缺口見上方紀錄。

## 目前接通的範圍

```text
明確標註的事件
  → confirm_join.c：同輪 AF 結果＋同次 final drive end＋新鮮同主體尺度
  → 每輪最多一個 shadow candidate
  → 僅 synthetic 回放可模擬接受
  → geometry.c：UNKNOWN／接近／遠離／靜止

四個原廠 callsite（ARM 模擬）
  → native_observer.S：每來源獨立有限 raw buffer
  → observer_decode.py：完整原始資料與未知條件
  ⇢ 尚未建立可信時間／身份／位置／光學條件，不能自動接上 confirm_join
```

正常產品運算仍以機內為目標；電腦只負責此處的離線驗證。EP83 留作後續研究資料傳回，不是幾何／AF 控制器。

### 合焦配對

`confirm_join.c/.h` 使用呼叫端持有的 116-byte state，不配置記憶體或呼叫 firmware。`BEGIN`、`DRIVE_BEGIN`、`AF_RESULT`、`DRIVE_END`、`SUBJECT`、`CANCEL`、`FAULT`、`TICK` 由單一 owner 排序；兩個完成訊號可以任一先到。最後完成與 AF 成功尚未配齊時不保留較早 subject，也不把 backlash 的中間停止當成 final end。

同一 episode 只能消費一次；新的 final drive 清除舊配對。舊 stream sequence 不污染狀態，forward gap、時序／身份／drive 不合、取消或失效會封鎖，需要新 episode。配對期限只限制候選建立前的等待；候選消費後仍檢查新鮮度與身份，幾何核心另管 anchor 壽命，避免配對的 500 ms 期限截斷正常追蹤。

`SETTLE_VALIDATED` 是輸入端必須另證明的條件，本模組沒有以等待固定時間冒充光學穩定。它只回傳候選，`confirmation_authorized=0`、`motion_authorized=0`，不呼叫 `fg_confirm()`。

`join_replay.py` 僅接受明確 `fp.confirmation.events/v1`、共用 ms epoch、線性尺寸與來源宣告。非 synthetic 資料禁止 `simulate_confirmation=true`。模擬接受另報 attempts／accepted／rejected，Geometry 拒絕的候選不計成已建立基準。

### Raw observer

四個接點與來源位址由 [ROM metadata](../../../../fpSup/focus/geometry/native_hook_sites.json)、[ABI 稽核](NATIVE_HOOK_PLAN.md)及 `verify_hook_sites.py` 固定。AF 在 callback 之前保存 172 bytes；lens、face、AAT 在原函式返回後保存 92／156／44 bytes。原 native 函式仍執行一次，原 SP 不變；新增 recorder 保存 r0–r12、APSR NZCVQ/GE 與 64 bytes stack frame，無 VFP／FPSCR 修改。後三個 wrapper 的 native incoming LR 指向本地返回點，最後跳回已稽核 continuation；不宣稱 exception unwinder 完全等價。

每來源 state 40 bytes；容量 1..1024、每筆 256 bytes。單次 LDREX/STREX 嘗試取得記錄權，忙碌即標記 loss 並返回；不等待、不重試。固定長度複製、完整 body/trailer 之後 DMB／commit／count，滿載不覆寫。每個來源獨立編號，不能當成四來源的總順序或曝光序號。DMB 不替代 DMA cache 維護。

這版不讀 timer，也不呼叫原廠微秒 getter：後者有 race／wrap 時的遞迴重讀，尚不符合 hook 的固定成本要求。`source_time_ms` 明確為 unknown。沒有以 snapshot 中的 raw native counter 冒充 episode、drive 或 target generation。

`build_observer.py` 沿用維護中的 `fp_usb_shell/armasm.py`。**輸出地址僅屬於模擬器配置**；不選真實 cave／pool、不產生 callsite patch、veneer、loader sections、AutoRun 或 installer。`state-disabled.bin` 預設停用。`observer_decode.py` 只解讀複製出的 bytes，拒絕 active／busy、不完整 commit、錯 nonce／source／長度與不自洽 count/full；disabled/busy 值本身仍不證明實機已靜止。

## 可重跑的離線驗證

由 [fpSup/focus/geometry 程式目錄](../../../../fpSup/focus/geometry/) 執行，輸出位置必須尚不存在：

```sh
python3 -B -m unittest discover -s . -p 'test_*.py' -v
python3 -B build_join.py --output /private/tmp/fp-join-arm-check
python3 -B join_replay.py fixtures/join-synthetic-v1.jsonl --output /private/tmp/fp-join-replay-check
python3 -B verify_hook_sites.py --output /private/tmp/fp-hook-rom-check.json
python3 -B build_observer.py --output /private/tmp/fp-observer-emulator-check
clang -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all fuzz_confirm_join.c confirm_join.c -o /private/tmp/fp-confirm-join-fuzz-check
/private/tmp/fp-confirm-join-fuzz-check
```

完整研究工作區才包含 ROM 與 `research/autofocus/af_subject_observation.py`；缺少時驗證會明確失敗，不靜默省略。實際測試結果與本輪來源／產物雜湊列於 [VALIDATION](VALIDATION.md)。舊 `arm-manifest.json` 與 `replay-summary.json` 是早一階段快照，不代表新增配對器或 observer 已完成當時未做的驗證。

## 下一個需要相機的邊界

下一步是觀測環境核對，仍不是啟用幾何控制：確認當次原廠字組／已裝功能、四來源 layout／初始化、相關 task 的 stack 餘量、合法常駐配置及安裝／停止的執行上下文。現有舊 pool 指標與歷史 cave 授權不能代替當次資源所有權。這些條件尚未取得，因此沒有生成可上機 installer。

取得該證據後，installer 須沿用 [SUP_BUILD_RULES](../../../../fpSup/SUP_BUILD_RULES.md) 的共用 loader／stage2／entry，將覆寫的原韌體字納入 loader journal，entry 返回、先完成 cache publication 再 arm，保留資源直到所有 producer 退出。首次觀測只量原廠流程與記錄成本；EP83 另驗單一傳送 owner、有限批次實收、漏樣與原廠事件共存，不在 hook 內送 USB。

此後才能補 native adapter：begin／cancel／drive generation、跨來源排序與時間、同主體尺度正規化、位置來源新鮮度，以及獨立光學確認。不能靠人工把 unknown flags 填成 true 接通流程。幾何反向遲滯、AAT 尺度真實性、對焦呼吸與 DFD 位移仍需實測；現階段沒有「連續 AF 已改善」的結論。
