# 2026-10-13 回歸測試：快取別名＋預先準備 IFD（一般版 `0ba4cd52…`，卡上 `013cb0fd…`）

工具：
- `rec_case.py`：錄一段，收尾等 60 s，逾時回報 HANG；
- `../20261013-shared-header/cpu_take.py`：量 CPU；
- 模式切換：`../20261013-registry-scan/camera_ui.py`，每一步都有截圖 `../20261013-registry-scan/reg-ui-*.jpg`。

## 結果

| 項目 | 結果 |
|---|---|
| 舊腳本會不會用 DMA 讀快取位址 | 現役腳本中只有 `20261012-pipeline-cost/read_phases.py`（舊診斷版專用）用 `mem_read`，已加 assert。舊快照裡的 `card_status` 遇到 0xC5… 會找不到紀錄，不會去讀 |
| FHD 29.97p 3 s（`rec-fhd30.json`） | 73/73 收尾；72 壓縮、第 1 幀 RAW（設計如此） |
| UHD 3 s（`rec-uhd24.json`） | 58/58 收尾。相機在 UHD 用 8-bit，LOSS 把整段交給原廠（`rec_raw` +1），行為同正式版 |
| OG3K 29.97p 2 s（`rec-og3k30.json`） | 44/44 收尾；42 壓縮、1 幀兩個 lane 都忙、第 1 幀 RAW。第 2、43 幀：24 tiles，和正式版 C trailer（`fpl_trailer_write_all`）在主機上重建的結果逐位元組相同，rawpy 解碼 2010×3024（`A001_228-frames/`） |
| FHD 59.94p 15 s，手動停止（`rec-fhd60-15s.json`） | 867/867 收尾。863 壓縮；1 幀引擎工作逾時（stall 保護，改存 RAW）；2 幀兩個 lane 都忙；第 1 幀 RAW。第 2、450、866 幀和主機參考實作逐位元組相同（`A001_227-frames/`） |
| HS280 119.88p 3 s／8 s（`rec-hs280-120*.json`） | 298/298、897/897 收尾，都是手動停止。所有幀照已知的 M12 問題被引擎拒絕，存 RAW；抽查的 RAW 可以解碼。**正式版在此模式約 1.8 s 自動停錄，這一版沒有自停**（行為改變，見下） |
| LOSS OFF，FHD 59.94p，2 段 CPU（`cpu-prep-plain-off-fhd60-*.json`） | 總 74.5／76.6（正式版 OFF 76.6），CamSch 43.0／45.4（正式版 OFF 43.3），SRecFile 2.7／2.4。沒有退化 |
| 原廠 RAW 片段回放 | 210 幀全部交給原廠解碼（`play.stock` 210，decoded 0，失敗 0） |
| 選單切換 LOSS 並存回 BIN | ON→OFF→ON：`saves` 1→2，失敗 0。兩次都把卡上的 BIN 讀回比對：OFF 時和一般版建置逐位元組相同，ON 時和 ON 部署檔逐位元組相同 |

## 注意事項

- **HS280 119.88p 不再自動停錄。** 正式版約 1.8 s（約 220 幀）就停，這一版 3 s、8 s 都錄到手動停止，收尾也正常。
  推測是 LOSS 處理每幀變快，在途幀沒有撞到原廠 96 格的上限。這不是錯誤，但行為和正式版不同。
  還沒測更長的錄影，也還沒測卡速不足（UHS-I）的情況。
- 自動停錄（overflow）的收尾路徑這次沒有被觸發，所以還沒驗證。
- 15 s 那段有 1 次引擎工作逾時。這是既有的保護機制（2026-10-02 加入），該幀改存 RAW。這次沒有拿正式版跑同樣長度的錄影來比較。
- CamSch 只有在 LOSS 開啟時偏高，LOSS 關閉時正常。另外排查。
- 操作選單時，有一次轉盤因選單記住上次頁面而進了「鏡頭光學補償」子選單。沒有改任何設定，按 MENU 退出了（`../20261013-registry-scan/reg-ui-04-popup-on.jpg`）。

相機最後的狀態：FHD 59.94p、LOSS ON（已存回 BIN）、LV 待機。
