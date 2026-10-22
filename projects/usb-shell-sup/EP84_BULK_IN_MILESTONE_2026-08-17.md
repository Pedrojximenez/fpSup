# SIGMA fp EP84 Bulk IN 里程碑

日期：2026-08-17  
硬體：SIGMA fp  
韌體：Ver. 5.02  
狀態：成功

## 成果

在保留原始 PTP interface 的情況下，新增 vendor-specific interface 1 與
EP84 Bulk IN。Mac 經由 libusb 成功收到完整 64-byte 測試封包：

```text
45 50 38 34 54 45 53 54 00 01 02 03 04 05 06 07
08 09 0a 0b 0c 0d 0e 0f 10 11 12 13 14 15 16 17
18 19 1a 1b 1c 1d 1e 1f 20 21 22 23 24 25 26 27
28 29 2a 2b 2c 2d 2e 2f 30 31 32 33 34 35 36 37
```

前 8 bytes 是 ASCII `EP84TEST`，其餘 pattern 全部正確。

## 根因與修正

先前 `FUN_c01e6b80(9)` 雖回傳 0 並取得 transfer resource 5，TRB 的 HWO
bit 卻一直維持 1，controller 從未消耗 descriptor。

根因是 late-added context 4 只更新 firmware shadow endpoint bitmap
`0xC31E398C`，沒有同步到實體 DWC3 endpoint-enable register：

```text
DALEPENA = 0x2100C720
EP84 IN physical endpoint index = 9
enable bit = 1 << 9 = 0x200
```

在 `FUN_c01e62a8(4)` 完成 mode-1 Bulk 初始化後執行：

```c
*(volatile uint32_t *)0x2100C720 |= 0x200;
```

再提交 context 4 的普通 Bulk TRB 後，host 即可收到 payload。

## 成功配置

- Composite interface 0：PTP
  - EP01 Bulk OUT
  - EP82 Bulk IN
  - EP83 Interrupt IN
- Composite interface 1：vendor-specific `0xFF`
  - EP84 Bulk IN
- Context：4
- Mode：1（normal Bulk）
- Direction：IN
- Endpoint number：4
- Physical command index：`(4 << 1) | 1 = 9`
- TRB control：`0x813`
- Payload length：`0x40`
- StartTransfer return：0
- Transfer resource index：5

## 成功使用的檔案

- AutoRun：`/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_PTP_EP84_BuilderHook_Test.txt`
- Bulk init：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_bulk_init.S`
- Bulk sender：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_bulk_context_sender.S`
- libusb receiver：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_libusb_read`
- libusb source：`/Users/dido/Documents/Codex/2026-08-16/4/ep84_libusb_read.c`
- 主研究紀錄：`PTP_EP84_RAW_STREAM_RESEARCH.md`

## 可重現流程

1. 拔 USB 與 SD，關閉相機。
2. 開機並等待 Live View 完整出現。
3. 啟動 `ep84_libusb_read`。
4. 插入含成功版 `AutoRun.txt` 的 SD。
5. 接上 USB，保持連線。
6. Receiver claim interface 1 後等待 40 秒。
7. Receiver 從 EP84 收到 64-byte `EP84TEST`。

目前測試為 RAM-only patch；重新開機可恢復正常狀態。

## 下一階段

新增 EP05 Bulk OUT，完成：

```text
Mac command -> EP05 Bulk OUT -> camera echo/dispatcher -> EP84 Bulk IN -> Mac
```

雙向固定 echo 成功後，再接入 firmware shell dispatcher，最後才替換為 RAW
frame producer 與 ring/double buffering。
