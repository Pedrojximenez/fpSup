# fp 原廠 AF 實測：自動半按、DMA 傳輸修正、原生掃焦曲線

日期：2026-09-16，SIGMA fp Ver.5.02。使用者授權由研究工具自行操作。

**同日更正：** 本文歷史 v2 記錄中的 capture-state／movie-recording 位址後來發現錯誤或
未獲證實，不能憑該欄位宣稱未錄影。原始資料不改寫；新版解碼將舊 recording 解為 unknown。
H/L／gain／原生掃描索引的獨立驗證不因此改值，但不得把舊 capture 欄位當成安全授權。
詳見 [更正與新版格式](FP_AF_CAPTURE_GUARD_CORRECTION_2026-09-16.md)。

## 結論

這次已完成「主機開始記錄 → 原廠半按 AF → 釋放 → 讀回原生掃焦歷史」，沒有拍照、錄影，
沒有改變選單曝光、對焦框或 AF 模式。取得六筆可與原廠峰值計算交叉驗證的歷史樣本。
這證明了量測路線，**不是已完成 DFD、幾何追焦或效能改善**。
已交叉驗證的是原廠歷史的索引配對與峰值計算；曝光中心位置的命名來自韌體路徑，
尚未用獨立光學／馬達真值驗證曝光時序。

最有力的配對驗證：三個 H 峰鄰點算出的頂點約 10013，與 Near 物件保存的原廠頂點 10013 相符。
最終命令位置為 10023，不能把命令位置當成每幀實際位置或把差值直接當光學誤差。

## 1. 原廠控制與保留狀態

- `key S1ON` / `key S1OFF`：原廠半按／釋放事件 4/5，未送 S2。
- dispatcher `0xC03F5DC0`，lookup `0xC03F5730`；表格 `0xC2F205C0/5CC`。
- 成功 handler 不印文字；主機只接受完整 daemon `OK \n`，不把 bare EOF 當成功。
- S1ON 不重試；即使開始回覆不明或收集中断，finally 仍嘗試 S1OFF。
- 釋放指令不受 event log 寫入失敗阻擋。通訊故障仍可能阻止硬體收訊，不能保證實體硬體 watchdog。
- 事件與 snapshot 走同一個主機 lock、序列化操作；S1OFF 先於 echo handler 還原。
- ACK 證明指令交換完成，**不等於合焦／實體按鍵狀態讀回**。釋放後另看到 route 返回 idle 14。

操作前後 getter 完全相同：

| Getter | 值 |
|---|---|
| SetFocusPosition | `784 341 128 128` |
| SetFocusMode | `0` |
| SetFocusArea | `0` |
| SetFocusAreaSize | `3` |

SetFocusPosition 是十進位 `x y width height`、1024×682 工作座標，不是鏡頭馬達位置。
getter 會套原廠 snap/clamp。生效 UserSetting `+C8..D4` 則是 left/top/right-inclusive/bottom-inclusive。
這輪没有移框；H/L 的 area slot 一直為 0，**slot 0 不代表畫面中心**。

## 2. 記錄器傳輸缺陷與修正

舊 952-byte handler 把 `C072F700` 工作區直接交給 USB DMA，只有 DSB，未處理可快取區的資料可見性。
既有 `dumpdirect.S` 已限制這條路徑用於 DMA pool/allocator；firmware image 應走 CPU copy。
`worker.S::arm_in_block` 不會替 payload 清理 cache。這會讓不同 cache line 混到不同代的記錄。

修正：仍在 C072F700 建立 record，然後 CPU 複製完整 208 bytes 到
`[*0xC3757A7C] + 0x2000` 的既有 capture buffer，再發布 CAP_LEN；CAP_PTR 明確清為 0。
沒有改 worker、USB endpoint、MMU 或全域 cache 設定。

新 handler：1000 bytes，位址 C072FC00..C072FFE7，未超出 1 KiB 工作槽。
SHA-256：`2bcde803e7948b2b0c375147936e37587d5d12960e5036e418c07beed484736d`。
舊版：`677e8049d72dec927c2ad960077c58cead8fe407eeb8953984df80142b9988cb`。
binary v2 / JSON v5 欄位未改；manifest 另標 `handler_transport=cpu-copy-to-worker-dma-buffer/v1`。

| 採集 | 條件 | 完整記錄 | 無效回覆 | 重複 | sequence gap |
|---|---|---:|---:|---:|---:|
| s1-right-a | 舊傳輸，6 s / 100 Hz，半按 AF | 239 | 241 | 117 | 356 |
| dma-copy-100hz | 新傳輸，純讀 3 s / 100 Hz | 300 | 0 | 0 | 0 |
| s1-right-b | 新傳輸，6 s / 100 Hz，半按 AF | 592 | 1 | 0 | 0 |

第二輪唯一無效回覆是 208-byte 請求收到 12-byte short reply，不是 sequence complement mismatch。
592 筆 sequence 連續，但**不代表所有 600 個排定時槽都有觀測**；控制／通訊停頓使採樣時程跳過一些時槽。
新路徑這两次沒有 stale nonce、out-of-order 或首尾序號混代。
舊版即使首尾序號相符，也不能排除中間 cache line 陳舊，舊動態資料只保留診斷用途。

證據：

- [舊版首輪 manifest](../../../../research/autofocus/captures/af-fusion/2026-09-16-s1-right-a/manifest.json)
- [100 Hz 純讀驗證](../../../../research/autofocus/captures/af-fusion/2026-09-16-dma-copy-100hz/manifest.json)
- [新版 AF manifest](../../../../research/autofocus/captures/af-fusion/2026-09-16-s1-right-b/manifest.json)
- [半按／釋放事件](../../../../research/autofocus/captures/af-fusion/2026-09-16-s1-right-b/events.jsonl)

## 3. 為什麼穩定索引仍讀到位置 0

這不是「0 永遠代表無效」；位置 0 可以是合法鏡頭端點。
問題是不同策略的 C329153C 意義不同：

- Fast::v5 `C025CD30`：寫完 mposm[k] 後發布 k。
- Near::v5 `C026AE50`：寫 mposm[k]。
- Near::v6 `C026B268`：可發布 **k+1**，下一格尚未寫好。

第二輪在半按後約 150.5 ms 讀到 index 2、position 0；161.6 ms index 3、position 0；
169.5 ms index 5、position 0；到 186.7 ms index 5 才有 9809。
因此 `snapshot_coherent=true` 只代表當次讀取的索引沒有變，不能授權 DFD 配對。

安全路線是 AF 完成後讀取原生歷史，利用 metadata 確認有效前綴：

| 資料 | 位址 | 排列 |
|---|---|---|
| mposm | C3291958 | i32 position[k] |
| per-area H history | C329B128 | 51×1000 u32，area stride 0xFA0 |
| per-area L history | C32CCE08 | 同上 |
| aggregate contrast | C32938A8 | 4×1000 words |
| Near object | C3206BE4 | delay +08、state +18、completion byte +28、vtable +38、raw n +3C |
| sweep descriptor | C320680C | count +08、H/L/position ptr +44/+48/+4C、delay +50 |

本次兩輪完整記憶體讀回一致：vtable C091F134、n=6、d=1、completion=1、descriptor count=6。
state=4 **也可以是正常完成狀態**：C0259D50 的同步 state-4 分支經 C025A618 執行 v5/v6，
完成時呼叫 v7 並設 completion=1，不必先改成 state 6；不能只接受 state 6。

有效位置前綴 k=0..n−d，即 0..5。對應 `H[k]/L[k] ↔ mposm[k]`，
**不要再把 H/L 位移 d 格**：d 表示位置晚幾幀填入，而非完成後陣列還要錯開索引。
原廠 Near::v14 C026D918、C0255718 和 C025AB90 的消費端皆使用相同索引。

## 4. 六點掃焦歷史與原廠峰值交叉驗證

| k | 曝光中心位置 | H | L |
|---:|---:|---:|---:|
| 0 | 10409 | 3130 | 34983 |
| 1 | 10340 | 4071 | 36619 |
| 2 | 10207 | 6404 | 39593 |
| 3 | 10076 | 8577 | 41945 |
| 4 | 9943 | 8525 | 42946 |
| 5 | 9809 | 7497 | 43042 |

H[6]=6967、L[6]=42905 仍存在，但該槽沒有有效 mposm 配對，不納入。
L 更後面的非零數字是舊歷史，不可依非零值延長樣本數。

H 最大值在 k=3。對 k=2/3/4 三點作不等距二次插值，頂點 `10012.5396`；
原廠整數規則得到 `10013`，正好與 Near +64、+7C 所存頂點相符。
後續核對 `C067E2AC → C067F804`：原廠採最近整數、半整數向遠離 0 方向捨入，不是截斷；
本例修正量 63.48236 兩種規則剛好皆為 63，不能只憑此例分辨。原廠加權差分與一般二次擬合
不是同一公式，詳見 [三輪重複性與離線驗證](FP_AF_REPEATABILITY_2026-09-16.md)。
global g_afpos=10023 是後續補正後的命令域；這次沒有另取鏡頭 drive-end getter 作獨立實際位置真值。

[兩次原生歷史讀回及設定核對](../../../../research/autofocus/captures/af-fusion/2026-09-16-s1-right-b/native-history.json)

## 5. 曝光與尚未完成的驗證

AF 期間感測器實際 relative gain 從 117 短暫升到 220、analog code 985→2441；
半按後 210.8 ms 仍為 220，291.4 ms 首次觀察到回復 117，真正切換發生在兩次觀測之間。
這是原廠 AF 路線自行改變曝光狀態，不是本工具送 ISO setter。UI ISO100 不等於 AF 期間增益固定。
第一輪也看到同類變化（117→218），但其舊傳輸資料不當作高精度時序證據。

H/L 是 CDAF 的高／低頻帶對比統計，不是 PDAF 左右相位像素。
單次同場景六點不足以建立可泛化的 DFD 模型；仍需不同失焦起點、方向、光圈、ROI、增益與鏡頭驗證，
並保存 filter/曝光轉換，避免把曝光變化當焦點變化。幾何輸入此次沒有有效 face/AAT ROI，未驗證追蹤。

本輪結束確認：S1OFF 交換完成、AF route 回到 14、movie_recording 全程 false、
四個設定 getter 與操作前一致、echo slot 還原為 C03D99A0。未刷新 firmware／改卡片 autorun。
