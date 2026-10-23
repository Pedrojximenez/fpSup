# res-lab 稽核：哪些能當前提、哪些不能（2026-10-23，第一輪，離線閱讀）

使用者判斷 res-lab 裡有大量錯誤。這份是 isp-lab 開工前的過濾：每條標成
**可用**（有上機證據且範圍清楚）／**存疑**（只在單一模式或單次觀察成立，或只有自己對自己的一致性）／**錯或不適用**。
讀過的：`res-lab/README.md`、`RESCUSTOM_STATUS.md`、validation 的 formula-audit、recording-formula、high-fps、
calculator-v3、unified-hirate、carrier-ab、clk0-full、raw14、no-padding、parity-audit（開頭）、hirate-preview-research（開頭），
以及 producer `open-gate/build/rl_v3.c`。**還沒讀**：`sl_menu/sl_modes.c`（2026 行）、consumer `res-custom/ogc*.c`、其餘 35 個 validation。

## A. 方法層的問題（影響所有結論）

| # | 問題 | 例子 |
|---|---|---|
| A1 | **「N 萬組案例通過」多半是自己對自己的一致性。** producer 的公式拿來驗 producer 的輸出，公式本身錯了一樣全過（memory re-verification-discipline：self-consistent wrong values） | formula-audit 142,800 組、1,750 組 ARM、62 模式 Apply：都是幾何不越界／重算不變，不是「錄出來的畫面對」 |
| A2 | **上機證據很薄**：多半只看首幀檔頭、抽 3–9 幀能解碼；FOV、畫質、逐幀內容幾乎沒驗 | formula-audit 自己寫「尚未逐幀解碼整段、驗收畫質」；recording-formula 只有 M12 一個模式 |
| A3 | **SSD 結論靠使用者手動錄，條件常常混淆**（shell、HDMI 開著與否），出現多次撤回 | carrier-ab 整段撤回；A001_319–322 shell+HDMI 開著 |
| A4 | **從單一模式推廣到全部**：預覽規則是在 M12（加 M98 一段）上試錯得來的，寫成通用規則 | r77→r78→v11→v12 都只修 M12 AUTO |
| A5 | **只驗了「配置路徑」**：原廠 ROM 選擇器在模擬器裡跑出正確 mux，不等於 LCD 真的讀對緩衝（recording-formula 自己撤回過一次） | v11 的 C 路徑推論 |

## B. 對 isp-lab 有用、可以當起點的（仍要在 isp-lab 重驗）

| 結論 | 證據 | 範圍限制 |
|---|---|---|
| rec = (window/bin)·1024/Z，&~15／&~1；act 置中、留 16/10 邊 | 與原廠 78 個影片 profile 逐欄吻合 [C] | 原廠 profile 的歸納，不是硬體極限；留邊是否必要未知 |
| 非等向 RWZM（2048/1023）錄得出正常 DNG | M12 實錄 [M] | 只有 M12 |
| 無合併時預覽兩軸要等向，否則開錄第一秒 LCD 接縫 | r77、v11 兩次重現，v12 使用者確認修好 [M] | 只有 M12／29.97p |
| 240/280 預覽走錄影路徑（預覽縮放＝錄影、光柵＝act+16/10） | 原廠 p379/p389 + 兩次成功 240 [C]+[M] | 沒檢查 rec 寬超過預覽來源 2100／可見 2000 的情況 |
| 9 個 >99 fps 閘門家族看 canvas +0x30；C0189440 時脈閘門全開改善 12-bit 240p 2.5× | clk0-full [M]；HIGH_FPS_PATH [碼] | 是錄影持續性問題，不是 ISP 幾何 |
| 虛擬 mode 230／p74 與原生 M12／p13 逐字對等，mode／pid 層沒有其他差異來源 | parity-audit [F]、parity-live [M] | 只比了 M12 |
| shell、HDMI 開著時 MovRec 請求速率掉到約 188 fps | unified-hirate [M] | 高格率測試條件 |

## C. 錯或不適用於 RES-Custom2

| # | res-lab 的做法 | 問題 |
|---|---|---|
| C1 | **「Crop」只是 DefaultCrop**：rec 仍寫整個視窗（rl_canvas_safe 以全 `w` 算 c[0]），完全沒有感光元件裁切 | 不省讀出、不加速、資料照寫。和使用者定的「sensor 先切高」相反；不能沿用 |
| C2 | **最高格率 = 72 MHz ÷ (HMAX × (META 列數 + META+0x5C))**（rl_encode） | 用原廠 META 欄位估，不是實際 TIM VMAX；imx410-lab 已實測 `VMAX_min = 接收列數 + 2·0016 + 12`、各類別 over 不同（GENERATOR §3）。自訂感光元件模式不能用這條 |
| C3 | **格率只能從原廠 donor 模式繼承**（rl_encode 只接受 META 表裡的 mode，`cnt ≤ 70`） | RES-Custom2 的感光元件設定來自 imx410-lab 生成器，不是 donor 原樣 |
| C4 | **位深宣告寫死 `bd=7`（8/10/12 都支援、任何媒體）** | 每個配方都宣告全支援，沒有逐配方證據 |
| C5 | CRCT bin 只收 1／3（rl_canvas_safe），筆記又說 H 可 1/3/5 | 文件與程式不一致；5 有沒有用過、畫質如何都沒資料 |
| C6 | RWZM 1024..16384、只能縮小 | 是規劃器政策，自己也承認「不是實測硬體極限」 |
| C7 | 錄影計時除以原生格率、240 選擇不跨重開、DNG FrameRate 曾標成 120000/1001 | 已知未修或修法未在所有路徑驗證；isp-lab 檢查 DNG 時要逐項看 |
| C8 | 「12-bit 每秒建立 245 個檔 → 時鐘掉 tick」 | 標 [推，未上機證實]，exFAT 1 s 解析度的推論，不採用 |

## D. 下一輪要讀的

1. `sl_menu/sl_modes.c` 的 `zoom()`、`snap()`、`rate_format`：Z 與裁切、格率表的原始規則。
2. consumer `ogc_virtual.c`：虛擬 profile 實際寫了哪些欄位、哪些沿用 donor（決定 isp-lab 能不能直接用 consumer 安裝）。
3. 預覽路由的 A–F 分支（`IMX410_FULL_DESIGN.md §6.2`）：哪些分支有實機證據、哪些只有選擇器模擬。
