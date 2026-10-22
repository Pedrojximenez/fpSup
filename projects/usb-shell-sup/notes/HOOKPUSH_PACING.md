# hook-push 的節奏規則 — BATCHPUSH 靜默期

<!-- index-stamp -->
> 這份寫的是 EP 0x05 OUT / EP 0x84 IN。現行 build 用 EP 0x01 / 0x82 / 0x83(`host/fpshd.c:31-32`、`patches.py:15-20`),EP84 在現行描述元下不存在。
> 先看 [`USB_SHELL_INDEX.md`](USB_SHELL_INDEX.md)。


> 2026-08-24 實機定案。今天為了這條規則拔了六次線,值得寫清楚。

## 一句話
**BATCHPUSH 之後約 1 秒內下任何命令,會把 EP84 打成 `LIBUSB_ERROR_PIPE`(端點 halt),
重起 daemon 救不回來,只能拔插 USB。** 一般 `ECHO` 命令彼此密集下則完全沒事。

## 直接對照證據
```
成功  fetch → sleep(0.5) → ping → sleep(1.2) → fetch    ×5 全過
失敗  fetch → ping(立刻)                                 → EP84 halt
```
第一個 BATCHPUSH 本身**是成功的**(資料好好回來了),是緊接著那個無害的
`ECHO echo p` 把端點打掛的。另一次:82 幀的鏡頭掃描完整成功,緊接的裸 socket ping 掛掉。

## 訂正:一開始規則想錯了
最初以為是「兩個 BATCHPUSH 靠太近」,於是只在 BATCHPUSH 之間加間隔 → **沒擋到真兇**。
真正要擋的是**BATCHPUSH 之後的所有後續流量**,不只是下一個 BATCHPUSH。

## 實作(monitor/telemetry.py)
```python
MIN_GAP  = 1.5    # 兩個 BATCHPUSH 之間
POST_GAP = 1.0    # BATCHPUSH 之後,任何命令之前
```
- `batchpush()` 是**唯一**入口(telemetry 與 lensdump 都走它),內含 `_BP_LOCK` + 時間戳。
- `wait_quiet()` 掛在 **`fpstate.Shell._round` 最底層** —— 所有命令都經過那裡,誰都繞不過。
  放在呼叫端是守不住的:兩個獨立呼叫者各守各的等於沒守(已驗證會掛)。
- 健康檢查一律用 **`telemetry.health()`**,它會先等靜默期。
  ⚠️ **不要自己開裸 socket 送 ECHO** —— 那會繞過閘門,今天被自己的測試腳本坑了兩次。

## 另一條硬約束:daemon 每幀 5 秒逾時
`fpshelld` 的 BATCHPUSH 對**每一幀**給 5 秒逾時。所以推送常式必須讓每幀都在 5 秒內出來。
- ❌ 錯誤設計:掃完一整批才推一次(71 個鏡頭區塊 = 21 秒才推第一幀 → 必然逾時)
- ✅ 正確設計:**每處理完一個單位就推一幀**(每幀約 0.3 秒,遠低於逾時)
  副效果:整趟只要**一個** BATCHPUSH,比分批更安全。

## 設計準則
1. **少次多筆** 永遠優於多次少筆。一次 100 筆的成本 ≈ 一次 20 筆,樣本卻多五倍。
2. 週期性/成批取資料 → 一律 hook-push;一次性幾個 word 的探測 → peek 可以;RAWGRAB → 永不。
3. 推送常式的迴圈裡要有 `FN_WAIT`,讓每幀同步到 host 的 bulk-IN(不要自己 usleep)。

## 現況數字(LUMIX S 40mm F2 實測)
| 項目 | 數值 |
|---|---|
| 遙測推送 | 0.14 ms/筆,100 筆/次,1 秒 1 個命令 |
| 陀螺儀取樣 | 100 筆跨 13.6ms,去重後約 33 筆(2500Hz 完全跟得上) |
| 鏡頭全區塊掃描 | 82 幀 / 35 秒 / 一個 BATCHPUSH / **零 mem read** |
| 鏡頭每幀 | 376 ms(純鏡頭匯流排速度,與 USB 無關) |
