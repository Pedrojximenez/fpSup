# 2026-10-13 拒絕閘門（refusal gate）與 HS280 切法實測

## 一、上機實測：HS280 每幀被拒，與切法無關

卡：正式版 LOSS v0.2.0test（`ad984ce6…`）＋ RES-Lab／virtual RES-CUSTOM（見 `../20261013-reslab-install/`）。
開機 8067144。HS280 = RES-Lab 存出的 RCD，RAW 1008×672、12-bit，輸出 992×662。
工具：`../20261013-registry-scan/tile_trial.py`（設 tile_force → 錄一段 → 讀計數 → tile_force 改回 0）。
原始紀錄：`../20261013-registry-scan/tile-*.json`、`tile-hs280-lastjob.txt`、`tile-fhd120-lastjob.txt`。

| 段落 | 模式 | 切法（格數） | 壓縮 | 拒絕 | 每工作 |
|---|---|---|---:|---:|---:|
| hs280-default | HS280 119.88p | 512×336（4，預設，無垂直補白） | 0 | 174+19 | 2.4 ms |
| hs280-512x352 | 同上 | 512×352（4，垂直補白） | 0 | 171+31 | 2.4 ms |
| hs280-512x224 | 同上 | 512×224（6，剛好整除） | 0 | 183+21 | 2.3 ms |
| hs280-256x336 | 同上 | 256×336（8） | 0 | 189+19 | 2.3 ms |
| hs280-256x224 | 同上 | 256×224（12，與 FHD 同形狀 4×3） | 0 | 169+21 | 2.2 ms |
| hs280-128x112 | 同上 | 128×112（48） | 0 | 172+20 | 2.0 ms |
| fhd120-default | FHD 1936×1090（幀率自動退到 59.94p） | 512×368（12） | 67+46 | 0 | 14.2 ms |
| fhd60-5s | FHD 59.94p，5 秒（繞過整個 RAW 池） | 512×368（12） | 179+95 | 1 | — |

（「A+B」= lane A + lane B。）

結論：
- **切法不是原因**：垂直補白、整除、格數 4～48、形狀與 FHD 相同，全部被拒。舊推測「無垂直補白」否定。
- **不是位址**：FHD 5 秒用到整個 RAW 池（含高位址），274/275 成功。
- **不是位元順序／列寬**：錄完後讀來源緩衝（非快取位址 0x598DEC00），HS 與 FHD 都是 DNG 標準 12-bit 順序，
  每列 1512 B 緊密排列（DNG StripByteCounts 1,016,064）；畫面很暗，值約 256。
- **引擎在一半就放棄**：end_position 0、total 0，耗時約 2.2 ms（完整一幀約 4.4 ms）；
  pattern 4＝輸出會超過 1,016,832 B。以錯誤的半位元組順序解讀同一資料會出現 16／4080 交替，
  每樣本約多一倍位元，正好在一半溢出。
- **最可能的原因（未證實）**：HS/M12 的 RAW 光柵是 2016×672，經 RWZM 縮成 1008×672；
  到達 hook（C038BFF0）時這一幀可能還沒寫進緩衝，引擎讀到的是緩衝裡的舊資料（例如之前 FHD 錄影、列距不同的殘留）。
  FHD 是感測器直接寫入，到達時已完整。要證實需在送出當下擷取緩衝，或找到 RWZM 完成的時點。
  **不得用「延後重試」當修正**：可能壓到寫到一半的畫面，產生看似正常但內容錯誤的檔案。
- 另見：正式版在 HS280 119.88p＋LOSS ON 時約 1.8 秒（約 220 幀）自動停錄，即已知的 96 格限制；
  候選版（擴充描述槽）在 M12240 120p 2 秒都還在錄（`../20261013-registry-scan/cand-120p.json`）。

## 二、修正：拒絕閘門（通用、不改變任何輸出）

`fpSup/lossless/native/refusal_gate.{h,c}`，接在 `card.c` 的 `fpl_card_arrive`：

- 同一段錄影內，連續 `FPL_GATE_STREAK`（8）幀沒有得到較小的檔案（引擎拒絕，或壓了但沒變小），且期間沒有任何一幀壓縮成功 → 閘門關閉。
- 關閉後的到達幀在進入 lane 前就直接交回原生流程（RAW），不佔 hold、不送引擎；每 `FPL_GATE_PROBE`（120）幀放一幀試探。
- 試探成功（壓縮了）→ 閘門重新打開。
- 失敗計數用 `no_benefit`（被拒的幀也會記一次 no_benefit），成功用 `compressed`；計數倒退（lane 重設）不算成功或失敗。
- 擴充槽版：先問閘門，再問記憶體預算；被閘門擋下的幀不計入預算。一般版也改走 `fpl_lanes_arrive_admitted`（allow=1 時行為不變）。
- 閘門只會讓幀以原樣寫出（與 LOSS OFF 相同），不可能讓輸出錯誤。FHD 這種偶爾 1 幀被拒的情況不會觸發（需連續 8 幀且無成功）。

預期效果（HS280／M12240 119.88p）：約 8 幀後不再送引擎，省下 LOSS 多出的 CPU（cand-120p vs off-120p 約 8 個百分點）與 lane 佔用；
輸出與 LOSS OFF 相同。

### 驗證（離線）

- `native/test_refusal_gate.py`：11 項，含 5 個變異（不重開、不關、不試探、成功不歸零、計數倒退當成功）全部被抓到。
- 整合：`test_slot_expansion test_card_emulation test_bulk_native test_v3_lossless` 78 項 OK（`integration-tests.log`）。
- 原生：19 組 OK（`native-tests.log`；`test_native_variable` 為既有的 25 個 BINDING 錯誤，與本次無關，未跑）。
- 候選 BIN：`candidate/10LOSS.BIN` 82,144 B，sha256 `7e9205251ba2abfaf588c385f053bec2401068d427902d70fe5fa5291530a471`
  （`--expand-slots`，包含 registry 掃描終點與格數公式的修改）。
- `card_status.py` 新增一行顯示閘門狀態。

### 上機結果（2026-10-13 上午，使用者執行部署）

部署：putfile 的 echo 回覆逾時（寫入結果不明），未重送；整檔讀回 `readback-10LOSS.BIN` 與候選版 sha 相同（`7e920525…`）。
重開機（boot 11387135）→ 選單打開 Lossless RAW（`gate-ui-0*.jpg` 在 `../20261013-registry-scan/`）。
工具：`gate_trial.py`（只讀 LOSS 狀態；`--no-gate` 是對照組：REC 後把 `gate.streak_limit` 寫成 0，下一段錄影會重設）。

| 段落 | 模式 | 閘門 | 引擎工作 | 原檔直送 | 壓縮 | 收尾 |
|---|---|---|---:|---:|---:|---|
| hs280-4s | HS280 119.88p 4 s | 開 | 12（8＋1 在途＋3 試探） | 427 | 0 | **卡住**：LOSS 440 幀、寫入器 434、完成 398 |
| fhd60-2s | FHD 59.94p 2 s | 開（未關） | 103 | 0 | 54＋49 | 正常：104/104 |
| hs280-4s-nogate | HS280 119.88p 4 s | 對照：關掉 | 453 | 0 | 0 | **卡住**：LOSS 456 幀、寫入器 449、完成 398 |

- **閘門行為與設計一致**：HS280 關閘 1 次，`skipped` 427＝幀數－引擎幀；4 秒仍在錄（正式版 1.8 秒自停）。FHD 不關閘，全部壓縮。
- **收尾卡住與閘門無關**：關掉閘門的對照組同樣卡住。原廠 `rec log-out` 兩次都停在 `fin_cnt=398`（1＋7×57），
  最後一批（36／51 檔）送出但從未完成；`slots.cookies[0].pending` 等於該批檔數；XMP 物件指標 `C358E140` 不歸零；
  MRecMgr 等 mailbox、CamSch 等 flag 55，全部停住，只能重開機（`stuck-snapshot.txt`、`status-after-hs280-stuck.txt`）。
  兩次都有 6～7 幀「到過 LOSS 的 arrive hook、交給 C037DD50，卻沒到寫入器」，之前所有正常收尾的錄影這兩數都相等。
- **寫卡變慢的原因：卡片退回 UHS-I**（`sdcard sdmode` → `UHS-I`，處理函式 C040AD00 只讀；10/12 的 rec log 都是 `exFAT, UHS-II`）。
  UHS-I 上限約 104 MB/s，實測 87 MB/s；FHD 也同樣變成 96 MB/s。卡片本身可寫 200 MB/s 以上（使用者）。
  何時退回未知（今天 shell reboot 3 次、開機時無 rec log）。需實體關機／重插卡恢復。
- **今天的卡比 10/12 慢**：HS280 每批 57 檔 ~726 ms、87 MB/s（10/12 同模式 240 MB/s；卡剩 21%）。
  HS280 120p 進量約 131 MB/s，超過卡速時積壓在 RAM；正式版 96 格會在約 1.8 秒自停，擴充槽版（560 格）讓它繼續錄，
  積壓到某個程度後原廠丟了幾幀，最後一批永遠等不到。**擴充槽版在「進量＞卡速、錄超過約 3.5 秒」時會讓相機卡死，不可發布。**
  下一步：找出丟幀點（C037DD50 的回傳值在 hold 路徑被丟棄：frame_hold.c 的 `native_enqueue(h->creator, h->native_id, 1)`；
  但閘門那次只有 12 幀走 hold 仍丟 6 幀，所以不只這裡），以及原廠在 96 格時自停所依據的條件，擴充槽版要在同一條件下停錄或改送 RAW。
- 卡上新增測試片段：A001_184（hs280-4s，最後 36 檔不完整）、fhd60-2s、hs280-4s-nogate（最後 51 檔不完整）。

### 尚未做

寫回正式版被自動權限擋下（2026-10-13 11:43），**卡上目前仍是候選版**（設定已存進 BIN，LOSS ON）。
重開機後幀率會回到 59.94p；在擴充槽問題修好前，不要用候選版錄 HS280 119.88p 超過約 3 秒。已備好：
- `restore-card/fpSup/10LOSS.BIN`（正式版 `ad984ce6…`，70,944 B）

舊的準備物：
- `deploy-card/fpSup/10LOSS.BIN`（候選版）
- `release-backup-10LOSS.BIN`（卡上原本的正式版，`ad984ce6…`，含其內存的設定）

上機步驟：
1. `python3 -B fpSup/fp_usb_shell/v3/deploy_v3.py projects/lossless-sup/validation/20261013-refusal-gate/deploy-card`
2. 重開機，從原生選單打開 Lossless RAW（設定存在 BIN 內，換 BIN 後會回到 OFF）。
3. HS280 119.88p 錄 2 秒：預期 `gate.closes`=1、`gate.skipped` 約為幀數−8、不自動停錄、CPU 接近 LOSS OFF。
4. FHD 錄 2 秒：預期 `gate.closes`=0，壓縮率與 fhd60-5s 相同。
5. 用 `restore-card` 還原正式版：`python3 -B fpSup/fp_usb_shell/v3/deploy_v3.py projects/lossless-sup/validation/20261013-refusal-gate/restore-card`，再重開機。
