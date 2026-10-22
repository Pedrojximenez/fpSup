# 2026-10-12：RES-Custom 位深由 RCD 宣告

已將可用位深移到各 RCD／producer 的配方。RES-Custom 驗證、編譯與套用宣告，
不依解析度名稱、SD／SSD 自行決定開放的 bit。**本輪僅離線建置及模擬，未操作相機、寫實體卡或發布。**

## 契約與行為

- RCD1 wire 保持 v3，Virtual RCD ABI 保持 2。新增 required section 13 `SEC_BITDEPTH`：
  一個 little-endian u32，bit 0／1／2 分別為 8／10／12-bit，有效 mask 1–7，MINCORE 至少 4。
  consumer core 4、consumer／Res Lab payload header v18。
- OG2K、OG3K、S16、OG35K、OG4K 的 producer 各自宣告 `(8, 10, 12)`；Res Lab 的 Apply／SAVE 輸出也宣告三種位深。
  可改為所需子集；consumer 不辨識格式名稱或 producer id。
- 兩份原生 bit CSV 的自有複本依活動 RCD 反灰。原生 quality normalizer 保留已允許的請求，
  不允許時採原生選單順序的第一個已允許位深；picker 不接受配方未允許的位深。
- 位深與格率分類在切換配方後一起重算。宣告 policy 的配方使用實際 picker entries 決定 FPS，
  避免原生媒體／位深分類把配方提供的格率反灰。切回原生解析度或 MOV 時恢復各 CSV 的原值。
- **未宣告 section 13 的舊 RCD 仍沿用原生限制。使用新規則需搭配新 consumer 和重新產生的 RCD。**

詳細 wire 與相容性見 [共同 RCD 契約](../../../open-gate/build/res-custom/VIRTUAL_RCD.md)。
各檔案的 mask、MINCORE、大小與雜湊見 [RCD 宣告核對](rcd-policies.json)。

## 新落點與還原

| 原生落點 | 作用 | 核對的原廠指令 |
|---|---|---|
| `C04A13E4` | bit-depth exclusion provider 的結果 | `mov r0,r1`，`E1A00001` |
| `C00A7FFC` | quality normalizer 的結果；r7 是原請求、r3 是原生判定 | `mov r0,r3`，`E1A00003` |

兩個 hook 使用共用 loader 的 claim／chain／journal，C 呼叫前將 SP 對齊 8 bytes。
builder 明確檢查兩個原廠指令；shims 在兩個座標建置後逐位元組一致。
原廠 CSV、sensor／recording tables 維持原值，活動複本與狀態由 consumer 常駐區塊擁有。

## 離線驗證

| 範圍 | 結果 |
|---|---|
| 既有 `test_v3_rescustom` | 65 項已核對，含全套執行與失敗項目的聚焦重跑，詳見下段 |
| 新增 `test_rcd_bitdepth` | 7 項通過：全部 7 種非空 mask、兩份 CSV、原生 SD／SSD quality 流程、legacy、損壞 section、失敗還原、ABI、突變 |
| OG35K／OG4K picker 與 canvas | 96 組通過：8 個正常／crop keys × 3 位深 × 2 配方 × 2 模擬媒體條件 |
| 真正 ARM `uia_apply`，`test_virtual_rcd_rates` | 2 項通過；靜態 RCD、Res Lab Apply、另一 producer 的 12-bit-only 配方與離開時還原 |
| `test_virtual_rcd` + `test_v3_reslab` | 完整 37 項通過，2031.348 秒；包含新 section 的匯出／完整讀回、載入與暖開機還原 |
| 成品 boot／entry／journal | normal、debug、Fast debug 三種通過；兩個產品返回、五份靜態 RCD 與動態 Apply、位深複本、journal、關機還原、ABI |

首次完整 consumer 回歸為 60 通過、5 失敗。四項是宣告 policy 後的 FPS 行為及新增 bit CSV
需要更新原測試預期，修改後聚焦四項與新增六項一起重跑通過（10／10）。
另一項仍預期已撤回的 engine60 試驗；用本次修改前的原始測試與 exact v17 BIN
（SHA-256 `5d4ff35675ef6e3e2c470fefe2780bbecbf3ef19dbc4de2028d03bb8f3c2224b`）重跑，
確認同樣失敗。更新為既有 239.76 cadence 的預期後該項通過；該預期修正沒有改動既有 FPS timing／cadence 計算。
證據見 [修改前重現](baseline-stale-test.json)。完整原生 quality 函式的新增第七項另行通過。

兩個突變只在模擬器內移除 bitclass／bitnorm hook，並清除 translated-code cache：
SD 原生反灰與 12→8-bit 判定重新出現，兩個行為斷言均偵測到錯誤。
正常／debug／Fast 成品的實際位元組、檢查與雜湊見 [開機驗證](boot-variants.json)；
可用 [重現程式](verify_boot_variants.py)重新檢查 final 目錄。
上述 unittest 共 111 項完成核對，另有三種包裝的 exact-artifact 開機案例。
彙整結果見 [測試摘要](test-results.json)。

native quality 兩個完整函式、shims、consumer、loader 及真正的 UI installer 有實際 ARM 執行。
媒體、原生 getters、GUI 物件、OS／儲存邊界由 fixture 模型提供；這些結果不能當成 SD／SSD 的實錄或持續寫入能力驗證。
Unicorn 在此 macOS 的 sandbox 內無法配置執行記憶體，以上模擬經自動審查允許後於 sandbox 外執行，仍未連接相機。

## 成品與交接

| 成品 | 大小 | SHA-256 |
|---|---:|---|
| [獨立 consumer](final/standalone/32RESCUS.BIN) | 183,936 B | `214b33cf01a8d5e8932107108bcbbe9fea3860827ca12c3defa08c0889899f11` |
| [Virtual RCD consumer](final/virtual-card/fpSup/32RESCUS.BIN) | 187,456 B | `394c49780cf25a2086e599274e3b2a9162e8dd189b265ca1efcae43fadd45592` |
| [Res Lab producer](<final/virtual-card/fpSup/50RES-Lab v0.1.0test.BIN>) | 609,720 B | `19491eb0b4a8798ddf145cf73c2704558f1caee82d07dfd8f74da384a4138d00` |

五份 RCD 在 [standalone/RESCUS](final/standalone/RESCUS/)；三種 Virtual RCD 包裝也各自包含同樣的五份 RCD。
[normal](final/virtual-card/)、[debug](final/virtual-debug/)、[Fast debug](final/virtual-fast-debug/) 使用相同產品 BIN。
normal／debug 的 AutoRun 與共用 LOADER 相同；同一 loader 配置換 payload 不需要更換 AutoRun。
Fast debug 由現行 `build_v3.boot_card(instant=True, fast=True, allsups=True)` 一起產生 coherent AutoRun／LOADER，
只供本輪離線開發驗證；若上機會使用持久化 bootstrap 設定，本次沒有部署。

建置使用 `build_v3_rescustom.py --out NEW_DIRECTORY` 與
`build_v3_reslab.py --virtual-rcd --card --no-shell --out NEW_DIRECTORY`。
debug 加入同一共用 builder 的 shell，Fast 使用同一 builder 的 coherent pair；未手工拼接載入鏈。
final 每份 `build.json`／`MANIFEST.sha256` 已核對，與測試用產品 BIN、AutoRun、LOADER 相同。
來源前後雜湊及修改範圍見 [來源核對](source-changes.json)，source-before 保留原始檔案。
本輪未修改共用 loader／AutoRun 原始碼及凍結發行品；未 commit、push 或發布。
