# OG2K 3×3 + USB shell,Fast Start 2 開發卡(2026-09-26)

```
OG_TARGET=og2k OG_V3TAP=1 python3 projects/open-gate/build/build_og3k_gyro.py --dev-card --no-gyro \
    --fast --loader-hook --four-box-bar --loader-hook-mark 0xC072E040 --banner 'OG2K-3x3-FS2!' --out <this dir>
```

| 檔案 | sha256 |
|---|---|
| AutoRun.txt | `6135a5ae76943681…`(32768 B,112 指令) |
| fpSup.BIN | `b98f7e63c50c201e…`(32768 B,96 區段,entry 0x4BF4) |
| FPSUPUI/0–4.BIN | 與 `rawview-2026-09-25/fs2-20/FPSUPUI` 逐位元組相同 |

- 與上機驗證過的 `open-gate/build/og2k_v3tap_20260924/og2k-3x3-debug`(`9d93f1ea…`)比:
  **94 區段相同**(含 GTAB `0xC0732100` 76 B,3×3 兩群組),1 個 84 B 的 dest-0 launcher 因區段順序不同而異,stage2 不比。
- 沒有 072A;與 debug 卡同一份 3×3 配方(5/4/4 ↔ 3/2/2)。
- 螢幕是 four-box,**不顯示 banner**;辨識靠 `mem get 0xC0732100` = 3。
- 離線:`test_loader_hook` 15/15;`test_boot_entry_chain` 的 og2k-combined-fast-debug 通過,
  其後 catalogue-vs-direct 比對 AssertionError(網頁合成器層,與本卡無關,未追)。
- **未上機。** 第一次開機走慢路徑並重新種設定區(會覆蓋 rawview 卡種下的 fast loader)。

## 上機紀錄

- 2026-09-26 06:56 putfile 寫入(相機當時跑一般版 3×3 卡,hook 已是原廠 `0xEB0000CC`)。
  讀回:fpSup.BIN 前 32768 B 一致(卡上 61440 B,舊尾巴);AutoRun.txt 前 32768 B 一致(卡上 32772 B,尾巴 `###\n`,註解行無害)。
  FPSUPUI 0–4 卡上讀回與本目錄一致,未重寫。
- **慢路徑(拔電池冷開)**:LOAD_DONE_US 15.32 s,hook armed(`0xEB0D4E90` → loader+4 `0xEA00003F`),
  journal 62/62 與映像一致,runs=0;GTAB 3、M139 5/4/4。9 筆 journal 顯示 live STOCK?(未查,推測 four-box 結束後復原)。
- **Instant 路徑(拔 USB、電源開關重開)**:LOAD_DONE_US **1.54 s**,runs=2,journal 63/63 一致,banner 未畫;GTAB 3、M139 5/4/4。
  → 此卡兩條路徑都通過 [C]。
- 2026-09-26 測完(§7.60 A001_077–081),從 Mac 讀卡機把卡換回 rawview `fs2-20`(sha 與備份相同)。
  設定區仍是本卡種下的 loader:rawview 下一次冷開機走慢路徑重新種。
