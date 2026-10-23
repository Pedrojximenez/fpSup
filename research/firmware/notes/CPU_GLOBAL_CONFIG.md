# CPU 全域設定：沒有「一個開關讓整台變快」(2026-10-16，離線)

靜態核對 `out/seg0_c0000000.bin` 與 `out/IPL.raw`。沒有相機 I/O。

| 項目 | 結果 | 位置 |
|---|---|---|
| 核心等級 | 有 udiv 785 處、sdiv 346 處 → 支援硬體除法，是 Cortex-A7/A15 級，**不是 A9** | 例 `C00009E0` |
| 分支預測 | IPL 與 MAIN 都沒設 SCTLR.Z(bit 11)；但 A7/A15 上 Z 固定為 1(RAO)，不影響 | — |
| SCTLR | MMU 初始化把 M、C、I(0x1005)設成 1；IPL 另外設 I | `C000E8F8`、IPL `+0x164` |
| ACTLR | 只 OR 了 0x40(SMP)，其餘保留重置值(A7 的 L1 預取預設就開) | `C000E8EC` |
| 頁表 | 預設表 `C0725F38`，4 筆，supersection：`C0000000` 1 GB 與 `00000000` 256 MB 是 inner WBWA + outer WBWA；`40000000` 2 GB 是 non-cacheable 別名；`2E000000` 2 MB non-cacheable | `C000E7B0` |
| memcpy / memset | 標準 ARM libc 寫法(LDM/STM 一次 32 B、處理未對齊)，沒用 PLD 和 NEON | `C001510C` / `C0015058` |
| 原廠 profiler | 只有 `analyzer tskmon_*`(以任務為單位)，沒有 PC 取樣 | — |
| IRQ 進入點 | `C00014A0`：用 `C0010130` 取得 IRQ 號碼，到 RAM 表 `0xC30000AC + n*4` 找處理函式；被中斷的 PC 存在 IRQ 堆疊 | — |

## 結論

快取、MMU、預取、記憶體複製都已經是合理設定。要優化就得先找出熱點函式，所以下一步是做 **PC 取樣 profiler**。
做法是把 `0xC30000AC` 表裡 tick 中斷那一格換成包裝函式：記下被中斷的 PC 和目前任務，再跳回原本的處理函式。
這樣只改 RAM 的 4 bytes，不改程式碼，可以還原。tick 是哪個 IRQ 還沒確認，需要上機讀一次那張表。

已有的任務層量測：錄影時 CPU 滿載(見 `projects/lossless-sup/validation/20261012-early-dng-handoff/README.md`)。
待機時沒有專門量過。

## 快取維護函式(2026-10-16 補，靜態)

| 函式 | 動作 | 關中斷 | 直接呼叫者(ARM BL + Thumb BL/BLX) |
|---|---|---|---|
| `C000E91C` | **整個 L1+L2** clean+invalidate(set/way，level 0 與 1 都走) | IRQ+FIQ 全程關 | 58 |
| `C000E9B8` | 整個 L1+L2 clean(set/way) | 全程關 | 6 |
| `C000EA54` | 範圍 clean+invalidate(逐 line) | 全程關 | 8 |
| `C000EB28` | 範圍 invalidate | 全程關 | 3 |
| `C000EB90` | 範圍 clean | 全程關 | 9 |
| `C000EABC` | ICIALLU | — | 2 |

- 包裝函式 `C0500A68(addr,size)`：**size ≥ 0x2800(10 KB)就改做整個快取的 clean+invalidate**，小於才逐 line。
  有 L2 的情況下這個門檻很低：整個快取清一次要走過 L1+L2 所有 line，而且會把其他任務的熱資料全部趕出去。
  它被 `C0500AA8` 呼叫(7 處，c04f2b.. / c0500d.. / c0501...)。
  **⚠ 更正(同日):這條只在 PTP vendor 指令路徑上，不在錄影/待機常態路徑，不是熱點嫌疑**(見 PER_FRAME_CPU_PATH.md)。
- 範圍操作也是全程關中斷，大範圍時會造成中斷延遲。
- **還不知道的事**：各函式在待機/錄影時每秒被呼叫幾次、一次花多久(L2 大小要在機上讀 CCSIDR)。
  這是 profiler 或呼叫計數器要回答的事；在那之前不能宣稱它是熱點。
