# loader v4 上機驗證

## 第 1 步(2026-10-20 03:00,fpSup2 卡;只放 v4 LOADER.BIN a2b44321 + SHELL.BIN d711f05c + v4 AutoRun cec232c1)
- 卡上原本 \fpSup\ 與 AutoRun 備份在 card-backup-20261020/(10LOSS.BIN 下載失敗未備份;使用者說不用備份，未重試)。
- 暖開機(shell reboot)10.7 s 回來(v3 時 14–15 s)。
- LOAD.LOG(20261020-LOAD.LOG):12 個 v3 sup 全部 `14`(OLD_FORMAT,FSB1)拒載;`0A 45049E40 SHELL.BIN`(4 claims);._ 檔未列入;每檔一行。
- USB:256 KiB 隨機檔 putfile→getfile sha256 相同。1 MiB 失敗是 v4 AutoRun 的 shell 緩衝池較小(非 v4 問題)。
- **選單延遲(無任何 fpSup UI hook = 純原廠)**:開選單 Update 191 ms / 約 285 ms 完成(v3 時 346 / 430);
  切分頁 Update 82–136(v3 131–210);關選單 Update 約 270(v3 482)。**v3 loader 的 UI hook 讓選單慢約 40%**。
- 尚未驗：核心在快取別名(核心開機後幾乎不執行，需在關機寫回或 page API 呼叫時驗);SHELL 依設計仍非快取。

## 開機時間量法(2026-10-20 訂正)
- **ui_drive.py reboot 的「up after N s」是主機往返(含 USB 重新列舉、daemon、寫死的 3 s 等待),不是開機時間——不要再引用。**
- shell `reboot` 會重新載入韌體映像 = 等同冷開機、會跑完整 AutoRun(bootmeasure.py 註解)。這次 v4 用的是舊版預設 AutoRun(文字進度條、無快速啟動),所以開機明顯慢。
- 相機自己的 µs 時鐘(與韌體 log 時間戳同一個):LOAD_DONE_US 0xC072F6F8;loader 開始 0xC072F6F4(只有 --profile 版)。
- 這次(v4 預設 AutoRun)時間軸:UicViewM 0.25 s、battery 0.52 s、DISP 層 1.57–2.29 s、**LvStarted 1.99/2.23/2.28 s**、**LOAD_DONE 3.42 s**。
- 精確量三種開機：等 v4 卡產生器的 `--boot-markers`(AutoRun 起點/動畫前後/loader 前後打戳)+ boot_timeline.py。

## 開機時間實測(2026-10-20,v4 卡 --boot-markers,shell reboot = 重新載入韌體映像)
| 路徑 | loader 完成(開機起算) | 備註 |
|---|---|---|
| 一般 AutoRun(--splash --instant,無 FS3)| 3.63–3.68 s ×3 | 動畫段夾帶 88 行引導程式 mem set |
| Fast Start 3 | 3.19–3.29 s ×3 | 動畫段只夾 30 行(其餘存設定區) |
| FS3 換 loader 後第一次 | 9.67 s | 一次性慢速路徑(逐行寫 loader) |
- LvStarted 約 1.9–2.0 s(原廠，改不到);每個標記約 9–12 ms。
- 兩版動畫指令完全相同(12 條 display,閃電俠縮短的版本兩邊都已套用);**FS3 的 ~0.45 s 效益來自少寫 ~58 行引導程式**(約 8 ms/行)。
- 之前「FS3 省 6 秒」是拿 FS3 首次慢速路徑比，錯誤;「10.7 s」是主機往返，作廢。
- 縮小引導程式已完成並設為 v4 預設(見下方 --slim 段落)。

## 旁證(2026-10-20,sigmafp-re-40 回報)
- sigmafp-re-40 在同一張 v4 卡上傳 \fpSup\IMXL.BIN(IMX410 Lab sup,v4 格式)重開機:LOAD.LOG `0A C504A080 IMXL.BIN`(3 claims),SHELL 正常、DONE。
- **載入位址 0xC504A080 = 快取別名(0xC5…)**→ v4 快取執行在真實 sup 上生效(SHELL 依設計仍在 0x45…)。
- 之後 IMXL.BIN 已刪除;卡上其他檔未動。

## 瞬間啟動(Fast Start 2)觸發實驗(2026-10-20,v4 nofs3 卡;每輪關機前在 cave 0xC072EFAC 放記號)
| 輪 | USB | 記號(映像保留) | 路徑 | loader 完成 |
|---|---|---|---|---|
| 1 | 插 | — | AutoRun | 3.64 s |
| 2 | 插 | 不見 | AutoRun | 3.70 s |
| 3a/3b | 拔(連撥兩次) | 3a 不見 | 3a AutoRun / 3b 瞬間 | 3b 1.43 s |
| 4 | 拔 | 在 | 瞬間 | 1.43 s |
| 5 | 拔 | 在 | 瞬間 | 1.43 s |
| 6 | 插 | 不見 | AutoRun | 3.70 s |
| 7 | 拔 | 在 | 瞬間 | 1.44 s |
- **觸發 ⇔ 映像保留**(記號在);失敗都是韌體映像被重新載入 → **換 hook 位置無效**。
- USB 是主要因素(拔:4/5 觸發;插:0/3),但使用者經驗是插著也不一定冷開機 → 非唯一因素。
- 瞬間啟動 loader 完成 1.43 s,**早於 LvStarted(約 1.56 s)**;FS3 3.2 s;一般 3.65 s。
- 待查：關機路徑中決定「下次重新載入映像」的條件(PowerOffMgr / PMIC),看能否提高保留率。

## 縮小引導程式(--slim)上機(2026-10-20,LOADER 18a9271e,AutoRun 591e93f9,--splash --instant --boot-markers --slim,無 FS3)
- 一般冷開機 ×3:loader 完成 **3.47 / 3.54 / 3.54 s**(原本 3.63–3.68)→ 快約 130 ms(預估 140)。動畫段 S2→S3 791–801 ms(原 950)。
- 瞬間啟動(拔 USB 撥開關):觸發，loader 1.44 s;hook 改指向 BIN 內 lhook stub(C03DA420=0xEB0D4ED4);記號保留。
- **0x2D000280 bit0**:冷開機 ×4 皆 0(0x37042730),瞬間啟動 1(0x37042733)→ 證實 IPL 只看這個位元(notes/IMAGE_RETENTION.md)。
- 插著 USB 開機時：喚醒原因 0x2D000308/30C = 0/0;關機管理器 +08 = 0(與「+08 = USB」推論不符，可能只在關機當下才設);[C31D848C] = C0023B60 ✓,+0x230 = 1。

## 關機記錄器上機(2026-10-20 06:2x,LOADER 8948d108 --pwroff-log)
- 早期記錄(設定區 +0x210)**三次都沒有**(插 USB 冷開機 ×2、拔 USB 瞬間 ×1)。設定區記號(+0x27C=0x5EED5E77,關機前寫入)插 USB 冷開機後仍在
  → 設定區在**我們的關機回呼之前**就存 flash、開機再讀回 → 早期記錄的設計不成立(回呼裡寫的會被蓋)。
- 關機物件有註冊：兩個 XC_PowerOffMgr 清單都有 0xC4F23D9C(快取別名)。
- **晚期記錄(cave 0xC072E100,拔 USB 瞬間那次)**:否決回呼 C0023B60 回 0、0x2D000300..30C 全 0、+0x230=1 → 送 0x10 → 瞬間啟動。符合推論。
- 插 USB 的原因仍未知(冷開機留不住晚期記錄)。改走：離線讀懂否決條件(obj->vt[+0x10]、C0024878)→ 找可安全直接呼叫的唯讀 getter,在插 USB 時直接問。

## fast-USB-reboot 開關上機(2026-10-20,LOADER 99ab85ee)
- 事先講好的標準 1(插 USB 時三條件):條件 1 成立、條件 3(VBUS=1、外部供電=1、busy=0)成立;條件 2 只讀到 TargetConfig +0x10=0(第一道檢查未決，後兩道需呼叫未證實無副作用的建構子，未測)→ **未決**。
- 開關 on + 插 USB 撥開關 ×1:**仍冷開機**(bit0=0、cave 記號清掉、開關被清)。使用者：關機時**沒亮充電燈**。
- 結論(實測):「否決回呼是插 USB 冷開機的原因」**未被證實**;RAM 記錄隨冷開機消失，無法區分「包裝沒跑 / 條件沒對上 / 走別條路徑」。
- 下一步：關機回呼把記錄寫進卡上 \fpSup\PWROFF.LOG(--pwroff-file),冷開機也讀得到。
- fastreboot.py:修正一次讀 980 字會失敗(改 64 字分段)。

## 關機寫卡記錄(--pwroff-file,LOADER 72a67403)上機(2026-10-20 07:1x)
| | 插 USB(FUSB 開) | 拔 USB |
|---|---|---|
| 關機回呼有跑 | ✅ | ✅ |
| **reason** | **3** | **1** |
| mgr+0x60 | 3 | 1 |
| 外部供電 | 1 | 0 |
| 0x2D00030C | 0x400 | 0x600 |
| 結果 | 冷開機 | 瞬間 |
- **實測結論：決定因素是關機 reason 3(插 USB 時)**;reason 3/4/6 走 mode 2 寫 0x20,不經否決回呼 → fast-USB-reboot 的「改否決回呼」做法無效。
- 喚醒原因非 0 在拔 USB 時也有，仍瞬間啟動 → 不是決定因素。
- 下一步(離線):查 reason 3 的來源與語意、改開關做法(reason 3→1 或 0x20→0x10);查原生 shell `poff`/`reboot`/`rebootf` 能否代替撥開關。

## ★ 免碰相機的瞬間重開：shell `poff N`(2026-10-20 實測，插著 USB)
- `poff`(無參數)= 立即關機(reason 1):使用者撥開關開回 → 瞬間(bit0=1、記號在)。【誤觸：本想看說明】
- `poff 5`:reason 1、mgr+0x08=1(鬧鐘喚醒)→ **5 秒後自己開機、瞬間啟動、記號在**,完全不用碰相機。
- 主機工具 `fpSup/fp_usb_shell/fastreboot.py now [--wake 2]`:poff + 等待 + 重連 daemon + 驗 bit0。實測 **7.4 s**(主機端、含 2 s 鬧鐘),loader 1.79 s 完成。
- 對照：插著 USB 撥電源開關 = reason 3(與 shell `reboot` 相同)→ mode 2/0x20 → 必定重新載入映像。fast-USB-reboot 開關改的是否決回呼，不在這條路徑上 → 無效(已實測),保留作紀錄。
- 結論：不需要改 loader 的關機行為;開發時用 `fastreboot.py now`。
- sigmafp-re-40 實測:`fastreboot.py now` 後**感光元件會重置**(imager testpattern 寫進 0x02B2 後消失),LOAD.LOG 正常(IMXB+SHELL),主機來回約 10.3 s。→ DRAM 保留，但感光元件重新上電。
