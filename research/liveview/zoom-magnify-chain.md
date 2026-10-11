# SIGMA fp Ver.5.02 — 畫面放大(AF/MF 放大)的完整路徑,與「錄影中不能放大」的出處

靜態反編譯(`out/decomp/full/`,映像 `out/seg0_c0000000.bin`)。
未上機驗證的項目在最後一節單獨列出。

## 0. 一句話

放大不是顯示層的事,是**改 LiveView 的幾何設定再整條重新套用**;
而許可判斷 `FUN_c04a5650`(canZoom)裡有一條 `FUN_c04a4eb8() == 0`,
`FUN_c04a4eb8` 在**正在錄影時回 1**,於是整個放大入口在錄影期間直接關掉。

## 1. UI 狀態機

類別名本身就說明了範圍 —— 只有 **Standby**(待機)的 LiveView 有放大狀態:

| 狀態 id | 類別 | 物件偏移 | vtable(fn0) |
|---|---|---|---|
| 0 | StandbyLiveViewZoomStateNone | +0x00 | 0xC0CD7510 |
| 1 | StandbyLiveViewZoomStateNormal | +0x14 | 0xC0CD7568 |
| 2 | StandbyLiveViewZoomStateAfZoom | +0x28 | 0xC0CD75C0 |
| 3 | StandbyLiveViewZoomStateAfAutoZoom | +0x3C | 0xC0CD7618 |
| 4 | StandbyLiveViewZoomStateMfZoom | +0x50 | 0xC0CD7670 |
| 5 | StandbyLiveViewZoomStateMfAutoZoom | +0x64 | 0xC0CD76C8 |

- 容器建構:`FUN_c0485b30`(六個狀態一次建好,實例在 0xC3765A3C,
  current-state 在 0xC3765A20+4)
- id → 物件:`FUN_c0485c68`
- 切換:`FUN_c04819d8(ctx, id, arg)` → `FUN_c0481a08`(舊狀態 v4 離開、新狀態 v3 進入)
- 選 AF 放大還是 MF 放大:`FUN_c0480160` —— 對焦模式 `FUN_c0059d18()==2`(MF) → id 4,
  否則 id 2。`FUN_c0480c18` 另有一條:`FUN_c04a51b8()`(uiState+0x85)非 0 時強制走 MF 放大。
- log 字串可當錨點:`ZoomLeave` `ToZoom` `ToNormal` `BackState`(0xC0CD71F4 附近)

MovRecFuncState* 那一族(REC/RECSTART/RECHOLD/…)**沒有**任何 Zoom 子狀態。

## 2. 許可判斷 `FUN_c04a5650`(canZoom)

來源檔 `src/apl/ui/src/oem/TH/util/LvOpe*.cpp`。逐條(任何一條不過就回 0):

1. 對焦模式 `FUN_c0059d18()==1`(AF-C)且 `FUN_c04a51b8()==0` → 不准
2. `FUN_c04a4f48()` 且 `FUN_c0058e70()==1` → 不准
3. **`FUN_c04a4eb8() != 0` → 不准**(← 錄影中就是走這條)
4. `FUN_c04a50a8()`(uiState+0x86)必須非 0
5. `FUN_c04ae0b8() != 0` → 不准(uiState+0x210==2 或 `FUN_c04fbe20()`)
6. `FUN_c04a51d0()`(UserSetting+0x3B0)、`FUN_c04a6698()`、`FUN_c04bc3c8()`(UVC 相關,
   字串 `Y_UVC_er`)都要是 0

外層還有 `FUN_c04a5790`:先問 `FUN_c04a7618(0)`,非 0 就擋並跳 `FUN_c04a7518(2)`
(OSD 提示 3000 ms + `FUN_c04a83d0(9)`)。`FUN_c04a7618` 讀的是設定物件 vtable+0x480
的屬性(getter `FUN_c0062f00`),語意未定 —— 見第 6 節。

## 3. ⚠ 這一節的推論**上機推翻了** —— 見文末「上機結果」

保留原文是因為那條推理鏈本身值得看一次:它每一步都自洽,而且錯了。
實測 `FUN_c04a4eb8` 在錄影中回 **0**;真正翻轉的是第 2 節第 5 條的 `FUN_c04ae0b8`。

### 原文:第 3 條:`FUN_c04a4eb8` 就是「錄影中」

```c
uiState = 0xC303384C;                 // FUN_c00178d8() + FUN_c0017ac8()
r = 1;
if (*(int*)(uiState+0x218) != 1) {
    if (RecMgr::v6() == 0) r = 0;     // FUN_c0370cf8() → FUN_c0370e18()
}
return r;                             // 1 = 不准放大
```

`RecMgr` 單例 0xC351FE88(`XC_RecMgrImpl`,vtable fn0 = 0xC0B99294)。
`FUN_c0370e18` 走 vptr+0x20 → **v6** = `FUN_c0371bd0`:

```c
obj = FUN_c0399248();        // 0xC358E1D4
return *(int*)(obj+4) != 0x80000000;
```

0xC358E1D4 的持有者是 `src/framework/recMgr/src/movie/R…`(錯誤字串
0xC0B9D5B0 / 0xC0B9D5E8),+4 是錄影中的檔案/工作句柄,0x80000000 = 沒在錄。
取得 = `FUN_c03992b8`,釋放 = `FUN_c0399620`(釋放時還去更新 uiState+0x1CC/+0x1D0
的錄影計數並 `FUN_c0017e38` 通知 UI)。

→ **正在錄影 ⇒ canZoom = 0 ⇒ 放大鍵、AF 放大、MF 自動放大全部不進狀態機,而且是靜默的**
(有 3 秒提示的是第 2 節那條 `FUN_c04a7618`,不是這條)。

## 4. 放大實際做了什麼

進入狀態 `StandbyLiveViewZoomStateZoom::v1`(0xC0480C90):

1. `FUN_c04a7290(isMf)` 取倍率檔位(回 1 或 2,來源是設定 `FUN_c005a3e0`/`FUN_c005a5a8`)
2. `FUN_c04a5fc8(lvope, ratio)`:
   - ratio!=0 時從設定讀目前的 LV 放大倍率(`FUN_c0062f98`,對應 PTP dump 的
     `[Grp4]LV_Magnify_Ratio`)存進 lvope+0x18,並用 `FUN_c04a6c10` 算放大框位置
     (參考 AF 框、人臉框 uiState+0x284.. 與 +0x590)
   - ratio 存 lvope+0x5C,然後 `FUN_c04a6b20` 套用
3. `FUN_c04a6b20`:把 `XC_UserSetting`(0x5E4 bytes,現值在 `FUN_c0021c40()`)整份複製出來,
   在 **1024x682 的畫布座標**(`local_604=0x400`, `local_600=0x2AA`)上用
   `FUN_c04d1460`/`FUN_c04d14C8` 算出放大矩形寫進副本,再 `FUN_c0021c50` 提交
4. 提交 = `FUN_c0021e78`,對 `XC_LockSubject<const XC_UserSetting&, 20U>` 的 20 個
   observer 全部廣播 → LiveView / 顯示鏈依新幾何重新配置

1024x682 這組數字跟 `projects/open-gate/notes/LIVE_VIEW_DISPLAY_CHAIN.md` 第 7 節
量到的「OSD 畫布 1024x682」是同一個座標系,兩邊互相印證。

離開:`Zoom::v2`(0xC0480DC0)寫 log `ZoomLeave`、`FUN_c04a5fc8(lvope,0)` 還原,
並重新啟動 LCD 自動關閉計時(`LcdOffStart`)。

## 5. 為什麼結構上不能在錄影中做

放大走的是「改 LiveView 幾何 → 重新套用整條顯示/影像鏈」,而錄影期間:

- 預覽走的是**錄影 profile 自己的預覽半部**,柵格/可見尺寸由該 profile 決定
  (見 LIVE_VIEW_DISPLAY_CHAIN.md 第 5 節)
- 顯示層的縮放與位移是**在錄影開始那一刻 latch 的,不是每幀重算**
  (同筆記第 7 節:按下錄影瞬間「從中心放大一點又鎖回去」就是 latch 的證據)

所以錄影中改這組設定不會被重新採用,且會與錄影輸出尺寸/DNG 裁切脫節。
韌體的做法是直接在許可判斷關掉入口,而不是讓它半生效。

## 6. 未驗證 / 下一步

- `uiState+0x218 == 1` 的語意未定(只知道它和「錄影中」並列成立時同樣禁止放大)。
  可實機讀 `0xC303384C+0x218`,錄影/非錄影各取一次對照。
- `FUN_c0062f00`(設定 vtable+0x480,PTP 屬性 0xFD)語意未定 —— 它同時擋 QS
  (`MenuQsHandler::v11`)與放大,預設值 2(`FUN_c04b3370`)。Crop Zoom / UVC 都有可能。
- 想測「放大能不能在錄影中成立」:hook `FUN_c04a4eb8` 讓它回 0,只會讓 UI 進入放大狀態;
  畫面會不會真的放大,取決於第 5 節那個 latch —— 這是兩個獨立的問題,要分開測。

## 7. 附:這份筆記用到的 vtable 換算

RTTI 名稱表在 `out/rtti_classes.json`(typeinfo 位址)。在映像裡搜尋指向 typeinfo 的 word:

```
vptr      → [0] offset_to_top
vptr + 4  → [1] typeinfo          ← 搜到的位置
vptr + 8  → [2] fn0 (解構子, Ghidra 的 __v0)
vptr + 8 + 4k → fnk (__vk)
```

物件第一個 word 存的就是 vptr(已用 `FUN_c03716f0` 的 MOVW/MOVT 立即值核對:
`XC_RecMgrImpl` vptr = 0xC0B9928C,typeinfo 在 0xC0B99290,fn0 在 0xC0B99294)。
所以反編譯裡的 `(**(code**)(*obj + N))` = `fn[(N-8)/4]`,編號與 Ghidra 的 `__vN` 一致。
例:`FUN_c0370e18` 用 +0x20 → v6 → `FUN_c0371bd0`。

---

# 上機結果 2026-09-28 —— 機制,不是政策

實驗與工具:`zoom-in-rec/`。五道守門全部拆掉、實機量測,結論是**拆掉也沒用**,
而且量到了放大真正在做什麼。

## 判讀指標(比預期好用)

```
0xC3765A20        current state 指標;(它 - 0xC3765A3C) / 0x14 = 狀態 id
0xC37610CC + 0x5C lvope 的放大倍率(0 = 沒放大)
0xC31DF594        可見 W, H, 來源 W, H      (開機起就對得上 open-gate 筆記)
0xC31E10F8        引擎輸出 W, H
```

`callfn` 可以直接呼叫 `FUN_c04a5650` 問 canZoom,不必靠猜。

## 訂正兩個靜態推論

| 我寫過 | 實測 | |
|---|---|---|
| `FUN_c04a4eb8` 是「正在錄影」 | 待機 0、錄影中**也是 0** | 它不是那道門 |
| `RecMgr::v6`(0xC358E1D4+4)= isRecording | 同上 | 也不是 |
| `FUN_c0062f00` 可能是錄影旗標 | 兩邊都 0 | 也不是 |

逐條量下來,待機→錄影中只有**一個**條件翻轉:

```
FUN_c04ae0b8    0 → 1        canZoom 要求它是 0
  = uiState(0xC303384C)+0x210 == 2  ||  FUN_c04fbe20() != 0
```

真正的門只有這一道,呼叫點 `0xC04A56B8`。

## 拆掉之後:UI 進得去,畫面不動

```
                 id  ratio   可見        來源         輸出
待機 正常         1    0     2000x1125   2016x1344   1620x911
待機 放大         2    1      750x500    6064x2022   1620x1080   ← 整條鏈換掉
錄影 正常         1    0     1920x1080   1936x1090   1920x1080
錄影 放大         2    1     1920x1080   1936x1090   1920x1080   ← 一個字都沒動
```

待機截圖確認 OSD 畫的是 `🔍 ×8.0 AF`,放大是真的生效。
錄影中狀態機照樣走到 AfZoom、ratio 照樣變 1,**顯示鏈完全沒有反應**。

## 放大在做什麼:換感光元件讀出,不是裁畫面

待機放大時來源變成 **6064x2022** —— 那是全寬、1:1 像素的讀出,不是從
2016x1344 的預覽裡裁一塊。可見 750x500 是那張大圖裡要送到面板的視窗。
這解釋了為什麼 fp 的放大對焦看起來是真的銳,也解釋了為什麼錄影中做不到:

**錄影期間感光元件讀出模式是錄影自己的(1936x1090),換掉它就是換掉錄影的畫面。**

所以這不是政策性禁止。韌體把入口關掉,是因為後面那條路在錄影中本來就走不通。
`LIVE_VIEW_DISPLAY_CHAIN.md` 第 7 節量到的 latch 是同一件事的另一面。

## 這對 B / C 兩條路的意義

- **B(改預覽可見視窗)** 假設被修正但沒有被否定:錄影中可見 1920x1080 / 來源
  1936x1090,把可見改小仍然是數位裁切放大,只是畫質等於預覽放大,不是待機放大
  那種 1:1 重讀。能不能在錄影中重新套用,還是要先解決 latch。
- **C(OSD 放大鏡窗)** 不受影響,仍然是保底解。

## 過程中的兩個坑

- **錄影中按 CAPTURE 鍵**(截圖)會讓 shell 端點 timeout,而且錄影被停掉。
  錄影中 `mem get` / `key OKON` / `key MOVON` 都沒問題,單單那一顆不行。
- `dir \CINEMA` 全程回報沒有新 clip,但 `is_recording` 與幾何都證明在錄 ——
  又一次 [[getfile 的假陰性]] 那一類,別拿 dir 當有沒有錄到的證據。
