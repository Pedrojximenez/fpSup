# 透明四框載入畫面：離線候選

效果：暫停原廠 GUI 重繪，保留載入區以外的 UI；白色 fp、參考圖的桃紅 Sup、小方框由左往右填滿。
**沒有黑線／黑底。** 第四格只在載入完成後填滿，停留 2 秒，再還原並要求原生 UI 重畫。

維護入口：`../../../fpSup/fp_usb_shell/build_autorun.py --loader --four-box-bar`。
新模式需帶 `AutoRun.txt`、`fpSup.BIN`、`FPSUPUI/0.BIN`…`4.BIN`。
目前是 opt-in；沒有替換產品卡、發行品或網站的預設畫面。

## 最新修正：覆蓋整條上排

目前交付為 `full-top-row/fpSup-four-box-full-top-row-20260924.zip`。
使用者截圖指出右側時間/STBY/檔名殘留；第一幀現為1024×56，清整條上排。
後四幀仍176×56小圖，字樣大小／位置不變，下排UI保持載入前靜態畫面。
AutoRun仍98條；BIN及1..4幀不變。至少一起更新AutoRun及0.BIN，整包已附齊。
離線4項共用載入、9項畫面/ARM測試與3-buffer row-copy檢查通過，尚未上機。

`preserve-bottom/`、`restore-fix/`、`system-ui/` 等保留前一輪修正及歷史比對。

## 預覽與產物

- `previews/four-box-preview.gif`：實際 ARGB4444 圖檔的五階段動畫。深灰底只供展示，實際背景透明。
- `previews/four-box-preview.png`：完成狀態。
- `cards/plain`、`cards/fast`：**無產品 payload** 的共用載入链範例。
- `cards/debug`、`cards/fast-debug`：上述範例加 USB shell，不是 OG／gyro 完整產品卡。
- `staging/`：本輪已審閱來源與共用筆記；`original/` 是修改前快照。
- `validation/counts.json`、`validation/SHA256.json`：實際命令數與產物識別。

建置範例（在 fpSup 根目錄，輸出必須用新的本機資料夾）：

```sh
python3 -B fp_usb_shell/build_autorun.py --loader --no-shell --four-box-bar --out /tmp/fpsup-four-box/AutoRun.txt
# debug 省略 --no-shell；Fast 另外加 --store-boot。
```

目前第一張圖 114,688 bytes，其餘四張各 19,712 bytes；五階段各畫三次，總讀圖 567 KiB。
原生 osdfile 每次讀整份檔案，因此使用五張獨立小圖，避免反覆讀五幀合集。
三次繪製保留是為了既有三緩衝／非同步 present 的不確定性。

| 指標 | 舊 | 新 |
|---|---:|---:|
| 普通 AutoRun display | 31 | 20 |
| 普通 AutoRun 全指令 | 104 | 106 |
| Fast 命中 AutoRun 全指令 | 69 | 58 |
| Fast 全稿（含 fallback） | 169 | 142 |

上述 display 數不包含 BIN 裡直接呼叫的 3 次完成 frame；2 秒停留也刻意在載入時間戳之後。
普通版總指令**沒有減少**，因為新增明確的 D/I 發布與失敗還原。不能據此宣稱實機載入更快。

## 驗證

- 共用 `test_boot_chain.py`：4/4 通過。
- 新 `test_splash.py`：8/8 通過，含實際 Unicorn ARM 執行，無跳過。
  本機沙箱會阻擋 emulator JIT；完整模擬在沙箱外執行，firmware calls 全部是 mocks。
- ordinary/debug/Fast 關閉新選項時，AutoRun、BIN 與修改前逐位元組相同。
- 新模式下替換相容 payload 的內容／長度，AutoRun、圖檔不變；loader bytes 不變。
- 拒絕與 redraw word 衝突的靜態 payload section；確認原始韌體字為 E92D4BF0。
- 未上機、未寫卡、未啟停 daemon、未 commit/push、未發布。

模擬不驗證 LCD、SD 讀取速度、快取硬體或原生 GUI 佇列。成功路徑有 native clear/redraw；
BIN 失敗時 AutoRun 仍會還原 prologue／D/I／echo，但完整畫面更新要等原廠事件。
詳細來源、位址與未驗證邊界已併入研究筆記 `research/display/notes/BOOT_BANNER.md` §11。
