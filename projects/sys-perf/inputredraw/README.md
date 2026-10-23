# inputredraw:有輸入時立即重畫(2026-10-19，離線)

**會改原廠行為**(使用者已同意)。狀態：離線完成，unicorn 測試全過;**沒有上機、沒寫卡、沒 commit**。
**[靜]** = 反組譯；**[模]** = unicorn 實跑；**[推]** = 推論。

## 1. 原廠的按鍵到畫面 [靜]

```
硬體鍵 → app 處理器(CommonEventHandler v71 → MenuHandler vN)
      → GUI 物件 UicContentsIfBase::v1  C06D13A0
          C055DB10  組訊息(GuiKeyType → UIC 碼、characters/system-keys)
          C055E1E8  放進 GUI 佇列(單例 0xC378BF30，雙緩衝)   ← 按下、放開都經過這裡(C06D1418)
          按下且鍵在該類別的「強制重畫清單」(vt+0x68)→ ReqForceDraw(C0527E68, 請求 C2E45DB0)
GUI 佇列只在 UIC drawer C0561198 裡被消化 → 它只在 DrawThread 的重畫輪 C0528700 裡跑
DrawThread(C0528F28)只在旗標 4 醒來畫；旗標 4 由 CYC_DRAW(每 16 ms，除數 3)每 48 ms 設一次
```

- 所以**按鍵連「被處理」都要等下一個 48 ms 邊界**,之後才渲染、三重緩衝、LCD 掃描。
- 原廠已經有「立即重畫」機制(`ReqForceDraw`:4 個 slot 全標 dirty + 旗標 4 + 旗標 0x10 去重),
  但只在**按下**且鍵在該 GUI 類別清單(vt+0x68)內時才用，多數類別清單是空的 [推]。
- 量化 [模](16 ms tick 用真的 `C05276F0` 跑，按鍵時間 1 ms 步進掃 48 ms):
  按鍵→喚醒 DrawThread **原廠最壞 48 ms、平均 24.5 ms;修補後 0 ms**(之後的渲染時間不變)。

## 2. 做法

把 `C06D1418` 的 `bl C055E1E8` 改成 `bl <veneer>` → `ir_enq_hook`:

1. **先照原樣呼叫 `C055E1E8`**(訊息先進佇列，畫的時候才看得到新狀態)。
2. `enable=0` → 原廠。錄影中且 `rec_ok=0` → 原廠(`C00178D8()+0x9C`,與 `status get is_recording` 同一位元組)。
3. `C0527F30(DrawMgr)` 已有待處理的強制重畫 → 不重複送。
4. 距上次強制重畫 < `min_ms`(預設 16)→ 不送，改把 CYC_DRAW 計數器 `0xC3782F98+0/+4` 預載成「除數−1」,
   下一個 16 ms tick 就跑完整一輪(關中斷改兩個字，因為 CYC_DRAW 在計時中斷裡跑;只往上調、不往下)。
5. 否則送**原廠同一個請求**(`{1,1,0,0,-1,0}` = `C2E45DB0` 的複本)給 `C0527E68`。

- 重畫輪本身一個字都沒改;強制輪走的就是原廠 `ReqForceDraw` 的路，`C0528700` 照常跑。
- 原廠清單內的鍵：我們先送，原廠接著看到 pending 就跳過，不會雙重請求 [模]。
- **不涵蓋**:不經 GUI 物件的鍵(MENU 開選單、MODE/COLOR/TONE 走 app 功能)，以及非按鍵的畫面切換。
  它們仍等 48 ms 節奏。要涵蓋得另找 app 層的換頁點。

## 3. 控制區(body +0)

| 偏移 | 欄位 | 預設 |
|---|---|---|
| 00 | `'INRD'` | |
| 08 | enable | 1 |
| 0C | rec_ok(錄影中也立即重畫) | 0 |
| 10 | min_ms | 16 |
| 14 / 18 / 1C | 看到的按鍵訊息 / 強制請求 / 預載 | |
| 20 / 24 | 跳過：錄影中 / 已 pending | |
| 28 | 上次強制的時間(ms) | |

## 4. 測試(`python3 -B test_inputredraw.py`,`--mutate`)

- 跑真的 `C06D13A0`(含它呼叫的 `C055DB10`/`C055DB98`/`C055DFD0`/`C06D14D8`)、我們的 hook、真的 `C05276F0`。
- 11 項：先入佇列再請求、請求內容 = `C2E45DB0`、放開也觸發、關閉=原廠、未修補=原廠、錄影跳過/rec_ok、
  pending 不重送、原廠清單鍵不雙重請求、16 ms 內改預載且**真的 `C05276F0` 下一個 tick 就 tick+4 slot dirty+wake**、
  預載只往上調、未預載時原廠第 3 個 tick 才觸發、firmware 以 sp≡4 呼叫時我們呼叫韌體都是 8 對齊、r4–r11/sp 保留。
- 延遲掃描(見 §1)。
- **與 dirtyclean 共存**:用 dirtyclean 自己的 rig 跑 12 輪連續「4 slot 全 dirty」強制輪(含整層清除),
  無髒 line 違規，12 輪全走 fast 路徑。三重緩衝 commit 在 `C0528700` 內，我們沒碰。
- `--mutate`:**12/12** 被抓到(順序顛倒、拿掉開關/錄影/rec_ok/pending/最小間隔/last、預載值錯、少預載一個計數器、
  拿掉堆疊對齊、請求內容錯)。

## 5. 上機驗證(未做)

1. 安裝(併入 perf sup 或單獨):body + veneer 寫入讀回 → `C000E91C`→`C000EABC` → 改 `C06D1418` 讀回 → 快取維護。
   關機還原：宣告 4-byte 區段(原字 `EBFA3372`,見 `patch.json`)。
2. `enable=0`:行為等於原廠，`calls` 隨按鍵增加、`kicks=0`。
3. `enable=1`:在選單裡送 `key DOWNON`/`DOWNOFF`(不要在 LV 送左右鍵，會進曝光模式選單)。
   `calls` +2(按下、放開)、`kicks`/`preloads` 增加。
4. 延遲：開 `uicMgr+0x198` bit0(`0xC37B71CC`),log 類別 0x2000 會印每輪 Gui Update/Render 的 µs 時間戳;
   比較送鍵當下的 `current_time` 與第一筆 Gui Update 的差，`enable` 0/1 各 20 次。可選：高速攝影拍 LCD。
5. CPU:連按方向鍵時 profiler 看 DrawMgr 佔比；最小間隔 16 ms 保證每秒最多多 ~60 輪。
6. 錄影中預設不生效(`skip_rec` 增加);要試錄影中再設 `rec_ok=1`。
