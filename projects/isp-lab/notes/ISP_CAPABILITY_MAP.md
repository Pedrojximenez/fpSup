# ISP 鏈能力地圖（第一輪，2026-10-23，離線整理）

RESEARCH_PLAN §2 的第一版。只整理既有證據，沒碰相機。
證據：**[M]** 上機量過、**[C]** 程式碼／反組譯、**[I]** 推論。主張後面附出處。
縮寫：`OGN/` = `projects/open-gate/notes/`、`IHW/` = `research/imaging-hw/notes/`、`RC/` = `projects/open-gate/build/res-custom/`。

## 0. 鏈（訂正過的版本）

```
感光元件（含自己的合併） → 接收端 0x3010 → CRCT 0x300F（DCLP／DEFC／PDAF 校正／Crmf／增益／Vbin・Hbin・Hbin2）
   ├─ a0 視窗 → 六選一 mux → BUFA0        ← 參考 RAW：mux=1 Crmf（與 imx410-lab 的邊界）
   ├─ a7 視窗 → 六選一 mux → BUFA7
   └─ bufa1 → RWZM → BUFA1                 ← 錄影縮放
→ DRAM → SIG／寫入層（CDNG）
   預覽分支：另一組 bin/RWZM 欄位 → 顯示 ring（YUYV，descriptor 寬）→ LCD／HDMI
```
走哪條分支由**路徑選擇器 `FUN_c0325228`** 依（錄影 RWZM、預覽 RWZM、兩邊 bin）決定 [C]（IHW/CRCT_PATH_SELECTOR_SOLVED.md、OGN/IMX410_FULL_DESIGN §6.2）。

| 分支 | 條件 | a7 mux | 主管線吃 | 原廠 profile 數 |
|---|---|---|---|---|
| B | 錄＝預覽，且 unity | 1 Crmf | 預覽 | 172 |
| C | 錄＝預覽，非 unity | 4 Hbin2 | 錄影的 bin 與 RWZM | 36 |
| D | 錄≠預覽，錄 unity | 1 Crmf | 預覽 | 81 |
| E | 錄≠預覽，預覽 unity | 3 Hbin（a7 未啟用） | RWZM＝錄影、bin＝預覽 | 17（原廠 UHD：預覽 ×3） |
| F | 兩邊都縮且不同 | 4 Hbin2 | 錄影；副管線＝預覽 | 0 |

**ISP 的設定面 = 一整列 PARAM profile（65 字）**：32 欄由公式決定，其餘是影片類常數或沿用底列（`open-gate/build/imx410_profile.py`，與原廠 78 組影片 profile 逐字相同 [C]）。
res-custom 以「虛擬 profile = 底列 + (偏移, 值) 對」安裝；錄影 29 欄、回放 13 欄、各格率另一組（SEC_CANVAS／SEC_RATECANVAS，`RC/ogc_layout.py`）。

## 1. 每一級

### 1.1 接收端（0x3010）
- 能裁：x 窗（12 px 單位，任意位置）、y 窗（要和感光元件一致，否則不出幀）[M]（imx410-lab IMX410_RULES §33 §15）。
- 不能縮放。水平裁不加速 [M]。
- **錄影路徑目前沒用它裁**：畫布視窗＝模式光柵 [C]。原廠窄寬模式用 TIM +0xA/+0xC 在接收端裁（mode 102 952..5128）[C]。→ 自訂裁切要走虛擬模式表（imx410-lab 的範圍）。

### 1.2 CRCT（0x300F）
- **錄影欄位的 bin（+0x5C/+0xC8）**：原廠 306/306 全 ×1 [C]。
  - 分支 B（bin×3 + RWZM unity）上機否定：只有幾何宣告縮小、拿到左上角裁切（A001_167，相關 +0.987 對裁切）[M]（OGN/IMX410_FULL_DESIGN §6.1）。
  - 分支 C（bin + 非 unity RWZM）理論上會開 Hbin2：**I0／I 對照組從沒上機** [C]。res-lab 的 M98 hbin3 992×360 只驗了檔頭，沒驗像素真的被平均 → **CRCT 錄影 bin 有沒有作用仍未證明**。
- **預覽欄位的 bin（+0x58/+0xC4）**：原廠 UHD 預覽用 ×3（分支 E，17 列）[C]。⚠ imx410-lab 說「306 個 profile CRCT 合併全關」只對錄影欄位成立；預覽路徑屬 isp-lab，CRCT 預覽 bin 是現役功能。
- 合法列舉：hbin 0/1/2 → ×1/×3/×5、vbin 0/1 → ×1/×3；**非法值會讓相機當場鎖死（要拔電池）** [C]（FUN_c022ee10/ee90）。×5 的五抽頭係數沒找到 [C]，先不當選項。
- 核：Hbin2 三抽頭 `[1 2 1]/4` 或 `[1 14 1]/16`（soft/std）；係數暫存器 0x300F0800/0840/08C0 [C]。res-custom SEC_BINFILT 可選 6 種核 [C]，上機效果未驗。

### 1.3 RWZM
- Z 為 ×1024 整數，1023 夾成 1024；兩軸獨立 [C]；非等向錄過（M12 2048/1023）[M]。
- 範圍 1024..16384、只縮不放：**規劃器政策**，硬體極限未量。
- **畫質已量過**（OGN/REDUCTION_KERNEL_MEASURED.md §0、§7）[M]：
  - RWZM 不做前濾波，每相位只是 2 抽頭級內插；抗疊紋完全來自感光元件那一級。
  - 相位表 16 格，`floor(16×frac(nR))`；用幾格取決於比例的分母：25/16 全開、3/2 兩格、整數一格。
  - 碰到 RWZM 的路線誤差 2.2–7.3%（和比例、尺寸無關），不碰的 0.7%／2.7%；FHD（÷1.5 經 RWZM）有 16 列週期橫紋。
  - → 這就是 Pareto 代價向量裡「條帶／疊紋」兩項的現成量法，isp-lab 沿用它的方法。
- 預覽 RWZM 原廠只用過 1024/1280/1536/1600/2048/3072 [C]。

### 1.4 寫入層／CDNG
- rec／act／16-10 邊／寬 16 的倍數：ISP_SIZE_RULES §1（imx410-lab notes）。
- 位深：原廠 8/10/12 平面碼 `PLANE={8:(10,10),10:(10,9),12:(7,7)}` 寫 +0x80/+0x84 [C]；14-bit 是 16 bpp 容器，consumer 尚未接 [C]。
- >99 fps：canvas +0x30（通道格率）> 99 → 管線改輪詢、時脈閘門 5/16 [C]（IHW/HIGH_FRAME_RATE_PATH.md）；全開閘門有效 [M]。
- 94 格 RAW 池、64 MiB 結算（memory lossless-early-stop-94）。

### 1.5 預覽分支（LCD）
- 規則：來源寬 ≤2100、可見寬 ≤2000 且 16 的倍數、光柵＝可見+16/10 不能超出來源（超出會花屏凍結）[C]+[M]。
- 無合併時兩軸要等向，否則開錄第一秒接縫 [M]（只在 M12）。
- 240/280：預覽走錄影路徑 [C]+[M]；大幅面未驗。
- **待機預覽是另外 6 個固定 profile**（視窗 2016×1344，3×3 全片幅讀出），可見寬高由錄影 FOV 換算 [C]（imx410_profile.standby_visible）。→ 待機畫面不是錄影管線的縮圖，**待機檢查要另外驗 FOV 對齊**。
- 顯示 ring 可依 descriptor 寬線性解成 YUYV [M]（IHW/IMAGE_CHANNELS.md 頁首）。

## 2. 安裝路徑與自動化相關（res-custom consumer）

- **Virtual RCD 的 APPLY 不用重開機**：producer 回傳 RCD blob → consumer 驗證 → 停 LV → 換表 → 原生 setter → 重啟 LV [C]（`RC/ogc_virtual.c`）。
  → isp-lab 可以註冊成 producer，每組配方幾秒內切換，自動化的關鍵。
- 限制：只能在 **UI thread** 呼叫；錄影中、XMP/MOV 活動中拒絕；每次開機最多 32 份圖示 pack／4 MiB（同 pack 去重）；最多 16 個虛擬 mode。
  isp-lab 的 producer 可以固定用同一份 pack，避免吃光名額。
- **主機怎麼進 UI thread（第 11 題，第一輪結論）**：三條候選
  1. **★ GUI 佇列 + 私有變數回呼**（建議）：isp-lab 的 sup 用 `C0560FB0(GUI_OBJECT, name, fn)` 訂閱自己的私有 app 變數，
     回呼「跑在 UI thread、新值在 descriptor+8、回 0」[C]（`open-gate/build/sl_menu/sl_modes.c:117-124`，引 C057A448/C057A6F8）；
     主機用 callfn 呼叫 `C0593F30(0, name, value)` 把整數更新丟進 GUI 佇列——668 個原廠呼叫者、任何任務都可呼叫 [C]
     （`research/firmware/notes/DISPLAY_MODE_SWITCH.md` §2b）。回呼裡做 vrc_apply。
     證據：res-lab 面板（sl_modes.c 的 subscribe/post）與 res-custom 管理頁（ogc_files.c rc_int）在相機上用過 [M]，
     但那些 post 都是從 UI 自己發的；**從 shell task 發 post 沒有實測**。要先上機確認：回呼的任務 id 是 UI task、不卡死 shell。
     注意：私有變數要先在 app 變數表登記（fp-native-ui skill）；觀察者另有 10 格上限的那套是別的機制（XC_Observer），不要混。
  2. 按鍵注入（imx410-lab 用 `key OKON/OKOFF` 進出放大，已實測）[M]：只適合「按一下就到」的動作；Apply 要走選單會很脆弱。
     且 imx410-lab 每 50–90 組在「退出放大」收尾時整機凍結一次，原因調查中（sigmafp-re-40，10-23）——等結果再判斷這條。
  3. 在 UI thread 週期性會跑的路徑掛 hook 查信箱：要多一個 claim，沒必要。

## 3. 矛盾與待解（第一批題目）

1. **CRCT 錄影 bin 在分支 C 是否真的平均像素**：I0／I 對照組（OGN §6.2）。這決定它算不算一條縮放路徑。
2. RWZM 硬體極限（<1024 放大、>16384）與 16 相位表以外的行為。
3. 寬度粒度：寫入器算 8、BUFA0 實測 16（ISP_SIZE_RULES §5-1）。
4. 留邊 16/10 是否必要（原廠 28 列沒留）。
5. 奇數起始列的 Bayer 相位。
6. 大幅面配 240/280 時預覽走錄影路徑會不會超出 2100/2000。
7. 待機 6 個 profile 與錄影 FOV 的對齊（待機檢查點）。
8. AF 統計格網（R28）與偵測影像在自訂幾何下是否跟著對（對焦檢查點）。
9. 放大（MF）時換讀出：自訂模式下放大的目標模式與放大區域（memory zoom-is-a-sensor-mode-change；imx410-lab 自己就是借 host 10 放大進虛擬模式，兩者會互相干擾，要確認）。
10. 回放：13 個回放欄位的意義、非標準尺寸 DNG 的縮圖與播放。
11. APPLY 進 UI thread 的方法（自動化前提）→ §2 候選 1，待上機確認「從 shell task post 是否在 UI thread 回呼」。
12. imx410-lab vmode 會覆寫 consumer 的描述元（它從 ROM 複製、還原回 ROM）；目前有 check_stock() 擋著會報錯。共用卡前要改成「從現值複製、還原原值、避開 consumer 的 mode id」（sigmafp-re-40 同意到時一起改）。

## 4. 通知 imx410-lab
- 第 1.2 節的訂正（預覽 bin 是現役功能）要告訴 sigmafp-re-40：邊界本身不變，但「CRCT 不算任何一邊」只對錄影欄位成立。
