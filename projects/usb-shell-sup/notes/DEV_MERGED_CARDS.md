# 開發用的合併卡 —— 怎麼建、跟使用者拿到的差在哪

2026-09-20

## 為什麼有這份

政策是「**合併版只在 fpSup-Merge 網頁產生**」（記憶 `merged-cards-only-from-the-page`），
理由是真的：`build_og3k_gyro.py` 曾經吐了好幾週錯的合併卡，卡名寫著 gyro、
裡面裝的卻不是出貨那個，**沒有任何東西失敗**，直到逐區段比對才發現。

但 2026-09-19 那天要驗 trampoline 和 gyro 的新 entry 契約，**網頁產不出來** ——
目錄裡的 shell 卡是兩代以前的 v3.1.0，worker 還住在空洞裡，跟 `ABORT_AT`
（`0xC072F080`）直接重疊。於是那三張實機測試卡是用腳本建的，而政策原文
剛好點名了那個旗標：「`--reference` 是給目錄產生器做比對基準用的，**不是拿去
插相機的**」。

與其下次再偷用，不如給這件事一個名字。

## 怎麼建

```sh
# gyro + USB shell（gyro 卡自己的除錯版本，本來就允許）
python3 fpSup/gyro/build_base_card.py --edition gcsv --debug \
        --version dev --banner 'fpSup-DEV!' --out DIR

# open gate + gyro + USB shell
python3 projects/open-gate/build/build_og3k_gyro.py --dev-card --out DIR
OG_TARGET=og2k python3 projects/open-gate/build/build_og3k_gyro.py --dev-card --out DIR
```

`--dev-card` 跟 `--reference` 產生**完全相同的位元組**，差別只有它會印出下面
那兩行差異。`--out` 是必要的：合併卡不能以成品形式躺在樹裡。

## 跟網頁產的差在哪 —— 2026-09-20 逐區段量過

拿 2026-09-19 實機驗過的 og3k+gyro+shell 卡，對上同一個組合由網頁產出的：

```
AutoRun.txt     逐位元組相同
fpSup.BIN       開發卡 97 區段   網頁 103 區段
  共同的 96 個                   每一個都逐位元組相同
  只在網頁那張 +6                EP 0x83 的 push 補丁，各 4 bytes
                                 開發卡走 --debug，它傳 --no-ep-patches
  trampoline                     兩邊都有，表格字不同（偏移不同造成）
  順序                           不同
```

**所以開發卡是網頁那張的子集加一個排列。** 在開發卡上驗到的行為適用於
網頁那張；反過來不一定 —— 網頁那張多開了推送端點。

順序差異的來源：`build_autorun.py` 把 worker 排在 `--also-bin` **之前**、
把 `--boot-bin` 排在**之後**；合併端照目錄順序走卡片，分不出那兩類。
這也是 `build_catalogue.py` 裡 `shell+gyro+og3k` 那兩個 STALE 的真正原因。

## ⚠ 重建 ≠ 拿到測過的東西

2026-09-19 的教訓，量出來的：

```
產出 A001_947 的 gyro 卡    launch 10,836 bytes  0b04c2681f59
已發布 gyro v1.12.0          launch 10,836 bytes  0b04c2681f59   ← 同一份
2026-09-20 重建              launch 10,964 bytes  4dbafdf396de   ← +128
```

那 128 bytes 是 `gcsv_json.S` 在 22:57 被改（`j_dng_dims` → `j_geom_dims`，
80/-42 行）——**在切完 release 之後**。要拿實機驗過的那份，從
`releases/fpsup-gyro-v1.12.0/` 取，不要重建。

## 規則

1. **要給人的卡一律走網頁。** 開發卡不進 `releases/`、不寄給別人。
2. **開發卡要說自己是開發卡** —— banner 裡寫 `DEV`，或至少別用發布版的 banner。
   兩張卡在相機裡長得一模一樣，banner 是唯一的辨識方式。
3. **改完任何一張卡就跑 `tools/card-composer/build_catalogue.py`**，它會驗
   五種組合。不過就拒絕寫出頁面。
4. **實機結論要綁在位元組上**，不是綁在「用哪個腳本建的」。記下 sha，
   或直接記 `launch` 區段的雜湊 —— 那是變動最頻繁的一塊。

相關：`fpSup/tools/card-composer/README.md`、`releases/TAGS.md`
