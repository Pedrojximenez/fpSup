# 2026-10-09 — 共用 Virtual RCD FPS 列與反灰修正

**反灰／選取修正已部署並通過實機核對。240／280 的完整錄影驗收尚未完成。**
最新候選為 [v9 普通卡](../../cards/20261009-virtual-rcd-v9/plain/)與
[v9 debug 卡](../../cards/20261009-virtual-rcd-v9/debug/)。Res Lab 與 res-custom 仍是兩個獨立 Sup，
所有產生器共用同一個 Virtual RCD 服務與 Custom 解析度列。

## 已定位並修正

1. res-custom 原本對六份 FPS CSV 各做四次 CSV_ADD，需要 24 個 returned slots，
   共用 UI installer 只有 8 個。實機 `VR_UI=0 / VR_WHY=23`，因此 240／280 未安裝。
   改用同一筆交易替換六份完整 CSV，各新增 NO 10..13；共用 installer 的容量與 ABI 保持原樣。
2. Res Lab 的 rate-canvas 首筆 rank 0 萬用項遮住後面的 exact 高 FPS 項，令 `+0xB0` 留為 0。
   改成 exact 100／119.88／239.76／279.72 在前，rank 0 的低 FPS fallback 在最後。
3. 已套用的 Virtual RCD 仍沿用原廠 FHD／媒體的 CSV 禁用旗標及 normalizer 上限。
   現在共用 consumer 依作用中配方的實際 entries 決定可選 FPS：提供項為 `1,2`，缺少項為 `0,0`。
   normalizer／列表分類依最快提供項的原生 enum 重算，虛擬 FPS 使用 backing enum。
   只有已成功 Apply 的活動 Virtual RCD 才使用此規則；切回普通解析度恢復原廠各分類旗標。
   磁碟 RCD 保留既有規則。判斷不依賴 Res Lab provider id。

## 精確成品與寫入

| 檔案 | Sup version | 大小 | program SHA-256 |
|---|---:|---:|---|
| 32RESCUS.BIN | 4 | 76,288 B | `5d0699f05aac9679765b953cc79a2e2b0ebfcf48f22dfa020df27b0466d5547a` |
| 50RESLAB.BIN | 6 | 452,448 B | `c910f4334cd930f130454da58083079fa89aac5c23bc0d6c5a0d11c079f19687` |

兩者 plain／debug 產品 BIN 相同。v8 已寫入 consumer／producer；v9 只再更新 consumer。
寫入前完整備份原 consumer，保留 file+32..128 的 96 B 設定並驗 FNV。
v9 實際 installed SHA-256 為 `27eb17f7a8d2165d78b0aad6046981c911a38a3d25706d778ff9633af0ef56b7`。
見 [成品核對](v9-artifact-proof.json)、[完整寫入讀回](v9-deployment.json)。
最後 [九份檔案稽核](../20261009-oncamera/v9-final-audit.json)全部通過：
兩個產品程式、原有 AutoRun／Loader 與五份磁碟 RCD；設定紀錄另按其合法所有權核對。
未改寫原有 AutoRun、Loader、其他 Sup 或磁碟 RCD；未 commit／push／發布。

## 離線 ARM 證據

- [真實 UI installer 與整合案例](v9-real-ui.log)：1 項整合測試通過，33.989 s。
  此 fixture 不以替身跳過 `uia_apply/ui_pool`，實際安裝六個解析度列與六份 FPS CSV。
  M12／M9 × Settings／QS 兩個原生回呼 × 239.76／279.72，共 8 組提交、picker、時序與高 FPS 畫布驗證；
  各種 incoming 原廠分類、M98 不支援高 FPS 的反灰、返回普通 FHD 的恢復也逐項斷言。
- [舊版反灰缺陷](v8-grey-regression.log)：相同測試在 v8 的 normalizer 斷言失敗，仍返回原廠較低上限。
- [完整 consumer 回歸](v9-core-full.log)：65 項通過，377.187 s，包含靜態格式／普通解析度原有反灰。
- [v6 真實安裝失敗](before-real-ui.log)：`VR_UI=0`；[v7 高 FPS 旗標失敗](after-real-ui.log)：`+0xB0=0`。
  兩者為保留的失敗證據，不是通過結果。
- v8 的 [5 項核心 FPS 回歸](core-rates.log)與 [5 項 Virtual RCD 回歸](v8-virtual-regression.log)亦保留。

## 原生選單與實機狀態

SIGMA fp Ver.5.02；從 Res Lab FILTER 選 239.76+，MODES 選 M12，OUTPUT 原生 Apply。
輸出 992×662；同一 Custom 列 index 5／current 6，generation 1，總解析度列數 6。
見 [原生 Apply 前後一致性](../20261009-oncamera/apply-v9-m12-high-fps.json)。

| 原生操作 | GUI row／虛擬 rank | backing enum | 引擎 FPS | 時序 cycles @72 MHz | 結果 |
|---|---|---:|---:|---:|---|
| 選 239.76，關閉選單 | 9／23976 | 7 | 239.7602386 | 300300 | 可選，提交計數 1 |
| 選 279.72，關閉選單 | 10／27972 | 7 | 279.7202759 | 257400 | 可選，提交計數 2 |
| 改回 29.97，再切普通 FHD | 3／0 | 3 | 不採用舊虛擬 latch | 不適用 | FLAG／current=0，EXCL 恢復 4 |
| 回 Custom，保持 29.97 | 3／0 | 3 | 原廠 nominal 30 | 2402400 | FLAG=1／current=6，EXCL=0 |

引擎 FPS 與時序是實機 RAM 的配置核對，不能替代實際影格間隔的量測。
退出 Custom 後的舊 FPSLATCH／LAST_ENT 不代表原廠錄影配置。
見 [240 配置](../20261009-oncamera/fps-v9-240-engine.json)、
[280 配置](../20261009-oncamera/fps-v9-280-engine.json)、
[普通 FHD](../20261009-oncamera/fps-v9-stock-fhd.json)、
[最後 Custom／29.97](../20261009-oncamera/fps-v9-final-2997.json)。

畫面證據：
[v8 的 239.76 反灰](../20261009-oncamera/screenshots/1589-v8-high-rate-grey.jpg)、
[v9 的 239.76 可選](../20261009-oncamera/screenshots/1591-v9-240-selectable.jpg)、
[v9 的 279.72 可選](../20261009-oncamera/screenshots/1595-v9-280-selectable.jpg)、
[普通 FHD 的 100／119.88 重新反灰](../20261009-oncamera/screenshots/1597-v9-stock-fhd-grey-restored.jpg)。
期間開錯的格式／Lossless popup 都取消，未提交其他格式或啟用 Lossless。

## 錄影發現與驗證邊界

239.76 的一次完整 MOVON／MOVOFF 啟動脈衝產生新片段 **A001_008**。
第一秒後的狀態讀取已為待機，未觀察到 `is_recording=1`，因此沒有重播停止 toggle。
原生錄影 log 的 req_cnt／fin_cnt 均為 94，rec factor／ui factor 均為 Nothing。
本輪沒有確認提前結束的原因，也沒有完成可控持續啟停。
見 [啟動觀察](record-v9-m12-240.log)、
[保留的觀察紀錄](../20261009-oncamera/record-v9-m12-240.json)。

只讀取已知新片段的首幀標頭，未列出 clip 內部檔案或刪除任何素材。
[首幀](../20261009-oncamera/A001_008-first-frame-header.dng)為 12-bit、raster 1008×672、
DefaultCropSize 992×662，但 **FrameRate=120000/1001**。
原廠 `FUN_c00c9bd0` 在 `out/decomp/full/blk_c00.c` 從錄影設定快照 `+0x14` 的 case 10 寫出此有理數，
`FUN_c00c9628` 等 metadata 流程使用它填 DNG tag 0xC764；本版沒有修改這條標記路徑。
實機虛擬 rank、picker entry、引擎 FPS 與配置的感測器時序仍保持 239.76。
這些證據不等同於已量得每秒 240 張乾淨影格，DNG 標記也尚未跟隨虛擬 FPS。
280 未錄影；其他模式、位深、長錄、全影格內容與十次實際電源暖開機未在本輪驗收。

v9 重開後遇到 macOS PTP 的 ACCESS 佔用。僅釋放實際確認的 SIGMA interface 0 佔用者，
使用者確認「螢幕正常，USB 已重新接好」後恢復；不能將 ACCESS 記作相機凍結。
最後九份讀回完成且 `is_recording=0`。相機留在 **Custom／M12／992×662／12-bit／29.97 待機**。
