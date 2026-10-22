# Sensor Lab RAW14：全模式開放的第一輪離線核對

2026-10-04。Sensor Lab 的目標是讓原廠 **全部八個 RAW14 感測器模式**及其可求解的輸出軸參與選擇，不以外部專案用過的 M100／23.976p 作為白名單。這份紀錄區分已保存的 r83 成品、目前來源修正和仍需實機驗證的錄影管線。

目前 fpSup2 已寫入 18p 診斷安全版 BIN 與相符的 MANIFEST，逐檔讀回 SHA-256 與候選成品一致；相機仍 idle，尚未重新開機或實錄。預設 veto 安全版仍僅供離線審核。現行來源已完成 M0／M141 的私有 18p 選值與 picker 橋接；詳見[18p 橋接驗證紀錄](18p-bridge-report.md)。舊 reviewed 目錄只保留作先前離線迭代。

使用者回報上次修正後已實機測試，按 REC 不再立即凍結。本輪沒有該次測試模式或片段的獨立資料；這項回報不能證明 RAW14 錄影、正常關機或私有 18p 已通過實機驗證。

## r83 精確成品基準

以固定 SHA-256 的 [r83 debug 卡](../../cards/20261004-b25-menu-r83-picker-reloc/debug/)執行 loader、stage2、USER 搬遷與錄影 picker；從原廠 RAW14 呼叫點送入 `eRawBitType=1`，檢查 AXIS、RECIPE、感測器 metadata、profile 87 與時序寫入。測試程式在 [test_sensor_lab_raw14_card.py](../../../open-gate/build/test_sensor_lab_raw14_card.py)，完整逐組結果在 [r83_picker_matrix.json](r83_picker_matrix.json)。這是**離線 picker 驗證**，不是錄影或 DNG 驗證。

| 原廠 RAW14 mode | 光柵 | r83 配方可求解的格率 |
|---|---:|---|
| M0、M141 | 6064×4042 | 無；現行最低 23.976p 高於約 19.55p 的零消隱物理上限 |
| M95 | 5712×3216 | 23.976、24 |
| M6、M100、M122 | 4176×2174 | 23.976、24、25、29.97 |
| M129、M144 | 3968×2640 | 23.976、24、25 |

八個 mode × 十一個引擎格率，共 **20 組可求解、68 組無解**。其中 400p 僅在引擎表，不在現行私有格率選單；可見選單為十個格率。無解的 r83 picker 仍回原廠 FHD30，RAW14 錄影不能以這個退回結果放行。

另以 [原廠 DNG 函式離線測試](../../../open-gate/build/test_raw14_native_dng_paths.py)執行 enum1 大小回呼、平面配置與 IFD 標籤建構；[逐光柵結果](native_dng_paths.json)涵蓋四種 RAW14 光柵。6064×4042 的原廠大小回呼給 `StripByteCounts=42,893,720`，IFD 建構給 `BitsPerSample=14`、`Compression=1`、`WhiteLevel=16383`；平面碼 8 另配置 16 bpp 的引擎緩衝。測試以四組交叉欄位確認 descriptor 的 `+0x20` 大小 enum 與 `+0x24` 位深 enum 是**各自獨立**的來源。測試未執行錄影 descriptor 的建立、DMA 或實際檔案寫入。

已加入唯讀的[實際 DNG 核對工具](../../../open-gate/build/raw14_dng_audit.py)，檢查 RAW14 主影像標籤、strip 邊界、packed 14-bit 長度與像素低兩位抽樣。它能拒絕現有 12-bit 錄影和壓縮 14-bit 靜照；目前尚無 RAW14 錄影檔供它驗證。

2026-10-04 讀回 fpSup2 時，AutoRun、BIN、MANIFEST 三個雜湊均與保存的 r83 相符。[卡上素材稽核](card-read-20261004.json)發現九段、699 幀無壞序號的 CinemaDNG，皆為未壓縮 12-bit；每段代表幀的 strip 都落在檔案內。其中 A001_005 只有一幀和約 0.10 秒 WAV。檔案本身無法確定拍攝當下的常駐韌體，也無法判斷是否曾在按 REC 後凍結。

## 本輪來源進度與尚待處理

### r86 精確成品：關機存檔保護

[r86 debug 離線卡](../../cards/20261004-b25-menu-r86-raw14-save/debug/)的 BIN SHA-256 為 `28ac9adb81a0070b979066a43aa81d7d8f5b71f240c2ea092b181ffc19db81ce`，MANIFEST SHA-256 為 `ca82441fe8314c939d210462baddfe91aad8b44e2d6fd1403a7c52bb9548b45b`；來源雜湊與建置時完全相符。此卡在原廠 SaveOn v2 的序列化呼叫點加入 USER 搬遷後的 hook：暫時把七組儲存記錄中的 RAW14 enum 1 寫作原廠 RAW12 enum 0，呼叫原廠 checksum／複製函式後還原來源記錄。[成品位元組的 ARM 模擬](../../../open-gate/build/test_imx410_raw14_save.py)確認待儲存副本為 12-bit、來源記錄和另一個運作中設定 bank 仍為 14-bit。這是**離線存檔路徑驗證**；實機正常關機與重開機仍未測得。

r86 精確 BIN 58,304 B，低於 61,440 B 選單區塊界線；成品檢查、15 種損壞成品拒絕測試、[四種建卡配置](r86-build-matrix/verification.json)、RAW14 picker 20 組合法／68 組無解、三種已辨識 REC 啟動事件的前置檢查均通過。loader→stage2→USER→關機模擬恢復 **299 筆** journal 記錄，原廠 cave **20,480 B** 原樣保留。核心 hook 21、後期 UI hook 10、受保護原廠位置 37。[精確成品 RAW14 描述子測試](R86_DESCRIPTOR_AUDIT.md)另直接執行 M100／23.976p 的 picker→原廠畫布→描述子鏈，確認 RAW 平面碼 8 與描述子兩個 enum 1；仍未執行真正錄影。18p 在 r86 只有配方核心與 DNG 格率 hook，沒有可選錄的私有選值。

r86 已依先前指定的 fpSup2 寫卡流程安裝，逐檔讀回八個啟動／UI 檔的 SHA-256 與 r86 成品相同；只有 `fpSup.BIN` 和 `MANIFEST.json` 與 r83 不同。原 r83 啟動檔保存在 [寫卡備份與逐檔雜湊](../../../../archive/fpSup2-20261004-pre-r86/write_report.json)。卡上的 **699 幀 DNG、9 個 WAV**仍在；沒有操作 CINEMA／DCIM。寫卡與讀回當時尚未有 r86 的相機開機、關機或錄影片段回報。

### 最新來源：私有 18p 橋接與診斷版寫卡

現行 MODE 目錄掃描全部 12 個配方格率；M0／M141 在 FILTER FPS 的 Any、18p+ 下可見。FILTER FPS 各列維持自己的門檻，使用者錄影 FPS 設定不縮減 MODE 清單。MODE 分頁的私有 Sensor rate = 18p 以原廠合法 23.976p enum 1 承載，另用 USER 內揮發性標記讓 picker 選 rate index 11；離開 CUSTOM、改回 Native 或變更原廠格率會清除標記，沒有寫入隱藏的 15p enum。

[預設 veto 安全版](18p-bridge-veto-safety/)與[手動短片診斷安全版](18p-bridge-diagnostic-safety/)的 BIN SHA-256 分別為 `7e7bab0a456622759d0b18baa4aaadfffb1e74ae714ac55608857848d68716ed`、`8d00088d1db0c4246279c140ca0865579b18930848accaf745fcd7151174884d`。兩份都是 debug、非 Fast 的成品，VBIN 分別為 58,992／58,984 B。診斷版已寫入 fpSup2；veto 版仍只在離線審核。整卡 ARM 模擬對 M0／M141 均取得 18p 配方 index 11：三個已知起錄事件在預設版都被阻擋；診斷版僅在完整 picker／原廠 carrier／實際時序相符時放行。每個 mode 的 16 種錯誤狀態都在原廠 prepare 前拒絕。兩版的成品來源雜湊一致，原廠 cave 非零資料變更數為 0；開機與關機模擬還原 299 筆 journal，保留 21,504 B 原廠 cave。四配置[建置矩陣](18p-bridge-safety-matrix/verification.json)通過，16 類損壞成品被拒絕。詳見[安全版逐卡結果](18p-bridge-safety-exact-card-audit.json)及[完整驗證紀錄](18p-bridge-report.md)。

維護的 USB `deploy.py --bin-only` 更新 BIN，另寫入相符 MANIFEST；寫入前 AutoRun 與五個 FPSUPUI 檔均讀回相符，寫入後根目錄 AutoRun、BIN、MANIFEST 的獨立 SHA-256 也與診斷安全版候選相符。診斷版 BIN 為 `8d00088d1db0c4246279c140ca0865579b18930848accaf745fcd7151174884d`，MANIFEST 為 `297b717f36572165f859a090be3ed71179ad5233aad186d8ab5338fb6b01a5b6`；原 r86 三個根目錄檔案與逐檔雜湊保存在[寫卡備份](../../../../archive/fpSup2-20261004-pre-18p-safety/write_report.json)。CINEMA 仍有九個資料夾；相機 idle，未重新開機，故目前只是**卡片位元組驗證**，沒有執行時或實錄結果。

診斷版必須用 `--diagnostic-18p-rec` 明確建置，**沒有自動片長限制**，只供人工控制的短片調查。WAV iXML 速度欄仍會標原廠承載值 23.976p；時間碼、音訊同步、RAW14 像素與真實錄影穩定性均待實錄核對，不能視為已可正常錄影。

已備妥[短片 DNG／WAV 只讀稽核工具與用法](RAW14_CLIP_AUDIT.md)，可在取得新實錄後逐格核對 RAW14 strip、像素低位、FrameRate、TimeCodes、序號及 WAV PCM／iXML 片長；目前沒有 RAW14 實錄可執行這項驗證。

[RAW14 增益與接收器審計](GAIN_RECEIVER_AUDIT.md)另指出八個模式分成兩組：M6／M95／M100／M122 使用原廠影片型接收器欄位，M0／M141／M129／M144 使用靜照型欄位。八個模式在數學上有可解時序，不能因此推論後四者已具備正確錄影黑位或硬體行為。14-bit 增益在目前 native enum 下落入 state 5，ISO 與黑位還要實錄量測。RAW14 真正的錄影描述子、像素打包、音訊與時間碼均未經 r86 實機驗證。

### r85 離線測試卡

[r85 debug 卡](../../cards/20261004-b25-menu-r85-raw14-preflight/debug/)把明確 M0 選值與 RAW14 錄影前檢查納入整卡。其 BIN SHA-256 為 `fc8858c366658a91feced84e1617d4deb0f95891a1c922916445d74d7dc07866`，MANIFEST SHA-256 為 `da98c7f09aca33325fc384f573fc02448ddc827201f9a045b55da7e2b9731b2e`。精確成品的[八模式矩陣](r85_picker_matrix.json)及[REC 事件測試](r85_rec_guard.json)通過：錄影事件 `3`、`0x0F`、`0x23` 在 picker 已發布且所有鎖存與實際時序一致時才呼叫原廠準備函式；資料缺漏或不一致先拒絕，不重算或改寫配方。這是已辨識的錄影啟動事件範圍，尚未證明所有原廠狀態切換都被涵蓋。

成品解析、15 種故意損壞的拒絕測試、普通／debug／Fast 普通／Fast debug 四組封裝，以及 loader→stage2→USER→關機還原的離線模擬均通過；後者恢復 298 筆 journal 記錄，原廠 cave 20,480 位元組保持原樣。r85 尚未寫入 fpSup2、未在相機上錄影。其目前最低格率仍為 23.976p，全高 M0／M141 沒有可用錄影格率。

r85 開放原廠真正的 RAW14 設定，但 `WITH_BIT_POFF=False`，正常關機時自動將 RAW14 改回 12-bit 的路徑尚未完成。離開 CUSTOM 時現有 setter 會改回 12-bit；若仍停在 CUSTOM／14-bit 直接關機，原廠設定可能保存 14-bit。這不同於已接受的異常斷電殘留風險，不能把 r85 視為符合正常關機還原條件的可上機版本。卡片目錄內的 [README](../../cards/20261004-b25-menu-r85-raw14-preflight/debug/README.txt)亦標示此限制。

- `AXIS[A_MODE]=0` 保留自動挑選；`0x100` 現在明確代表真正的 M0。ARM 配方、Python 模型與選單寫入已修改，尚未成為 r83 卡上的位元組。
- 錄影啟動前必須核對原廠位深／格率與最新配方；RAW14 無解或選了 RAW14 mode 卻仍是 RAW12 時要拒絕啟動，避免產生位深宣告與感測器來源不一致的素材。
- M0／M141 的配方核心已有 18p：ARM 配方與模型逐字一致，兩模式在 15／18／19p 可解，20p 和 23.976p 無解；18p 為 HMAX 911、VMAX 4391、tail 710。原廠隱藏的 15p 設定值不能直接打開：其 picker export 會進入原廠 assert。現行來源已用合法 23.976p 承載與揮發性私有標記接上 18p 選值、MODE 清單與 picker；REC 預設仍拒絕。DNG FrameRate、時間碼、音訊與錄影排程仍需實錄核對；研究背景見 [低格率審計](../../../open-gate/notes/IMX410_RAW14_LOWRATE.md)。
- [18p 錄影／音訊審計](RAW14_18P_RECORDER_AUDIO_AUDIT.md)未找到原廠 23.976 承載值會直接阻止短片手動啟停的證據；但它會使畫面片長與逐格 DNG 時碼錯誤，RAW14 全高約 772 MB/s 也可能很快耗盡緩衝。[WAV 格式深追](RAW14_18P_AUDIO_SINGLETON_TRACE.md)確認 PCM 取樣率獨立於承載格率，iXML 的兩個速度欄卻會標 23.976；BWF 樣本參考值的來源與換算都用承載格率，不能只改其中一邊。實際 WAV 時長仍需有限短片核對；診斷片不能當作支援完成。
- 反編譯確認 RAW14 位深列舉在目前 raw-movie 增益分派落入 state 5；ISO 政策尚未量測與定案。原廠 RAW14 大小／IFD 函式已在離線模擬中執行，但兩個 descriptor 欄位是否在實錄時同為 enum1、像素是否正確打包、黑位／白位與回放仍需實錄核對。
- [sigma-fp-supmod R120 分析](../../../../research/other/external/sigma-fp-supmod-R120/JULIEN_14BIT_AND_MODES.md)提供已知 RAW14 錄影管線的對照；其固定 M100／23.976p 配置不限制 Sensor Lab 的模式範圍。

使用者已回報上次修正後按 REC 不再立即凍結；仍需取得該次測試的模式與片段資料，並另驗正常關機和重開機，才能判定各條路徑的實際狀態。私有 18p 診斷安全版雖已寫卡，但未重新開機或實錄；預設 veto 版仍僅離線。
