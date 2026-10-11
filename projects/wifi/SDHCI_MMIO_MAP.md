# SIGMA fp Ver.5.02 — SD host controller 靜態定位

反編譯來源：`out/decomp/full/blk_*.c`（47,156 函式全覆蓋）
影像：`out/MAIN_c0000000.bin` @ `0xc0000000`、`out/seg1_c2ef6e00.bin` @ `0xc2ef6e00`
日期：2026-09-20

---

## 1. 結論先講

| 項目 | 值 |
|---|---|
| 控制器型態 | **標準 SDHCI**，Host Controller Spec **v4.0**（Host Version 4 Enable 有開） |
| 通道 0（內部 MMC/eMMC） | 控制器 id `0x0B` → MMIO base **`0x21A00000`** |
| 通道 1（可換式 SD 卡槽） | 控制器 id `0x0E` → MMIO base **`0x28A00000`** |
| 命令暫存器 | `base + 0x0C`，寫入值 = `(SDHCI_CMD16 << 16) | XFER_MODE16` |
| 參數暫存器 | `base + 0x08` |
| **CMD48 / CMD49 / CMD56** | 驅動的 data-command 分派器**明確列舉並處理**（見 §5） |
| 韌體實際發過的命令 | CMD0–CMD55 標準集，**從未發過 CMD48/49** |

## 2. base 位址怎麼來的

```c
/* FUN_c01f12e8 @ c01f12e8  —— id -> MMIO base */
undefined4 FUN_c01f12e8(int id)
{
    if (id == 0xb) return 0x21a00000;
    if (id == 0xe) return 0x28a00000;
    return 0;
}
```

這支在整個韌體只被 SD 驅動呼叫（`blk_c06.c` 內 414 次，其他檔 0 次），
是 SD/MMC 專用的 base mapper。

通道 → id 的對照表在 seg1：

```
DAT_c2f2e740[] = { 0x0B, 0x0E }     // 通道 0, 1 的控制器 id
DAT_c2f2e90c[] = { 1, 0 }           // 1 = 走 CMD1 (MMC), 0 = 走 ACMD41 (SD)
```

所以 **通道 1 / id 0x0E / base `0x28A00000` 就是使用者插卡的那個 SD 槽**。
`FUN_c0665c18 @ c0665c18` 的初始化狀態機用 `DAT_c2f2e90c[ch]` 分流：
`==1` 走 `FUN_c0666488(0x40FF8000)`（eMMC CMD1，sector mode OCR），
`==0` 走 SD 的 ACMD41 迴圈。id `0x0E` 另有專屬初始化 `FUN_c0663c50()`
與額外的 clock-stable 重試迴圈。

目前通道由全域 `_DAT_c381b4c0` 決定，只能是 0 或 1：

```c
/* FUN_c066c550 @ c066c550 */ bool set_channel(int ch) { if (ch <= 1) _DAT_c381b4c0 = ch; ... }
/* FUN_c066c538 @ c066c538 */ int  get_channel(void)   { return _DAT_c381b4c0; }
```

周邊位址空間參考：GPIO / pinmux 在 `0x3008_xxxx`–`0x300A_xxxx`
（`FUN_c01f1318`、`FUN_c01f13d0` 直接操作 `_DAT_300a0004` / `_DAT_300a0008` / `_DAT_300807b0`）。

## 3. 暫存器圖（由驅動實際存取反推，完全吻合 SDHCI 標準）

| off | n | 標準名稱 | 韌體用法佐證 |
|---|---:|---|---|
| `0x00` | — | SDMA Sys Addr / **32-bit Block Count (v4)** | `FUN_c0669200` 在 v4 模式下把 block count 寫這裡 |
| `0x04` | 17 | Block Size(16) \| Block Count(16) | `FUN_c0669118` 寫低 12 bit = block size；上限取自 Caps[17:16] |
| `0x08` | 36 | **Argument** | `*(base+8) = arg` 緊接在每次發命令前 |
| `0x0C` | 9 | **Transfer Mode(16) \| Command(16)** | `FUN_c0668b70` 結尾 `*(base+0xc) = cmdword` |
| `0x10`–`0x1C` | 12 | Response 0–3 | CID/CSD 讀取、OCR 取回 |
| `0x20` | 9 | **Buffer Data Port (PIO)** | `FUN_c0669ac0` 讀 SCR 8 bytes，前置條件 `PresentState & 0x800`（Buffer Read Enable） |
| `0x24` | 34 | Present State | `&1` CMD inhibit、`&2` DAT inhibit、`&0x800` buf read en、`&0x10000` card inserted |
| `0x28` | 59 | HostCtl1 \| PwrCtl \| BlockGap \| WakeUp | |
| `0x2C` | 89 | ClockCtl(16) \| Timeout(8) \| SwReset(8) | `&2` = Internal Clock Stable、`\|4` = SD Clock Enable |
| `0x30` | 28 | NormalIntStat \| ErrorIntStat | |
| `0x34` | 22 | NormalIntStatEn \| ErrorIntStatEn | `\|= 0xC0` = Card Insertion/Removal |
| `0x38` | 126 | NormalIntSigEn \| ErrorIntSigEn | |
| `0x3C` | 67 | AutoCmdErrStat(16) \| **HostCtl2(16)** | `\|= 0x1000_0000` → HC2 bit12 = **Host Version 4 Enable**；`\|= 0x0400_0000` → HC2 bit10 = 26/32-bit Block Count |
| `0x40` | 10 | Capabilities[31:0] | `(caps>>16)&3` 取 Max Block Length |
| `0x44` | 18 | Capabilities[63:32] | |
| `0x54`,`0x58` | 5 | ADMA Error Status / ADMA Sys Addr | |
| `0x60`–`0x6C` | 9 | Preset Value（SDHCI 3.0+） | |
| `0xAC`,`0x110` | 8 | **vendor 擴充** | `*(base+0x110) |= 1` |
| `0xFC` | 5 | SlotIntStat(16) \| **HostCtlVersion(16)** | `(v & 0xFF0000) > 0x3FFFF` → Spec Version ≥ 4 才開 v4 模式 |

（`0x110` / `0xAC` 是 vendor 區。Socionext/Fujitsu F_SDH30 系列在 `0x100`+ 有 vendor
暫存器，加上韌體裡的 `MB86` 字樣與 `src/adjust/XactiProtocol` 路徑，**推測**是
Socionext 系 SDHCI IP —— 此點未證實，僅為假設。）

## 4. 命令編碼

`cmdword = (CMD_reg16 << 16) | XFER_MODE16`，其中
`CMD_reg16 = (index << 8) | flags`，`flags`：bit0-1 response type、bit3 CRC check、
bit4 index check、bit5 data present。`XFER_MODE16`：bit0 DMA en、bit1 block count en、
bit2-3 auto CMD、bit4 方向（1=read）、bit5 multi-block。

指令索引在 `bits[29:24]`，由 `FUN_c0668b70` 首行確認：

```c
cmd_index = (param_1 << 2) >> 0x1a;   /* == (param_1 >> 24) & 0x3f */
```

全韌體實際發出的 cmdword（掃描所有傳給 `FUN_c0668a68` / `FUN_c0668b70` 的常數）：

| cmdword | 命令 | cmdword | 命令 |
|---|---|---|---|
| `0x01020000` | CMD1 (MMC OP_COND) | `0x11 3a0010` | CMD17 READ_SINGLE |
| `0x02090000` | CMD2 ALL_SEND_CID | `0x123a0030` | CMD18 READ_MULTI |
| `0x031a0000` | CMD3 SEND_RCA | `0x133a0010` | CMD19 (tuning) |
| `0x061a0000` / `0x061b0000` / `0x063a0010` | CMD6 SWITCH | `0x171a0000` | CMD23 SET_BLOCK_COUNT |
| `0x071b0000` | CMD7 SELECT (R1b) | `0x183a0000` | CMD24 WRITE_BLOCK |
| `0x081a0000` / `0x083a0010` | CMD8 | `0x193a0020` | CMD25 WRITE_MULTI |
| `0x09090000` | CMD9 SEND_CSD (R2) | `0x2a1a0000` | CMD42 LOCK_UNLOCK |
| `0x0a090000` | CMD10 SEND_CID (R2) | `0x29020000` | ACMD41 |
| `0x0b1a0000` | CMD11 VOLTAGE_SWITCH | `0x333a0010` | ACMD51 SEND_SCR |
| `0x0cdb0000` | CMD12 STOP | `0x371a0000` | CMD55 APP_CMD |
| `0x0d1a0000` / `0x0d3a0010` | CMD13 STATUS | `0x101a0000` | CMD16 SET_BLOCKLEN |

**沒有 CMD48 / CMD49。**

## 5. 但是驅動認得 CMD48 / CMD49

`FUN_c0668b70 @ c0668b70` 的 data-command 分派器：

```c
idx = (cmdword >> 24) & 0x3f;
if (idx < 0x2a) {
    if (idx in {0x18,0x19,0x1a} || idx == 0x12 || idx == 0x11) -> data path;
    else -> LAB_c0668ca0 (non-data)
} else if (idx != 0x2a) {
    if (idx == 0x2b) -> data path;
    if (idx != 0x30 && idx != 0x31 && idx != 0x38) -> LAB_c0668ca0 (non-data)
    /* 0x30 / 0x31 / 0x38 落入 data path */
}
data path:  cmdword &= ~0xE;            /* 清 auto-CMD / block-count-en */
            if (dma_mode & 3) cmdword |= 1;   /* 開 DMA */
LAB_c0668ca4: *(base + 0x0C) = cmdword;
```

走 data path 的索引集合是
`{0x11 CMD17, 0x12 CMD18, 0x18 CMD24, 0x19 CMD25, 0x1a CMD26, 0x2a CMD42, 0x2b CMD43,
0x30 CMD48, 0x31 CMD49, 0x38 CMD56}`。

`0x30` = **CMD48 READ_EXTR_SINGLE**、`0x31` = **CMD49 WRITE_EXTR_SINGLE** —— 正是
iSDIO / SD 擴充暫存器存取命令，`0x38` = CMD56 GEN_CMD。
也就是說：**底層 SDHCI 驅動具備發 CMD48/49 的處理邏輯，只是相機上層從來不用。**

依這套編碼，iSDIO 所需的 cmdword 應為：

```
CMD48 READ_EXTR_SINGLE :  0x303a0010   /* R1, data present, 讀 */
CMD49 WRITE_EXTR_SINGLE:  0x313a0000   /* R1, data present, 寫 */
```

（`0x3a` = R1 48-bit + CRC + index check + data present；低 16 bit 的 `0x0010` = 讀方向。
與韌體自己的 CMD17 `0x113a0010` / CMD24 `0x183a0000` 完全同形。）

## 6. 發命令的四步驟 ABI

```c
FUN_c0668a68(cmdword)          /* 前置檢查：clock stable、CMD/DAT inhibit、card present；回 0 = 不可發 */
FUN_c0668cc0(0x000f0001)       /* 準備中斷遮罩 / 事件旗標 */
*(FUN_c01f12e8(id) + 8) = arg  /* 寫 Argument */
FUN_c0668b70(cmdword)          /* 寫 base+0x0C，正式發出 */
FUN_c0668d58(&status)          /* 等完成，回 0 = 失敗；status 內含 int status 影本 */
```

輔助：
- `FUN_c0669118(size)` → 設 block size（`base+0x04` 低 12 bit）
- `FUN_c0669200(count)` → 設 block count（v4 模式寫 `base+0x00`，否則 `base+0x04` 高 16 bit）
- `FUN_c0669ac0()` → PIO 讀 `base+0x20`
- `FUN_c066c550(ch)` → 切換通道

## 7. 從 USB shell 直接碰暫存器是可行的

`mem` 指令（top-level 表 `0xC0BAC14C` 第 34 筆，handler `c03fa2a8`）：

```
[usage]
  memory write                  : mem set [address] [data]
  memory read start_address     : mem get [start address,,]
  memory read start-end address : mem get [start address,end address,]
  memory read start-start+size  : mem get [start address,,size]
  memory save ...               : mem save [path] [start address,end address,]
```

`mem set` 實作 `FUN_c03fa010`：`*(int*)addr = data`（**32-bit 寫**），寫完自動回讀比對。
位址檢查 `FUN_c03f9dd8` **只驗 4-byte 對齊，沒有任何範圍白名單** ——
所以 `mem set 0x28A00008 ...` / `mem set 0x28A0000C ...` 可以直接打 SDHCI 暫存器，
`mem get 0x28A00020,,4` 可以讀 Buffer Data Port。

`sdcard` 指令（第 57 筆，handler `c040b4d0`，子表 `0xc0bc2660`）提供
`mnt` / `umnt` / `checkinit` / `sdmode` / `slot`，可以在實驗前後讓驅動掛載或卸載。

### 風險提醒

驅動有自己的 ISR 與狀態機，且 FAT 層隨時可能發命令。直接寫 `base+0x0C` 等於
跟驅動搶控制器。實驗前必須先 `sdcard umnt`，並確認沒有錄影／寫檔在跑；
命令發出後 Normal/Error Int Status（`base+0x30`）會被驅動的 ISR 吃掉，
狀態要從 `base+0x24` Present State 與 Response（`base+0x10`）自己判讀。

## 8. 下一步

1. **唯讀對照**：`mem get 0x28A00000,0x28A00120,` 與 `mem get 0x21A00000,0x21A00120,`
   各 dump 一次，插卡／不插卡各一組，確認 base 正確（Present State bit16 應隨插拔變化）、
   Capabilities 與 Host Controller Version 讀得到 ≥ 0x0004。
2. 確認 `0x28A00000` 是 SD 槽而非 eMMC（Present State bit16 隨插拔翻轉即可證明）。
3. 再決定 CMD48 要走「直接寫暫存器」還是「找到可被 shell 觸發的驅動入口」。
   前者不需要程式碼注入，但要先讓驅動閉嘴；後者更安全但需要能呼叫任意函式。
