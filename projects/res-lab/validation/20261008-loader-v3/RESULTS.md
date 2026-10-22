# res-lab loader_v3 遷移複核 — 2026-10-08

本次修改本機來源、建置及離線測試；沒有操作相機、寫實體卡、commit／push 或發布。

## 修改與架構

- `build_v3_reslab.py` 沿用既有 PIC 核心與 `rl_v3.c` entry；從專案根目錄建置時，分類階段在來源目錄組譯。
- `--card` 直接呼叫現行 `build_v3.loader_bin()`、`autorun()`、`splash_frames()` 與 `shell_sup()`。`--no-shell` 產普通卡；`--from-card` 僅選擇離線 shell 來源，loader／AutoRun／動畫仍由現行來源建置。
- `50RESLAB.BIN` 的最低服務版本為 3，與目前 uishare 的所有者查詢介面一致。FSB1 entry 回傳 KEEP／RELEASE，核心、選單及狀態都住在自己的區塊。兩原點 PIC 證明仍在建置時執行。
- claim 數與 journal 容量由目前 `sloader.c` 的上限檢查；來源 SHA-256 記在每張卡的 `build.json`，產物另有 `MANIFEST.sha256`。
- `sl_menu.c` 的 `SL_MENU_IN_BLOCK` 分支允許完整資料恰好填滿配置空間；宣告超長或不足標頭時先拒絕，才讀取 SLMP 欄位。舊 AutoRun 卡仍保留「讀滿可能截斷」檢查。
- `test_v3_reslab.py` 可用 `RESLAB_V3_CARD` 指向保存的卡片，執行其實際 AutoRun loader words、LOADER.BIN 及產品 BIN。真安裝器以模型 GUI 物件執行，既有替身只用來測試受控的安裝失敗分支。

## 建置

從完整專案根目錄執行：

```sh
python3 -B projects/open-gate/build/build_v3_reslab.py --card --no-shell --out projects/res-lab/cards/20261008-loader-v3/plain
python3 -B projects/open-gate/build/build_v3_reslab.py --card --out projects/res-lab/cards/20261008-loader-v3/debug
```

兩張卡同一份 `50RESLAB.BIN`：468,048 B，常駐塊 469,824 B，SLMP 365,392 B。
25 個核心 hook、10 個後期 hook、4 組 movw/movt 外部指標、1 筆資料指標 fixup，143 筆 PC 相對改寫。
297 筆 claim 涵蓋 19,132 B 原廠資料，journal（含各範圍標頭）21,508 B，小於 32 KiB。

| 檔案（普通／debug 相同） | SHA-256 |
|---|---|
| AutoRun.txt | `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0` |
| fpSup/LOADER.BIN | `41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c` |
| fpSup/50RESLAB.BIN | `3655a17fa4f65040c5bebe7b3d0fee6d1383b72121ff3d223f14966f5237345e` |

兩份 manifest 逐檔核對通過。debug 另帶當前 USB shell，普通卡不含 shell。
增減 shell 檔案不改 AutoRun 或 loader；相容的產品更新不加入 runtime 雜湊配對。

## 精確成品驗證

| 驗證 | 結果 | 證據 |
|---|---|---|
| 普通卡完整 v3 測試 | 21 項通過，0 skipped | [日誌](plain-tests.log)、[檔案身分與結果](plain-verification.json) |
| debug 實際 installer／picker／shell／關機 | 4 項通過，0 skipped | [日誌](debug-tests.log)、[檔案身分與結果](debug-verification.json) |
| 兩張卡整個 48 MiB 韌體映像／關機 | 各 1 項通過，0 skipped | [日誌](firmware-coverage.log)、[結果](firmware-coverage.json) |
| exact-fit 重新改成拒絕 | 測試失敗，確認抓到 | [mutation](mutation-exact-fit-rejected.log) |
| 移除短標頭前置檢查 | 測到宣告外的 SLMP 欄位讀取，確認抓到 | [mutation](mutation-short-header-read.log) |
| entry 注入未 claim 的韌體寫入 | 完整映像比較報出該位置，確認抓到 | [mutation](mutation-unclaimed-write.log) |
| 既有選單／模式 host 回歸 | 69 項通過 | [結果](menu-regression.log) |
| mutation 後對原 debug 成品重驗 | 4 項通過，0 skipped | [日誌](post-mutation-tests.log)、[結果](post-mutation-verification.json) |

測試涵蓋所有 claim 的原廠 journal、靜態補丁、146 個執行期字、核心／後期 veneer、
picker 找核心及回傳 profile 87、SLMP 直接從塊讀取且不重新開檔、49 個選單變數、
晚期 hook 與 B2_5 切頁、NBR 拒絕後回原頁、CHAIN page-id 套娃、claim 衝突、
cave 不足時 RELEASE、殘留 hook 修復，以及兩次關機寫回。
映像比較排除共用 loader／arena／交接區；其他改過的韌體字都在 journal 裡。
`0xC0730000..0xC0738000` 的舊佈局原廠資料逐位元組保持原樣。

Unicorn 在 sandbox 內 JIT 記憶體映射會因 SIGILL 中止；上述 ARM 驗證在獲准的
本機 sandbox 外執行，沒有相機連線。早先的 SIGILL 不列成通過測試。
三個 mutation 僅改臨時建置的 C 副本，沒有改壞或還原共用來源。

## 部署與實機界線

第一次從舊單檔卡切換需要同時更新 AutoRun，使用 `fpSup/LOADER.BIN`、
`fpSup/50RESLAB.BIN`、`fpSup/UI/`，debug 再放 `00SHELL.BIN`。
不要把新產品附加到舊根目錄 `fpSup.BIN`，也不要以舊 loader 的 0xF000 上限封裝。
本次未部署；首次上機應以同一目錄的完整成品追溯。

`og3krestore` 的設定服務、原廠配置器／檔案／快取／OS／變數註冊呼叫仍由模型替代；
shell 只驗 entry 建立任務與返回，沒有執行 USB worker 的硬體傳輸。
真實 UI、感測器、RAW14、音訊／時間碼、錄影、SD 關機時機、跨卡暖開機與 Fast Start
都不能由這些離線結果宣稱通過。res-lab 核心仍維持獨立；與其他解析度核心的互斥位置由 claim 拒載。
