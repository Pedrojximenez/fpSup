# I-cache 同步：舊 stage1 的顧慮需要第二顆核心，而這份韌體看不到第二顆

2026-09-28，靜態核對 `out/seg0_c0000000.bin`（SHA-256 `aaa5208a…`，與現行 builder 使用的同一份）。**只讀映像；沒有相機 I/O、沒有安裝、沒有量測。**

## 問題是什麼

舊 [`focus/dfd` stage1](AF_PRIOR_HOOK_REVIEW_2026-09-28.md) 把自己的 live install 硬停，理由是：把 hook 程式寫進 cave 後，沒有證據顯示真正執行 `AfContinuousObserver` 的 context 會看到新程式。它指出 `C000EABC` 是 `ICIALLU`，**只對執行它的 context 生效**，而我們是從 USB shell task 呼叫的。

「只對執行它的 context 生效」這句話的實際含義要講精確：ICIALLU 作用在**執行它的那顆核心**的 I-cache。同一顆核心上換 task 不會讓 I-cache 失效變得無效——I-cache 是 per-core，不是 per-task。**只有在有第二顆核心、而 AF observer 跑在那顆核心上時，這個顧慮才成立。**

## 三項靜態證據

| 證據 | 結果 | 意義 |
|---|---|---|
| `C000EABC` 實際指令 | `mcr p15,0,r0,c7,c5,0` → **ICIALLU**（本地），後接 `dsb sy`／`isb sy` | 確認舊筆記對指令的判讀正確：不是廣播版 |
| 全映像掃描 **MPIDR** 讀取（`mrc p15,0,Rt,c0,c0,5`） | **0 次** | 沒有任何程式碼問「我是哪一顆核心」。SMP 作業系統不可能不讀它 |
| 全映像掃描 **PERIPHBASE**（`mrc p15,4,Rt,c15,c0,0`）／SCU 存取 | **0 次** | 從未初始化 Cortex-A9 的 Snoop Control Unit |
| 全映像掃描 **ICIALLUIS**（廣播 I-cache 失效） | 唯一一筆在 `C1307CC0`，反組譯後前後皆為亂碼（`rscshs`、`cdpeq p13`），**是資料不是程式** | 韌體從不使用廣播失效 |
| 韌體自己的 D-cache 維護 | 使用 **set/way**（`DCCISW`、`DCCSW`，搭配 `CSSELR`／`CCSIDR` 的層級迴圈） | **關鍵。** set/way 操作在架構上不會廣播，ARM 明確說明它在 SMP 下不足以維持一致性。原廠自己的程式就假設單核 |

`ACTLR`（`c1,c0,1`）確實被設了 bit 6（SMP bit，`orr r0,r0,#0x40`）。這在單核 A9 上也常見——它讓 D-cache 正確參與 cacheable shared memory 的行為——所以它不構成多核證據，本頁不拿它當任何一邊的證據。

## 結論

**執行這份映像的 ARM 核心只有一顆。** 因此從 USB shell task 呼叫 `C000E91C()`（D-cache 清到 PoU）再 `C000EABC()`（I-cache 全失效）之後，AF observer 之後取指所用的就是同一顆核心的 I-cache——沒有第二份可能過時的副本。舊 stage1 硬停的那個機制**在這顆機器上不成立**。

這也和維護規範一致：[SUP_BUILD_RULES](../../../fpSup/SUP_BUILD_RULES.md) §4 把 `C000E91C() → C000EABC()` 列為新寫入 ARM 程式首次執行前的**已驗證**做法，而 gyro v1.13.1 出貨時就是用它發布一段之後由韌體 power-off manager（完全不同的 context）呼叫的常式。

## 這頁沒有證明什麼

- **這是靜態證據，不是量測。** 沒有在相機上讀 MPIDR，也沒有觀察過實際核心數。
- SoC 裡可能另有核心（DSP／協處理器），但那些不共用這顆 ARM 的 I-cache，與本問題無關；也可能有第二顆 ARM 核心而這份韌體從不啟動它，結論相同。
- 不涉及 DMA 與其他匯流排主控的一致性：那是另一回事，由 [EP83 記憶體契約](EP83_MEMORY_MAPPING_2026-09-16.md) 管。
- 不表示我們寫進去的程式是對的，只表示它會被看見。
- **發布順序仍然必要**：先 D-cache 清出、再 I-cache 失效，順序反了無效。現行 `probe.publish()` 就是這個順序。

## 對計畫的影響

`arming` 的前置條件從「cache 同步未證明」改為「**已由單核證據排除；發布順序仍須維持**」。它不再擋住 hook 安裝。仍然擋住的是：測試卡尚未宣告 hook 接點的 4-byte 區段（[關機還原](AF_LOADER_CONVENTION_FINDING_2026-09-28.md)），以及 USB 自 9/27 20:30 起不可用。

重現：

```sh
python3 - <<'EOF'
import array, collections
rom = open('out/seg0_c0000000.bin','rb').read()
w = array.array('I'); w.frombytes(rom[:len(rom)//4*4])
for v in w:
    if (v & 0x0F000010) != 0x0E000010 or ((v >> 8) & 0xF) != 0xF: continue
    key = ((v>>21)&7, (v>>16)&0xF, v&0xF, (v>>5)&7)      # opc1, CRn, CRm, opc2
    ...                                                   # (0,0,0,5) is MPIDR
EOF
```
