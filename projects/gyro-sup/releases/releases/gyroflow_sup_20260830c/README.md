# Gyroflow sup — SIGMA fp Ver.5.02 — 2026-08-30c

插卡、開機、拍攝。每段影片結束後,卡上就有 Gyroflow 需要的一切,**全程不接電腦**。

```
\GYRO\A001_017.GYR                 原始陀螺資料(備查,Gyroflow 用不到)
\CINEMA\A001_017\A001_017.gcsv     陀螺 + 水平儀,七欄
\CINEMA\A001_017\A001_017.json     鏡頭 profile
```

實機驗證:A001_016、A001_017 兩段,三個檔齊全,`xmp` 298 bytes(沒有凍結),
json 為 mode 106 / 捲簾 10.556 ms / fx 1509.972。

## 開發轉發布的流程

**同一份原始碼,兩個組建。** 差別只有一個組譯器旗標。

```
gyro/makecard.py debug       開發用:多一個 USB shell,可以接線診斷
gyro/makecard.py release     出貨用:沒有 shell,也沒有任務
```

兩者都會從原始碼建置、複製三個檔、建立 `GYRO/`、逐位元組驗證 sha256、退出卡。
**開發時只用 debug 版**,功能穩了才切 release —— 兩版的 logger 與池程式碼完全相同,
不同的只有 loader 的引導方式,所以 debug 上通過的東西 release 上也成立。

| | release | debug |
|---|---|---|
| AutoRun 指令 | 157 | 221 |
| loader | 97 字(不建任務) | 128 字(建任務) |
| VSHL.BIN 區段 | logger、park、hook | worker、logger、park、hook |
| USB shell | 無 | 有 |
| 開機時間 | 約 18 秒 | 較久 |

### 為什麼發布版不建任務

loader 的工作是讀 `\VSHL.BIN` 再把裡面的區段放到記憶體。debug 版讀完之後那個任務
**要變成 USB shell 的 worker**,所以非有任務不可。release 版沒有 worker,任務讀完就
只能睡著 —— 一個永遠睡著的任務,卻要花 31 個字的 loader 去建立它,也就是 31 條
`mem set`、約 1.9 秒的開機時間。

所以 release 版直接在陀螺回呼裡把檔案讀完就返回。代價是那一次取樣環的排空會晚
幾十毫秒 —— 發生在開機當下,沒有任何東西在錄影,而環本身有 240 ms 餘裕。
**實機確認過:進度條走完到 `fpSup!`,韌體的檔案 API 在回呼情境下不會卡互斥鎖。**

做法是 `templates/loader.S` 裡的 `#ifdef NOTASK`,由 `armasm.assemble(src, ['NOTASK=1'])`
帶進去(`build_autorun.py` 在 `--no-shell` 時自動加)。**兩版共用同一份原始碼,
不會分岔。**

## 開機時間

```
開機 → 0%        6s   相機自己開機,AutoRun 還沒跑 —— 動不了
101 條 mem set   6s   每條約 60 ms
 55 條 display   2s   每條約 36 ms
memmgr 配 1 MB    4s
                ────
                18s
```

量測方式是 A/B:同一張卡只改進度條的粗細(`FPSUP_THIN_BAR=1`)、或只改 loader
建不建任務,各開機一次按碼表。

- 滿版進度條 + 建任務 = 20s
- 細進度條 + 建任務 = 18.5s(**顯示不是瓶頸**,砍掉 42 條只省 1.5 秒)
- 滿版進度條 + 不建任務 = **18s** ← 現在

再往下的空間很小:那 1 MB 的池是 logger 拿 gcsv/json 工作區的地方(池的分佈用到
0xF9800),不能縮;進度條要留;剩下 loader 的 97 個字再擠大約省 1 秒,但每一刀都在
開機路徑上。**建議停在這裡。**

## 相機自己做的事

- **鏡頭 profile**:讀 L-mount 鏡頭的名稱與焦距、查韌體自己的 IMX410 時序與幾何表、
  算出捲簾時間與 focal_px、格式化成 JSON。換鏡頭自動跟上(實測 LUMIX 40mm →
  SIGMA 28mm,`fx` 從 2157.103 變成 1509.972)。
- **捲簾時間**取自那一段真正使用的模式,在第一個區塊寫入時取樣(766 ms),
  避開錄影開始與結束兩端的即時取景模式。FHD 29.97 → mode 106 → 10.556 ms。
- **gcsv** 含陀螺(2500 Hz)與水平儀(100 Hz),與主機解碼器逐位元組相同。
  加速計軸向 `(ax,ay,az) -> (ay,-ax,az)`,`ascale = 1/1024`。

## 架構

```
注入區 0xC072E064..0xC072EFB4(3900 bytes 上限)
    logger 3068 bytes:陀螺回呼、writer 執行緒、跳板
池記憶體(bufmem,開機由 logger 自己讀 \PGEN.BIN 進去)
    profile 生成器 + gcsv 建構器,4016 bytes
```

`gcsv_build` 與 profile 生成都在池裡跑 —— 注入區塞不下,而它們只在錄影結束後才動。

## 兩個曾經很難查的問題

**凍結**(已修):`gcsv_build` 在錄影剛結束時回讀 250 KB、再寫 600 KB,把檔案系統
佔住,讓優先權 6 的 `SRecFile` 進不來(我們的 writer 是 28)。二分法定位,每組 7–9 段:
沒有 logger 0 次、只寫 .GYR 0 次、加上 profile 0 次、加上 gcsv 約四分之一。
**修法是每讀寫一塊 `dly_tsk(5)` 讓出**,整段多花約 0.2 秒。縮短單次呼叫不夠 ——
呼叫仍然一個接一個。

**判讀凍結**:`\CINEMA\<clip>\SPP_metadata.xmp` **0 bytes 就是那一段當時卡死**
(相機在錄影開始時建立它,收尾才寫)。正常是 298–299。這是唯一能事後判讀的證據。

## 已知問題

1. **軟關機後下次開機失敗**,要拔電池冷開。近期版本沒再出現,推測是 logger 的
   復歸防護修掉的(發現池位址變了就把韌體原本的指令寫回去、自己退場),
   **但沒有經過足夠次數的確認**。
2. 偶爾有一段不產生 `.GYR`(曾見於 A001_044、068、069)。原因未查。
