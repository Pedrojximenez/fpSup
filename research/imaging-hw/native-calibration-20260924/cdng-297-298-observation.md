# 真實 CinemaDNG：A001_297 OFF 與 A001_298 Standard

日期：2026-09-24。唯讀檢查來源媒體；沒有修改 DNG、相機或 Resolve 專案。

## 結論

**在這次實際錄影條件下，Standard CinemaDNG 確實直接寫入原廠 normal ColorMatrix1/2。**
不再只是由靜態 DNG 或共同 writer 推測錄影會採用這組矩陣。

- A001_297：98 幀，000001–000098；PictureMode = OFF。
- A001_298：122 幀，000001–000122；PictureMode = Standard。
- 兩段各自的 CM1/2、校準光源、HueSatMap、ToneCurve、AsShotNeutral 全序列不變。
- 298 的兩個 CM payload 與既有 `C_firmware_normal.DNG` **逐 byte 相同**。
- 297 的兩個 CM payload 與既有 `A_original.DNG` **逐 byte 相同**。
- 以各檔的機身 CameraCalibration 和原廠 ROM 依 `inverse(D_body) @ CM_ROM`、乘 10000 後向零截斷，精確重建兩段代表幀的相應 CM payload。

來源目錄：

- `/Users/dido/Movies/fpSup/color area/A001_297`
- `/Users/dido/Movies/fpSup/color area/A001_298`

## 實際拍攝條件與範圍

兩段代表幀共同資訊：

- Software：`SIGMA fp Ver.5.02.0.V91`。
- 機身序號：91411817；機身校準矩陣相同。
- ISO 800、1/60 秒、f/2、40 mm，LUMIX S 40/F2。
- 拍攝白平衡 AsShotNeutral 相同：`0.5130260521, 1, 0.583143508`。
- 12-bit、未壓縮 CFA；儲存 1936×1090、裁切 1920×1080、29.970 fps。
- CalibrationIlluminant1/2 = 17/21（A／D65）；BaselineExposure = 3，WhiteLevel = 4095。

結論限於這次實測的檔案及錄影條件，不擴張為所有位深、解析度、韌體或 HDMI RAW 路徑均已驗證。

## Standard 不只是替換 ColorMatrix

| 標準 DNG profile 項目 | 297 OFF | 298 Standard |
|---|---|---|
| ColorMatrix1/2 | OFF 組 | normal 組，等於 C 候選 |
| 每光源 HueSatMap | 72/72 控制點為 identity | 71/72 控制點非 identity |
| ProfileToneCurve | 128 點，x=y | 128 點，非 identity |

例如曲線輸入 0.302978515625：OFF 輸出同值，Standard 輸出 0.52117919921875。
這是 metadata 的顯影指示，不是已證明 RAW 像素被烘焙該曲線；本次也沒有測試 Resolve 對這些額外 profile 標籤的支援情形。

所以 Standard 原檔不應被稱為「與 C 完全相同」：只有兩個 CM payload 已確認相同。
C 保留 OFF 的 identity HSM 與 tone，Standard 則帶有完整的非 OFF 基礎 profile。

## 非色彩矩陣差異與限制

- BlackLevel 在各序列中微幅變動，297 有 45 種 payload、298 有 47 種；兩個代表幀約為 255.9922 與 256.0254。
- OpcodeList3 在 297 全段一致，298 有 10 種 payload。本次只記錄差異，未把它歸因於色彩模式，也未驗證 Resolve 是否使用。
- 拍攝時間、時間碼、私有 metadata 等亦不同；不是只改 metadata 的同一份 RAW。
- 沒有進行這兩段的 RAW 像素等同性或完整上游 ISP 路徑驗證。
- 各目錄的 `SPP_metadata.xmp` 只有 TopFile／TotalSize；本結論來自 DNG 本體，非 sidecar 指令。
- 尚未在 Resolve 對這兩段進行渲染比較，也沒有證明絕對色準。

## 工作流程意義

**「Standard 拍 cDNG，直接取得 normal 矩陣，省去事後替換 CM」這個實作前提，現在已確認成立。**

Rec.709／Rec.709 Gamma 是解碼輸出選擇，不是修復來源矩陣的機制；也不代表原始 RAW 已被改寫為 709 Gamma。
既有 P3 D60／Linear → DWG → Rec.709 流程仍可以保留。
應先使用 normal profile 建立基準，勿把那個經驗性的 BMD Gen1 補償直接再疊加上去。

這完成了真正非 OFF CinemaDNG 的 profile 選擇確認；不等於完成所有 Resolve profile 行為或色度量測驗收。

## 可重現資料

- [逐項數值與 payload 雜湊](./cdng-297-298-audit.json)
- [唯讀檢查程式](./audit_cdng_297_298.py)

程式只會更新這個研究目錄的衍生 JSON，不會寫入來源目錄。
