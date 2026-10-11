# 上機部署:r2 fast-debug

2026-09-30 11:0x。經使用者同意(「開始吧」;先前指定 Fast Start 2),透過 USB shell 寫卡。

## 部署前檢查(唯讀)

| 項目 | 結果 |
|---|---|
| Fast AutoRun 與使用者原卡相同 | ✅ `35a3141f…f775` 逐位元組相同 —— 設定區裡現存的 loader 就是這一個,**本次不帶新的持久化變動** |
| 卡上 `FPSUPUI/` 資料夾 | ✅ 已存在(`putfile` 不會建資料夾) |
| `FPSUPUI/0..4.BIN` | ✅ 五個檔卡上與 r2 相同,**不寫** |

途中 `getfile` 一度報 `LOAD_DONE_US reads zero`。直接連讀 12 次都是 `0x10efe32`(約 17.8 s,
非 Fast 卡的慢速路徑)—— 是**讀取掉包造成的誤報**,正是 `cave.py` 第 97 行註解記載的情況。
重試後正常。沒有繞過該防護。

## 部署

`fpSup/fp_usb_shell/deploy.py cards/20260930-240-menu-r2/fast-debug`

```
fpSup.BIN    32768 B  (attempt 1)
AutoRun.txt  32768 B  (attempt 1)
both files read back identical; safe to reboot
```

## 獨立驗證

| 檔案 | 卡上 | 預期 |
|---|---|---|
| `fpSup.BIN` | `b877d174…821d` | `b877d174…821d` ✓ |
| `AutoRun.txt` | `35a3141f…f775` | `35a3141f…f775` ✓ |

部署前卡上是 preflight debug(兩檔皆在 repo)。使用者原本產品的備份仍在
`../20260930/card-backup/`。

## 接下來(尚未執行)

預設軸 H2(12-bit、2016x672、RWZM 2048/1024 -> 1008x672)。關機 -> 拔 USB 開機 -> 插回 ->
CinemaDNG / 12-bit / CUSTOM 下,格率 119.88 -> 240 -> 119.88 再重進,
看 popup、收合摘要、待機字樣,並讀 AXIS / RECIPE 與開機路徑。不錄影。
