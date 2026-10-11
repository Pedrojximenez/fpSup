# fp LCD 色彩截斷：舊實驗證據回查（2026-09-24）

本輪僅讀本機資料、離線計算；沒有操作相機、執行 AutoRun、寫卡或修改舊研究。

## 主要結論

1. 找回了 2026-08-16 的原始 tone 修改腳本。**當時留存的「stretched ID83」不是線性輸出曲線 `y=x`**，而是把原廠 ID83 的有效輸入區間 `0..1918`，等比例拉到 `0..2047`；原廠的非線性肩部、逐通道/亮度處理語意等仍未由這個修改解決。
2. 找回了數個「超過 LUT 輸入門檻就變黑」的診斷版本；它們能測 LUT 控制的輸入區段，不等於判斷 sensor RAW 是否飽和，更不是完整色彩校正。
3. 歷史使用者確有「成功修改記憶體，做出過曝提醒的 LCD 曲線」的回報。但此資料夾中沒有對應 LCD 前後影像、RAW 同步影格、曲線寫後 dump，因此無法從保留的資料定量證明 linear/stretched tone 解決了多少色彩截斷。
4. 舊 `NoClipTone_Test_README.md` 聲稱 family 5 全程遞增到 100%，這個說法過強。ROM 數字顯示其末尾仍長時間保持 8190，只有最末點 8191；不能把「最末點才首次到最大」當作「全域保有階調」。

## 如何找回舊實驗

現存專案的 `research/imaging-hw/notes/COLOR_SCIENCE.md` 與 `fpSup/projects/color-sup.md` 沒有這輪 on-camera 實驗。`notes-history-before-restructure.bundle`（HEAD `fea962a019434920db6b31fbdfce4946d123726b`）也只有同一份早期 COLOR_SCIENCE。

針對這個 SIGMA 專案的歷史 Claude transcript 找到：

- `/Users/dido/.claude/projects/-Users-dido-Developer-localized-SIGMAfp-re/b45e5417-78a4-428d-8cb3-c8666534f908.jsonl:9273`，2026-08-16 22:56:53 UTC，使用者回報：「autorun其實很強，我在另一個專案成功修改記憶體，做出過曝提醒的lcd曲線」。這是使用者的實機觀察，範圍是「修改有效」，不是色準/截斷量化。
- 同檔 `:9281`，使用者給出 `/Users/dido/Documents/Codex/2026-08-16/4/outputs`。
- 該資料夾與上層 `work/` 目前仍在，以下均由原始檔讀出。

## A. 原廠 family 5 指標替換

來源：

- `/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_NoClipTone_Test.txt:4`
- `/Users/dido/Documents/Codex/2026-08-16/4/outputs/NoClipTone_Test_README.md:3`

脚本保存 `0xC31D7540..+0xA0`，再把兩個 slot `0xC31D7580`、`0xC31D75C8` 改為 `0x00268BCD`，對應 `0xC09A2F34`（ID50）。這是換到既有曲線，不是把曲線改成線性。舊 README 的「2048 個點一路遞增至 100%」不能成立：本輪直接讀 ROM，ID50 在 index 1919..2046 都是 8190、2047 才 8191；有長平台。

README `:25-27` 本身也說指標可能已 latch 或被 PictureQuality 覆寫，畫面沒變不能單憑此推論曲線效果。沒有在這個資料夾找到 `TONEPTR_BEFORE.bin`、`TONEPTR_AFTER.bin`。

## B. Stretched ID83：實際數學與寫入位置

來源 `/Users/dido/Documents/Codex/2026-08-16/4/work/generate_stretched_curve_autorun.py`：

- `:8-16`：來源曲線 ID83，即 ROM `0xC09C3F34`；`last_useful=1918`，取原曲線第一次到最大值的位置。
- `:18-25`：對每個新輸入 `x=0..2047`，算 `position=x*1918/2047`；對原 ID83 的相鄰點做線性內插、round 成 uint16。
- `:30-33`：新表放 `0xC3414DA8`，CH0 slot `0xC31D7580`，encoded pointer `0x00D0536A`。
- `:43-50`：用 1024 次 32-bit `mem set` 寫 4096-byte 表，再改 CH0 slot、保存前後資料。

對應輸出 `/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_Stretched_ID83_Test.txt:1`，目前仍在。

這個修正只拓展原曲線的輸入範圍。若已證實 LUT 前訊號、增益/正規化與 active curve 都不變，最大可回收量約為 `log2(2047/1918) ≈ 0.094 stop` 的 LUT 輸入；**不能把此數字當成 RAW-to-LCD 動態範圍差**。它保留了原廠曲線的非線性形狀，無法由程式本身推出色彩截斷已修好。

## C. Clip-to-black 診斷演進

各腳本前四行記錄設計，全部仍在 `/Users/dido/Documents/Codex/2026-08-16/4/outputs/`：

| 檔案 | 變黑規則 |
|---|---|
| `AutoRun_ClipToBlack_ID83_Test.txt` | 98..99% 淡出，99..100% 黑 |
| `AutoRun_ClipToBlack_ID83_V2_90pct.txt` | 88..90% 淡出，90..100% 黑 |
| `AutoRun_ClipToBlack_ID83_V3_80pct.txt` | 78..80% 淡出，80..100% 黑 |
| `AutoRun_ClipToBlack_ID83_V4_85pct_Hard.txt` | ≥85% 硬切黑 |
| `AutoRun_ID83_1pctWhite_99pctBlack_Hard.txt` | ≤1% 白，≥99% 黑 |
| `AutoRun_ID83_OnlyCode2047Black.txt` | 只有輸入 code 2047 黑 |

最後版本的生成器 `/Users/dido/Documents/Codex/2026-08-16/4/work/generate_clip_to_black_autorun.py:13-33` 仍先套 stretched ID83，只將 `x==2047` 的輸出改 0；`:35-38` 與上述 CH0 地址相同。

這能形成高光標記，但黑色是「這張 LUT 收到某輸入值」，不能據此認定 RAW 通道過曝，且非單調映射本身會改變色彩。若要用作鑑別，應保留真實 RAW 與 before/after display samples 同步比較。

## D. 尚在的 RAM dumps：無法當作 active tone 變動證據

`outputs/OFF/` 與 `outputs/T&O/` 各有：

- `TONE_CH0.bin`、`TONE_CH1.bin`：20 bytes；四個檔案全部為 0，SHA256 均 `de47c9b27eb8d300dbb5f2c353e632c393262cf06340c4fa7f1b40c4cbd36f90`。
- `PQP844.bin`：2116 bytes；OFF 與 T&O 完全相同，SHA256 均 `6bd7d08b94f7a44043d5c40f3d21c52ed198f6220d0121dd3da1967917cdfd86`。

來源腳本 `/Users/dido/Documents/Codex/2026-08-16/4/outputs/AutoRun_PQPrePstDump.txt`；說明 `/Users/dido/Documents/Codex/2026-08-16/4/outputs/PQPrePstDump_README.md:19-26`：當時取 `0xC3824258` 物件、CH0 `+0x140` / CH1 stride `0x41C` 的 20 bytes，送 `FUN_c01012b8`。原 README 已明說是定位測試，尚不能斷言是 93% 截斷來源。

對應存留資料夾 `captures/` 主要是後續 USB transport 實驗。未找到 tone/curve 的寫後記憶體、同步 RAW、LCD before/after 截圖。這是**目前回收 artifact 的限制**，不否定使用者當時看到的變化。

## E. 色彩重現項目與這次 LCD 問題的界線

`/Users/dido/Developer.localized/SIGMAfp_re/fpSup/projects/color-sup.md:14-44` 的目標是讓 CinemaDNG 後製重現 JPEG Standard。`/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/dctl/SIGMA_fp_Standard_InPipeline.dctl:1-3` 直接寫明對實際 sRGB output transform 做擬合；`:17-19` 明確把各通道 tone 的輸入 clamp 到 `[0,1]`。這不是消除 LCD 截斷的實作，也不能當作其前後測試。

保有四組 `_SDI0010..0013.DNG/JPG`（6000×4000 JPEG，2026-08-15 03:40:40..55，ISO800、1/125s、f/1.4）與 TIFF exports，均在 `/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/color-characterisation/`。它們可重新分析 RAW/JPEG 色彩差，卻没有一一對應這次 tone 修改的 LCD frame。

`/Users/dido/Developer.localized/SIGMAfp_re/projects/usb-shell-sup/fpshell_tool/monitor/rawview.py:73-74` 的 `linear` 是 host-side WB 後套 `stretch(..., gamma=2.2)`；`:56-59` 使用全圖 1..99.5 percentile，會主動 clip；`:30-32` CCM 仍是 identity fallback，`:78` 直接去負值。它不是已校準的 LCD 線性 tone，也不能作本題真值。

## F. 本輪 ROM 數字複核

`rom-tone-88-summary.json` 讀 `/Users/dido/Developer.localized/SIGMAfp_re/out/seg0_c0000000.bin` 的 `0x971F34` 起 88×2048 uint16 little-endian；無任何 camera I/O。這個 JSON 的 `plateau_first_index` 定義是「最後終值的持續平台起點」，所以 ID45..55 的末點 8191 會讓值等於2047，**這不代表前面没有平台**。

曲線1：index 1918=8189，1919..2047=8190。所有曲線 monotonic nondecreasing，但不是 strictly increasing。原 `COLOR_SCIENCE.md` 的硬體 block 地址另有本輪獨立反編譯更正，故本報告不沿用舊圖當作 active LCD pipeline 證據。

## 後續應以這些差異做實驗

先確認真正 active LUT / ISP path 和在 LUT 前的 gain/CCM/clamp；再比較原廠、stretched、真正單調 smooth shoulder，並保存相同場景相同曝光的 RAW/LCD/HDMI。把「RAW 有訊號，但 display 色彩或亮度平台」與「RAW 本身飽和」分開。色彩矩陣負值/越界與顯示色域映射不能由一條 1D tone 曲線完整處理。
