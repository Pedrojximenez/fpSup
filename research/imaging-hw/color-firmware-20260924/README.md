# SIGMA fp／Sony A7 III 色彩韌體分析：第一輪結果

2026-09-24。只分析既有韌體、反編譯結果及既有 DNG；未操作相機、刷寫韌體或改動原始影像。Sony 使用之前解析的 ILCE-7M3 4.04 `av-cam.bin`，不是 Sony 公開的原始碼。本輪不生成新的「校準矩陣」，避免把尚未確認用途的矩陣當作校準。

## 最重要的判斷

**OFF 在一個明確的 RGB 顯色矩陣階段刻意使用單位矩陣，已有程式與實際 metadata 的相互驗證。** 這比「看起來像 sRGB」「飽和度不像另一部相機」更直接，但不表示全部 RAW 路徑都沒有校準，也不證明 RAW 的物理色彩響應就是 sRGB。

「SIGMA 完全沒做色域校準」「OFF 本來應該是 BMD Gen1」「改選 sRGB 解碼就會準確」都不能由目前證據推出。韌體分析能還原設計與轉換定義；是否準確對應真實場景，是另一個驗證問題。

## fp：本輪新增的硬證據

- 既有 CinemaDNG A 和四張 still DNG 均攜帶完整 16 模式私有矩陣表。OFF 的 RGB 表為單位矩陣，Standard 則不是；相同完整表出現在不同模式檔案中，不代表模式無效。
- 找到明確的線性 RGB／XYZ 基底常數，包括 linear sRGB→XYZ D50，及 Adobe RGB→linear sRGB。
- 私有當前矩陣 tag `0x34` 一般分支為 `inverse(S × M_selected × diag(WB))`；Adobe RGB 分支另有基底轉換。ARM 指令補足了反編譯 C 遺漏的反矩陣與 float 轉換。
- 從原始 OFF cDNG 的私有白平衡及當前矩陣反算，`M_selected` 與單位矩陣最大差 **3.98×10⁻⁸**。這是該次渲染設定的證據，不是 RAW 像素已經通過此矩陣的證據。
- 非 OFF 私有資料包含模式 RGB 處理、亮度／色差處理；標準 DNG profile 的 HueSatMap／ToneCurve 是另外一條已核對的描述路徑。Resolve 對這些私有資料或全部 profile 欄位的採用情況尚未驗證。
- 私有 current matrix 存在硬體 11-bit 係數包裝語意，不能直接複製成 IDT。也不能僅憑這個現象宣稱像素顯色有 bug。

完整來源、地址、公式及限制：[fp 私有色彩資料分析](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/color-firmware-20260924/fp-private-color-findings.md)。

逐檔提取與反算：[驗證數據](/Users/dido/Developer.localized/SIGMAfp_re/research/imaging-hw/color-firmware-20260924/fp-private-matrix-audit.json)。

## A7 III：已比對到的實作，不是直接可搬用的校準

- 色域識別與 Gamma 識別分開：前者有 S-Gamut、S-Gamut3、S-Gamut3.Cine，後者有 S-Log2、S-Log3。因此參考 Sony 的色彩架構，不要求 fp 的 Bayer RAW 改為 Log。
- 已定位 Gamma 選擇程式及數值資源表，並核對實際讀取位置。這些是 tone／編碼路徑線索，不是感光元件→XYZ 的矩陣。
- 已從機器碼確認 RGB matrix setter `0x63BDF594` 與 checker `0x63BE9B1C`。九個係數按 signed short 檢查，另有一個 switch；setter 只是接收請求並保存，不是計算感光元件校準。
- 指令分派表 `0x6473A9E0` 將 command `0x40F3`、setter、checker 配對，進一步確認此路徑。**上游係數產生者及其色彩座標定義尚未追完。**
- 同名或近似的 `SET_COLOR_CORRECT` 是另一組參數，不能因名稱相似就誤認為 RGB 校準。`idt_cam.bin` 也未證明與 ACES IDT 有關。

詳細地址與資源：[Sony 分析](/Users/dido/Developer.localized/SIGMAfp_re/sony_a7m3/color-firmware-20260924/README.md)。本輪 Ghidra 只操作舊專案的本地副本，且使用不保存分析變更的模式；反編譯記錄位於 `sony_a7m3/color-firmware-20260924/logs/`,Ghidra 專案在 `sony_a7m3/ghidra/`。

## 對解決方案的影響

目前有根據的方向是：**保留線性 RAW，將相機輸入轉換與 SIGMA 顯色風格分開定義。** 不必先模仿 Blackmagic 或 Sony 的 Log，也不應只替 OFF 貼上某個品牌色域標籤。

但還不能宣稱已完成色準校準：fp 的 normal ColorMatrix、私有模式矩陣、上游處理之間，尚缺一段經證實的串接關係。現在把 normal CM 與 Standard 私有矩陣直接合成，可能重複加入顯色效果。

下一個具體離線追查點：

1. fp `FUN_c02cfcf0` 的上游 vtable／輸入資料，確認進入模式 RGB 矩陣前的基底與增益；分清 body calibration、逐拍白平衡、模式處理及 tone 順序。
2. Sony command `0x40F3` 的係數產生者；只有確認輸入基底、尺度及用途後，才有資格與 fp 的對應層比較。
3. 利用既有 RAW／JPEG、目前已產生的 CM 候選比較設計一致性。這可驗證是否重現相機處理，不能把重現 JPEG 說成客觀色準。

這輪已證明：**沒有色卡不妨礙繼續做有證據的韌體還原；但「還原廠商做法」和「證明物理色準」要分開。**
