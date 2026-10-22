# fp 5.02 AF producer 高速 recorder：固定 ABI 與 payload 契約

日期：2026-09-16。範圍只限背景 callsite
`C022C858 -> C023E9D0 -> C022C85C` 的離線候選。對應實作為
[`highrate/af_publication.S`](../highrate/af_publication.S)、離線格式／batch decoder 為
[`highrate/af_batch.py`](../highrate/af_batch.py)。本文沒有操作 USB／相機，也不新增 installer、
RAM ownership 或部署授權。

## 結論

第一版高速路徑應在 **native H/L producer 返回後**，用固定容量、append-only 的 RAM capture
記下一批 publication，再整批讀回；不再以 PTP 對每一筆 H/L 輪詢。這個設計的 hot path 可以遵守：

- 原 producer 恰好執行一次，且看到原來的 `r0/r1/r2` 與精確原 SP；
- after-native recorder 不改 SP、不呼叫函式，只用 `r0/r1` 作 scratch；
- 保留 `r2/r3/r4..r12`，最後固定回到 `C022C85C`；
- 每筆 128 bytes、無 wrap、無 back-edge，commit word 最後發布；
- 同時保存 area-0 H/L、scheduler mode、兩種**不同語意**的位置，以及必要 gain/context。

這解決的是「每次 CPU publication 都在相機端低成本留下一筆」；不會因此自動得到 sensor frame ID、
曝光對齊位置或可直接驅動鏡頭的 DFD 資料。第一版 decoder 應持續標記
`usable_for_af_control=false`、`usable_for_dfd=false`。

## 1. 已由 ROM／既有 audit 確認的 ABI

原 callsite：

| 地址 | 已核對行為 |
|---|---|
| `C022C84C` | `r2=0` |
| `C022C850` | `r0=r4`（model） |
| `C022C854` | `r1=0`（producer processing mode 0） |
| `C022C858` | 原字組 `EB00485C`，`BL C023E9D0` |
| `C022C85C` | producer 返回後的原 continuation；立即以 `r4` 覆寫 `r0` |
| `C022C860` | 立即以 0 覆寫 `r1` |

固定 wrapper 控制流為：

```text
patched BL wrapper
  -> 不改 SP/flags/原參數，令 LR=after_native
  -> branch C023E9D0
  -> native producer 正常返回 after_native
  -> bounded r0/r1-only recorder
  -> branch C022C85C
```

`C023E9D0` 正常出口把 `r0` 設為 `0x518`，恢復其保存的 `r4/r5/r6/r7/r10`，再以保存的
LR 返回。此 callsite 的 continuation 對 recorder 有以下精確界線：

| 狀態 | recorder 契約 |
|---|---|
| `SP` | 完全不改；producer 看到原 observer 的精確 SP phase |
| `r0/r1` | 可作 scratch；continuation 立即覆寫 |
| `r2` | 不改；雖然下一個 direct callee 先覆寫，窄設計不利用這點擴權 |
| `r3/r12` | 不改；尚未證明所有下游都不讀 incoming value |
| `r4` | 只讀、不可改；continuation 立即用作 model |
| `r5..r11` | 不改 |
| `LR` | wrapper 用作 native 返回點；最後固定跳 `C022C85C`，不可 `BX lr` |
| `NZCV` | 已證對直接 continuation 為 dead；普通 `CMP` 可改 |
| APSR `Q/GE` | 未證 dead；不得用會改它們的 DSP/SIMD／飽和指令 |

因此 hot recorder 不得有 `PUSH/POP`、`BL/BLX`、VFP/DSP/SIMD、USB、printf、allocation、
sleep/wait 或 clock getter。固定地址可用 `MOVW/MOVT r1`，`r0` 持 record pointer，再以
`LDR{B} r1`／`STR r1` 完成複製。

## 2. Capture header v1（64 bytes）

State 與 records 在 camera RAM 可以不相鄰；兩者實際地址必須由另行證明的 lease 提供。
現有 builder 檢查 alignment、32-bit wrap、code/state/records 彼此重疊及 BL range；
已排除 callsite／continuation、producer `C023E9D0..C023EC23` 與已知固定 source globals。
這份排除表不是完整 RAM ownership map，未涵蓋所有 firmware 使用者或 MMIO。
因此 `assemble()` 成功及 manifest 的 address checks **不是 lease 證據**；manifest 保持
`deployment_ready=false`、`ownership_verified=false` 是必要限制。

| offset | 型別 | 欄位／固定值 |
|---:|---|---|
| `0x00` | u32 | magic `0x31464841` |
| `0x04` | u32 | schema `1` |
| `0x08` | u32 | record bytes `128` |
| `0x0C` | u32 | capacity，第一版 `1..256` |
| `0x10` | u32 | nonzero capture nonce |
| `0x14` | u32 | enabled；arm 時 1，填滿後 writer 設 0 |
| `0x18` | u32 | committed-prefix count，初值 0 |
| `0x1C` | u32 | full marker；初值 0，完整 finite capture 才設 1 |
| `0x20` | u32 | source callsite `C022C858` |
| `0x24` | u32 | producer `C023E9D0` |
| `0x28` | u32 | continuation `C022C85C` |
| `0x2C` | u32 | header bytes `64` |
| `0x30..3C` | 4 x u32 | 必須為 0 |

Writer 在原 producer 返回後先核對 `r4==C32044D8`，再核對 magic/schema/record-size/capacity/nonzero nonce/enabled/full==0，並只接受
`count < capacity`。格式錯誤或 disabled 時直接回原 continuation，不重試、不修 header。

## 3. Record v1（128 bytes，32 個 little-endian u32）

`i=count`、`sequence=i+1`。signed position 仍以 raw u32 儲存，host 才作二補數解讀。
表中的 `h_area0/l_area0` 在目前 Python decoder 中名為 `h/l`，batch metadata 固定 `statistic_area=0`。

| offset | 欄位 | 來源 | 精確語意 |
|---:|---|---|---|
| `0x00` | `commit` | writer | 初值 0；完整 body 後最後寫 `sequence` |
| `0x04` | `nonce` | state `+0x10` | 本次 capture 身分 |
| `0x08` | `sequence` | `count+1` | 本地 CPU producer-return 序號，不是 frame ID |
| `0x0C` | `model` | `r4` | 此固定 callsite 的 model pointer |
| `0x10` | `h_area0` | `C32985E8` | processed CDAF H，固定 area 0 |
| `0x14` | `l_area0` | `C32986B4` | processed CDAF L，固定 area 0 |
| `0x18` | `cached_lens_position_raw` | `C3476418` | signed native-L cached position；`C035FD48()` 最終解參照的 F+4 word，只在 drive-end 更新 |
| `0x1C` | `phase_before` | `C31F8CB4` | scheduler 循環 phase，不是 generation |
| `0x20` | `mode_before` | `C31F8CB8` | scheduler mode；與固定 producer processing mode 0 不同 |
| `0x24` | `chosen_area` | `C3291514` | host 既有命名；`0xFF` 可表示未選 |
| `0x28` | `reference_area` | `C3291534` | 實際 H/L area index guard；第一版只接受 0 |
| `0x2C` | `route` | `C32915B0` | AF route／strategy state |
| `0x30` | `relative_gain` | `C343B5A0` | IMX410 relative gain raw |
| `0x34` | `analog_code` | `C343B5A8` | applied 12-bit sensor gain code |
| `0x38` | `analog_ratio_raw` | `C343B5B4` | linear analog ratio x100 raw |
| `0x3C` | `hcg` | byte `C343B5BC` | zero-extended；0=LCG、1=HCG |
| `0x40` | `af_rgb_gain` | `C32915B4` | AF pipeline linear ISO/gain scale raw |
| `0x44` | `af_sensitivity` | `C3291694` | AF sensitivity context raw |
| `0x48` | `af_shutter` | `C329169C` | AF shutter context raw |
| `0x4C` | `af_f_number` | `C32916B0` | AF f-number context raw |
| `0x50` | `capture_busy_word` | u32 `C30338C8` | 四個 bytes：StillExposing/StillSaving/MovieSaving/StillImageProcessing |
| `0x54` | `movie_recording` | byte `C30338D0` | zero-extended MovieRecording |
| `0x58` | `shutter_sequence` | `C3033A6C` | full u32 shutter-sequence gate |
| `0x5C` | `af_area_mode` | `C32046A4` | AF area mode raw |
| `0x60` | `af_drive_mode` | `C32065A0` | AF drive／servo mode raw |
| `0x64` | `roi_count` | `C3298918` | producer 有效 ROI 數，合法範圍 1..51 |
| `0x68` | `hpf_0` | `C343B7BC` | cached HPF H context raw |
| `0x6C` | `hpf_1` | `C343B7C0` | cached HPF L context raw |
| `0x70` | `phase_after` | `C31F8CB4` | record 尾端再讀；應等於 before |
| `0x74` | `mode_after` | `C31F8CB8` | record 尾端再讀；應等於 before |
| `0x78` | `af_manager_position_raw` | `C32914E0` | signed AF manager target／g_afpos accumulator；**不是實測 lens position** |
| `0x7C` | `commit_complement` | writer | `sequence ^ 0xFFFFFFFF`，在 commit 前寫入 |

兩個 position 都必須保留其名稱與限制：

- `C3476418` 是 native cached position，不是連續 motor telemetry，也沒有曝光對齊；
- `C32914E0` 是 AF manager 位置／目標域 accumulator，不可當成實際馬達或曝光中心位置；
- 若需要移動中曝光中心位置，仍須使用已審核的 `mposm[]`／Near-history 路徑及正確 sample index，
  不能從這兩個欄位自行推導。

`C3476418` 的固定來源已再次沿 ROM／decomp 核對：native-L singleton
F=`C3476414`、vtable=`C0B8EEEC`；`C033DBC8` 回傳 F+4，`C0332308` 解參照該 pointer，
而 `C035FD48 -> C0360128 -> controller vtable+0xB4` 最終到 `C0332308`。因此在
`C3476408==1` 且 F vtable 身分正確時，直接 `LDR [C3476418]` 與 getter 的 position word 相同，
又不用在 hot path 新增函式呼叫。這個等價不涵蓋非 native-L／未初始化身分；該身分必須放在 run 前後 guard。

## 4. Publication／reader 規則

每個 slot 的唯一合法寫入順序是：

1. `commit=0`；寫 nonce、sequence 與全部 body；
2. 寫 `commit_complement=~sequence`；
3. `DMB SY`；最後寫 `commit=sequence`；
4. `DMB SY`；更新 header `count=sequence`；
5. 若 `sequence==capacity`，寫 `enabled=0`，`DMB SY`，最後寫 `full=1`。

沒有 wrap、overwrite、producer retry 或 ring-reader 競爭。Reader 不可在 hook active 時清空／重用 records。
第一版 host 只接受完整 finite capture：header 身分與 nonce 正確、`enabled=0`、`full=1`、
`count=capacity`，且第 i 筆同時滿足 `commit==sequence==i+1`、`complement==~sequence`。

`DMB` 只界定同一 CPU writer 的 store ordering；它不是 D-cache clean、DMA publication 或跨 CPU
coherence 的完整證明。`full=1` 也只表示資料已填滿，**不表示 hook 已 detach 或 code/data 可回收**。

填滿後 records 在 single-writer／header 未被改動的假設下不再被 recorder 寫入，可以唯讀擷取；
但 callsite 仍然是 patched，每次 publication 仍會進 wrapper 並至少讀 STATE 後才返回。此時：

- 不得重新初始化／覆寫 STATE，否則可能意外重新 enable 或令仍在執行的 wrapper 讀到混合 header；
- 不得回收／覆寫 wrapper code；`full` 不代表 scheduler 已離開 wrapper；
- records 也先維持唯讀 lease，不以「目前 enabled=0」推定可以另作他用；
- detach 仍需 scheduler-ready 的原子 try-commit、核對 callsite 身分、還原原字組、發布 cache，
  並在 quiescence 成立後才回收各 lease。

## 5. Context 判讀與高速讀回邊界

本地 sequence 只證明 hook 完成一次。每筆至少要保留下列 diagnostic 判讀：

- model 必須是 `C022AD58()` 的固定回傳 `C32044D8`；只有整批相同仍不足以取代此 expected-value check；
- scheduler mode 只接受已審核的 1／3，且 before==after；phase 必須在 0..2 且 before==after；
- chosen area=0、reference area=0、route=14，否則 area-0 H/L 不是第一版受控 ROI；
- capture busy word、MovieRecording、shutter sequence 全為 0；
- AF area/drive mode、ROI count、gain/HCG、exposure、HPF context 符合本次 run 的固定條件；
- 整批的 model 與上述 context 未變；任何變化只可回報 diagnostic issue，不可拿最後一筆繼續控制。

有意不放入每筆 hot record 的欄位包括 timing selector/effective timing/raw subcycle、完整 observer
identity、UI focus rectangle/settings。它們仍需在 capture 前後做一次慢速 guard。這使 PTP 從「逐筆取樣」
退到「run 前後驗證」；完整 batch 未來可由 task-context sender 一次送出，hook 本身絕不做 USB。

run 前後 guard 還必須確認 native-L selector/vtable、slot-0 observer/table/enable、observer state/readiness
與 background processing flag。前後一致只能排除已看見的改變，不能形式化排除 capture 期間變動後又復原的
ABA；因此第一版 burst 仍是診斷資料，不是控制 interlock。

batch frame 的 CRC 只驗證傳輸完整性，不會把 CPU publication 變成 sensor exposure，也不會彌補
缺失的 pre/post guard。任何未完成批次的 short read、超長、nonce／CRC／header 不符、額外 bytes 或 timeout 都應整批拒收，
不掃 magic、不 resync、不自動重送相機動作。

目前 EP83 契約是 camera 以**單一 TRB／transfer**送出完整 `header || capture`。host 不能在
SuperSpeed MPS=1024 的端點先要求只有 64 bytes，否則 packet boundary／overflow 語意不安全；
第一個 read 必須要求完整 MPS，從收到的第一包驗證 64-byte header 後，再依宣告的剩餘長度要求
不超過 remainder 的完整 packet multiples。最後 remainder 小於 MPS 時仍要求一個 MPS，且只接受
「short packet 恰好結束宣告 batch」；zero 或任何 nonterminal short 都是永久 fault。若宣告總長恰好
落在 packet boundary，收滿已知長度即完成，不額外等待 ZLP。

`BatchReceiver.feed()` 在離線測試支援 arbitrary software chunks 只是位元流 decoder 能力；實際
EP83 adapter 仍須維持一個 absolute deadline、在 fault 後停止，不 drain、不掃下一個 magic、不重試
或把未知／下一次 transfer 拼上來。每次 USB read 只能使用同一 deadline 的剩餘時間，不能重新起算。

stale 防線依賴每次新 arm 使用新的 nonzero nonce。格式本身無法區分「同一 nonce 的完整舊 batch」；
因此 nonce 不可在新 capture 重用，uncertain／short／CRC-failed transfer 也不可自動當作同一次成功資料重送。
若未來要支援明確的同批 re-drain，必須另加可證明的 session／attempt 語意，不能把它冒充新 capture。

## 6. 條件式設計假設

下列不是 payload 自己能證明的 source fact：

1. 只有固定 scheduler callsite 寫此 capture，且它不重入；
2. code/state/records 位址已有排他 lease，與 USB scratch、DMA、既有 payload 不重疊；
3. host／sender 看到 record 的 cache/coherence 路徑已另外處理；
4. 安裝／拆除的 try-commit 能在 scheduler ready 且正確 CPU 執行域內原子核對原字組與 owner；
5. recorder 的最壞執行時間與額外 memory traffic 可被 CameraMgrScheduler 接受。

任一條不成立，都不能由 commit word、nonce 或 CRC 補救。

## 7. 仍未完成的工程項目

- 固定 code/state/records 的實際 ownership、before-image 與不重疊證據；
- installer/detacher、D/I-cache publication、same-CPU 執行域及 quiescence 的端到端實作；
- recorder 指令數／cache miss／scheduler 延遲的上限量化；
- task-context batch sender 與 host transport 的整合；目前格式本身不等於已有高速 USB 通道；
- 以受控資料確認 producer-return rate、遺失／合併行為，以及 local sequence 對 DMA／曝光的關係；
- 移動中 H/L 與曝光中心位置的配對。現有兩個 position 欄位都不能取代 `mposm[]` 證據。

目前 decoder 已把輸出硬標為不可控制／不可 DFD，且已逐筆標記
`model!=C32044D8`、phase 不在 `0..2`、mode／phase 前後不一致及其他 context 問題。
在解除這兩個不可用標記前，仍須將上述 native-L／timing／observer pre/post guard 做成不可略過的
capture 身分證據，而不是只寫在操作說明裡。

現有 19 項 highrate 離線測試已覆蓋 compiled field copy、commit prefix、容量 1／256、branch range／veneer、
context 標記與 batch corruption／truncation；724-byte image 的模型最長路徑為 179 個 wrapper/recorder
instructions（不含 native producer），這不是真實時間或 cache 上限。builder 已補上已知
self-target／source-overlap 拒絕，commit-order 測試也直接核對所有 body stores 都早於 commit。
另有 22 項 EP83 packet-safe 接收測試、13 項 C task sender 測試及 30 項既有 snapshot／bridge 回歸，合計 84/84 通過。
下一步是以實際候選 RAM lease 完成 ownership／lifecycle 與 task-context sender，再驗證整批 EP83
端到端傳輸；在此之前不把 recorder 接入鏡頭控制。

若 writer 被正常搶占，會恢復並完成 count→disabled→full。若執行在這段被異常永久中止，
不能靠下一次 callback 自動補完：count==capacity 會直接返回。此時 host 拒收 partial capture；
installer/detacher 不得放棄正在執行的 wrapper，也不得在未證 quiescence 時改寫 header「修復」。
