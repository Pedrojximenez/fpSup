# Sensor Lab 私有 18p 橋接：離線驗證紀錄

日期：2026-10-04。本報告的測試結果屬離線驗證。其後，診斷安全版已寫入 fpSup2，逐檔讀回相符；相機仍 idle，尚未重新開機或實錄。預設 veto 安全版仍僅離線。

## 行為

- MODE 目錄掃描全部 12 個配方格率，僅受 FILTER FPS 及其他 FILTER 欄限制。改變使用者當前錄影 FPS 不會增減 MODE 列。FILTER 的 12 列為 Any、18p+、23.98p+ 至 239.76p+，各列門檻均經測試。
- M0、M141 的 RAW14 全高 18p 配方可在 Any 與 18p+ 下列出。選擇 MODE 分頁的 Sensor rate = 18p 時，原廠只設定合法 23.976p enum 1，另以 USER 內揮發性 `RATE18=1` 讓 picker 選配方 index 11。離開 CUSTOM、改變原廠 FPS 或選回 Native 會清除標記。沒有寫入原廠隱藏 15p enum。
- REC 前置守衛核對已發布的 AXIS、RECIPE、ENTRY、位深、原廠 carrier、實際時序與 picker 鎖存。預設成品對私有 18p 的三種已知起錄事件 3、0x0F、0x23 均拒絕。
- 只有明確加入 `--diagnostic-18p-rec` 才移除最後的 18p veto。診斷版仍需完整配方核對。此開關**沒有自動片長上限**，只供人工控制的短片診斷。

## 成品與寫卡狀態

| 版本 | 目錄 | fpSup.BIN SHA-256 | MANIFEST.json SHA-256 |
| --- | --- | --- | --- |
| 預設 veto 安全版 | [18p-bridge-veto-safety](18p-bridge-veto-safety/) | `7e7bab0a456622759d0b18baa4aaadfffb1e74ae714ac55608857848d68716ed` | `3c696b25278f72abbc92a5eff777dc42c023b4a5303ea89a54cf866ae1a208cd` |
| 手動短片診斷安全版 | [18p-bridge-diagnostic-safety](18p-bridge-diagnostic-safety/) | `8d00088d1db0c4246279c140ca0865579b18930848accaf745fcd7151174884d` | `297b717f36572165f859a090be3ed71179ad5233aad186d8ab5338fb6b01a5b6` |

兩版都是 debug、非 Fast 卡；`persistent_settings_write=false`。預設版／診斷版的 VBIN 分別為 58,992／58,984 B，均低於 61,440 B 選單區塊界線。成品審計對兩版皆得 `source_differences=[]`、`stock_nonzero_cave_changes.count=0`、305 sections、37 stock sites。Sensor Lab 的 `0xC0730000..0xC0735400` 皆沒有固定 VBIN 目的區；後段 `0xC0735000..0xC0735400` 只用作 USER pack 來源座標。搬遷開機與關機模擬保留原廠該區 21,504 bytes，並還原 299 個 journal records。先前的 `18p-bridge-veto-reviewed`／`18p-bridge-diagnostic-reviewed` 僅保留作離線迭代歷史，以本表安全版為目前基準。

維護的 USB `deploy.py --bin-only` 已將診斷版寫入 fpSup2，另寫入相符 MANIFEST；寫入前 AutoRun 與五個 FPSUPUI 檔讀回相符，寫入後根目錄 AutoRun、BIN、MANIFEST 均獨立讀回，SHA-256 與候選完全相同。診斷版 BIN 為 `8d00088d1db0c4246279c140ca0865579b18930848accaf745fcd7151174884d`，MANIFEST 為 `297b717f36572165f859a090be3ed71179ad5233aad186d8ab5338fb6b01a5b6`。[r86 三檔備份及寫卡報告](../../../../archive/fpSup2-20261004-pre-18p-safety/write_report.json)保存逐檔雜湊。CINEMA 仍有九個資料夾；相機 idle、未重新開機，因此此寫卡只證明媒體位元組相符。

## 測試

- MODE 與 FILTER host 測試 55/55；原廠設定同步觸發 `sl_menu_live` 時私有 18p 標記仍保持；MODE 清單不受錄影 FPS 變動影響。
- 私有選單 host 安裝 21/21；ARM 選單 4/4；USER pack 7/7；cave 與診斷開關 10/10；RAW14 REC guard 13/13。
- `test_sensor_lab_exact_18p.py` 直接載入兩份安全版 BIN，經 loader 與 USER 搬遷執行 M0、M141 picker，均發布 RECIPE rate index 11。預設版在三個起錄事件均回 0；診斷版均呼叫原廠 prepare 並回 7；非起錄事件維持原廠結果 7。每個模式另測 16 種錯誤狀態，涵蓋 RAW12 位深、錯誤 carrier、私有標記、AXIS／PICKOK、ENTRY、實際時序、CUSTOM／CinemaDNG 狀態與失效的 imager／descriptor 指標，均在 prepare 前拒絕；殘留的 RATE240 標記不會改寫私有 18p 選值。機器可讀結果見 [安全版逐卡測試](18p-bridge-safety-exact-card-audit.json)。
- [四配置建置矩陣](18p-bridge-safety-matrix/verification.json)的普通／debug／Fast 普通／Fast debug 全部通過成品解析、來源雜湊與 cave 零變更檢查；16 類故意破壞的成品均被拒絕。交付安全版另核對私有 MODE 畫面會分別標示 `18p REC off` 與 `18p test`。

## 尚待實機確認

- 診斷片的 iXML `MASTER_SPEED`、`CURRENT_SPEED` 仍會標原廠 carrier 23.976p。時間碼與音訊同步尚未以實錄核對，不能把診斷版視為可用的 18p 錄影成品。
- 診斷安全版已寫卡但尚未重新開機；預設 veto 版仍未寫卡。MODE 選值、私有 18p 實錄與關機尚未上機驗證。使用者回報上次修正後按 REC 不再立即凍結，但本輪沒有該次測試的模式或片段獨立資料，不能由此推論 RAW14 或私有 18p 錄影已驗證。
