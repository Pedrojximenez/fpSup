# M12240 記憶體容量檢查，2026-10-12

**確認存在 RAM 預算的設計缺口，但沒有證據可將前一段 119.88p 無回應直接判定為 RAM 耗盡。** 1016 個管理位置不等於可同時存放 1016 張影像；壓縮後檔案縮小，目前影格所持有的 RAW allocation 卻沒有跟著縮小。

## 本輪實測

相機重新開機，boot `12760957`，先確認 CINE 待機、writer flags 為 0、初始 96 個位置空閒。開機後的記憶體配置仍是 STILL_REC；因此沒有將這時約 518 MiB 的 RAW 數字拿來當 CinemaDNG 的容量。

以已通過的 M12240 29.97p／12-bit／LOSS ON 做一次 3 秒窗口試錄。A001_138：到達、要求、完成均 68 格，全部 RAW；正常停止、832／832 位置空閒，writer／registry／cookies 清空。未重做 119.88p 或 239.76p。

停錄後原生 `memmgr bufuse` 顯示 **MOVIE_REC_DNG (3)**：

| 區域 | 總量 | 當下使用 | 原生使用峰值 | 當下剩餘 |
| --- | ---: | ---: | ---: | ---: |
| USER | 30.00 MiB | 22.91 MiB | 22.91 MiB | 7.09 MiB |
| RAW | 708.12 MiB | 0 | 71.65 MiB | 708.12 MiB |
| RAW_SUB | 82.00 MiB | 0 | 0 | 82.00 MiB |
| C++ heap | — | — | — | 6.00 MiB，最大單塊亦約 6.00 MiB |

RAW_SUB 是 linked fallback，不能把它與 RAW 當成一塊连续配置，也不能把 YUV／JPEG 對 RAW 的連結重複算入容量。USER、RAW 與 C++ heap 各有用途，不能把它們全部相加當作某個分配器的自由空間。

數字是在停止後讀取原生使用量與峰值，並非錄影期間持續遙測。RAW 本段峰值遠低於其容量，且停止後 used=0，未見本段 RAW buffer 殘留；這不能代替已關電的 119.88p 當次證據。前一段 REC log 已清除，`rec log-out` 在本轮短錄前回覆 no data。

證據：`memory-check-standby.json`、`memory-usage-standby.json`、`memory-check-30p.json`、`memory-usage-after-30p.json`、`memory-audit.json`。

## 實際占用與公式缺口

本候選版整塊 LOSS 常駐區為 **5,971,968 B（5.70 MiB）**，包含程式、位置、registry、cookies 與 metadata rings，屬 USER 配置。1016 是管理容量上限，沒有預先配置 1016 張 RAW。

M12240 的一張 RAW allocation 請求是：

```text
raster = 1008 × 672 × 12 / 8 = 1,016,064 B
allocation = 0x15400 + align512(raster) = 1,103,360 B ≈ 1.052 MiB
```

LOSS 每段另持有兩個相同大小的 spare、91,136 B workspace 與 2,048 B 的第二條 codec table，合計請求 **2,299,904 B（2.19 MiB）**。這些數字尚未加原生 allocator 的 bookkeeping／實際取整；它們不是整個錄影流程的總占用。

`frame_hold.c` 的交換流程只是交換原始 frame 與 spare 的 handle／capacity；被交給 writer 的壓縮影格仍持有原大小的 allocation。copy-back 路徑亦不縮小原配置，不能用寫出的 DNG bytes 直接代表 RAM 用量。

目前 `slot_capacity.c` 的保守檔案下限為 163,520 B，一批 64 MiB 取 411 格，兩批為 822 格。如果這兩批位置都裝滿並保留完整影格配置：

| 條件 | 只計影格 allocation 請求 |
| --- | ---: |
| 822 張，兩批保守位置 | 906,961,920 B＝864.95 MiB |
| 832 張，低幀率初始 active count | 917,995,520 B＝875.47 MiB |
| 1016 張，全部管理位置 | 1,121,013,760 B＝1069.08 MiB |

即使暫時把 RAW 與 RAW_SUB 的名義容量合看，約 790 MiB 也小於兩批最壞需求，且尚未算 codec 與其他在途資料。因此現有位置公式只能證明**管理位置數**足夠，不能保證相同數量的影像都放得下。這是條件式最壞預算，不是聲稱本次曾實際排隊 822 張，亦不是證明實際影像會達到該壓縮下限。

現行 `card.c:test_readiness()` 忽略 reserved 參數、直接回傳測試用 readiness；`fpl_slots_prepare()` 檢查位置／registry／cookies 是否空閒，但沒有加入實際 RAW free bytes 或最大可用區塊檢查。這是應補正的實作限制。

反過來，以本次全 RAW 的實際檔案 1,095,168 B 計算，一批只需 62 格。若仍採兩批，加上 119.88p 與前一段 469,659 µs 預算的 57 格到達預留及 6 格管線／停止預留，四對齊後為 188 格；影格 allocation 約 **197.82 MiB**。這只是條件式容量估算，說明全 RAW 不必填滿 832／888 個位置才能達到 64 MiB，不能把最壞壓縮情境當作 119.88p 無回應的既定根因。若媒體持續寫不及，任何有限 RAM 仍可能最後耗盡。

## 另需驗證的存取效能

shared loader 以 `C001CF78(0)` 取得 USER／NonCacheBuffer block；`slots.pool` 直接置於此常駐區，沒有改用原生 descriptor 的 cached C++ heap。來源見 `fpSup/fp_usb_shell/v3/sloader.c`、`fpSup/lossless/native/slot_runtime.h` 及 `slot_runtime.c`。目前啟用的 pool pointer 也在已核對的 LOSS block 內。

歷史 `projects/open-gate/build/pooldepth.py` 與 `fpSup/opengate/HSW_DEVELOPMENT_STATUS.md` 已記錄過：高頻 CPU descriptor 放在 non-cache 區會拖慢高幀率與 USB worker。這提供一個具體的效能疑點；沒有在本輪量到 cache miss／CPU 時間，也沒有做 cached／uncached A/B，所以不能宣稱已證明這次故障根因。也不能直接切換位址 alias 或在線搬動有在途引用的 pool。

## 修正方向與本輪結束狀態

維持原廠 64 MiB 批次門檻與 STOPFX 獨立。下一步應把每個影格保留的 allocation bytes、RAW 可用量及到達預留一起納入容量／壓縮接收判斷；僅繼續增加位置，無法補上這個保證。同時應核對高頻管理資料的 cached 配置與讀寫成本。若要實際承諾兩批高度壓縮資料的容量，還需設計能釋放原 RAW allocation 的儲存方式，或限制壓縮接收以控制實際 RAM 用量；這些都需要獨立生命週期與實機驗證。

本輪只新增檢查紀錄，未改產品、記憶體分區、64 MiB 門檻或正式 merge。相機留在 **M12240 29.97p／LOSS ON／待機**，寫入已完成。
