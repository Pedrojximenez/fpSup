# OFF 模式色彩還原:2 個 byte 的韌體補丁

2026-09-26。使用者自行改韌體,把 OFF 的 DNG ColorMatrix 換成 normal 那組;本筆記是補丁點的定位、
全 ROM 副作用稽核,以及用藍色 LED 做的實拍驗證。Ver.5.02.0.V91,機身 SN 91411817。

## 結論

1. **補丁點只有兩個 `movw` 立即數,實際改動 2 個 byte。** 四個矩陣常數在全 ROM 各只被引用一次,
   全部在 `FUN_c02c4a50` 裡 —— 沒有第二個消費者,不碰 MakerNote、即時路徑或硬體 CCM。
2. **靜態 DNG 與 CinemaDNG 共用同一個 writer**,所以一個補丁同時修好照片和影片。
3. **HueSatMap / ToneCurve 的 OFF 分支不要動**,它們在另外兩個函式裡。補丁後 OFF 仍是 identity look
   —— 這正是「只修描述、不加 look」的色彩還原定義。實拍 A001_075 證實。
4. **韌體補丁與位元組補丁等價**:同一顆 LED,兩者差 ΔE76 mean 1.61(而且是兩次不同 take)。
5. **飽和色上的差是 ΔE ~10、峰值 ~20**,這是先前室內素材量不到的量級。

## 補丁點

`FUN_c02c4a50` 裡兩段對稱的判斷,唯一差別是傳給 `FUN_c02c9860`(3×3 乘法,`inv(CameraCalibration) × ROM`)
的常數指標:

```asm
c02c4bd8  cmp   r0, #0x24          ; r0 = 目前 Color Mode(0x24 = OFF)
c02c4be0  bne   #0xc02c4c00
c02c4be4  movw  r2, #0xfd74        ; OFF CM1     ← 補丁點 1
c02c4be8  movt  r2, #0xc096
c02c4bec  bl    #0xc02c9860
...
c02c4c00  movw  r2, #0xfd2c        ; normal CM1
...
c02c4c8c  cmp   r0, #0x24
c02c4c94  bne   #0xc02c4cb0
c02c4c98  movw  r2, #0xfce4        ; OFF CM2     ← 補丁點 2
...
c02c4cb0  movw  r2, #0xfc9c        ; normal CM2
```

兩條路之後匯流到同一個量化迴圈(SRATIONAL 分母 `DAT_c096fdc0`/`c8` = 10000,兩邊相同),
所以矩陣以外沒有別的差異。

### 最小改法

`0xFD2C`/`0xFD74` 的 imm4 同為 `0xF`,`0xFC9C`/`0xFCE4` 亦然 —— 只有 imm12 的低位元組不同:

| 補丁點 | VA | 檔案位移 | byte | 指令 |
|---|---|---|---|---|
| CM1 | `0xC02C4BE4` | `0x2C4BE4` | `74` → `2C` | `movw r2,#0xfd74` → `#0xfd2c` |
| CM2 | `0xC02C4C98` | `0x2C4C98` | `E4` → `9C` | `movw r2,#0xfce4` → `#0xfc9c` |

原始位元組:`74 2d 0f e3` / `e4 2c 0f e3`。`cmp #0x24` 與 `bne` 保留不動,兩條路現在拿一樣的常數
——無害的冗餘,但保住原結構,回退也只是改回那 2 個 byte。

**替代改法**:把 `c02c4be0` / `c02c4c94` 的 `bne` 改成 `b`(各 4 bytes)。效果相同但留下死碼。

## 副作用稽核

`audit_matrix_refs.py`。位址是 `movw`+`movt` 組出來的,不在文字池,所以要配對掃描:

```
normal CM1 0xC096FD2C → 1 處  c02c4c00
OFF    CM1 0xC096FD74 → 1 處  c02c4be4
normal CM2 0xC096FC9C → 1 處  c02c4cb0
OFF    CM2 0xC096FCE4 → 1 處  c02c4c98
```

同一支腳本對**已補丁**的映像跑,會把那兩個點報成「已補丁(指向 normal)」,可當回歸檢查。

補丁改的是常數指標,`FUN_c02c9860` 仍會乘上該機身的 `CameraCalibration`,所以**不需要 per-body 客製**;
A001_075 的 CM2 與同機身 Standard 檔逐位元組相同,已驗證。

## 實拍驗證:藍色 LED

`/Users/dido/Movies/fpSup/off_test/`,兩段 FHD 12-bit 23.976p,相隔 31 秒,ISO 800 / 1/25 / f8 /
LUMIX S 40 / MF / Auto WB / ASN `0.4981 1 0.5818`:

| | 韌體 | PictureMode | ColorMatrix | HueSatMap / ToneCurve |
|---|---|---|---|---|
| A001_074(314 幀) | 未補丁 | OFF | **OFF 矩陣** | identity / 線性 |
| A001_075(440 幀) | 已補丁 | OFF | **normal 矩陣** | identity / 線性 |

整份 metadata 逐項比對,除了時間戳、TimeCode、RawDataUniqueID、BlackLevel(每次錄影本來就微幅不同)
之外,**唯一差異就是 ColorMatrix1/2**;兩段各抽 13 幀,整段內部一致。

RAW max 3854 / 4095、渲染後 max 0.907 → **沒有截幅**,是乾淨的窄頻飽和光源。

### 三個受測檔

| | 來源 | 說明 |
|---|---|---|
| L1 | A001_074 第 151 幀原樣 | 未補丁,OFF 矩陣 |
| L2 | 同一幀,CM1/CM2 換成 normal | 只改 46 bytes,RAW SHA-256 不變 |
| L3 | A001_075 第 151 幀原樣 | 已補丁韌體,相機自己寫的 |

在使用者專案副本設定下渲染(RCM v2、DWG/DI 時間軸、Rec.709 輸出),取 L1 最大通道 > 0.3 的
204 個像素(31×21 px 燈芯):

| | R | G | B | 飽和度 |
|---|---|---|---|---|
| L1 OFF 原樣 | 0.3612 | 0.4865 | 0.6302 | 0.509 |
| L2 位元組補丁 | 0.4153 | 0.4679 | 0.6614 | 0.436 |
| L3 韌體補丁 | 0.4105 | 0.4688 | 0.6599 | 0.445 |

| 比較 | LED 區 ΔE76 mean / p99 / max |
|---|---|
| L1 → L2(矩陣的效果) | **9.69** / 18.20 / 19.89 |
| L1 → L3(同上,韌體版) | 9.32 / 16.18 / 19.14 |
| **L2 → L3(兩種補丁法比較)** | **1.61** / 5.37 / 6.39 |

L2 與 L3 是相隔 31 秒的兩次錄影,1.61 就是 take 底線 → **兩種補丁法等價**。

### 一個跟直覺相反的方向

修正後**不是變飽和,而是往洋紅/紫移、飽和下降**(0.509 → 0.436,R 升 G 降)。

這跟用合成色塊算出來的「寬頻飽和藍 ΔE 36.5、變更飽和」方向相反。原因是這顆 LED 是窄頻(~450–470 nm),
感光元件藍通道在該波長過度敏感,正確矩陣把它往紫的方向拉回並降飽和。
**矩陣的效果不能一概而論成「變飽和」,要看顏色在空間裡的方向。**

## 界線

- 絕對色準仍未驗證 —— 沒有色卡、沒有已知光源、沒有光譜量測。本輪只證明「補丁後 = 原廠 normal 矩陣的結果」,
  不證明那個結果色準正確。
- 補丁位址是 Ver.5.02.0.V91 的;其他韌體版本要重跑 `audit_matrix_refs.py` 定位。
- 只比了每段一張(第 151 幀)。
- **補丁後拍的素材會跟補丁前的長得不一樣**(飽和色 ΔE ~10)。既有專案若已就舊的淡版調過色,會對不起來。
- 沒有測 Adobe Camera Raw / Lightroom 等其他解碼器。

## 檔案

- `audit_matrix_refs.py` — 掃描韌體映像列出四個常數的引用點,兼作補丁驗證器
- `led_ab.py` — 建 L1/L2/L3 三個 DNG(驗 RAW SHA-256)+ 回讀 TIFF 分析 → `led_results.json`
- `led_results.json`

素材(不在 repo 內):

- `/Users/dido/Movies/fpSup/off_test/A001_074`(未補丁)、`A001_075`(已補丁)
- `/Users/dido/Movies/fpSup/off_test/ab/` — L1/L2/L3 + `renders_user/` 三張 16-bit TIFF + `preview_L1_L2_L3.png`

## 相關

- [`profile-tags-ab-20260925/`](../profile-tags-ab-20260925/README.md) — Resolve 吃哪幾個 profile tag、
  為什麼只換矩陣就夠(look tag 保持 identity)
- [`native-calibration-20260924/`](../native-calibration-20260924/README.md) — normal 矩陣的 writer 來源鏈
- [`colormatrix-ab-20260923/`](../colormatrix-ab-20260923/README.md) — OFF 矩陣 = `diag(g)·inv(sRGB)` 的推導
