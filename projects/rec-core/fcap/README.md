# FCAP — 批次幀數上限(護欄)

Loader v3 sup,ID `FCAP`,檔名 `30FCAP.BIN`(316 B)。**不是優化**:修正我們的功能(LOSS 壓縮、res-custom 小幀)
踩到的原廠隱含前提。背景與推導:[`../WRITER_PLAN.md`](../WRITER_PLAN.md) §3a。

## 做什麼

原廠在每幀結束時檢查這一批的幀數 `vol+0x4850`,`== 0x80` 才送出;128 > 94(描述子池可用量),永遠輪不到。
FCAP 把立即數改成 40:

| 位址 | 原廠 | FCAP |
|---|---|---|
| 0xC063F824(整字宣告,SL_EXCL) | `02 20 80 2A`(`ldr.w` 尾 + `cmp r2, #0x80`) | `02 20 28 2A`(`cmp r2, #0x28`) |

k = (94 − 保留 14) / 2 = 40:媒體跟得上時,寫入期間新到的幀 ≤ k,在途幀 ≤ 94,與檔案大小、壓縮、解析度、格率無關。
一批不到 40 幀時(原廠模式 8–30 幀)不介入。`vol+0x4850` 只在這個比較之後 +1,並由 C063F140/C063F220 歸零,
所以 `==` 一定會觸發。

## 建置與測試

```sh
python3 -B build.py                  # build/30FCAP.BIN
python3 -B -m unittest test_fcap     # 7 項
```

- 真 loader v3 載入、日誌記錄原廠字、關機還原;第二個獨佔宣告者被拒。
- 在 unicorn 執行原廠 C063F81C 起的比較序列:第 40 幀送出,0/1/39/41/127 不送出。
- mutation:原廠映像下 40 不送出、128 才送出(測試能失敗)。

## 未驗證

- 保留量 14 沿用經驗值,未從原廠描述子生命週期算清楚。
- 與 LOSS、寫入層互不依賴;兩者都不得宣告 0xC063F824。

## 上機(2026-10-15,`validation/20261015-live/`)

卡:10LOSS `75b02a9b`(tag 版 ON,無 64 MiB 調整)+ 30FCAP。LOAD.LOG:FCAP LOADED、`C063F824 = 2A282002`。
FHD 59.94p、LOSS ON、UHS-II,錄 8 s:**450 幀錄滿，沒有在 94 停**(同一個 LOSS 版本不加 FCAP 約 2 s 就停)。
rec log 每批 fincnt +40、間隔 684 ms(= 41 幀 × 16.7 ms)、寫入 400–425 ms → 在途峰值約 65 < 94。
LOSS 計數 compressed 445 + hold_b 4 = flush.applied 449,tag_failed 0。卡上保留 30FCAP(使用者指示)。

## 合併頁

快照在 `fpSup/tools/merge-v3/inputs/fcap-20261015/`,sha256 是 `d2b22eda…`。頁面會比對這個 hash,不符就拒絕。
**重建 30FCAP.BIN 後，要通知 lossless-sup 或使用者更新快照。** 勾選 Lossless 會用軟連結(`links`)一併勾選 FCAP,但使用者可以取消。
