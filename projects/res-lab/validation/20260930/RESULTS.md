# Sensor Lab：2026-09-30 離線驗證紀錄

本輪依使用者要求收尾，遵循 [`SUP_BUILD_RULES.md`](../../../../fpSup/SUP_BUILD_RULES.md)。
**沒有相機連線、實體寫卡、commit、push 或發布。** 上機前須先交接範圍。
目前完成的是離線修補與驗收準備；完整機上 mode 選單、條件反灰、逐段回放等仍未完成。

## 修改與問題定位

1. 原生 picker 的同次 config `+0x20` 是位深 enum。只接受已核對的三個返回點
   `C043B8D8/B908/B92C`，先同步 AXIS 再算配方，14-bit 的 BITLATCH = 1。
   payload 移至 `C0730740`，不與 aspect2／fps 重疊，沒有新增 hook。
2. 原 fmt 測試把 ENTRY 放在 RECIPE 的尾端，配方擴至 27 字後重疊。
   測試配置已修正並比對完整配方；交付產品原有獨立配置不受此測試缺陷影響。
3. 安裝器處理短批次讀取，寫後讀回不符會有限重試，最後一次寫入結果不明也回復。
   九個 AXIS 字加入可變狀態集合；同一版不因正常選單操作被誤判外來。
4. RAW14／240 納入主機選單；連拍資料率使用完整記錄矩陣。
   容量未知時不報格數／秒數；14-bit 暫依已知 16 bpp RAW 緩衝估算，CDNG packing 未驗。
5. 新 builder 封裝 2042 個產品字，加上 146 個執行期修改位址的原字宣告。
   stage2 在 entry 前將它們納入 journal；普通 148 區段、debug 158 區段。
6. 真正執行精確 BIN 時，發現 stage2 在呼叫端 SP 偏移 4 bytes 時違反入口對齊要求。
   共用 `stage2.S` 只增加保存 SP、對齊 SP、恢復 SP 三條指令，保留兩個 pass、
   `r0 = entry 自身位址` 和原入口順序。未改 loader、entries ABI 或 shutdown 架構。

## 通過項目

| 測試 | 結果 |
|---|---|
| `test_imx410_full.py` | 58/58 |
| `test_imx410_recipe.py` | 14/14 |
| `test_imx410_fmt.py` | 16/16 |
| `test_imx410_canvas.py` | 10/10 |
| `test_imx410_plan.py` | 39/39 |
| `test_imx410_load.py` | 27/27 |
| `test_imx410_menu.py` | 13/13 |
| `imx410_menu.py --sweep` | 2280 組，0 broken |
| 共用 `test_boot_chain test_loader_hook test_splash` | 29 項，0 skipped |
| `test_boot_entry_chain.py` | 14 建置、3 AutoRun 比較、8 catalogue references |
| `test_sensor_lab_card.py` | 普通／debug 各 12 項，另 2 組 payload-only 比較 |

七組 Sensor Lab 合計 177 項；各組 stdout/stderr 在同目錄 `.log`。
共用 suite 完整結果在 [`shared-loader.log`](shared-loader.log)。
OG 建置報告在 [`open-gate-entry-chain.json`](open-gate-entry-chain.json)，原始產物留於
`/private/tmp/sensor-lab-entry-chain-20260930-r2`；只呼叫 catalogue 的 `refs()`，未執行發布 main。
精確 Sensor Lab 產物與 manifest 在 [`../../cards/20260930-preflight`](../../cards/20260930-preflight/)。

精確卡片測試的 12 項：雜湊、入口 ABI、快取呼叫次序、146 字 runtime journal、
兩次關機回復、保留 cave 的暖映像、保存 CUSTOM 選擇、MOV guard、缺 BIN、
真實 RAW14 picker、journal 宣告突變、entry 對齊突變。
兩組突變直接修改測試中的 BIN 副本，不改交付 BIN 或共用來源。

執行環境：macOS 的 Python 3.9／Unicorn 2.1.4。Unicorn 在受限執行環境中
`emu_start` 曾以 SIGILL 結束，經核准改於非沙箱執行純離線模擬後成功；
未將崩潰當成測試通過。沒有以模擬結果宣稱已驗證硬體快取或實際開关機。

## 中途失敗與修正

- Sensor Lab plain 最初在實際 entry 因 SP 未對齊失敗，據此修共用 stage2；
  新增對齊／未對齊兩種呼叫端測試，並用刪掉 `bic sp,sp,#7` 的突變確認能抓到。
- debug 測試起初把 worker offset 加到固定 heap 起點，忽略 loader 真正的 read buffer。
  harness 改從 `F_READ` 的 r1 取得 staging base；worker stub 也核對 r0/SP。
- 整合測試最初在 catalogue source 比較失敗。差異是測試用舊文字橫幅配置對比
  catalogue 的四格配置（stage2 大小不同），非產品 payload 差異。
  只修 `test_boot_entry_chain.py`，讓 combined 比較加 `--four-box-bar`；
  沒有修改網站目錄、降低逐 byte 相等要求或覆寫 frozen release。全矩陣重跑通過。

## 重跑方式

```sh
# 在 projects/open-gate/build；每支含自己的 runner，不需 pytest
python3 -B test_imx410_full.py
python3 -B test_imx410_recipe.py
python3 -B test_imx410_fmt.py
python3 -B test_imx410_canvas.py
python3 -B test_imx410_plan.py
python3 -B test_imx410_load.py
python3 -B test_imx410_menu.py
python3 -B imx410_menu.py --sweep

# 在 fpSup/fp_usb_shell
python3 -B -m unittest test_boot_chain test_loader_hook test_splash

# 在專案根目錄；指定的目錄必須是新的
python3 -B projects/open-gate/build/test_boot_entry_chain.py --out /tmp/og-entry-new
python3 -B projects/open-gate/build/test_sensor_lab_card.py --out /tmp/sensor-card-new
```

`imx410_load.py --check` 會讀相機，**不是離線檢查**，本輪未執行。

## 精確檔案與相容性

| 成品 | SHA-256 |
|---|---|
| plain AutoRun.txt | `57845e1b8d422289167d7a29cdd9cdd4b453e82fc9b2b8513e624171d533910f` |
| plain fpSup.BIN | `9d155ef11dc8c20947163a0b944b437b7633ad8d088895713453ab82dcad5a4f` |
| debug AutoRun.txt | `5d5e31189e08e888d60df6ea85980d3b820d4536e33b3e82df359e641bec2b4d` |
| debug fpSup.BIN | `6033a8cc1daf35efc1b8a5f099d2e432d6d5fde887db0b79e648e1babf848f2c` |

每張卡的完整來源指紋與限制見各自 `MANIFEST.json`。修改 stage2 前後的 plain
AutoRun 已逐 byte 比較相同；換 AXIS 的 plain/debug 比較也相同，BIN 有變。
因此相容的 payload 更新只換 BIN，不加 runtime 雜湊或綁版要求。
首次安裝或切換普通/debug 仍使用該配置完整一組檔案。

## 限制與待驗收

模擬執行真實 loader/stage2/entries/restore/selector/picker；worker spawn、檔案、
配置、OS、快取服務、原廠 getter/setter body 及 inactive LV 為 stub。
相機上的模式選單／條件反灰與每段幾何回放仍未完成；RAW14、CRCT I0/I、
≥100 fps SSD、240 音訊／時間碼、未知容量、十輪不錄影開關機與跨卡暖啟動仍待驗。
本次不支援 Fast／多產品合併，也不保證可疊在搬移 sensor mode table 的產品之上。

原始修改前副本保留於
`archive/codex-worklog/sensor-lab-closeout-20260930/before/`，避免混同使用者原有變更。
