# USB gadget 正規註冊路徑 — RE 進行中 (2026-08-25)

## 為什麼要做這個
我們的 vendor 通道是 hook `0xC04DC618` 硬插進 PTP 的建構路徑,端點靠 worker 自己
強制啟用(CTX4_MODE 3→2、`DALEPENA |= 0x600`)。**PTP 與 CDC 都不這樣做,兩者都能跟
錄影共存;我們的不行。** 目標是讓 vendor gadget 走韌體自己的註冊,端點交給韌體管。

達成後自然得到:不需要 ctx4 覆寫、不需要手動 DALEPENA、**不需要 REC_FLAG gate**
(PTP/CDC 根本不看它),而且「邊錄邊串」自然成立。

**使用者已放寬一個限制:不需要跟 PTP 並存。** 所以 vendor 可以像 CDC 一樣
獨佔一個模式,不必嫁接。

## 已解出的
```
FUN_c00328b8(desc_set)   ★ 註冊入口
    str r0, [0xC3078BB0 + 0x714]      掛上描述元集合
    清 [+0] [+0x708] [+0x70c] [+0x710]
    sub sp, #0xD06                    3334 B 堆疊緩衝組裝裝置描述元
    *(u16*)sp     = 0x296B            VID(= USB_DEBUG 的那個)
    *(u16*)(sp+2) = 0xFFFE            PID

FUN_c0032320 / FUN_c0032348           **不是**端點位址重寫,只是查表存取器:
    idx = *(0xC3078BAC)               當前速度/模式索引
    return *(0xC072AF6C + idx*4)      /  *(0xC072AF80 + idx*4)
    → 依當前 USB 速度取出對應的端點位址

FUN_c0015058                          memset

描述元暫存區(RAM)
    CDC/MSC   0xC307A0C0   建構器 FUN_c003b7b0
    vendor    0xC3079340   建構器 FUN_c00333d0
    PTP       0xC3774820   建構器 FUN_c04e9148

CDC 建構器的動作:先 memset 幾個區段(+0x00/0x28/0x40/0x58/0x70/0xA0/0xF0),
再從 ROM 範本 0xC072B1xx 逐段 ldm/stm 複製,呼叫 0xC0032320/48 取端點位址填入,
最後 FUN_c00328b8 註冊。

模式關鍵字表 0xC0BC7B9C: msc/uvc/ptp/cdc/off/chg/on
func_id: 見 USB_MODES_COMPLETE.md（此行原本是錯的，正確為 MSC=4 PTP=5 UVC+UAC=8 CDC=12 卸載=0x11 其他=vendor）
```

## 還缺的
**描述元集合的完整結構定義** —— 暫存區那些 offset 各放什麼(裝置/設定/介面/端點/
功能描述元、字串索引…)。要把 `FUN_c003b7b0` 剩下的 ldm/stm 逐段對出來。
可做,但需要一段完整時間。

## 之後的驗證
註冊成功後要測:連線 + 錄影 + 錄影中下指令三者同時 —— 那是 PTP 已經做到的基準。

## ★ 更小的方法:借用 CDC 的端點,不要自己註冊 (2026-08-25)
CDC 已經提供了我們需要的一切:
| 條件 | CDC |
|---|---|
| 韌體正規註冊 | ✓ |
| 兩個 bulk 端點(0x01 OUT / 0x82 IN,HS mps 512) | ✓ |
| **沒有任何消費者** | ✓ 實測:第一次寫入成功之後全部逾時,被動聽 90 秒零位元組 |
| **與錄影共存** | ✓ 實測:claim 兩介面保持 90 秒,錄影完全正常 |

→ **切到 CDC 模式,讓 worker 服務 CDC 的端點**,就不需要 CTX4_MODE 覆寫、
不需要 DALEPENA |= 0x600、不需要描述元 hook、不需要 REC_FLAG gate。
worker 只剩它真正該做的:收指令 → 分派 `shl`/`call` → 回覆。

**不建議借用 MSC**:`usb msc` 會啟動大量儲存服務,把 SD 卡交給主機,直接跟錄影衝突。
CDC 的「沒有實作」在這裡反而是優點。

## ⚠️ 對既有標籤的質疑
worker 的 `CTX4_MODE = 0xC31E38C8` 這個名字是**先前實測歸納**的,不是靜態解出來的。
靜態看那個區域是**固定 0x14 間距的記錄表**,形狀像 `{0, 0xF, 0, shift, offset}`
(暫存器欄位描述表),而且初始化寫進 `+0x8C8` 的是 **0x536**,不是 worker 寫的 2。
**兩者對不起來 —— 在確認它到底是什麼欄位之前,不要在這個標籤上繼續建。**
(初始化函式在 0xC001F700 附近,基底 r4 → 若 base = 0xC31E3000 則
 +0x274/+0x748/+0x8C8/+0x98C 就是先前記錄的那幾個位址。)

## 結構性障礙:CDC 模式下無法互動探索
切到 CDC 之後 vendor 通道消失,**沒有任何方式跟相機說話**。所以不能像今天這樣
一步步試 —— 第一版 AutoRun 必須一次到位。

### 取得 CDC 執行期狀態的方法(下次硬體 session)
```
1. vendor 模式下注入常式:等 N 秒 → dump USB 結構區 → 寫檔到卡
2. shl usb cdc 切換(vendor 通道隨即消失,但常式仍在跑)
3. 等 dump 寫完
4. 拔電池 → 讀卡
```
那份 dump 會給出:CDC 用哪些 endpoint context、TRB ring 位址、DALEPENA 實際值。
**有了它才能寫第一版 AutoRun。**


---
## 2026-08-25 修正與補完
本檔的模式號對照 **原本是錯的**，完整且已驗證的解析移到 **`notes/research/interfaces/USB_MODES_COMPLETE.md`**。
該檔含：六組描述元集合的完整內容、七個 `usb` 關鍵字的 handler、充電模式實作、
Type-C 角色表，以及「韌體的 gadget 從不使用 EP 0x84 / 0x05」的窮舉證明。
