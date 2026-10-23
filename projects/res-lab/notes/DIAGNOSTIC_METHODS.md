# RES-Custom 診斷方法與教訓 — 2026-10-14

這週為了 240p 做的工具和流程，之後查 RES-Custom 其他問題也用得上。
腳本都在對應的 `validation/` 目錄，路徑如下。

## 1. 掛鉤呼叫計數（HOOKCNT 診斷建置）

- 建置：`OGC_HOOKCNT=1 python3 -B build_v3_reslab.py --virtual-rcd --card --no-shell --out <dir>`。
  consumer VERSION 會變成 22。
- 原理：每個掛鉤先進一段計數跳板，`hookcnt[i] += 1` 之後再跳到原本的 shim。
  計數器放在 shim 視窗最後 64 字，也就是 `S − 0x100`（S = consumer_state）。順序和 `ogc_layout.HOOKS` 相同。
- 讀取：`validation/20261014-hookcnt/take.py NAME 秒數`。
  它會讀待機 2 秒的計數，錄一段 SD，再讀錄影期間的增量和原生 rec log。
- **教訓：跳板不能動任何暫存器，ip 也不行。** 第一版 v22 用 ip 跳轉，相機開機就卡住，
  原因是 canvas／ratio 的 shim 依賴 ip 的值。修正版：`sub sp,#4; push {r0,r1}; …; str target,[sp,#8]; pop {r0,r1,pc}`。
  `test_hookcnt.test_stub_preserves_every_register` 用 unicorn 逐一執行每段跳板，
  檢查 r0–r12、sp、lr、NZCV/T 都沒變。
- 實測（2026-10-14）：待機和錄影時大約每秒 2000 次呼叫，都是 LV／UI 輪詢。錄影中每幀只有 hdrcopy 會跑。

## 2. 錄影 profile 記錄抓取（v22c）

- HOOKCNT 建置裡，`ogc_canvas` 碰到虛擬 pid 時，把 PARAM 記錄存到 `S − 0x400`：
  - 前 16 bytes：{次數, pid, 記錄位址}；
  - +0x10：韌體填好的原樣（67 字）；
  - +0x120：consumer 改寫後的記錄（67 字）。
- shim 視窗因此放大到 0x2400；`RESERVED_BACK` 確保程式碼不會蓋到抓取區。
- 讀取：`validation/20261014-parity-live/capread.py NAME`。
  它會輸出 consumer 改了哪些字，並和 9/29 的重建值比較：原廠 p13 欄加上 25 組讀回，再加上 +0x30。

## 3. 相機程式碼全區比對

- `validation/20261014-parity-live/codediff.py [lo hi]`：用 read_bulk 讀回 0xC0000000–0xC0730000，
  和 `out/MAIN_c0000000.bin` 逐字比對，大約 2 秒。
- 拿結果對 `LOAD.LOG` 的 `12 <addr> <value>` 記錄，就知道每個改動是哪個 Sup 寫的。
  2026-10-14 共 72 個非 cave 的字：consumer 64 個、00SHELL 2 個（C0033B3C、C01E7704）、loader 2 個。
- 這是「現在相機上到底改了什麼」最直接的答案，比讀原始碼或建置紀錄可靠。

## 4. clone 表和原生表的逐字比較

- `validation/20261014-parity-live/rowdiff.py` 和 `donordiff.py`：讀每個虛擬 mode 的 7 張 clone 列，
  和描述子裡 donor mode 的列逐字比較。
- 注意：要用「第 0 字 == donor id」找原生列，不能用「最相似的列」。
  R28／R38／R14 裡 mode 140 和 mode 12 的列內容完全一樣，取最相似會誤判成 mode 140。

## 5. 部署與救援

- USB 部署：`deploy.py` 先核對卡上舊版，保留卡上的設定區（bytes 32..128），寫入後整檔讀回；
  重開另外用 `reboot.py <fpshd pid>`。部署和重開分兩步。
- **新版開機卡住時：** 把 SD 插到 Mac（`/Volumes/fpSup2`），把舊檔另存成證據，
  寫入「新 BIN 的前 32 bytes + 卡上設定區 + 新 BIN 其餘部分」，用 shasum 核對後 `diskutil eject`。
  `validation/20261014-hookcnt/restore_sd.sh` 是放回 v21 的版本。
- `camera.snapshot()` 的 REFERENCE 要指向相機上實際那一版的 card 目錄。

## 6. 錄影測試的條件與陷阱

- **判定只看 SSD。** SD 撐不住 240p，SD 停在 94 格不代表任何事。SD 錄影只用來讀計數或抓記錄。
- **00SHELL 和 HDMI 都要關。** 兩者開著時，MovRec 的請求速率會掉到約 188–204 fps。
  2026-10-14 A001_330–332 就是在 shell 開著時錄的，那組比較作廢。
  每段錄影都要記下 shell／HDMI 狀態。
- 重開後格率選擇會回到 59.94 或 119.88，解析度則會保留。錄之前要確認格率。
- 錄影中 USB 不能下任何指令。原生 rec log 存在 RAM，重開前都讀得到（`rec log-out`）。
- 判斷實際長度用：幀數、WAV 長度、每秒建立的檔案數（exFAT 時間戳精度 1 秒）。
  不要用畫面上的計時，它是幀數 ÷ 載體格率。

## 7. 這次確認過的事（之後不用重查）

- 虛擬 mode 230／231 的 clone 表、mode 和 pid 的判斷、錄影 PARAM 記錄，都和原生 mode 12／p13 逐字對等。
  細節見 [MODE_AND_PROFILE_LOOKUPS](../../../research/imx410/notes/MODE_AND_PROFILE_LOOKUPS.md)。
- 高格率路徑和時脈閘門見 [HIGH_FRAME_RATE_PATH](../../../research/imaging-hw/notes/HIGH_FRAME_RATE_PATH.md)。
- 測試資料和待辦見 [RESCUSTOM_STATUS](../RESCUSTOM_STATUS.md)。

## 8. FPS 文字驗收要在選單／QS 更新後拍（2026-10-15 更正）

- 使用者指出：開機後尚未開關選單／QS 的 LCD 可能還是原廠舊畫面。`VR_UI=1`、新 drawText 已在元件樹內，也不能證明它已畫到 LCD。
- 先確認 LV 待機，再以單次 QSON／QSOFF 開 QS、下一次 QSON／QSOFF 關閉，逐次核對 QS／LV；回 LV 後才連拍兩張。工具 `validation/20261015-qs-first-open/on-camera/capture_after_qs.py` 保存完整序列與圖片。
- 1910 與原廠白字遮罩一致的結果已撤回外觀驗收：它拍在更新前。更新後 1911 才是 fix4 的實際文字，較細、間距偏大，沒有描邊。
- 只核對屬性值也不足以驗收呈現。後續描邊版本的 size／color／outline-width／outline-mode 讀值正確，實拍仍可能缺字或出現細小綠字；必須以實拍判定成功。資料見 `on-camera/run4/`。
- 四個對角各一像素的黑字副本＋白色中心可形成外緣；fix8 的暫時對比色控制 1923 已實拍證明。控制色只改完整核對過的自有常駐記錄，最後必須完整讀回還原黑色；fix9 加字體欄位後，color offset 從 45 改為 49，不能沿用舊偏移。
- 若整條底列連快門／光圈一起不見，不要直接當成 FPS 元件失敗。fix9 1933 與暫時移除 RES-Custom、確認原廠 picker／draw 記錄的 1937 都出現此現象；來源尚未區分為實體顯示或截圖流程。原廠對照 1935 亦保留，避免只選正常照片。
- fix12 加厚外框採保留內側副本、再增加外側副本，中心白字與 fix10 的幾何／14-state 曲線不變。1943 對比色外接範圍比白字四側各多 3 px，之後完整還原黑色；不是把白字加粗。表與單筆上限因副本增加同步提高，精確界限見 `run7/RESULTS.md`。
- 擷取工具若同時使用目標畫面與目的檔案，分別命名。初次 1942 後的第二張 assertion 失敗，是 `target` 從畫面名稱被覆蓋成 Path，不能推論相機跳回 QS。已改為 `destination`，並在每張照片後保存紀錄；最終對比色／黑色流程已完成。
