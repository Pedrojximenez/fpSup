# 原廠 AF 結果與鏡頭完成：fg_confirm 來源稽核

日期：2026-09-27；fp Ver.5.02。本次只讀既有筆記、反編譯與 ROM，**未連相機、未呼叫 native 函式、未新增 probe、未修改 transport**。此文件是 adapter 契約與候選觀測點，不是 hook 已部署或光學驗收完成的宣告。

## 結論

找到可觀測的原廠 AF 結果出口，也找到獨立的 native-L drive-end 出口；**兩者不能合併成同一個「已合焦」boolean**。

- `C028D968` 產生 AF terminal result，從 `C028E310` 呼叫 `C022B720` 發布 0xAC-byte payload。byte 0 在該路徑只有 `C329160B==0` 才設為 1，可稱「原廠本次 AF 結果接受」。
- 這個發布點可能在**最後一次目標驅動完成之前**。它前面才呼叫 `C028E7F8` 提交最終位置，實際 wait-selector `C028EA70` 固定回 0，因此不能在 result callback 直接呼叫 `fg_confirm()`。
- native-L `C0340210` 的 message 3 先更新位置 cache，處理 backlash，再在 final branch 呼叫原有 completion callback，最後設 done bit；適合作為**另一條 motor event**。它不量影像清晰度，也沒有證明光學 settle。
- 應由 adapter 配對同一 AF episode 的 **原廠成功結果、對應最後驅動完成、可信來源時間／位置、同一主體的新鮮尺度**；任一證據缺失、取消或身份變更，就不送 `FG_CDAF_CONFIRMED`。尚未完成這條實機配對驗證。

輸入限制沿用 [NATIVE_INPUT_AUDIT](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/geometry/NATIVE_INPUT_AUDIT.md:5)；core 要求見 [geometry.h](/Users/dido/Developer.localized/SIGMAfp_re/fpSup/focus/geometry/geometry.h:101)。以下 source 的「success」是原廠演算法判斷，並非獨立光學真值。

## 1. 可達 AF 路徑與結果出口

AfMgrSingle singleton `A=0xC33D51C0` 由 `C028B770` 回傳；`XC_ThreadHandlerAfMgr::v1 @ C028EAA0` 呼叫 `C028C620(A)`。[singleton](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:85856)、[task entry](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87447)

`C028C620` 的 case 2 呼叫 `C028CDB8` 初始化一輪；case 3 選策略，case 4 推進 `C0259D50`，策略無下一 route 或 case 5 時進入 `C028D968`。目前策略指標保存在 `C33D520C`。這條 manager 同時有不同 mode／Rocking 分支，**AfMgrSingle 的類名不能當成所有呼叫都符合 AF-S 光學確認**。[派發與收尾](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:86488)

### 本次結果是如何構造的

`C028D968`：

1. 讀取 `C329160B` 原始 error byte，先傳給 `C024D670`，再作 position／history 整理。這個早期 helper 不代表最後鏡頭已停。[開頭](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87007)
2. 清空 0xAC-byte `local_198`，byte 0 預設 0；**只有 error==0 才把 byte 0 設 1**，並呼叫 `C028EBF8` 填結果區域。[payload 構造](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87046)
3. 可能再以 `SAF_EstimateCore_NearAfAfterSearchPeak` 修正 `C32914E0` 最終候選；這是原廠預測目標，尚非實體落點。[最終目標修正](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87129)
4. 呼叫 `C028E7F8` 處理 final drive；之後 `C022AD58 → C022B720(manager,payload,0)` 發布結果。[drive 與 result](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87198)

`C022B720` 在 observer 存在時呼叫其 vtable+0x0C，並把 AF manager+0x2254 寫到 payload+0xA8。它是**通用轉發器**，還被取消／停止／其他 AF 模組呼叫，不可只 hook 此函式就把每個 payload 解成成功合焦。observer 不存在時也可能沒有實際 callback。[轉發器](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32811)、[其他停止呼叫](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32514)

首版適合在 `C028D968` **特定 callsite** 收集完整 payload、error、策略、episode 與取消上下文，命名 `native_af_result`。payload+0x9C/+0x9D/+0x9E、+0xA8 的完整外部消費語意本輪未解，先保留 raw，不把其中任一 byte 自行命名 `settled` 或 generation。

### Result 早於 final drive-end 的直接證據

`C028E7F8` 比較 `C32914E0` 與 `C035FD48()` 的 cached position；需要移動時呼叫 `DriveIntermittent` vtable+0x14。只有 wait-selector 非零分支才隨後呼叫 `C035FF08()`；但 `C028EA70()` 在目前韌體直接 return 0。[兩條 drive 分支](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87403)、[selector](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87438)

ROM ARM 已離線核對：`C028E298 bl C028E7F8` 在 `C028E310 bl C022B720` 前；函式後面某些 mode 才有 `C028E580 bl C035FF08` 與 Vd waits，不能把這些後段等待搬到 result 發布之前解讀。[ROM](/Users/dido/Developer.localized/SIGMAfp_re/out/seg0_c0000000.bin)、[後段等待來源](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87267)

## 2. 成功、失敗、取消、重試的邊界

| 觀測 | 能支持的結論 | 不能當成 |
|---|---|---|
| 指定 terminal callsite，error==0 且 payload[0]==1 | 本次原廠 AF 結果被接受的候選事件 | 鏡頭已完成 final move、影像已重新量測清楚 |
| 同 callsite，error!=0 或 payload[0]==0 | 原廠未提供可接受合焦結果；保留 error raw | 可更新錨點的事件 |
| `C329160B==0` 單字快照 | 此時全域值為 0 | 新事件、目前主體成功、沒有 retry／cancel |
| `C0259D50` 回 3、strategy+28 completion=1 | 這個策略已走完某完成分支 | 成功合焦；state 4、6 都可走完成出口 |
| Near::v7 回 1 | 函式完成某分支 | error==0；見下列反例 |
| route 14、S1 ACK、PTP completion、函式 return | 對應控制／傳輸狀態 | 光學結果 |

Near::v7 `C026B6D0` 呼叫 `C0255260` 判斷 SlowAfResult，失敗時把 `C329160B=1`、記錄 `ng Judge_SlowAfResult`，**仍沿尾端 return 1**。[原始碼](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:67465) ROM `C026BD44 bl C0255260`、其後 error branch、`C026BE48 mov r3,#1`／`C026BE4C mov r0,r3` 已核對。

`C0259D50` 在 state 4 與 state 6 都設 strategy+28=1、回 3；state 6 還可由 panning/tilting 否決轉入。[策略完成](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:59156)、[否決分支](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:59063)

`C028C620` case 4 的取消分支會 abort 並回 state 0；退出內層處理時也可能經 cleanup 再呼叫 `C028D968`。所以 terminal result callsite 雖優於讀全域旗標，**仍要標記呼叫路徑／取消原因，不可靠 error==0 一個 gate**。[取消與 cleanup](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:86521)

## 3. native-L stopped 與位置來源

本節限定已核對 native-L selector `C3476408==1`、focus singleton `F=C3476414`、vtable `C0B8EEEC`。其他鏡頭／轉接模式不能套用。既有 [native control 稽核](/Users/dido/Developer.localized/SIGMAfp_re/projects/fp-af-assist/notes/research/FP_NATIVE_FOCUS_CONTROL_2026-09-16.md:77) 提供 wrapper ABI；本輪重新核對以下完成路徑。

### 完成事件與 backlash

`C0340210` 是 focus drive task：

- message 0：清 F+44 event bit 1、送驅動，再設 bit 2。
- message 1：abort；只發原廠停止请求，**本身不設 done**。
- message 3：先用 `*(F+58)` 指向的 lens sync 資料 `+30` 更新 F+4；若還有 backlash 第二段，继续送修正而不做 final completion。
- final branch：清 abort-pending F+28，呼叫 `C0340668(F)` 原有 callback，然後 `C036D758(F+44,1)` 設完成 bit。

來源：[task message 邏輯](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:42132)。ROM `C034044C bl C0340668`、`C0340458 bl C036D758` 先後順序已核對。**只在 message3 初次更新 F+4 時增 done generation 會錯把 backlash 中間落點當完成。**

F+44=`C3476458` 是 RTOS event wrapper，不是旗標本體。`C036D888(wrapper,out[3])` 必須成功回 1 才可用 out[2]；完成 pattern 要**恰為 3**。失敗時函式不覆寫輸出。native busy getter `C033F7D0` 卻未檢查 reference return，故 adapter 不應盲信它的 boolean。[event reference](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:74895)、[busy getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:41767)

`C035FF08 → C033F810` 是 wait，不是 stop。它在 disconnected 分支也能回 1；回傳成功不能單獨證明 lens-end。[disconnected branch](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:41847)

### Drive-end 是 firmware／協定完成，不是光學 settle

message 3 由 `C033FC40` enqueue；normal path `C0340128` 還檢查協定 busy／event 狀態，advanced path 有不同的狀態流程。另有 `C033FCD8` 的泛用完成檢查途徑，需保留發出原因與連線狀態。[enqueue](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:41939)、[normal producer](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:42090)、[advanced producer](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:42042)

done pattern 不區分原廠掃焦、最終定位、手動／PTP 驅動及 abort；它也沒有 AF episode ID。主機輪詢可能漏掉完整 busy→done 循環，故讀到 3 不能自行建立新 motor event。需在原生事件邊界產生自己的 drive generation，或在已證明無其他控制者的條件下完成配對。

`FG_LENS_STATIONARY` 最多可以從「已支持 native-L 路徑的 final drive-end、沒有新的 drive／abort／故障、有效新鮮位置與已驗證 settle policy」導出。**目前沒有查到可直接代表鏡片振動消失、focus breathing 結束或當次影像已完全穩定的現成單一欄位。** 任意固定 sleep 或兩次相同 cache 都補不上此證據。

### 位置是有來源的 cache，不是命令，也不是持續光學量測

F+4 的 getter `C033DBC8` 回 pointer，由 `C035FD48` wrapper 取 signed position；setter `C033DC10` 只是存值。F+18 是別的 target field。final drive-end 的 F+4 來源為 lens sync cache，不是把 C32914E0 原封當成馬達落點。[getter/setter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:40701)、[更新](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:42186)

但不能把 F+4 說成「只會在 drive-end 更新」的唯一事件來源：`C035B450`、初始化／週期通訊分支也呼叫相同 setter。[其他更新](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:59834)、[週期分支](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:61621)、[初始化分支](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:61247)

而 lens sync 的 `+34` 還有 `C035D9C8` 特殊分支，在 `+15A!=0` 時由計算值覆寫；未確定此模式的實際用途前，位置來源驗證必須保留這些 mode，不能泛稱任意 cache 都是感測實測真值。[特殊覆寫](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:61433)

LDAFR 通訊具有 header／checksum／錯誤處理，但這只能支持協定完整性；不能單憑它斷言某 position tuple 是本次 AF 最後曝光的真值。[通訊檢查](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:59210)

## 4. 可實作的 adapter 事件契約（設計，尚未上機）

至少分成以下三類事件，不共享一個模糊 `completed`：

| 事件 | 候選來源 | 必存資訊 |
|---|---|---|
| `af_episode_begin` | `C028CDB8` 完成初始化；只含已支持 manager/mode | adapter episode_generation、時間、mode/strategy、target/ROI/context/scale generations |
| `native_af_result` | `C028D968` 的 C028E310 callsite；另標 cancel cleanup 路徑 | episode、result_seq、error raw、payload[0]與完整payload、最終 target、是否 final drive/no-op/rejected、當時 motor generation、取消／故障狀態 |
| `native_lens_drive_end` | `C0340210` final message3 branch，原callback及done發布之後 | drive_generation、end_seq、時間、連線／protocol mode、abort history、backlash final、event查詢結果、位置值與來源／接收時間 |

`C028CDB8` 原本會把 A+3C（`C33D51FC`）加一，適合作為旁路診斷，但不是 source exposure ID，也沒有身份失效契約；adapter 使用自己的 episode_generation。[原生計數與初始化](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:86620)

新的 `focus_event_seq` 應在 adapter **成功配對並接受一次確認**時生成；重播同一原生 result 不增代。另保留所有 result/end 序列，包括失敗與取消，供診斷與去重。新 drive 提交即使 target 數值相同，也必須辨認是否 no-op／新命令；不能只用「位置變了」產生事件。

Hook 只能有界複製與發布紀錄；保留原有 callback、register/stack ABI 與 event 語意，不直接取代 F+50 callback、不呼叫 wait、不在 hook 做 USB／動態配置。AF manager 與 lens task 是不同 producer，需設計不可撕裂的傳遞與 ownership，不能假設兩處時間相近即同一輪。

## 5. 何時才允許呼叫 fg_confirm

最小接受條件是全部成立：

1. 已支持的 CDAF manager／策略 episode；在明確 terminal 路徑收到新 `native_af_result`，error==0、payload[0]==1，沒有取消、失敗／故障或 source reset。
2. 配到**本輪最後定位**的 native drive-end；或已獨立驗證的 no-op terminal 分支。不得借用之前掃描的最後 done，也不得等待「任意下一次」lens-end 來湊。
3. 新鮮、支持的 native position tuple；不是 C32914E0 command、舊 mposm、Near 峰或 disconnected wait return。方向器只保存此 native 單位，不把它換成光學距離。
4. completion 後取得同 target/context/scale generation 的有效 native 尺度；age／時間配對成立，鏡頭與投影條件符合已驗證 policy。若 result 與 completion 之間主體移動、reseed／crop 改變或 scale 太舊，就不能補套舊尺度。
5. 原廠成功結果與上述完成時間／尺度關係已用受控實機資料驗明，並保留獨立影像清晰度對照以界定可靠範圍；**這是待驗收工作，不是本文件已達成**。

通過後才能設 `FG_CDAF_CONFIRMED | FG_POSITION_VALID`，連同符合 core flags 的 `FgSample` 送 `fg_confirm`。原廠 acceptance 可成為設計上的合焦確認來源，但研究評估仍應區分「原廠說成功」與「獨立清晰度基準通過」。沒有新鮮尺度時保留 raw AF/motor 事件，幾何維持 UNKNOWN，不從事件編造 scale。

## 尚未解除的限制與下一有界工作

- 靜態已證實 result byte 與 error、final drive 的先後；尚未有包含上述三類事件的實機同時 trace。
- 尚未完成 payload 全欄位／observer consumer 語意、cancel/fault 所有路徑、每種 mode／鏡頭的 final-drive ownership；首版應只 whitelist 一條已驗證 CDAF／native-L 路徑。
- 尚無光學 settle 時間、focus breathing 對尺度影響或 packet position 年齡的校準；不借用固定等待／一般 drive-end 宣稱它們已解決。
- 下一個離線工作可先實作 **事件配對／拒絕狀態機與合成反例測試**：success-before-drive-end、retry、cancel後terminal、backlash中間end、不同episode的end、no-op、掉事件、重送、身份切換。這不需要相機，也不自動產生 native 已驗證 flags。

本輪沒有修改任何原廠狀態／callback，也沒有實作硬體 adapter；只把下一步必要觀測點與拒絕條件定位清楚。
