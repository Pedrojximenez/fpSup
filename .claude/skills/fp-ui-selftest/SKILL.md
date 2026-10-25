---
name: fp-ui-selftest
description: Test a SIGMA fp menu change on the camera by yourself — deploy fpSup.BIN, reboot over USB, drive the menus with keys, screenshot and look at every step. Holds the verified navigation map (live view → SHOOT → 記錄設定 → 解析度 popup → Sensor Lab page), the one-command tool (fpSup/fp_usb_shell/ui_drive.py), and the navigation rules that stop an agent getting lost. Use whenever a UI change needs checking on the camera instead of asking the user to press buttons.
---

> **設定區風險（2026-10-04 更新）**：自測時選到的值可能寫進設定區，原廠會在 loader 前讀取。
> 使用者已指出現在有還原手段；依實際值、症狀與該流程的適用條件評估，不再一律視為不可恢復。
> 原廠合法值及本卡已調查過的 CUSTOM、14-bit 可依各自的紀錄操作；其他值先確認
> 會保存什麼、如何還原。詳見 `research/SETTINGS_AREA_FIRST_RULE.md`。
> 上機動作依本次對話已授權的範圍執行；舊的 `sensor-lab-auto-deploy` memory
> 在目前環境找不到，不能拿它推定部署、重開或操作權限。`mem set` 實驗須先確認範圍。

# 一個指令：`ui_drive.py`

```sh
cd fpSup/fp_usb_shell
python3 -B ui_drive.py reboot                       # shell reboot, restart fpshd, wait for pong (+3 s)
python3 -B ui_drive.py MENU RIGHT DOWN:2 shot:tag   # keys in order, then a screenshot
python3 -B ui_drive.py RIGHT wait1 shot:after       # wait1 = sleep 1 s
```

- 每個 `shot` 印出本機 JPG 路徑（`/tmp/fp_ui/HHMMSS-tag-SSnnnn.jpg`），**用 Read 看圖**。
- 鍵數用 `DOWN:2`，**不要 `DOWN*2`**（zsh 會當成 glob，整個指令失敗）。
- 只允許選單鍵；S2 / MOV 在 CINE 會開始錄影，工具直接拒絕。
- 鍵與鍵之間 0.8 s；連續狂送曾讓 USB worker 卡死。
- **不要 `import bootmeasure`**：它沒有 `__main__` 保護，匯入就重開一次（2026-10-03 重開了兩次）。
  重開用 `ui_drive.py reboot`（同一套邏輯）。

相容 BIN-only 熱更新（AutoRun 不變）：

```sh
python3 -B deploy.py --bin-only <card-directory>   # 先核對 AutoRun，再寫入並全長讀回
# 只有完整驗證成功、且重開在授權範圍內，才另行執行：
python3 -B ui_drive.py reboot
```

**部署和重開分開執行**（2026-10-03 r39）。檔案只寫一半時重開，可能載入
混合內容。Mode 7 只覆寫前段，不會截短舊檔；只比對新 BIN 前綴的 SHA
會漏掉舊尾巴。`deploy.py` 必須確認完整遠端長度與內容。傳輸卡住時記下
目前步驟和 daemon 身分；不要用定時器取消仍在進行的寫入，也不要清掉
所有同名程序。先確認傳輸是否仍在執行，僅按已查明的狀態恢復。

**putfile 寫 BIN 曾卡住（2026-10-04，根因尚未經實機確認）**：成功過的條件是「相機用電源開關開機、開好後才插 USB，
接著馬上 putfile」；shell 重開後寫、或做過一輪選單操作後寫，多次卡死。卡死就用 `say` 叫使用者拔插，
或請使用者把 SD 插到電腦（`/Volumes/fpSup2`，直接 cp + shasum + `diskutil eject`）。
以前的紀錄：**部署前先 `ui_drive.py reboot`**（2026-10-04 兩次，後來證明不夠）：一輪選單操作 + 大量 `mem get` 之後，putfile 卡在
`stage pass 1: N words missing, repairing`，接著 USB worker 沒回應、重啟 fpshd 也沒用，要使用者拔插 USB。
剛開機或剛重插時寫入都正常。舊版 `putfile` 對附加式 `echo` 盲目重試、
未核對已收位元組數，可能把遺失一段擴大成整段錯位與大量逐字修補；現行工具改為分段核對並重送。
這能解釋部分慢速情況，仍須以一次授權的實機更新輸出確認是否也解決當時的 USB 卡死。

putfile 偶爾以「LOAD_DONE_US reads zero」拒寫。先查當次讀回與 worker
狀態，確認沒有未結束的寫入，再決定是否重試；單次讀取失誤不是自動重試
非冪等寫入的證據。

# 先用 `where`，截圖留給要看畫面的時候

```sh
python3 -B ui_drive.py where      # ~4 s，只用 mem get
screen SL_LAB                     # app+0x84C = 目前畫面，+8 名稱
  MENU_Level2  4254               # 各頁的焦點變數 = 焦點物件編號（附名稱）
  SL_LabFocus  38159 (MenuItem_Jump)
  SL_LabTab    2                  # Sensor Lab 的分頁 0/1/2
  SL_O_A0      1                  # 資訊區正在編輯 W
```

導航時每一步用 `where` 確認位置（使用者 2026-10-03：「每次都要拍照挺累的」）；
要看排版、文字、箭頭這類視覺結果才 `shot`。彈出清單是否打開 `where` 看不出來（焦點變數仍是列）。

# 導航地圖（2026-10-03 實機，Sensor Lab 卡，CINE）

| 在哪 | 畫面特徵 | 按鍵 → 結果 |
|---|---|---|
| 任何選單畫面 | — | `S1`（半按）→ 直接回 live view，凍結時也有效 |
| 待機 live view | 上方 STBY、下方 fps/快門/光圈 | `MENU` → 選單（開機後在 SHOOT 第 1 頁，**焦點在分頁列**，沒有列反白） |
| 分頁列焦點 | SHOOT/PLAY/SYSTEM，下方 6 段頁碼條，沒有列反白 | `RIGHT`/`LEFT` = 換頁；`DOWN` = 進入第 1 列 |
| SHOOT 第 2 頁 | DC裁剪 / 記錄設定 / 音訊記錄 | 從分頁列 `DOWN:2` 到「記錄設定」，`RIGHT` 進去 |
| 記錄設定（B2_5） | 標題「記錄設定 CINE」；格式 / 位元深度 / 解析度 / 每秒幀數；**進入時焦點在第 1 列「格式」** | `DOWN:2` = 解析度；`RIGHT` 開清單 |
| 解析度清單 | 右側 UHD / FHD / CUSTOM，游標在目前值；CUSTOM 時底部「› 更多選項」 | `UP`/`DOWN` 移動；`RIGHT` = 確定（CUSTOM 再跳 Sensor Lab）；`OK` = 確定不跳；`MENU` = 取消 |
| Sensor Lab（SL_LAB） | 分頁 FORMAT/OFFSET/STYLE（暫時的圖片標題）；進入時焦點在分頁列 | `RIGHT`/`LEFT` 換分頁（在分頁列上）；`DOWN` 進列、`UP` 回到分頁列；列上 `RIGHT` 開清單；`MENU` 取消清單／回記錄設定（焦點在解析度）。第三個分頁 OUTPUT（r34）：`DOWN` 先到資訊區那一列（反白在數字後面），`RIGHT`/`OK` 進入編輯（欄位上下出現箭頭）：`LEFT`/`RIGHT` 換欄位 W/H/BinH/BinV、`UP`/`DOWN` 改值、`OK`/`MENU` 結束；再 `DOWN` 是 Ratio、再 `DOWN` 是 Data rate（r45：左右切換格率，「Setting」= 目前錄影設定）。第二個分頁 MODE（r44）：一列，左右照推測畫質切 mode、`OK` 開清單（最多 70 項，上限跟著 `SL_ModeMax`）；讀選擇用 `sl_menu/appvars.py SL_M_Sel SL_ModeMax` |

開機後從 live view 到 Sensor Lab，已驗證的一串：

```sh
python3 -B ui_drive.py MENU RIGHT DOWN:2 RIGHT DOWN:2 RIGHT shot:popup RIGHT wait1 shot:lab
python3 -B ui_drive.py ... RIGHT wait1 RIGHT:2 shot:out     # 再右切兩次 = OUTPUT 分頁
```
一次部署的實測時間（r30）：建置 18 s、putfile 5 s、讀回 1 s、重開 23 s、走到 OUTPUT 並截圖 16 s。

**這串只在「剛開機、選單第一次打開」成立。** 選單會記住上次的位置，三層都記：
`S1` 退出後再按 `MENU` → SHOOT 第 2 頁、焦點在「記錄設定」列（不是分頁列）；
進記錄設定 → 焦點在上次的「解析度」（剛開機是「格式」）；進 Sensor Lab → 上次的分頁與列。
所以同一次開機裡**每進一層都先 `shot`**，不要重放開機路徑。

解析度摘要顯示「3」= CUSTOM（原廠摘要沒有 CUSTOM 文字），FHD 顯示「FHD」。

# 不迷路的規則（從失敗學的）

1. **每換一個畫面就截一張再決定下一步。** 已驗證的固定路徑才可以一次送完，送完也要截圖確認終點。
2. **先認畫面再按鍵**：認標題列（SHOOT 分頁 vs「記錄設定 CINE」vs FORMAT 分頁）、
   **認焦點**（左邊藍色條與反白的那一列；分頁列焦點時沒有任何列反白）、認底部提示（確定/取消/更多選項）。
   底部是「MENU 取消」代表在清單（popup）裡，「MENU 退回」代表在頁面上。
3. **RIGHT 的意義看層級**：分頁列 = 換頁；列 = 進入／開清單；清單 = 確定。按錯層級是最常見的迷路原因。
4. 迷路時不要亂試：按 `MENU` 一次、截圖，退到認得的畫面再走地圖。
   **按了 MENU 畫面不變、沒有任何列反白 = 焦點掉進看不見的物件（凍結）**：
   `ui_drive.py S1` = 半按快門，直接退回 live view，不錄影、不用重開（2026-10-03 實機，
   使用者提示「rec 可以半按」；S1ON 的 USB 回覆可能逾時，鍵照樣送到）。S1 沒用才 `ui_drive.py reboot`。
   不要送 MOV/S2（完整按下）：CINE 下會開始錄影。
   ⚠ `S1OFF` 偶爾沒送到：快門停在半按（畫面有綠色對焦框），之後 MENU 完全沒反應。
   `ui_drive.py S1` 現在會多補一次 `S1OFF`；還是不行就手動 `host/fpsh key S1OFF`。
5. **焦點進了看不見的列（分頁標題變白、沒有任何列反白）就停**，不要繼續按方向鍵。
   2026-10-03：焦點進了被 BG 蓋住的 FILTER 第 1 列，再按兩次 DOWN 後 USB shell 整個沒有回應
   （ping 失敗、重啟 fpshd 也沒用），只能請使用者到相機前處理。這種時候先 `S1`。
6. **整台掛掉（shell 也斷）時，下一張卡做「由安全到危險」的矩陣**：把幾個條件放在同一頁的不同列，
   由上往下一列一列移、每步截圖，第一個出事的就是答案——每輪只讓使用者拔一次電池
   （2026-10-03 d5：3/5/6/11 項 → d6：上限／事件／摘要，兩輪就定位到本地編號撞號）。
   不要用「猜一個原因 → 做一張修正卡」：那次猜 `>` 字元，白白多一次拔電池。
7. 一個實驗只回答一個問題，結果寫下來（哪張卡、哪一步、看到什麼），再設計下一個。
8. 結果「沒反應」時，先做一張「最直接的版本」證明底層能動（例：無條件跳頁），再往上加條件。
   2026-10-03：r20/r21/d1/r22/d3 五張都「沒反應」，d2（無條件 sync-request）一張就把問題切成兩半。

# 用 `where` 導航的焦點編號（2026-10-04 實機，Sensor Lab 卡）

使用者：「請使用 ui log 導航」——每一步讀 `where`，截圖只留給要看畫面結果（LV 比例、DNG 以外的視覺）。

| 畫面 | 焦點變數 = 值 | 意思 |
|---|---|---|
| MainB2（SHOOT 第 2 頁） | `MENU_Level1 650` | 「記錄設定」列 |
| B2_5（記錄設定） | `MENU_Level2 4247` / `4254` | 格式 / **解析度** |
| SL_LAB | `SL_LabFocus 35010` | 分頁列（`SL_LabTab` 0/1/2 = FILTER/MODES/OUTPUT） |
| SL_LAB | `SL_LabFocus 43115` | MODES 的 MODE 列（`appvars.py SL_M_Sel` = 第幾個 mode） |
| SL_LAB | `SL_LabFocus 43220` | OUTPUT 的 Ratio 列（`appvars.py MV_SLScale`：0 AUTO、1 RAW、16 Free） |

- **進 B2_5 之後要 `wait1`**：頁面還在載入時送的 DOWN 會被吃掉，接著的 RIGHT 打開的是「格式」清單
  （CinemaDNG / MOV）。那時按 `MENU` 取消，**絕不能選 MOV**。
- Ratio 列上 `RIGHT` 直接切下一個選項（AUTO → RAW），不會開清單。
- 選單記住上次位置：再按 MENU 回到 MainB2「記錄設定」、進去焦點在解析度、Sensor Lab 回到上次的分頁與列 ——
  每一層先讀 `where` 再決定按鍵。

# 錄影（使用者 2026-10-04 授權自己按）

```sh
fpSup/fp_usb_shell/rec_take.sh 3   # MOVON/MOVOFF 脈衝開始 → 3 s 內**完全不碰 USB** → 再一次脈衝停止 → 等 5 s → ping
```

- **錄影中 host 一個交易都不能下**（`projects/usb-shell-sup/notes/RECORD_SHELL_COEXIST_RESOLVED.md`）：
  2026-10-04 錄影開始 1.5 s 送截圖 → `LIBUSB_ERROR_PIPE`、停止鍵沒送到、錄了 ~30 s，要使用者拔插 USB。
- 不要 `dir` 一個很大的片段資料夾（數百個 DNG）：回覆塞爆後 shell 的 `dir` 連 `\CINEMA` 都失敗，
  重開才好。抓格子直接用檔名：`getfile.py '\CINEMA\A001_004\A001_004_20261004_000100.DNG' out --size N`。

# 讀狀態（不用截圖）

- 私有頁有沒有裝：`[0xC37B7048]` = app；`app+0x80` 畫面數（原廠 221，+私有頁）、`app+0xF8` 狀態機數（原廠 17）。
- Sensor Lab 結構：`[0xC0730388]` = struct sl_menu（`+0` result 1 = 裝好、`+16` 頁面位址、`+24` 長度）。
- 頁面整段讀回比對：`putfile.read_direct(addr, n)`（65 MB/s），和建置的頁逐位元組比；
  只應差開機時寫入的私有字串位移。

# fpSup 頁（Loader v4）導航與量測（2026-10-25 實機）

- 路徑：`MENU` → SHOOT 1（MainB1，焦點在分頁列）→ `LEFT` = fpSup 頁 `FT_Y6`。**每次進頁焦點都在分頁列**（沒有列反白、標題列變灰底）；
  此時 `RIGHT`/`LEFT` 是換頁（RIGHT 回 MainB1），要先 `DOWN` 進列，再 `RIGHT` 開子頁。2026-10-25 我在分頁列按 RIGHT 跑去 MainB1，
  接著 MENU 直接退出選單。
- 子頁：SupManager `FT_LIST`、RES-Custom `FT_RCFILES`、Color `FT_LUTMGR`。MENU 回 fpSup 頁、焦點回分頁列。
- 讀變數比截圖快：`gui geti FT_Focus / SM_Focus / RC_Focus / FT_Go`（唯讀可用；不要對綁定的文字變數 `gui sets`）。
- **量「連按會不會掉鍵」**：`fpSup/fp_usb_shell/ui_burst.py <tag> DOWN 4 0.15`（開 GUI 時間日誌、按鍵間隔 0.15 s、讀回 render 次數），
  然後**截圖數游標停在哪一列**——render 次數不等於移動數。對照：剛開機 4 下 = 4 列；進過直接設畫面的子頁後只動 1–2 下
  （原因與修法：`research/ui/MENU_PAGE_SWITCH.md`）。
- **截圖資料夾太大時 `shot` 會說「no new screenshot appeared」**：`dir \DCIM\100SIGMA` 回覆上限 16 KB，約 300 個檔後看不到新檔。
  截圖其實有存：用 `getfile.py '\DCIM\100SIGMA\SS__NNNN.JPG' out --size 300000` 先拿到「file length is N」再用 N 抓
  （`fpSup/fp_usb_shell/ui_shot.sh N tag` 包好了；N 是上一張 +1）。
- **別送 S1（半按快門）**：鏡頭有人手動調好對焦時會跑焦（2026-10-25 我送了一次，要通知對方）。退出選單用 MENU；
  卡在半按（綠點、MENU 沒反應）時送 `key S1OFF`。
- 選單快速連按的成本用 GUI 自己的時鐘量（`gui-key-cost-measurement` 記憶）：`ui_latency.py` 的 start_after_key 會隨開機時間漂移。
