# isp-lab — ISP 路徑研究（2026-10-23 起）

研究工具，不是產品。和 imx410-lab 一起作為 RES-Custom2 的依據。
先讀：[notes/RESEARCH_PLAN.md](notes/RESEARCH_PLAN.md)（目標、檢查點、階段、分工）、
[notes/ISP_CAPABILITY_MAP.md](notes/ISP_CAPABILITY_MAP.md)（每一級的能力與待解）、
[notes/RESLAB_AUDIT.md](notes/RESLAB_AUDIT.md)（res-lab 結論哪些能用）。

## 工具

| 檔 | 內容 | 狀態 |
|---|---|---|
| `sup/`（ISPL.BIN） | DNG 錄進 DRAM：從 imx410-lab 的 IMXL sink 分出（來源 sha256 在 `sup/UPSTREAM.sha256`）。加了：取樣政策（先留 K 個 block，之後每隔一段時間留一個，其餘丟棄）、每個 block 一行紀錄、控制 task 自己按 REC 開始與停止（`FUN_c03D9C20` 執行 `key MOVON/MOVOFF`，同原廠 FUN_c0405ba0 的錄影腳本）。修了 IMXL 位址檢查在 0xC0000000 以上溢位繞回的 bug | unicorn 27 項。**⛔ 擱置（10-23）**：兩次上機錄影都停不下來（第二次連實體 REC 都停不了），見 [validation/20261023-ispl-take](validation/20261023-ispl-take/RESULTS.md)。isp-lab 改成不錄影為主 |
| `host/ispl.py` | ISPL 主機工具：`take`（借記憶體＋log、寫參數、最後寫 ctl＝armed，之後完全不送指令直到停錄後 10 秒）、`status`、`pull`（拆 DNG、block 紀錄檢查 seq 連續與帳目）、`disarm`。錄影判斷用原生 `status get is_recording`；配置器借用 `imxl.heap`（class 0） | 離線 8 項（寫入順序、arm 後靜默、錄影中拒絕、失敗時歸還記憶體、pull 拆檔與 log 檢查）；**未上機** |
| `host/rawpool.py` | 停錄後 RAW 區（class 10）裡還留著的 CDNG：probe（類別表與鏈）、scan（MEM1 讀整區、收下 DNG）、match（跟卡上檔案比 sha256）。錄影中、RAW 仍在用時拒絕 | 離線 6 項＋突變；**10-25 上機**：停錄後最後 14 幀與卡上逐位元組相同（[validation/20261025-rawpool-01](validation/20261025-rawpool-01/RESULTS.md)） |
| `host/bufa1.py` | 待機 BUFA1（RWZM 輸出）唯讀讀取 | **10-24 上機**：讀到 8-bit Bayer 2016×1344（[validation/20261024-bufa1-01](validation/20261024-bufa1-01/RESULTS.md)）；工具假設的 0xC31D96D4 在待機為 0，要改用 0x30182280＋1344×504 字 |
| `host/lcd.py` | LCD 影像層直取：讀三個原生輸出描述元、借一個唯讀 MEM1 窗口讀一格 ring、YUYV 解碼並自檢 stride。錄影中拒絕執行 | 離線 8 項；**10-23 上機通過**（CINE 待機 1620×911，[validation/20261023-lcd-01](validation/20261023-lcd-01/RESULTS.md)） |

```sh
cd host && python3 -B -m unittest test_lcd test_ispl
cd sup && python3 -B build.py && python3 -B -m unittest test_card     # 約 5 分鐘
python3 -B lcd.py decode RING.bin W H OUT.png     # 離線
python3 -B lcd.py grab OUT_DIR                     # 上機（先廣播相機使用權、通知使用者）
```

## 階段 0 還缺
- 讀哪一格最新：描述元 word 31 讀取中 1→3，疑似目前寫入格索引（待驗）；目前固定讀第 0 格。HDMI／EVF 接上時另外兩個描述元是否啟用待查。
- BUFA0 mux=1 參考 RAW：`imx410-lab/bufa_probe.py frame OUT --mux 1` 在一般 LV 可用（10-20 實測）；但待機是 MONIT 模式（mode 8），不是錄影模式（106/123…），要同模式參考得用 vmode 把錄影模式放到 host 10 再進放大。錄影中不能抓（韌體自己用 BUFA0）。凍結已查明（imx410-lab IMX410_RULES §70）：在幀中途停 BUFA0 會卡死匯流排；必須在相機上一次做完「清旗標 → 等下一次 BUFA0 完成 → 停」（`imx410-lab/sensor_read/bufa_stop.S`，bufa_probe.startstop 已改用），不能從主機分兩步。修正後的 300 次驗證待跑；isp-lab 若自己 arm／停 BUFA0 必須用同一停法。
- ~~ISPL 上機前要先證明：借出的記憶體跨錄影安全（用 class 0，不用 10）、非快取複製速度、控制 task 從非 UI 任務按 REC 能否開始／停止錄影、shell 執行器在錄影中被呼叫是否安全（strtok 不可重入）~~ → ISPL 擱置。
- 改成不錄影：查 BUFA1（RWZM 輸出）能否在待機手動開、用 imx410-lab 的安全停法抓。
