# 錄影 + USB shell 共存 — 已解決(真因訂正)

> 2026-08-23 實機定案。**推翻**之前一整天對「錄影凍結」的所有版本推論。

## 一句話真因
**凍結的兇手是 host 端(daemon/monitor)在 record-start 那一瞬間下的 shell 交易(peek/mem read)** ——
那筆交易的 DWC3 DEPCMD 撞上錄影 record-start 的 link/power flutter → IRQ-0x34 livelock。
**跟 AutoRun/worker 版本無關。** 只要 host 在錄影(尤其 record-start)時不下交易,shell 與錄影**本來就共存**。

## 實機證據
- **穩定版 = recsafe(pre-disarm hook + 原始 worker)**,SHA `10fe9125`(功能等同重建版 `ad46de3d`,
  存於 `fpSup .../autorun/AutoRun.recsafe-original.txt`,stub `0xD11E2800` / patch `0xB06AF141`)。
- 使用者在**我完全不連 daemon、不 poll** 的情況下錄影 → **完全正常,不凍**。
- 先前所有「凍結」的測試,凍結時刻都**正好落在我 monitor 的一次 peek**(且該 peek 命中 REC=1 / record-start 窗口)。

## 訂正:之前的錯誤推論(全部作廢)
- ❌「pre-disarm hook 害事」— 錯。hook 沒害事(它在錄影時根本不 fire,因 record-start 不呼叫 FUN_c01e62a8(0),DALEPENA 全程 0x6a7)。
- ❌「composite 下 0x600 被拆」— 錯。DALEPENA 全程 0x6a7,從沒被拆。
- ❌「worker state>=2 讓 suspend 漏過」→ state==4 gate — 錯方向。record-start 根本不改軟體 state(全程 state=2)。
- ❌「REC_FLAG 換成 0xC351FF35 修 re-gate」— 無關,反而讓開機列舉時序更容易卡。
- ❌「clean composite 才穩 / 10fe9125 害事」— 完全相反,是我 monitor 造成的假象。
- **共通錯誤根源:我用「自己 poll 造成的凍結」去評斷版本,越改越亂。**

## 正確用法
- **DFD(AF 統計 + 掃焦)不錄影** → 沒有 record-start flutter → host 正常 poll 也不會凍。這條本來就通。
- **要在錄影中用 shell**:host 必須在錄影期間**靜默**。做法:
  1. 手動:錄影前先停 daemon/poll(最簡單、已驗證可行)。
  2. 自動:daemon 以**很慢**的節奏 poll REC_FLAG(0xC351FF35),偵測到 !=0 就完全靜默,=0 才恢復。
     ⚠️ 連「偵測用的 poll」都可能撞 record-start 窗;最保險是使用者告知「要錄了」→ host 靜默。
- **穩定卡版本 = `AutoRun.recsafe-original.txt`(功能 10fe9125)。這是 canonical 穩定版,別再疊改動。**

## ★ 遺留項已定位(2026-08-25)
下面那條「怪怪的 / 待查」不再是模糊現象 —— 四段二分已經釘住觸發點:

```
libusb open 裝置                        → 錄影正常
+ claim 介面 1                          → 錄影正常
+ 一次 bulk IN on EP84(daemon 的 drain) → 錄影正常
+ 一次完整指令交換(EP05 OUT + EP84 IN)  → ★ 錄影可開始可停止,但【完全沒有資料】
斷開 daemon                             → 立刻恢復,不需重開機
```

**觸發點是「worker 服務過一次指令之後、重新 arm 端點的狀態」**,不是連線本身,
也不是 host 輪詢(這次全程沒有輪詢,連 hook 都沒裝)。

症狀與凍結不同:相機接受錄影開始與停止,不當機,只是產出空白。

**這也訂正了本文的「一句話真因」的適用範圍**:host 靜默可以避免*凍結*,
但避免不了這個*空白*現象 —— 只要 daemon 連著且交換過指令就會發生。

### 修復方向(給 task #11)
worker 原始碼本來就有對應設計,但顯然沒在這個 build 生效:
- `obs_notify` 在「recording exclusive lock 釋放」時重設 `GO`(worker state `0xC072F000` 的 `[16]`)
- `camera/poll_gate.S` 輪詢錄影旗標 `0xC347E08F`,連續 3 次 clear 才繼續 endpoint-enable handler
- `AutoRun.recsafe-pollgate.txt` 是帶這個 gate 的 build,而 canonical 卡用的是 `recsafe-original`

候選做法:錄影前把 worker 解除 arm(`GO=0`),靠 `obs_notify` 在錄影結束時自動恢復。
可用 `shl mem set` 寫 `GO`(worker 自己的 `mem set` 閘門寫不到那裡)。

**目前的迴避方式(已驗證可行):錄影前停掉 daemon,錄完再連回來。**
hook 跑在相機端,不需要 daemon 在場。

### ⚠️ 但這個迴避方式對串流無效
**Bayer raw 串流必須維持連線接收資料** —— 一旦要「邊錄邊串」,就不能斷開 daemon,
必須真的修好。影響範圍:
| 用途 | 需要連線 | 需要錄影 | 受影響 |
|---|---|---|---|
| DFD(AF 統計 + 掃焦) | 是 | 否 | 否,本來就通 |
| 陀螺/IMU 記錄 | 否(hook 寫卡) | 是 | 否,可斷開 |
| **Bayer raw 串流 + 錄影** | **是** | **是** | **是** |

### ★ 2026-08-25 續:範圍比錄影大,而且不是政策
**拍靜態照片也會凍結。** 所以不是錄影專屬互斥,是**任何寫卡的擷取動作**。

而且政策性阻擋會優雅地拒絕,不會凍結 —— 所以「翻一個權限旗標」的假設變弱。
本文開頭診斷的 **DWC3 IRQ-0x34 livelock** 更可能是同一個機制:
**USB worker 一旦 armed,它的 IRQ 處理跟卡片寫入的 IRQ 互相鎖死**。
空白 = 輕微資源飢餓,凍結 = 完全 livelock,同一衝突的兩種程度。

**現象不穩定**:同樣設定下看過凍結、空白、正常三種結果,差異很小。
→ 任何修法都必須**重複驗證多次**,單次通過不算數。

### ★ 但這可能不擋 Bayer 串流
| 情境 | 需要寫卡 | 狀態 |
|---|---|---|
| 相機推幀 → 主機接收(DFD 那條路) | 否 | **已驗證可行**,0.125ms/幀、311 MB/s,全程連線無問題 |
| 邊錄卡 + 邊串流 | 是 | 受影響 |

**DFD 證明「連線 + 高速推資料」本身沒問題,出事的一直是寫卡。**
所以只有「同時錄到卡」才被擋住;若串流是取代錄影(推到主機存),這條路是通的。

### 舊假設:政策性阻擋(已弱化,保留供參)
今天挖到的符號指向權限機制:
```
UsbPermissionChanged                      (字串 0xC0CF0094)
GetCamOpPermission / SetCamOpPermission   (字串 0xC0CF4C7C / 0xC0CF4E34)
來源檔 src/apl/ui/src/oem/TH/func_usb/UsbMenuCommand.cpp
觀察者 0xC04BD0D0 / 0xC04C0810
```
症狀吻合政策而非崩潰:錄影**接受**開始與停止、相機不當機、只是產不出資料;
斷開立刻恢復不用重開機。相機的標準行為就是「接上 PC 就不能拍」。

若成立,修法是找出權限變數並維持,或阻止 worker 觸發權限變更 ——
比端點/DMA 衝突好處理。RE 目標:`SetCamOpPermission` 操作的變數、
`UsbPermissionChanged` 的觸發鏈、錄影互斥鎖 `0xC347E08F`、worker 的 `GO` `0xC072F010`。

## 遺留(可選,非阻塞)
- 「怪怪的」(錄影音量表無反應 / 相機回播)—— 見上,已定位。
- record-start 的 hook（disarm worker）當時是為了「host 不用管」而設想;既然真因是 host-poll，**不需要那個 hook** — 手動/慢-poll 靜默即可。

## 2026-10-14 追記：shell 載入時對高格率錄影的影響
- 00SHELL.BIN 載入時改寫兩個程式碼字（相機 LOAD.LOG 與全區比對都看得到）：
  - `C0033B3C`：`bl`（EB129F0D）→ `mov r0,#0`（E3A00000）；
  - `C01E7704`（Thumb）：`beq`（D01E）→ `b`（E01E）。
  這兩處各自的作用還沒有查。
- 實測：shell 開著（不管 USB 有沒有通訊）時，239.76p 的 MovRec 請求速率只有約 188–204 fps（A001_320／322 的原生 rec log），
  達不到 239.76，SSD 很快就以 vbuf 停止。HDMI 輸出開著也有類似影響。
- 所以 240p 這類吞吐量測試一律關掉 00SHELL 和 HDMI。證據：
  [unified-hirate](../../res-lab/validation/20261014-unified-hirate/RESULTS.md)、
  [parity-live 全區比對](../../res-lab/validation/20261014-parity-live/RESULTS.md)。
